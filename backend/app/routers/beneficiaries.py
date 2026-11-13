"""Beneficiary endpoints: list, create, detail, QR resolve, QR image."""
import base64
import io
import secrets

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import Beneficiary, DangerAlert, FollowUp, SmsReminder, VisitRecord
from app.routers.dashboard import broadcast_dashboard_event
from app.schemas import (
    BeneficiaryCreate,
    BeneficiaryDetailResponse,
    BeneficiaryListResponse,
    QrResponse,
)

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"], dependencies=[Depends(get_current_worker)])

_QR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous characters


def _new_qr_id() -> str:
    part = lambda: "".join(secrets.choice(_QR_ALPHABET) for _ in range(4))
    return f"ASN-{part()}-{part()}"


def _beneficiary_out(b: Beneficiary, visits: list[VisitRecord], followups: list[FollowUp],
                     open_alerts: list[DangerAlert]) -> dict:
    """Common projection: last visit, next follow-up, and a derived status."""
    last_visit = max((v.visit_date for v in visits), default=None)
    upcoming = [fu.due_date for fu in followups if fu.status == "upcoming"]
    next_followup = min(upcoming) if upcoming else None
    if open_alerts:
        status = "danger"
    elif any(fu.status in ("overdue", "missed") for fu in followups):
        status = "overdue"
    elif next_followup:
        status = "upcoming"
    else:
        status = "ok"
    return {
        "id": b.id,
        "qr_id": b.qr_id,
        "name": b.name,
        "age": b.age,
        "category": b.category,
        "gender": getattr(b, "gender", "") or "",
        "village": b.village,
        "address": getattr(b, "address", "") or "",
        "last_visit_date": last_visit,
        "next_followup_date": next_followup,
        "status": status,
    }


@router.get("", response_model=BeneficiaryListResponse)
def list_beneficiaries(search: str = "", category: str = "", db: Session = Depends(get_db)):
    query = db.query(Beneficiary)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (Beneficiary.name.ilike(term)) | (Beneficiary.village.ilike(term)) | (Beneficiary.qr_id.ilike(term))
        )
    if category.strip():
        query = query.filter(func.lower(Beneficiary.category) == category.strip().lower())
    beneficiaries = query.order_by(Beneficiary.name).all()

    items = []
    for b in beneficiaries:
        visits = db.query(VisitRecord).filter(VisitRecord.beneficiary_id == b.id).all()
        followups = db.query(FollowUp).filter(FollowUp.beneficiary_id == b.id).all()
        alerts = db.query(DangerAlert).filter(DangerAlert.beneficiary_id == b.id, DangerAlert.status == "open").all()
        items.append(_beneficiary_out(b, visits, followups, alerts))
    return {"beneficiaries": items}


@router.post("", response_model=BeneficiaryListResponse)
def create_beneficiary(payload: BeneficiaryCreate, db: Session = Depends(get_db)):
    b = Beneficiary(
        qr_id=_new_qr_id(),
        name=payload.name.strip(),
        age=payload.age or 0,
        category=payload.category,
        gender=(payload.gender or "").strip(),
        village=(payload.village or "").strip(),
        address=(payload.address or "").strip(),
        phone=payload.phone,
        lmp_date=payload.lmp_date,
        birth_date=payload.birth_date,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    broadcast_dashboard_event("new_beneficiary", {"id": b.id, "name": b.name, "category": b.category})
    return {"beneficiaries": [_beneficiary_out(b, [], [], [])]}


@router.get("/{beneficiary_id}")
def get_beneficiary(beneficiary_id: int, db: Session = Depends(get_db)):
    b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return _build_detail(db, b)


@router.get("/resolve/{qr_id}")
def resolve_beneficiary(qr_id: str, db: Session = Depends(get_db)):
    b = db.query(Beneficiary).filter(Beneficiary.qr_id == qr_id.strip().upper()).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return _build_detail(db, b)


@router.get("/{beneficiary_id}/qr", response_model=QrResponse)
def beneficiary_qr(beneficiary_id: int, db: Session = Depends(get_db)):
    """QR PNG data URL encoding ONLY the beneficiary's qr_id string."""
    b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    img = qrcode.make(b.qr_id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"qr_id": b.qr_id, "data_url": data_url}


def _build_detail(db: Session, b: Beneficiary) -> dict:
    visits = db.query(VisitRecord).filter(VisitRecord.beneficiary_id == b.id).order_by(VisitRecord.visit_date.desc()).all()
    alerts = db.query(DangerAlert).filter(DangerAlert.beneficiary_id == b.id).order_by(DangerAlert.created_at.desc()).all()
    reminders = db.query(SmsReminder).filter(SmsReminder.beneficiary_id == b.id).order_by(SmsReminder.due_date.desc()).all()
    followups = db.query(FollowUp).filter(FollowUp.beneficiary_id == b.id).order_by(FollowUp.due_date).all()

    visits_out = []
    for v in visits:
        structured: dict = {}
        if v.notes:
            import json

            try:
                structured = json.loads(v.notes)
            except ValueError:
                structured = {"notes": v.notes}
        visits_out.append(
            {"id": v.id, "visit_date": v.visit_date, "category": v.category,
             "structured": structured, "source": v.source}
        )

    beneficiary = _beneficiary_out(b, visits, followups,
                                   [a for a in alerts if a.status == "open"])
    return {
        "beneficiary": beneficiary,
        "visits": visits_out,
        "alerts": [
            {"id": a.id, "phrase": a.triggered_phrase, "rule_id": a.rule_id,
             "message": a.message, "severity": a.severity, "status": a.status,
             "created_at": a.created_at}
            for a in alerts
        ],
        "reminders": [
            {"id": r.id, "type": r.type, "due_date": r.due_date, "status": r.status,
             "sms_consent": r.sms_consent, "message": r.message}
            for r in reminders
        ],
        "followups": [
            {"id": f.id, "type": f.type, "due_date": f.due_date, "status": f.status}
            for f in followups
        ],
    }
