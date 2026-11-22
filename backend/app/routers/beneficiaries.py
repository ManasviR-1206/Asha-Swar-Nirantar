"""Beneficiary endpoints: list, create, detail, QR resolve, QR image."""
import base64
import io
import json
import secrets

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.data_scope import visible_beneficiaries, visible_households
from app.database import get_db
from app.models import (
    AshaWorker,
    Beneficiary,
    CarePlanTask,
    DangerAlert,
    FollowUp,
    HealthMeasurement,
    Household,
    ImmunisationRecord,
    NewbornRecord,
    PatientRequest,
    PregnancyRecord,
    SmsReminder,
    UploadedDocument,
    VisitRecord,
)
from app.routers.dashboard import broadcast_dashboard_event
from app.routers.visits import _alert_dict
from app.schemas import (
    BeneficiaryCreate,
    BeneficiaryDetailResponse,
    BeneficiaryListResponse,
    BeneficiaryOut,
    BeneficiaryUpdate,
    QrResponse,
)

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"], dependencies=[Depends(get_current_worker)])

_QR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous characters


def _new_qr_id() -> str:
    part = lambda: "".join(secrets.choice(_QR_ALPHABET) for _ in range(4))
    return f"ASN-{part()}-{part()}"


ACTIVE_ALERT_STATUSES = {"open", "new", "acknowledged", "in_progress", "escalated"}


def _beneficiary_out(b: Beneficiary, visits: list[VisitRecord], followups: list[FollowUp],
                     active_alerts: list[DangerAlert]) -> dict:
    """Common projection: last visit, next follow-up, and a derived status."""
    last_visit = max((v.visit_date for v in visits), default=None)
    upcoming = [fu.due_date for fu in followups if fu.status in ("upcoming", "due")]
    next_followup = min(upcoming) if upcoming else None
    if active_alerts:
        status = "danger"
    elif any(fu.status in ("overdue", "missed") for fu in followups):
        status = "overdue"
    elif any(fu.status == "due" for fu in followups):
        status = "due"
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
        "phone": b.phone,
        "email": b.email,
        "date_of_birth": getattr(b, "date_of_birth", None),
        "birth_date": getattr(b, "birth_date", None),
        "lmp_date": getattr(b, "lmp_date", None),
        "household_id": getattr(b, "household_id", None),
        "assigned_worker_id": getattr(b, "assigned_worker_id", None),
        "pregnancy_status": getattr(b, "pregnancy_status", "") or "",
        "medical_conditions": getattr(b, "medical_conditions", "") or "",
        "allergies": getattr(b, "allergies", "") or "",
        "current_medications": getattr(b, "current_medications", "") or "",
        "child_health_notes": getattr(b, "child_health_notes", "") or "",
        "registration_notes": getattr(b, "registration_notes", "") or "",
        "emergency_contact": getattr(b, "emergency_contact", "") or "",
        "emergency_contact_consent": bool(getattr(b, "emergency_contact_consent", False)),
        "data_origin": getattr(b, "data_origin", "registered") or "registered",
        "verification_status": getattr(b, "verification_status", "asha_verified") or "asha_verified",
        "last_visit_date": last_visit,
        "next_followup_date": next_followup,
        "status": status,
    }


@router.get("", response_model=BeneficiaryListResponse)
def list_beneficiaries(search: str = "", category: str = "", db: Session = Depends(get_db)):
    query = visible_beneficiaries(db.query(Beneficiary))
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
        alerts = db.query(DangerAlert).filter(
            DangerAlert.beneficiary_id == b.id,
            func.lower(DangerAlert.status).in_(list(ACTIVE_ALERT_STATUSES)),
        ).all()
        items.append(_beneficiary_out(b, visits, followups, alerts))
    return {"beneficiaries": items}


def _validate_refs(db: Session, household_id: int | None, assigned_worker_id: int | None):
    if household_id is not None:
        if visible_households(db.query(Household)).filter(Household.id == household_id).first() is None:
            raise HTTPException(status_code=404, detail="Household not found")
    if assigned_worker_id is not None:
        if db.query(AshaWorker).filter(AshaWorker.id == assigned_worker_id).first() is None:
            raise HTTPException(status_code=404, detail="Assigned worker not found")


