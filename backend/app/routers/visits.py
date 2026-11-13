"""POST /api/visits — record a visit from structured fields (+ optional transcript).
POST /api/visits/batch — record multiple visits atomically across beneficiaries/households.
"""
import json
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import (
    AshaWorker,
    Beneficiary,
    DangerAlert,
    ExtractedField,
    FollowUp,
    Household,
    HouseholdMember,
    HouseholdVisit,
    ImmunisationRecord,
    NewbornRecord,
    PregnancyRecord,
    VoiceTranscript,
    VisitRecord,
)
from app.routers.dashboard import broadcast_dashboard_event
from app.rules import (
    REFERRAL_MESSAGE,
    detect_danger_signs,
    next_anc_due,
    next_newborn_due,
    next_vaccine_due,
    weeks_pregnant_on,
)
from app.schemas import BatchVisitCreate, BatchVisitResponse, VisitCreate, VisitCreateResponse

router = APIRouter(prefix="/api/visits", tags=["visits"], dependencies=[Depends(get_current_worker)])


def _generate_qr_id() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part = lambda: "".join(secrets.choice(alphabet) for _ in range(4))
    return f"ASN-{part()}-{part()}"


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()


def _alert_dict(alert: DangerAlert, beneficiary_name: str) -> dict:
    return {
        "id": alert.id,
        "beneficiary_id": alert.beneficiary_id,
        "beneficiary_name": beneficiary_name,
        "phrase": alert.triggered_phrase,
        "rule_id": alert.rule_id,
        "message": alert.message,
        "severity": alert.severity,
        "status": alert.status,
        "created_at": alert.created_at or datetime.utcnow(),
    }


