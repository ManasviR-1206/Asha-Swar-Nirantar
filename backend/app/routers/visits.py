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
from app.data_scope import visible_beneficiaries
from app.database import get_db
from app.models import (
    AshaWorker,
    Beneficiary,
    DangerAlert,
    ExtractedField,
    FieldAudit,
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


def _alert_dict(alert: DangerAlert, beneficiary_name: str, beneficiary=None, household_map: dict | None = None) -> dict:
    status = alert.status or "open"
    if status == "open":
        status = "new"
    status = (status or "new").lower().replace("-", "_")
    category = alert.alert_category or "danger_sign"
    detected_sign = (getattr(alert, "triggered_phrase", "") or "").strip()
    visit_id = getattr(alert, "visit_id", None)
    reason = alert.reason or (f'Detected approved danger phrase "{detected_sign}" (rule {alert.rule_id}).' if detected_sign else "Detected approved danger sign from recorded observation.")
    recommended = alert.recommended_action or alert.message or "Refer to PHC as per approved guidelines."
    household_id = None
    household_name = ""
    if beneficiary is not None and getattr(beneficiary, "household_id", None):
        household_id = beneficiary.household_id
        hh = (household_map or {}).get(household_id)
        if hh is not None:
            village = getattr(hh, "village", "") or ""
            qr = getattr(hh, "qr_id", "") or ""
            household_name = f"{village} household ({qr})".strip() if (village or qr) else f"Household {household_id}"
        else:
            household_name = f"Household {household_id}"
    elif visit_id and beneficiary is not None:
        # fallback if household not joined but beneficiary has no household link
        household_id = getattr(beneficiary, "household_id", None)

    clinical_source = getattr(alert, "clinical_source", "") or "ASHA Swar Nirantar deterministic danger-sign phrase rules (backend/app/rules.py). Clinical review/approval pending."
    rule_version = getattr(alert, "rule_version", "") or "draft-unreviewed-v1"
    ben_origin = (getattr(beneficiary, "data_origin", None) or "registered") if beneficiary is not None else "registered"
    is_synthetic = ben_origin == "synthetic_demo" or (getattr(beneficiary, "verification_status", "") == "synthetic_demo" if beneficiary is not None else False)
    trigger_detail = alert.trigger_detail or (f'Verified phrase "{detected_sign}" detected in recorded visit observation.' if detected_sign else "")
    if visit_id:
        source_observation = f"Visit record #{visit_id}" + (f": {trigger_detail}" if trigger_detail else "")
    else:
        source_observation = trigger_detail or (f'Recorded observation: "{detected_sign}"' if detected_sign else "Recorded observation (visit not linked)")
    detection_ts = alert.created_at or datetime.utcnow()

    return {
        "id": alert.id,
        "beneficiary_id": alert.beneficiary_id,
        "beneficiary_name": beneficiary_name,
        "beneficiary_data_origin": ben_origin,
        "is_synthetic_demo": bool(is_synthetic),
        "household_id": household_id,
        "household_name": household_name,
        "visit_id": visit_id,
        "phrase": detected_sign,
        "triggering_phrase": detected_sign,
        "detected_danger_sign": detected_sign,
        "rule_id": alert.rule_id,
        "rule_version": rule_version,
        "clinical_source": clinical_source,
        "message": alert.message,
        "severity": alert.severity,
        "status": status,
        "alert_category": category,
        "trigger_detail": trigger_detail,
        "trigger_value": alert.trigger_value or detected_sign,
        "triggering_event": trigger_detail or detected_sign,
        "source_observation": source_observation,
        "reason": reason,
        "recommended_action": recommended,
        "assigned_worker_id": alert.assigned_worker_id,
        "escalation_note": alert.escalation_note or "",
        "resolved_note": alert.resolved_note or "",
        "referral_facility": getattr(alert, "referral_facility", "") or "",
        "referral_date": getattr(alert, "referral_date", None),
        "referral_note": getattr(alert, "referral_note", "") or "",
        "referred_at": getattr(alert, "referred_at", None),
        "referred_by_worker_id": getattr(alert, "referred_by_worker_id", None),
        "referral_pending": bool((getattr(alert, "referral_facility", "") or getattr(alert, "referred_at", None)) and status not in ("resolved","dismissed")),
        "dismiss_reason": (alert.resolved_note or "") if status == "dismissed" else "",
        "detection_timestamp": detection_ts,
        "updated_at": alert.updated_at,
        "resolved_at": alert.resolved_at,
        "created_at": detection_ts,
        "generated_at": detection_ts,
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
    idempotency_key: str = "",
) -> tuple[VisitRecord, Beneficiary, list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Core logic to process and persist one visit record."""
    beneficiary = None
    if beneficiary_id:
        beneficiary = (
            visible_beneficiaries(db.query(Beneficiary))
            .filter(Beneficiary.id == beneficiary_id)
            .first()
        )
        if beneficiary is None:
            raise HTTPException(status_code=404, detail="Beneficiary not found")

    if beneficiary is None and beneficiary_name:
        spoken_name = beneficiary_name.strip().lower()
        all_bens = visible_beneficiaries(db.query(Beneficiary)).all()
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
        idempotency_key=(idempotency_key or "")[:128],
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

    # Danger signs (evaluate verified transcript and structured observations)
    alerts_out: list[dict[str, Any]] = []
    alert_generation_error: str | None = None
    combined_text = (transcript or "").strip()
    has_structured_obs = any(isinstance(v, (str, list, dict)) and v for k, v in (structured or {}).items() if any(tok in str(k).lower() for tok in ("danger", "symptom", "complaint", "note", "observation", "finding", "concern", "problem", "remark")))
    if combined_text or has_structured_obs:
        try:
            with db.begin_nested():
                flags = detect_danger_signs(transcript, beneficiary.category, structured=structured)
                for flag in flags:
                    existing = (
                        db.query(DangerAlert)
                        .filter(
                            DangerAlert.beneficiary_id == beneficiary.id,
                            DangerAlert.rule_id == flag["rule_id"],
                            DangerAlert.status.notin_(["resolved", "dismissed"]),
                        )
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
                            rule_version="deterministic-v2",
                            clinical_source=flag.get("guideline_citation") or "ASHA Swar Nirantar deterministic danger-sign phrase rules (backend/app/rules.py). Clinical review/approval pending.",
                            message=flag.get("message") or REFERRAL_MESSAGE,
                            severity=flag.get("severity", "high"),
                            status="new",
                            alert_category=flag.get("applies_to") or "danger_sign",
                            trigger_detail=f'Verified phrase "{flag["phrase"]}" matched rule {flag["rule_id"]}.',
                            trigger_value=flag["phrase"],
                            reason=f'Danger sign detected from recorded observation/transcript: "{flag["phrase"]}" matched approved rule {flag["rule_id"]}.',
                            recommended_action=flag.get("message") or REFERRAL_MESSAGE,
                            assigned_worker_id=beneficiary.assigned_worker_id,
                            updated_at=datetime.utcnow(),
                        )
                        db.add(alert)
                        db.flush()
                        try:
                            from app.models import AlertAuditLog
                            db.add(AlertAuditLog(alert_id=alert.id, action="created", actor_label="system", note=f"Rule {flag['rule_id']} triggered from visit record."))
                        except Exception:
                            pass
                    alerts_out.append(_alert_dict(alert, beneficiary.name, beneficiary))
        except Exception as e:
            # Preserve the saved visit; surface alert-processing failure for safe retry/investigation.
            alert_generation_error = str(e.__class__.__name__)
            try:
                from app import logger as _logger
                _logger.warning("Danger alert generation failed for visit %s: %s", getattr(visit, "id", None), e.__class__.__name__)
            except Exception:
                pass

    # Auto-schedule follow up (persisted task, idempotent)
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
        from app.models import FollowUpHistory
        from app.services.followups import status_for_due

        reason_map = {
            "anc": "ANC follow-up visit",
            "newborn": "Newborn follow-up visit",
            "vaccination": "Vaccination follow-up",
            "nutrition": "Nutrition follow-up",
            "community": "Community health follow-up",
        }
        reason = reason_map.get(fu_type, f"{fu_type} follow-up")
        existing_fu = (
            db.query(FollowUp)
            .filter(
                FollowUp.beneficiary_id == beneficiary.id,
                FollowUp.due_date == next_due,
                FollowUp.type == fu_type,
                FollowUp.status.in_(["upcoming", "due", "overdue"]),
            )
            .order_by(FollowUp.id.desc())
            .first()
        )
        if existing_fu:
            # Do not silently overwrite existing active follow-up details; keep schedule link fresh.
            if not existing_fu.visit_id:
                existing_fu.visit_id = visit.id
            if not getattr(existing_fu, "source_type", ""):
                existing_fu.source_type = "visit"
                existing_fu.source_id = visit.id
                existing_fu.source_ref = f"visit:{visit.id}"
            existing_fu.updated_at = datetime.utcnow()
            fu = existing_fu
        else:
            fu = FollowUp(
                beneficiary_id=beneficiary.id,
                visit_id=visit.id,
                type=fu_type,
                category=fu_type,
                due_date=next_due,
                status=status_for_due(next_due),
                priority="normal",
                reason=reason,
                description=f"Auto-scheduled from recorded visit on {visit_date.isoformat()}.",
                recommended_action="Conduct the scheduled follow-up visit and record observations.",
                assigned_worker_id=getattr(beneficiary, "assigned_worker_id", None) or worker.id,
                source_type="visit",
                source_id=visit.id,
                source_ref=f"visit:{visit.id}",
                dedup_key=f"visit:{visit.id}:{fu_type}:{next_due.isoformat()}",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(fu)
            db.flush()
            db.add(
                FollowUpHistory(
                    followup_id=fu.id,
                    action="created",
                    from_status="",
                    to_status=fu.status,
                    note=f"Auto-generated from confirmed visit #{visit.id}.",
                    actor_id=worker.id,
                    actor_label=worker.name or "worker",
                    changed_at=datetime.utcnow(),
                )
            )
        follow_up_out = {"id": fu.id, "type": fu.type, "due_date": fu.due_date, "status": fu.status}

    return visit, beneficiary, alerts_out, follow_up_out, alert_generation_error


@router.post("", response_model=VisitCreateResponse)
def create_visit(payload: VisitCreate, db: Session = Depends(get_db),
                 worker: AshaWorker = Depends(get_current_worker)):
    confirmation = getattr(payload, "confirmation", None)
    if confirmation is None or not getattr(confirmation, "confirmed", False):
        raise HTTPException(status_code=400, detail="Explicit confirmation is required before saving a visit.")
    if getattr(confirmation, "method", "voice") not in {"voice", "ui_fallback"}:
        raise HTTPException(status_code=400, detail="Invalid confirmation method.")
    idem = (getattr(payload, "idempotency_key", None) or "").strip()
    if idem:
        existing = (
            db.query(VisitRecord)
            .filter(
                VisitRecord.worker_id == worker.id,
                VisitRecord.beneficiary_id == payload.beneficiary_id,
                VisitRecord.idempotency_key == idem,
            )
            .order_by(VisitRecord.id.desc())
            .first()
        )
        if existing:
            return {
                "visit": {
                    "id": existing.id,
                    "beneficiary_id": existing.beneficiary_id,
                    "visit_date": existing.visit_date,
                    "category": existing.category,
                    "source": existing.source,
                    "structured": payload.structured or {},
                },
                "alerts": [],
                "follow_up": None,
                "idempotent_replay": True,
            }
    visit, beneficiary, alerts_out, follow_up_out, alert_generation_error = _process_single_visit(
        db=db,
        worker=worker,
        beneficiary_id=payload.beneficiary_id,
        beneficiary_name=None,
        structured=payload.structured or {},
        transcript=payload.transcript,
        language=payload.language,
        visit_type=payload.visit_type,
        create_if_missing=False,
        idempotency_key=(getattr(payload, "idempotency_key", None) or ""),
    )
    for corr in (getattr(payload, "corrections", None) or []):
        if not isinstance(corr, dict):
            continue
        field = str(corr.get("field") or corr.get("field_name") or "").strip()
        if not field:
            continue
        db.add(FieldAudit(
            entity_type="visit_field",
            entity_id=visit.id,
            field_name=field[:64],
            old_value=str(corr.get("old_value", ""))[:500],
            new_value=str(corr.get("new_value", corr.get("value", "")))[:500],
            changed_by=worker.id,
            reason=str(corr.get("reason", "voice_correction"))[:256],
            source=str(corr.get("source", "voice"))[:32],
        ))
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
        "alert_generation_error": alert_generation_error,
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
            visit, ben, alerts, fu, alert_err = _process_single_visit(
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
