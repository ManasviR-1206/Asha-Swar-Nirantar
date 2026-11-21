"""Household Health & Hygiene endpoints.

- GET    /api/households                 list (+search)
- POST   /api/households                 create (with members)
- GET    /api/households/{id}            detail: household + members + visits + follow-ups
- GET    /api/households/resolve/{qr_id} resolve a household QR identifier
- GET    /api/households/{id}/qr         QR PNG data URL encoding ONLY the household qr_id
- POST   /api/households/{id}/visits     record a hygiene/water/sanitation observation visit

Privacy: the QR holds only the opaque household identifier. Observations are
recorded without shaming or cleanliness scores — counselling notes only.
"""
import base64
import io
import json
import secrets
from datetime import date, datetime, timedelta

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.data_scope import (
    visible_beneficiaries,
    visible_followups,
    visible_household_members,
    visible_households,
)
from app.database import get_db
from app.models import AshaWorker, Beneficiary, FollowUp, Household, HouseholdMember, HouseholdVisit
from app.routers.dashboard import broadcast_dashboard_event
from app.schemas import (
    HouseholdCreate,
    HouseholdDetailResponse,
    HouseholdListResponse,
    HouseholdVisitCreate,
    QrResponse,
)

router = APIRouter(prefix="/api/households", tags=["households"], dependencies=[Depends(get_current_worker)])

_QR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_qr_id() -> str:
    part = lambda: "".join(secrets.choice(_QR_ALPHABET) for _ in range(4))
    return f"HN-{part()}-{part()}"


def _household_out(h: Household, visits: list[HouseholdVisit], followups: list[FollowUp]) -> dict:
    last_visit = max((v.visit_date for v in visits), default=None)
    upcoming = [fu.due_date for fu in followups if fu.status in ("upcoming", "due")]
    next_followup = min(upcoming) if upcoming else None
    if any(fu.status in ("overdue", "missed") for fu in followups):
        status = "overdue"
    elif any(fu.status == "due" for fu in followups):
        status = "due"
    elif next_followup:
        status = "upcoming"
    else:
        status = "ok"
    # Attention flag: latest observation reported stagnant water and no later
    # visit has recorded that it was cleared (record for verification only —
    # this is an observation follow-up, not a medical claim).
    attention = False
    if visits:
        latest = max(visits, key=lambda v: (v.visit_date, v.id))
        try:
            structured = json.loads(latest.notes) if latest.notes else {}
        except ValueError:
            structured = {}
        attention = bool(structured.get("stagnant_water"))
    return {
        "id": h.id,
        "qr_id": h.qr_id,
        "village": h.village,
        "address": h.address,
        "member_count": h.member_count,
        "data_origin": getattr(h, "data_origin", "registered") or "registered",
        "latitude": h.latitude,
        "longitude": h.longitude,
        "location_source": h.location_source or "",
        "location_updated_at": h.location_updated_at.isoformat() if h.location_updated_at else None,
        "last_visit_date": last_visit,
        "next_followup_date": next_followup,
        "status": "attention" if attention and status == "ok" else status,
    }


@router.get("", response_model=HouseholdListResponse)
def list_households(search: str = "", db: Session = Depends(get_db)):
    query = visible_households(db.query(Household))
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (Household.village.ilike(term))
            | (Household.address.ilike(term))
            | (Household.qr_id.ilike(term))
        )
    households = query.order_by(Household.id).all()
    items = []
    for h in households:
        visits = db.query(HouseholdVisit).filter(HouseholdVisit.household_id == h.id).all()
        followups = visible_followups(db.query(FollowUp), db).filter(FollowUp.household_id == h.id).all()
        items.append(_household_out(h, visits, followups))
    return {"households": items}


