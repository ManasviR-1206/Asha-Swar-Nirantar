"""GET /api/dashboard — aggregated stats, today's schedule, activity, reminders,
alerts and recent voice transcripts."""
import asyncio
import json
from datetime import date, datetime
from typing import Set

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import (
    Beneficiary,
    DangerAlert,
    FollowUp,
    Household,
    HouseholdVisit,
    SmsReminder,
    VisitRecord,
    VoiceTranscript,
)
from app.rules import refresh_statuses
from app.schemas import DashboardResponse

router = APIRouter(prefix="/api", tags=["dashboard"])

# Global set of subscriber queues for real-time SSE updates
_SSE_QUEUES: Set[asyncio.Queue] = set()


def broadcast_dashboard_event(event_type: str, data: dict) -> None:
    """Notify all connected SSE clients when a visit or household record is saved."""
    payload = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    }
    for q in list(_SSE_QUEUES):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


@router.get("/dashboard/events")
async def dashboard_events(request: Request):
    """Server-Sent Events stream for live dashboard updates."""
    q: asyncio.Queue = asyncio.Queue()
    _SSE_QUEUES.add(q)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            _SSE_QUEUES.discard(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# Synthetic time slots for the demo schedule (field visits are not clocked
# to the minute in the register; slots are display-only).
SLOT_TIMES = ["09:00 AM", "09:45 AM", "10:30 AM", "11:15 AM", "12:00 PM"]


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db), _worker=Depends(get_current_worker)):
    # Keep statuses fresh on every dashboard load (idempotent, cheap).
    refresh_statuses(db)
    today = date.today()

    beneficiaries = db.query(Beneficiary).all()
    names = {b.id: b.name for b in beneficiaries}
    households = db.query(Household).all()
    household_labels = {
        h.id: (f"{h.village} household" if h.village else f"Household {h.qr_id}")
        for h in households
    }
    household_ids = {h.id for h in households}

    todays_visits = db.query(VisitRecord).filter(VisitRecord.visit_date == today).count()
    todays_household_visits = db.query(HouseholdVisit).filter(HouseholdVisit.visit_date == today).count()
    upcoming = (
        db.query(FollowUp)
        .filter(FollowUp.status == "upcoming")
        .order_by(FollowUp.due_date)
        .all()
    )
    overdue = db.query(FollowUp).filter(FollowUp.status.in_(["overdue", "missed"])).count()
    open_alerts = db.query(DangerAlert).filter(DangerAlert.status == "open").all()
    reminders = (
        db.query(SmsReminder)
        .filter(SmsReminder.status.in_(["scheduled", "overdue"]))
        .order_by(SmsReminder.due_date)
        .all()
    )

    def _subject_name(fu: FollowUp) -> str:
        if fu.household_id:
            return household_labels.get(fu.household_id, "Household")
        return names.get(fu.beneficiary_id, "Unknown")

    def _subject_village(fu: FollowUp) -> str:
        if fu.household_id:
            h = next((x for x in households if x.id == fu.household_id), None)
            return h.village if h else ""
        return next((b.village for b in beneficiaries if b.id == fu.beneficiary_id), "")

    schedule = [
        {
            "time": SLOT_TIMES[i % len(SLOT_TIMES)],
            "beneficiary_name": _subject_name(fu),
            "type": fu.type,
            "village": _subject_village(fu),
        }
        for i, fu in enumerate(upcoming[:5])
    ]

    recent_visits = (
        db.query(VisitRecord).order_by(VisitRecord.visit_date.desc(), VisitRecord.id.desc()).limit(6).all()
    )
    recent_hh_visits = (
        db.query(HouseholdVisit).order_by(HouseholdVisit.visit_date.desc(), HouseholdVisit.id.desc()).limit(3).all()
    )
    merged = sorted(
        recent_visits + recent_hh_visits,
        key=lambda v: (v.visit_date, getattr(v, "id", 0)),
        reverse=True,
    )[:6]
    recent_activity = []
    for v in merged:
        is_household = isinstance(v, HouseholdVisit)
        if is_household:
            recent_activity.append(
                {
                    "beneficiary_name": household_labels.get(v.household_id, "Household"),
                    "action": f"{'Voice' if v.source == 'voice' else 'Manual'} household hygiene visit recorded",
                    "action_code": "voice_household" if v.source == "voice" else "manual_household",
                    "date": v.visit_date,
                    "category": "household",
                }
            )
        else:
            recent_activity.append(
                {
                    "beneficiary_name": names.get(v.beneficiary_id, "Unknown"),
                    "action": f"{'Voice' if v.source == 'voice' else 'Manual'} {v.category} visit recorded",
                    "action_code": "voice_visit" if v.source == "voice" else "manual_visit",
                    "date": v.visit_date,
                    "category": v.category,
                }
            )

    recent_voice = []
    transcripts = (
        db.query(VoiceTranscript).order_by(VoiceTranscript.created_at.desc(), VoiceTranscript.id.desc()).limit(5).all()
    )
    for t in transcripts:
        visit = db.query(VisitRecord).filter(VisitRecord.id == t.visit_id).first() if t.visit_id else None
        recent_voice.append(
            {
                "beneficiary_name": names.get(visit.beneficiary_id) if visit else None,
                "date": visit.visit_date if visit else today,
                "language": t.language,
                "status": "processed",
            }
        )

    alert_items = [
        {
            "id": a.id,
            "beneficiary_name": names.get(a.beneficiary_id, "Unknown"),
            "phrase": a.triggered_phrase,
            "message": a.message,
            "severity": a.severity,
            "created_at": a.created_at,
        }
        for a in open_alerts[:5]
    ]

    return {
        "stats": {
            "total_beneficiaries": len(beneficiaries),
            "total_households": len(households),
            "todays_visits": todays_visits + todays_household_visits,
            "upcoming_followups": len(upcoming),
            "overdue_followups": overdue,
            "active_alerts": len(open_alerts),
        },
        "schedule": schedule,
        "recent_activity": recent_activity,
        "reminders": [
            {
                "id": r.id,
                "beneficiary_name": names.get(r.beneficiary_id, "Unknown"),
                "type": r.type,
                "due_date": r.due_date,
                "sms_status": r.sms_status or r.status,
                "status": r.status,
            }
            for r in reminders[:5]
        ],
        "alerts": alert_items,
        "recent_voice": recent_voice,
    }
