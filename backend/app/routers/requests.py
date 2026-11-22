"""Connect with My ASHA: patient/household requests and feedback."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, Beneficiary, Household, PatientRequest

router = APIRouter(prefix="/api/requests", tags=["requests"], dependencies=[Depends(get_current_worker)])


class RequestCreate(BaseModel):
    beneficiary_id: int | None = None
    household_id: int | None = None
    assigned_worker_id: int | None = None
    requester_type: str = "beneficiary"
    category: str
    subject: str = ""
    message: str = ""
    priority: str = "normal"
    is_emergency: bool = False
    rating: int | None = Field(default=None, ge=1, le=5)


class RequestStatusUpdate(BaseModel):
    status: str
    response_note: str = ""
    is_read: bool | None = None


def _out(r: PatientRequest, db: Session) -> dict:
    ben_name = None
    hh_label = None
    if r.beneficiary_id:
        b = db.query(Beneficiary).filter(Beneficiary.id == r.beneficiary_id).first()
        ben_name = b.name if b else None
    if r.household_id:
        h = db.query(Household).filter(Household.id == r.household_id).first()
        hh_label = (h.village + " household") if h else None
    return {
        "id": r.id,
        "beneficiary_id": r.beneficiary_id,
        "beneficiary_name": ben_name,
        "household_id": r.household_id,
        "household_label": hh_label,
        "assigned_worker_id": r.assigned_worker_id,
        "requester_type": r.requester_type,
        "category": r.category,
        "subject": r.subject,
        "message": r.message,
        "priority": r.priority,
        "status": r.status,
        "is_emergency": r.is_emergency,
        "rating": r.rating,
        "response_note": r.response_note,
        "is_read": r.is_read,
        "submitted_at": r.submitted_at,
        "acknowledged_at": r.acknowledged_at,
        "resolved_at": r.resolved_at,
        "updated_at": r.updated_at,
    }


@router.get("")
def list_requests(status: str = "", category: str = "", unread: bool = False, db: Session = Depends(get_db)):
    q = db.query(PatientRequest)
    if status:
        q = q.filter(PatientRequest.status == status)
    if category:
        q = q.filter(PatientRequest.category == category)
    if unread:
        q = q.filter(PatientRequest.is_read == False)  # noqa: E712
    rows = q.order_by(PatientRequest.submitted_at.desc(), PatientRequest.id.desc()).all()
    return {"requests": [_out(r, db) for r in rows]}


@router.post("")
def create_request(payload: RequestCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    allowed = {
        "callback", "health_concern", "visit_request", "missed_followup", "pregnancy_concern",
        "vaccination_info", "emergency", "feedback", "help", "record_correction", "contact_correction",
    }
    if payload.category not in allowed:
        raise HTTPException(status_code=400, detail="Invalid request category")
    if payload.beneficiary_id:
        if db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first() is None:
            raise HTTPException(status_code=404, detail="Beneficiary not found")
    if payload.household_id:
        if db.query(Household).filter(Household.id == payload.household_id).first() is None:
            raise HTTPException(status_code=404, detail="Household not found")
    priority = payload.priority if payload.priority in {"low", "normal", "high", "urgent"} else "normal"
    if payload.is_emergency or payload.category == "emergency":
        priority = "urgent"
    r = PatientRequest(
        beneficiary_id=payload.beneficiary_id,
        household_id=payload.household_id,
        assigned_worker_id=payload.assigned_worker_id or worker.id,
        requester_type=payload.requester_type or "beneficiary",
        category=payload.category,
        subject=(payload.subject or "").strip(),
        message=(payload.message or "").strip(),
        priority=priority,
        status="submitted",
        is_emergency=bool(payload.is_emergency or payload.category == "emergency"),
        rating=payload.rating,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"request": _out(r, db)}


@router.post("/{request_id}/status")
def update_request_status(request_id: int, payload: RequestStatusUpdate, db: Session = Depends(get_db)):
    r = db.query(PatientRequest).filter(PatientRequest.id == request_id).first()
    if r is None:
        raise HTTPException(status_code=404, detail="Request not found")
    allowed = {"submitted", "received", "acknowledged", "in_progress", "resolved", "closed"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    r.status = payload.status
    r.response_note = payload.response_note or r.response_note
    if payload.is_read is not None:
        r.is_read = payload.is_read
    now = datetime.utcnow()
    r.updated_at = now
    if payload.status == "acknowledged" and r.acknowledged_at is None:
        r.acknowledged_at = now
    if payload.status in {"resolved", "closed"} and r.resolved_at is None:
        r.resolved_at = now
    db.commit()
    db.refresh(r)
    return {"request": _out(r, db)}