@router.post("", response_model=HouseholdListResponse)
def create_household(payload: HouseholdCreate, db: Session = Depends(get_db)):
    for member in payload.members:
        if member.beneficiary_id is not None:
            beneficiary = (
                visible_beneficiaries(db.query(Beneficiary))
                .filter(Beneficiary.id == member.beneficiary_id)
                .first()
            )
            if beneficiary is None:
                raise HTTPException(status_code=404, detail="Beneficiary not found")

    h = Household(
        qr_id=_new_qr_id(),
        village=payload.village.strip(),
        address=payload.address.strip(),
        member_count=payload.member_count or len(payload.members),
    )
    db.add(h)
    db.flush()
    for m in payload.members:
        db.add(HouseholdMember(
            household_id=h.id, name=m.name.strip(), age=m.age,
            gender=m.gender, relation=m.relation, beneficiary_id=m.beneficiary_id,
        ))
    db.commit()
    db.refresh(h)
    return {"households": [_household_out(h, [], [])]}


def _build_detail(db: Session, h: Household) -> dict:
    visits = (
        db.query(HouseholdVisit)
        .filter(HouseholdVisit.household_id == h.id)
        .order_by(HouseholdVisit.visit_date.desc(), HouseholdVisit.id.desc())
        .all()
    )
    followups = (
        visible_followups(db.query(FollowUp), db)
        .filter(FollowUp.household_id == h.id)
        .order_by(FollowUp.due_date.asc(), FollowUp.id.desc())
        .all()
    )
    members = (
        visible_household_members(db.query(HouseholdMember))
        .filter(HouseholdMember.household_id == h.id)
        .order_by(HouseholdMember.id)
        .all()
    )

    visits_out = []
    for v in visits:
        structured: dict = {}
        if v.notes:
            try:
                structured = json.loads(v.notes)
            except ValueError:
                structured = {"notes": v.notes}
        visits_out.append(
            {"id": v.id, "visit_date": v.visit_date, "structured": structured, "source": v.source}
        )

    household = _household_out(h, visits, followups)
    return {
        "household": household,
        "members": [
            {"id": m.id, "name": m.name, "age": m.age, "gender": m.gender,
             "relation": m.relation, "beneficiary_id": m.beneficiary_id}
            for m in members
        ],
        "visits": visits_out,
        "followups": [
            {
                "id": f.id,
                "type": f.type,
                "category": getattr(f, "category", "") or f.type,
                "due_date": f.due_date,
                "status": f.status,
                "priority": getattr(f, "priority", "normal"),
                "reason": getattr(f, "reason", "") or "",
                "description": getattr(f, "description", "") or "",
                "recommended_action": getattr(f, "recommended_action", "") or "",
                "assigned_worker_id": getattr(f, "assigned_worker_id", None),
                "notes": getattr(f, "notes", "") or "",
                "completion_notes": getattr(f, "completion_notes", "") or "",
                "cancellation_reason": getattr(f, "cancellation_reason", "") or "",
                "completed_at": getattr(f, "completed_at", None),
                "cancelled_at": getattr(f, "cancelled_at", None),
                "created_at": getattr(f, "created_at", None),
                "updated_at": getattr(f, "updated_at", None),
            }
            for f in followups
        ],
    }


@router.get("/resolve/{qr_id}")
def resolve_household(qr_id: str, db: Session = Depends(get_db)):
    h = visible_households(db.query(Household)).filter(Household.qr_id == qr_id.strip().upper()).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return _build_detail(db, h)


@router.get("/{household_id}")
def get_household(household_id: int, db: Session = Depends(get_db)):
    h = visible_households(db.query(Household)).filter(Household.id == household_id).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return _build_detail(db, h)


@router.get("/{household_id}/qr", response_model=QrResponse)
def household_qr(household_id: int, db: Session = Depends(get_db)):
    """QR PNG data URL encoding ONLY the household's qr_id string."""
    h = visible_households(db.query(Household)).filter(Household.id == household_id).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")
    img = qrcode.make(h.qr_id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"qr_id": h.qr_id, "data_url": data_url}