@router.post("", response_model=BeneficiaryListResponse)
def create_beneficiary(payload: BeneficiaryCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    _validate_refs(db, payload.household_id, payload.assigned_worker_id)
    b = Beneficiary(
        qr_id=_new_qr_id(),
        name=payload.name.strip(),
        age=payload.age or 0,
        category=payload.category,
        gender=(payload.gender or "").strip(),
        village=(payload.village or "").strip(),
        address=(payload.address or "").strip(),
        phone=payload.phone.strip() if payload.phone else None,
        email=(payload.email or "").strip() or None,
        lmp_date=payload.lmp_date,
        birth_date=payload.birth_date,
        date_of_birth=payload.date_of_birth,
        household_id=payload.household_id,
        assigned_worker_id=payload.assigned_worker_id if payload.assigned_worker_id is not None else getattr(worker, "id", None),
        pregnancy_status=(payload.pregnancy_status or "").strip(),
        medical_conditions=(payload.medical_conditions or "").strip(),
        allergies=(payload.allergies or "").strip(),
        current_medications=(payload.current_medications or "").strip(),
        child_health_notes=(payload.child_health_notes or "").strip(),
        registration_notes=(payload.registration_notes or "").strip(),
        emergency_contact=(payload.emergency_contact or "").strip(),
        emergency_contact_consent=bool(payload.emergency_contact_consent),
        verification_status=(payload.verification_status or "asha_verified").strip() or "asha_verified",
        data_origin="registered",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    broadcast_dashboard_event("new_beneficiary", {"id": b.id, "name": b.name, "category": b.category})
    return {"beneficiaries": [_beneficiary_out(b, [], [], [])]}


@router.patch("/{beneficiary_id}", response_model=BeneficiaryOut)
def update_beneficiary(
    beneficiary_id: int,
    payload: BeneficiaryUpdate,
    db: Session = Depends(get_db),
):
    """Update a beneficiary's profile/contact details (review/add/edit)."""
    b = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id == beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")

    _validate_refs(db, payload.household_id, payload.assigned_worker_id)

    for field in ("name", "gender", "village", "address", "pregnancy_status", "medical_conditions", "allergies", "current_medications", "child_health_notes", "registration_notes", "emergency_contact", "verification_status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(b, field, value.strip() if isinstance(value, str) else value)
    if payload.age is not None:
        b.age = payload.age
    if payload.category is not None:
        b.category = payload.category
    if payload.phone is not None:
        b.phone = payload.phone.strip() or None
    if payload.email is not None:
        b.email = payload.email.strip() or None
    if payload.lmp_date is not None:
        b.lmp_date = payload.lmp_date
    if payload.birth_date is not None:
        b.birth_date = payload.birth_date
    if payload.date_of_birth is not None:
        b.date_of_birth = payload.date_of_birth
    if payload.household_id is not None:
        b.household_id = payload.household_id
    if payload.assigned_worker_id is not None:
        b.assigned_worker_id = payload.assigned_worker_id
    if payload.emergency_contact_consent is not None:
        b.emergency_contact_consent = bool(payload.emergency_contact_consent)

    db.commit()
    db.refresh(b)
    visits = db.query(VisitRecord).filter(VisitRecord.beneficiary_id == b.id).all()
    followups = db.query(FollowUp).filter(FollowUp.beneficiary_id == b.id).all()
    alerts = (
        db.query(DangerAlert)
        .filter(
            DangerAlert.beneficiary_id == b.id,
            func.lower(DangerAlert.status).in_(list(ACTIVE_ALERT_STATUSES)),
        )
        .all()
    )
    return _beneficiary_out(b, visits, followups, alerts)


@router.get("/{beneficiary_id}")
def get_beneficiary(beneficiary_id: int, db: Session = Depends(get_db)):
    b = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id == beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return _build_detail(db, b)


@router.get("/resolve/{qr_id}")
def resolve_beneficiary(qr_id: str, db: Session = Depends(get_db)):
    b = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.qr_id == qr_id.strip().upper()).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    return _build_detail(db, b)


@router.get("/{beneficiary_id}/qr", response_model=QrResponse)
def beneficiary_qr(beneficiary_id: int, db: Session = Depends(get_db)):
    """QR PNG data URL encoding ONLY the beneficiary's qr_id string."""
    b = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id == beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    img = qrcode.make(b.qr_id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"qr_id": b.qr_id, "data_url": data_url}


def _build_detail(db: Session, b: Beneficiary) -> dict:
    visits = db.query(VisitRecord).filter(VisitRecord.beneficiary_id == b.id).order_by(VisitRecord.visit_date.desc(), VisitRecord.id.desc()).all()
    alerts = db.query(DangerAlert).filter(DangerAlert.beneficiary_id == b.id).order_by(DangerAlert.created_at.desc(), DangerAlert.id.desc()).all()
    reminders = db.query(SmsReminder).filter(SmsReminder.beneficiary_id == b.id).order_by(SmsReminder.due_date.desc(), SmsReminder.id.desc()).all()
    followups = db.query(FollowUp).filter(FollowUp.beneficiary_id == b.id).order_by(FollowUp.due_date.asc(), FollowUp.id.desc()).all()
    measurements = (
        db.query(HealthMeasurement)
        .filter(HealthMeasurement.beneficiary_id == b.id, getattr(HealthMeasurement, "is_deleted", False) == False)  # noqa: E712
        .order_by(HealthMeasurement.recorded_at.desc(), HealthMeasurement.id.desc())
        .all()
    )
    documents = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.beneficiary_id == b.id, getattr(UploadedDocument, "is_deleted", False) == False)  # noqa: E712
        .order_by(UploadedDocument.created_at.desc(), UploadedDocument.id.desc())
        .all()
    )
    preg_records = (
        db.query(PregnancyRecord)
        .filter(PregnancyRecord.beneficiary_id == b.id)
        .order_by(PregnancyRecord.id.desc())
        .all()
    )
    newborn_records = (
        db.query(NewbornRecord)
        .filter(NewbornRecord.beneficiary_id == b.id)
        .order_by(NewbornRecord.id.desc())
        .all()
    )
    imm_records = (
        db.query(ImmunisationRecord)
        .filter(ImmunisationRecord.beneficiary_id == b.id)
        .order_by(ImmunisationRecord.date_given.desc().nullslast(), ImmunisationRecord.id.desc())
        .all()
    )
    care_tasks = (
        db.query(CarePlanTask)
        .filter(CarePlanTask.beneficiary_id == b.id)
        .order_by(CarePlanTask.due_date.is_(None), CarePlanTask.due_date.asc(), CarePlanTask.id.desc())
        .all()
    )
    reqs = (
        db.query(PatientRequest)
        .filter(PatientRequest.beneficiary_id == b.id)
        .order_by(PatientRequest.submitted_at.desc(), PatientRequest.id.desc())
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
            {"id": v.id, "visit_date": v.visit_date, "category": v.category,
             "structured": structured, "source": v.source}
        )

    household = None
    household_obj = None
    if getattr(b, "household_id", None):
        h = db.query(Household).filter(Household.id == b.household_id).first()
        if h:
            household_obj = h
            household = {"id": h.id, "qr_id": h.qr_id, "village": h.village, "address": h.address, "member_count": h.member_count}

    active_alerts = [a for a in alerts if (a.status or "").lower() in ACTIVE_ALERT_STATUSES]
    beneficiary = _beneficiary_out(b, visits, followups, active_alerts)
    hh_map = {household_obj.id: household_obj} if household_obj else {}
    return {
        "beneficiary": beneficiary,
        "visits": visits_out,
        "alerts": [
            _alert_dict(a, b.name, b, hh_map)
            for a in alerts
        ],
        "reminders": [
            {"id": r.id, "type": r.type, "due_date": r.due_date, "status": r.status,
             "sms_status": getattr(r, "sms_status", r.status), "sms_consent": r.sms_consent, "message": r.message}
            for r in reminders
        ],
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
                "visit_id": getattr(f, "visit_id", None),
                "source_type": getattr(f, "source_type", "") or "",
                "source_ref": getattr(f, "source_ref", "") or "",
                "rescheduled_from": getattr(f, "rescheduled_from", None),
            }
            for f in followups
        ],
        "measurements": [
            {
                "id": m.id, "visit_id": m.visit_id, "measurement_type": m.measurement_type,
                "value": m.value, "value_text": m.value_text, "unit": m.unit,
                "recorded_at": m.recorded_at, "source": m.source,
                "verification_status": getattr(m, "verification_status", "recorded"),
                "recorded_by_worker_id": m.recorded_by_worker_id, "notes": m.notes,
                "created_at": m.created_at, "updated_at": m.updated_at,
            }
            for m in measurements
        ],
        "documents": [
            {
                "id": d.id, "original_filename": d.original_filename, "mime_type": d.mime_type,
                "size_bytes": d.size_bytes, "category": getattr(d, "category", "other") or "other",
                "upload_source": d.upload_source, "uploaded_by": d.uploaded_by,
                "verified": d.verified, "notes": d.notes, "created_at": d.created_at,
                "preview_url": f"/api/documents/{d.id}/preview",
                "download_url": f"/api/documents/{d.id}/download",
            }
            for d in documents
        ],
        "pregnancy_records": [
            {
                "id": p.id, "visit_id": p.visit_id, "weeks_pregnant": p.weeks_pregnant,
                "bp_sys": p.bp_sys, "bp_dia": p.bp_dia, "weight_kg": p.weight_kg,
                "hemoglobin": p.hemoglobin, "fetal_heart": p.fetal_heart, "notes": p.notes,
            }
            for p in preg_records
        ],
        "newborn_records": [
            {
                "id": n.id, "visit_id": n.visit_id, "weight_kg": n.weight_kg,
                "temperature": n.temperature, "feeding": n.feeding, "jaundice": n.jaundice, "notes": n.notes,
            }
            for n in newborn_records
        ],
        "immunisation_records": [
            {
                "id": im.id, "visit_id": im.visit_id, "vaccine_name": im.vaccine_name,
                "dose_number": im.dose_number, "date_given": im.date_given, "next_due_date": im.next_due_date,
            }
            for im in imm_records
        ],
        "household": household,
        "care_plan_tasks": [
            {
                "id": t.id, "title": t.title, "description": t.description, "category": t.category,
                "due_date": t.due_date, "priority": t.priority, "responsible": t.responsible,
                "status": t.status, "notes": t.notes, "completed_at": t.completed_at,
                "created_at": t.created_at, "updated_at": t.updated_at,
            }
            for t in care_tasks
        ],
        "requests": [
            {
                "id": r.id, "category": r.category, "subject": r.subject, "message": r.message,
                "priority": r.priority, "status": r.status, "is_emergency": r.is_emergency,
                "response_note": r.response_note, "submitted_at": r.submitted_at,
                "acknowledged_at": r.acknowledged_at, "resolved_at": r.resolved_at, "updated_at": r.updated_at,
            }
            for r in reqs
        ],
    }