def _process_single_visit(
    db: Session,
    worker: AshaWorker,
    beneficiary_id: Optional[int],
    beneficiary_name: Optional[str],
    structured: dict[str, Any],
    transcript: str,
    language: str = "en",
    visit_type: Optional[str] = None,
    create_if_missing: bool = True,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    village: Optional[str] = None,
    household_id: Optional[int] = None,
) -> tuple[VisitRecord, Beneficiary, list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Core logic to process and persist one visit record."""
    beneficiary = None
    if beneficiary_id:
        beneficiary = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()

    if beneficiary is None and beneficiary_name:
        spoken_name = beneficiary_name.strip().lower()
        all_bens = db.query(Beneficiary).all()
        beneficiary = (
            next((b for b in all_bens if b.name.strip().lower() == spoken_name), None)
            or next((b for b in all_bens if b.name.strip().lower().split()[0] == spoken_name), None)
            or next((b for b in all_bens if spoken_name in b.name.strip().lower()), None)
        )

    if beneficiary is None:
        if not create_if_missing:
            raise HTTPException(status_code=404, detail=f"Beneficiary '{beneficiary_name}' not found")
        # Automatically register a new beneficiary
        raw_cat = (structured.get("category") or visit_type or "general").strip().lower()
        if raw_cat not in {"pregnancy", "newborn", "child", "immunisation", "elderly", "nutrition", "adolescent", "community", "general"}:
            raw_cat = "general"
        beneficiary = Beneficiary(
            qr_id=_generate_qr_id(),
            name=beneficiary_name or f"Beneficiary-{secrets.token_hex(2).upper()}",
            age=age or structured.get("age", 0),
            category=raw_cat,
            gender=gender or structured.get("gender", ""),
            village=village or structured.get("village") or worker.phc or "Village",
            phone=structured.get("phone"),
        )
        db.add(beneficiary)
        db.flush()

        # Link to household member if household is provided
        if household_id:
            db.add(HouseholdMember(
                household_id=household_id,
                name=beneficiary.name,
                age=beneficiary.age,
                gender=beneficiary.gender,
                relation=structured.get("relation") or "member",
                beneficiary_id=beneficiary.id,
            ))
            db.flush()

    visit_date = _parse_date(structured.get("visit_date")) if structured.get("visit_date") else date.today()
    source = "voice" if (transcript or "").strip() else "manual"
    cat = (visit_type or "").strip().lower() or beneficiary.category
    if cat not in {"pregnancy", "newborn", "child", "immunisation", "nutrition", "community", "elderly", "general", "followup"}:
        cat = beneficiary.category

    visit = VisitRecord(
        beneficiary_id=beneficiary.id,
        worker_id=worker.id,
        visit_date=visit_date,
        category=cat,
        notes=json.dumps(structured),
        source=source,
    )
    db.add(visit)
    db.flush()

    # Save ExtractedField rows
    for key, value in structured.items():
        db.add(ExtractedField(visit_id=visit.id, field_name=key, field_value=str(value)))
    db.add(ExtractedField(visit_id=visit.id, field_name="_structured_json", field_value=json.dumps(structured)))

    # Save category-specific clinical record
    weeks_now: Optional[int] = None
    if beneficiary.category == "pregnancy" or cat == "pregnancy":
        weeks = structured.get("weeks_pregnant")
        if weeks is None and beneficiary.lmp_date:
            weeks = weeks_pregnant_on(beneficiary.lmp_date, visit_date)
        weeks_now = int(weeks) if weeks is not None else None
        db.add(PregnancyRecord(
            beneficiary_id=beneficiary.id,
            visit_id=visit.id,
            weeks_pregnant=weeks_now,
            bp_sys=structured.get("bp_sys"),
            bp_dia=structured.get("bp_dia"),
            weight_kg=structured.get("weight_kg"),
            hemoglobin=structured.get("hemoglobin"),
            fetal_heart=structured.get("fetal_heart"),
            notes=transcript or "",
        ))
    elif beneficiary.category == "newborn" or cat == "newborn":
        db.add(NewbornRecord(
            beneficiary_id=beneficiary.id,
            visit_id=visit.id,
            weight_kg=structured.get("weight_kg"),
            temperature=structured.get("temperature"),
            feeding=structured.get("feeding"),
            jaundice=structured.get("jaundice"),
            notes=transcript or "",
        ))
    elif (beneficiary.category in ("child", "immunisation") or cat in ("child", "immunisation")) and structured.get("vaccine_name"):
        vaccine = str(structured["vaccine_name"]).upper()
        dose = structured.get("dose_number") or 1
        db.add(ImmunisationRecord(
            beneficiary_id=beneficiary.id,
            visit_id=visit.id,
            vaccine_name=vaccine,
            dose_number=int(dose),
            date_given=visit_date,
            next_due_date=next_vaccine_due(vaccine, beneficiary.birth_date) if beneficiary.birth_date else None,
        ))

    # Transcript
    if (transcript or "").strip():
        db.add(VoiceTranscript(visit_id=visit.id, transcript=transcript, language=language))

    # Danger signs
    alerts_out: list[dict[str, Any]] = []
    if (transcript or "").strip():
        flags = detect_danger_signs(transcript, beneficiary.category)
        for flag in flags:
            existing = (
                db.query(DangerAlert)
                .filter(DangerAlert.beneficiary_id == beneficiary.id,
                        DangerAlert.rule_id == flag["rule_id"],
                        DangerAlert.status == "open")
                .first()
            )
            if existing:
                alert = existing
            else:
                alert = DangerAlert(
                    beneficiary_id=beneficiary.id,
                    visit_id=visit.id,
                    triggered_phrase=flag["phrase"],
                    rule_id=flag["rule_id"],
                    message=REFERRAL_MESSAGE,
                    severity=flag["severity"],
                    status="open",
                )
                db.add(alert)
                db.flush()
            alerts_out.append(_alert_dict(alert, beneficiary.name))

    # Auto-schedule follow up
    follow_up_out = None
    next_due: Optional[date] = None
    fu_type = cat
    if cat == "nutrition":
        days = structured.get("follow_up_days")
        next_due = visit_date + timedelta(days=int(days) if days else 30)
        fu_type = "nutrition"
    elif cat == "community":
        days = structured.get("follow_up_days")
        next_due = visit_date + timedelta(days=int(days)) if days else None
        fu_type = "community"
    elif cat == "pregnancy" and weeks_now is not None:
        next_due = next_anc_due(visit_date, weeks_now)
        fu_type = "anc"
    elif cat == "newborn" and beneficiary.birth_date:
        next_due = next_newborn_due(beneficiary.birth_date, visit_date)
        fu_type = "newborn"
    elif cat in ("child", "immunisation"):
        latest_vax = (
            db.query(ImmunisationRecord)
            .filter(ImmunisationRecord.beneficiary_id == beneficiary.id)
            .order_by(ImmunisationRecord.date_given.desc())
            .first()
        )
        if latest_vax and latest_vax.next_due_date:
            next_due = latest_vax.next_due_date
        fu_type = "vaccination"

    if next_due:
        existing_fu = (
            db.query(FollowUp)
            .filter(FollowUp.beneficiary_id == beneficiary.id, FollowUp.due_date == next_due,
                    FollowUp.status == "upcoming", FollowUp.type == fu_type)
            .first()
        )
        fu = existing_fu or FollowUp(beneficiary_id=beneficiary.id, visit_id=visit.id,
                                     type=fu_type, due_date=next_due, status="upcoming")
        if fu not in db:
            db.add(fu)
        db.flush()
        follow_up_out = {"id": fu.id, "type": fu.type, "due_date": fu.due_date, "status": fu.status}

    return visit, beneficiary, alerts_out, follow_up_out


@router.post("", response_model=VisitCreateResponse)
def create_visit(payload: VisitCreate, db: Session = Depends(get_db),
                 worker: AshaWorker = Depends(get_current_worker)):
    visit, beneficiary, alerts_out, follow_up_out = _process_single_visit(
        db=db,
        worker=worker,
        beneficiary_id=payload.beneficiary_id,
        beneficiary_name=None,
        structured=payload.structured or {},
        transcript=payload.transcript,
        language=payload.language,
        visit_type=payload.visit_type,
        create_if_missing=False,
    )
    db.commit()
    db.refresh(visit)

    # Broadcast event for real-time dashboard update
    broadcast_dashboard_event("new_visit", {
        "visit_id": visit.id,
        "beneficiary_id": beneficiary.id,
        "beneficiary_name": beneficiary.name,
        "category": visit.category,
        "visit_date": visit.visit_date.isoformat(),
        "source": visit.source,
    })

    return {
        "visit": {
            "id": visit.id,
            "beneficiary_id": visit.beneficiary_id,
            "visit_date": visit.visit_date,
            "category": visit.category,
            "source": visit.source,
            "structured": payload.structured or {},
        },
        "alerts": alerts_out,
        "follow_up": follow_up_out,
    }


@router.post("/batch", response_model=BatchVisitResponse)
def create_batch_visits(
    payload: BatchVisitCreate,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """Save multiple visits and household observations atomically in one transaction."""
    saved_visits = []
    saved_hh_visits = []
    all_alerts = []

    try:
        # Process individual visits
        for item in payload.visits:
            visit, ben, alerts, fu = _process_single_visit(
                db=db,
                worker=worker,
                beneficiary_id=item.beneficiary_id,
                beneficiary_name=item.beneficiary_name,
                structured=item.structured,
                transcript=item.transcript,
                language=item.language,
                visit_type=item.visit_type,
                create_if_missing=item.create_if_missing,
                age=item.age,
                gender=item.gender,
                village=item.village,
                household_id=item.household_id,
            )
            saved_visits.append({
                "id": visit.id,
                "beneficiary_id": ben.id,
                "beneficiary_name": ben.name,
                "visit_date": visit.visit_date.isoformat(),
                "category": visit.category,
                "source": visit.source,
                "structured": item.structured,
                "alerts_count": len(alerts),
                "follow_up": fu,
            })
            all_alerts.extend(alerts)

        # Process household visits if provided
        for hh_item in payload.household_visits:
            hh_id = hh_item.get("household_id")
            hh = None
            if hh_id:
                hh = db.query(Household).filter(
                    (Household.id == hh_id) | (Household.qr_id == str(hh_id))
                ).first()
            if hh is None:
                # Find by village or create demo household
                hh = db.query(Household).first()

            if hh:
                obs = hh_item.get("household_observations") or {}
                v_date = _parse_date(obs.get("visit_date")) if obs.get("visit_date") else date.today()
                hh_visit = HouseholdVisit(
                    household_id=hh.id,
                    worker_id=worker.id,
                    visit_date=v_date,
                    notes=json.dumps(obs),
                    source="voice" if hh_item.get("transcript") else "manual",
                )
                db.add(hh_visit)
                db.flush()
                saved_hh_visits.append({
                    "id": hh_visit.id,
                    "household_id": hh.id,
                    "visit_date": hh_visit.visit_date.isoformat(),
                    "source": hh_visit.source,
                })

        db.commit()

        # Broadcast live event for real-time dashboard updates
        broadcast_dashboard_event("batch_visits_saved", {
            "count": len(saved_visits),
            "household_visits_count": len(saved_hh_visits),
            "beneficiary_names": [v["beneficiary_name"] for v in saved_visits],
            "visit_date": date.today().isoformat(),
        })

    except Exception:
        db.rollback()
        raise

    return BatchVisitResponse(
        saved_visits=saved_visits,
        saved_household_visits=saved_hh_visits,
        total_saved=len(saved_visits) + len(saved_hh_visits),
        alerts=all_alerts,
    )