@router.post("/{household_id}/visits")
def create_household_visit(
    household_id: int,
    payload: HouseholdVisitCreate,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    h = db.query(Household).filter(Household.id == household_id).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")

    structured = payload.structured or {}
    visit_date = date.today()
    if structured.get("visit_date"):
        try:
            visit_date = date.fromisoformat(str(structured["visit_date"])[:10])
        except ValueError:
            visit_date = date.today()
    source = "voice" if (payload.transcript or "").strip() else "manual"

    visit = HouseholdVisit(
        household_id=h.id, worker_id=worker.id, visit_date=visit_date,
        notes=json.dumps(structured), source=source,
    )
    db.add(visit)
    db.flush()

    # Auto-create the household follow-up when the worker states one.
    # A reported stagnant-water observation gets a 7-day verification
    # follow-up by default (deterministic rule) unless a specific date
    # was spoken.
    follow_up_out = None
    follow_days: int | None = None
    if isinstance(structured.get("follow_up_days"), (int, float)) and structured["follow_up_days"] > 0:
        follow_days = int(structured["follow_up_days"])
    elif structured.get("stagnant_water"):
        follow_days = 7
    if follow_days:
        due = visit_date + timedelta(days=follow_days)
        from app.models import FollowUpHistory
        from app.services.followups import status_for_due

        existing = (
            db.query(FollowUp)
            .filter(
                FollowUp.household_id == h.id,
                FollowUp.status.in_(["upcoming", "due", "overdue"]),
                FollowUp.type == "household",
            )
            .order_by(FollowUp.due_date.asc(), FollowUp.id.desc())
            .first()
        )
        if existing:
            # Preserve existing active follow-up; don't silently overwrite user-managed details.
            if not existing.visit_id:
                existing.visit_id = None
            existing.updated_at = datetime.utcnow()
            fu = existing
        else:
            reason = "Household hygiene/water-sanitation follow-up"
            if structured.get("stagnant_water"):
                reason = "Stagnant water verification follow-up"
            fu = FollowUp(
                household_id=h.id,
                type="household",
                category="household",
                due_date=due,
                status=status_for_due(due),
                priority="normal",
                reason=reason,
                description=f"Auto-scheduled from household visit on {visit_date.isoformat()}.",
                recommended_action="Conduct the household follow-up visit and record observations.",
                assigned_worker_id=worker.id,
                source_type="household_visit",
                source_id=visit.id,
                source_ref=f"household_visit:{visit.id}",
                dedup_key=f"household_visit:{visit.id}:{due.isoformat()}",
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
                    note=f"Auto-generated from household visit #{visit.id}.",
                    actor_id=worker.id,
                    actor_label=worker.name or "worker",
                    changed_at=datetime.utcnow(),
                )
            )
        follow_up_out = {"id": fu.id, "type": fu.type, "due_date": fu.due_date, "status": fu.status}

    db.commit()
    db.refresh(visit)

    # Broadcast event for real-time dashboard update
    broadcast_dashboard_event("new_household_visit", {
        "visit_id": visit.id,
        "household_id": h.id,
        "village": h.village,
        "visit_date": visit.visit_date.isoformat(),
        "source": visit.source,
    })

    return {
        "visit": {
            "id": visit.id, "household_id": visit.household_id,
            "visit_date": visit.visit_date, "source": visit.source,
            "structured": structured,
        },
        "follow_up": follow_up_out,
    }
class HouseholdLocationUpdate(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    location_source: str = Field(default="manual_verified")
    verification_note: str = ""


@router.patch("/{household_id}/location")
def update_household_location(household_id: int, payload: HouseholdLocationUpdate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    h = visible_households(db.query(Household)).filter(Household.id == household_id).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")
    lat = payload.latitude
    lng = payload.longitude
    source = (payload.location_source or "manual_verified").strip()[:32]
    if source not in {"gps", "manual_verified", "imported_verified", "synthetic_demo"}:
        raise HTTPException(status_code=400, detail="Invalid location source")
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Latitude and longitude are required")
    if not (-90.0 <= float(lat) <= 90.0 and -180.0 <= float(lng) <= 180.0):
        raise HTTPException(status_code=400, detail="Invalid coordinates")
    # Never fabricate: only store explicitly provided coordinates.
    h.latitude = float(lat)
    h.longitude = float(lng)
    h.location_source = source
    h.location_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(h)
    return {
        "household_id": h.id,
        "latitude": h.latitude,
        "longitude": h.longitude,
        "location_source": h.location_source,
        "location_updated_at": h.location_updated_at.isoformat() if h.location_updated_at else None,
        "verification_note": (payload.verification_note or "")[:256],
        "updated_by": worker.id,
    }
