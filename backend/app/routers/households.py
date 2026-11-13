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
from datetime import date, timedelta

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, FollowUp, Household, HouseholdMember, HouseholdVisit
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
    upcoming = [fu.due_date for fu in followups if fu.status == "upcoming"]
    next_followup = min(upcoming) if upcoming else None
    if any(fu.status in ("overdue", "missed") for fu in followups):
        status = "overdue"
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
        "last_visit_date": last_visit,
        "next_followup_date": next_followup,
        "status": "attention" if attention and status == "ok" else status,
    }


@router.get("", response_model=HouseholdListResponse)
def list_households(search: str = "", db: Session = Depends(get_db)):
    query = db.query(Household)
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
        followups = db.query(FollowUp).filter(FollowUp.household_id == h.id).all()
        items.append(_household_out(h, visits, followups))
    return {"households": items}


@router.post("", response_model=HouseholdListResponse)
def create_household(payload: HouseholdCreate, db: Session = Depends(get_db)):
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
    followups = db.query(FollowUp).filter(FollowUp.household_id == h.id).order_by(FollowUp.due_date).all()
    members = db.query(HouseholdMember).filter(HouseholdMember.household_id == h.id).order_by(HouseholdMember.id).all()

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
            {"id": f.id, "type": f.type, "due_date": f.due_date, "status": f.status}
            for f in followups
        ],
    }


@router.get("/resolve/{qr_id}")
def resolve_household(qr_id: str, db: Session = Depends(get_db)):
    h = db.query(Household).filter(Household.qr_id == qr_id.strip().upper()).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return _build_detail(db, h)


@router.get("/{household_id}")
def get_household(household_id: int, db: Session = Depends(get_db)):
    h = db.query(Household).filter(Household.id == household_id).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return _build_detail(db, h)


@router.get("/{household_id}/qr", response_model=QrResponse)
def household_qr(household_id: int, db: Session = Depends(get_db)):
    """QR PNG data URL encoding ONLY the household's qr_id string."""
    h = db.query(Household).filter(Household.id == household_id).first()
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
        existing = (
            db.query(FollowUp)
            .filter(FollowUp.household_id == h.id, FollowUp.status == "upcoming")
            .first()
        )
        fu = existing or FollowUp(household_id=h.id, type="household", due_date=due, status="upcoming")
        if existing:
            fu.due_date = due
        if fu not in db:
            db.add(fu)
        db.flush()
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
