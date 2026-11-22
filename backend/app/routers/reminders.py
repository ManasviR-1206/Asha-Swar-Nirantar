"""SMS reminder endpoints: list, create, send (live/demo-honest), reschedule.

Reminder sends reuse the shared notification SMS service (TextBee/legacy/demo) so delivery,
validation, consent checks, duplicate prevention, and history are consistent.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, Beneficiary, SmsReminder
from app.schemas import ReminderCreate, ReminderListResponse, ReminderOut
from app.services import notifications as notify

router = APIRouter(prefix="/api/reminders", tags=["reminders"], dependencies=[Depends(get_current_worker)])


@router.get("", response_model=ReminderListResponse)
def list_reminders(db: Session = Depends(get_db)):
    reminders = db.query(SmsReminder).order_by(SmsReminder.due_date).all()
    names = {b.id: b.name for b in db.query(Beneficiary).all()}
    return {"reminders": [_reminder_out(r, names.get(r.beneficiary_id, "Unknown")) for r in reminders]}


@router.post("", response_model=ReminderOut)
def create_reminder(
    payload: ReminderCreate,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    b = db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    reminder = SmsReminder(
        beneficiary_id=b.id,
        type=payload.type,
        # Generic body only — the SMS never carries a name or any health detail.
        message=notify.build_sms_body(payload.type, "en"),
        due_date=payload.due_date,
        status="scheduled",
        sms_status="pending",
        sms_consent=True,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder, b.name)


@router.post("/{reminder_id}/send")
async def send_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
):
    """Send the reminder SMS via the configured provider (TextBee/legacy) or record a demo send.

    Reuses the shared SMS notification service for validation, provider handling, and history.
    """
    reminder = db.query(SmsReminder).filter(SmsReminder.id == reminder_id).first()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    ben = db.query(Beneficiary).filter(Beneficiary.id == reminder.beneficiary_id).first()
    if ben is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")

    if not getattr(reminder, "sms_consent", True):
        raise HTTPException(status_code=400, detail="SMS consent is required before this reminder can be sent.")

    # Record consent for this reminder send (explicit action by authorized worker).
    consent = notify.record_consent(
        db, ben, "sms", True, purpose="reminder_sms", worker_id=worker.id
    )

    body = (reminder.message or "").strip() or notify.build_sms_body(reminder.type, "en")
    try:
        result = await notify.send_sms_notification(
            db,
            beneficiary=ben,
            follow_up_type=reminder.type,
            language="en",
            body=body,
            worker_id=worker.id,
            follow_up_id=reminder.follow_up_id,
            consent=consent,
            allow_duplicate=False,
        )
    except Exception:
        reminder.sms_status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Could not process the SMS request. Please try again.")

    # Keep SmsReminder state in sync with delivery outcome
    if result.get("duplicate") and result.get("ok"):
        # Existing non-failed notification already exists; reflect a sent/pending-compatible state.
        dup_status = (result.get("status") or "").lower()
        if dup_status == "demo":
            reminder.sms_status = "demo_sent"
            reminder.status = "sent"
        elif dup_status in ("submitted", "sent", "delivered"):
            reminder.sms_status = "sent"
            reminder.status = "sent"
        elif dup_status == "pending":
            reminder.sms_status = "pending"
        db.commit()
        return {
            "status": "demo_sent" if dup_status == "demo" else ("sent" if dup_status in ("submitted", "sent", "delivered") else "pending"),
            "note": result.get("note") or "Duplicate SMS prevented (already sent or pending).",
            "notification_id": result.get("id"),
            "duplicate": True,
        }

    if result.get("ok") and result.get("is_demo"):
        reminder.sms_status = "demo_sent"
        reminder.status = "sent"
        db.commit()
        return {
            "status": "demo_sent",
            "note": result.get("note") or notify.DEMO_LABEL,
            "notification_id": result.get("id"),
            "duplicate": False,
        }

    if result.get("ok"):
        # Provider accepted/submitted the message (or explicitly delivered where reported)
        reminder.sms_status = "sent"
        reminder.status = "sent"
        db.commit()
        return {
            "status": "sent",
            "note": result.get("note") or "Submitted to the SMS provider.",
            "notification_id": result.get("id"),
            "duplicate": False,
        }

    reminder.sms_status = "failed"
    db.commit()
    return {
        "status": "failed",
        "note": result.get("note") or "SMS delivery failed.",
        "notification_id": result.get("id"),
        "duplicate": False,
    }


@router.post("/{reminder_id}/reschedule", response_model=ReminderOut)
def reschedule(reminder_id: int, payload: dict, db: Session = Depends(get_db)):
    reminder = db.query(SmsReminder).filter(SmsReminder.id == reminder_id).first()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    try:
        new_date = date.fromisoformat(str(payload.get("due_date"))[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="due_date must be YYYY-MM-DD")
    reminder.due_date = new_date
    if reminder.status in ("overdue", "sent", "demo_sent"):
        reminder.status = "scheduled"
    if reminder.sms_status in ("demo_sent", "failed"):
        reminder.sms_status = "pending"
    db.commit()
    db.refresh(reminder)
    return _reminder_out(reminder, _beneficiary_name(db, reminder.beneficiary_id))


def _reminder_out(r: SmsReminder, name: str) -> dict:
    return {
        "id": r.id,
        "beneficiary_id": r.beneficiary_id,
        "beneficiary_name": name,
        "type": r.type,
        "message": r.message,
        "due_date": r.due_date,
        "status": r.status,
        "sms_status": r.sms_status or r.status,
        "sms_consent": r.sms_consent,
    }


def _beneficiary_name(db: Session, beneficiary_id: int) -> str:
    b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    return b.name if b else "Unknown"
