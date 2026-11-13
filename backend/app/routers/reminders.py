"""SMS reminder endpoints: list, create, send (live/demo-honest), reschedule."""
import json
import urllib.request
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import get_env
from app.auth import get_current_worker
from app.database import get_db
from app.models import Beneficiary, SmsReminder
from app.schemas import AckResponse, ReminderCreate, ReminderListResponse, ReminderOut

router = APIRouter(prefix="/api/reminders", tags=["reminders"], dependencies=[Depends(get_current_worker)])

_DEFAULT_MESSAGES = {
    "anc": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
    "vaccination": "Reminder: A community health visit is scheduled. Please coordinate with your local ASHA worker.",
    "newborn": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
    "nutrition": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
    "community": "Reminder: A community health visit is scheduled. Please coordinate with your local ASHA worker.",
    "household": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
}
# The SMS body is deliberately generic: no name, no category, no condition.
_GENERIC_REMINDER = "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker."


@router.get("", response_model=ReminderListResponse)
def list_reminders(db: Session = Depends(get_db)):
    reminders = db.query(SmsReminder).order_by(SmsReminder.due_date).all()
    names = {b.id: b.name for b in db.query(Beneficiary).all()}
    return {"reminders": [_reminder_out(r, names.get(r.beneficiary_id, "Unknown")) for r in reminders]}


@router.post("", response_model=ReminderOut)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)):
    b = db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    reminder = SmsReminder(
        beneficiary_id=b.id,
        type=payload.type,
        # Generic body only — the SMS never carries a name or any health detail.
        message=_DEFAULT_MESSAGES.get(payload.type, _GENERIC_REMINDER),
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
def send_reminder(reminder_id: int, db: Session = Depends(get_db)):
    """Send an SMS via the configured provider.

    LIVE: only if SMS_PROVIDER_URL + SMS_PROVIDER_KEY are set (an HTTP POST).
    Otherwise the reminder is marked "demo_sent" and the response says, in
    plain language, that no real SMS was sent.
    """
    reminder = db.query(SmsReminder).filter(SmsReminder.id == reminder_id).first()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    provider_url = get_env("SMS_PROVIDER_URL")
    provider_key = get_env("SMS_PROVIDER_KEY")
    if provider_url and provider_key:
        try:
            payload = json.dumps(
                {
                    "to": _beneficiary_phone(db, reminder.beneficiary_id) or "",
                    "message": reminder.message,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                provider_url,
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {provider_key}"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15)
            reminder.sms_status = "sent"
            reminder.status = "sent"
            db.commit()
            return {"status": "sent", "note": "Sent via configured SMS provider"}
        except Exception as exc:
            # Live send failed — do NOT pretend it was sent.
            reminder.sms_status = "failed"
            db.commit()
            return {"status": "failed", "note": f"SMS provider error: {exc}"}

    # No provider configured: mark it clearly as a simulated send.
    reminder.sms_status = "demo_sent"
    reminder.status = "sent"
    db.commit()
    return {"status": "demo_sent", "note": "Demo mode: no real SMS sent"}


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


def _beneficiary_phone(db: Session, beneficiary_id: int) -> str | None:
    b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    return b.phone if b else None


def _beneficiary_name(db: Session, beneficiary_id: int) -> str:
    b = db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first()
    return b.name if b else "Unknown"
