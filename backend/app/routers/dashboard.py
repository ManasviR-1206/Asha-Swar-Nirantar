"""GET /api/dashboard — aggregated stats, today's schedule, activity, reminders,
alerts and recent voice transcripts."""
import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Set

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import get_env
from app.auth import get_current_worker
from app.database import get_db
from app.data_scope import visible_beneficiaries, visible_households
from app.models import (
    ApiToken,
    AshaWorker,
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

# Local ASHA/beneficiary records and clearly separated synthetic demo dataset records.
LOCAL_BENEFICIARY_ORIGINS = ("registered", "asha_verified", "demo", "synthetic_demo")
LOCAL_HOUSEHOLD_ORIGINS = ("registered", "asha_verified", "demo", "synthetic_demo")

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


def _sse_worker(request: Request, db: Session) -> AshaWorker:
    """Authenticate the SSE stream via Bearer header or ?token= query param."""
    auth = request.headers.get("authorization") or ""
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = (request.query_params.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    row = db.query(ApiToken).filter(ApiToken.token == token).first()
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ttl_hours = float(get_env("TOKEN_TTL_HOURS", "168") or "168")
    if ttl_hours > 0 and row.created_at is not None:
        if datetime.utcnow() > row.created_at + timedelta(hours=ttl_hours):
            db.delete(row)
            db.commit()
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

    worker = db.query(AshaWorker).filter(AshaWorker.id == row.worker_id).first()
    if worker is None or not worker.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return worker


@router.get("/dashboard/events")
async def dashboard_events(request: Request, db: Session = Depends(get_db)):
    """Server-Sent Events stream for live dashboard updates (authenticated)."""
    _sse_worker(request, db)
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

    # ASHA Beneficiary Statistics: separated by data origin from DB (no record changes).
    # Public/research dataset observations/indicators are separate and never counted
    # as registered beneficiaries. Operational workflow lists/metrics below use the
    # visible local scope for normal/demo mode; separated counts reflect DB state.
    all_local_beneficiaries_visible = visible_beneficiaries(
        db.query(Beneficiary).filter(Beneficiary.data_origin.in_(LOCAL_BENEFICIARY_ORIGINS))
    ).all()
    beneficiaries = all_local_beneficiaries_visible  # visible operational workflow scope
    beneficiary_ids = {b.id for b in beneficiaries}
    names = {b.id: b.name for b in beneficiaries}

    all_local_households_visible = visible_households(
        db.query(Household).filter(Household.data_origin.in_(LOCAL_HOUSEHOLD_ORIGINS))
    ).all()
    households = all_local_households_visible
    household_labels = {
        h.id: (f"{h.village} household" if h.village else f"Household {h.qr_id}")
        for h in households
    }
    household_ids = {h.id for h in households}

    # DB-origin counts for separated reporting (consistent with stored records)
    registered_beneficiaries_count = (
        db.query(Beneficiary).filter(Beneficiary.data_origin == "registered").count()
    )
    synthetic_demo_beneficiaries_count = (
        db.query(Beneficiary).filter(Beneficiary.data_origin == "synthetic_demo").count()
    )
    local_beneficiaries_total_db = (
        db.query(Beneficiary)
        .filter(Beneficiary.data_origin.in_(LOCAL_BENEFICIARY_ORIGINS))
        .count()
    )
    registered_households_count = (
        db.query(Household).filter(Household.data_origin == "registered").count()
    )
    synthetic_demo_households_count = (
        db.query(Household).filter(Household.data_origin == "synthetic_demo").count()
    )
    local_households_total_db = (
        db.query(Household)
        .filter(Household.data_origin.in_(LOCAL_HOUSEHOLD_ORIGINS))
        .count()
    )

    todays_visits = (
        db.query(VisitRecord)
        .filter(VisitRecord.visit_date == today, VisitRecord.beneficiary_id.in_(beneficiary_ids) if beneficiary_ids else False)
        .count()
    ) if beneficiary_ids else 0
    todays_household_visits = (
        db.query(HouseholdVisit)
        .filter(HouseholdVisit.visit_date == today, HouseholdVisit.household_id.in_(household_ids) if household_ids else False)
        .count()
    ) if household_ids else 0
    scope_filter = (
        (FollowUp.beneficiary_id.in_(beneficiary_ids) if beneficiary_ids else FollowUp.beneficiary_id == -1)
        | (FollowUp.household_id.in_(household_ids) if household_ids else FollowUp.household_id == -1)
    )
    upcoming_rows = (
        db.query(FollowUp)
        .filter(FollowUp.status == "upcoming", scope_filter)
        .order_by(FollowUp.due_date.asc(), FollowUp.id.asc())
        .all()
    )
    due_rows = (
        db.query(FollowUp)
        .filter(FollowUp.status == "due", scope_filter)
        .order_by(FollowUp.due_date.asc(), FollowUp.id.asc())
        .all()
    )
    overdue_rows = (
        db.query(FollowUp)
        .filter(FollowUp.status == "overdue", scope_filter)
        .order_by(FollowUp.due_date.asc(), FollowUp.id.asc())
        .all()
    )
    completed_count = (
        db.query(FollowUp)
        .filter(FollowUp.status == "completed", scope_filter)
        .count()
    )
    upcoming = upcoming_rows
    overdue = len(overdue_rows)
    active_alert_statuses = ["open", "new", "acknowledged", "in_progress", "escalated"]
    open_alerts = (
        db.query(DangerAlert)
        .filter(
            DangerAlert.status.in_(active_alert_statuses),
            DangerAlert.beneficiary_id.in_(beneficiary_ids) if beneficiary_ids else DangerAlert.beneficiary_id == -1,
        )
        .all()
    )
    reminders = (
        db.query(SmsReminder)
        .filter(
            SmsReminder.status.in_(["scheduled", "overdue"]),
            SmsReminder.beneficiary_id.in_(beneficiary_ids) if beneficiary_ids else SmsReminder.beneficiary_id == -1,
        )
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

    schedule_source = due_rows + upcoming_rows
    schedule = [
        {
            "time": SLOT_TIMES[i % len(SLOT_TIMES)],
            "beneficiary_name": _subject_name(fu),
            "type": fu.type,
            "village": _subject_village(fu),
            "due_date": fu.due_date,
            "status": fu.status,
        }
        for i, fu in enumerate(schedule_source[:5])
    ]

    recent_visits = (
        db.query(VisitRecord)
        .filter(VisitRecord.beneficiary_id.in_(beneficiary_ids) if beneficiary_ids else VisitRecord.beneficiary_id == -1)
        .order_by(VisitRecord.visit_date.desc(), VisitRecord.id.desc())
        .limit(6)
        .all()
    )
    recent_hh_visits = (
        db.query(HouseholdVisit)
        .filter(HouseholdVisit.household_id.in_(household_ids) if household_ids else HouseholdVisit.household_id == -1)
        .order_by(HouseholdVisit.visit_date.desc(), HouseholdVisit.id.desc())
        .limit(3)
        .all()
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
        db.query(VoiceTranscript).order_by(VoiceTranscript.created_at.desc(), VoiceTranscript.id.desc()).limit(10).all()
    )
    for t in transcripts:
        visit = db.query(VisitRecord).filter(VisitRecord.id == t.visit_id).first() if t.visit_id else None
        if visit and beneficiary_ids and visit.beneficiary_id not in beneficiary_ids:
            continue
        if visit and not beneficiary_ids:
            continue
        recent_voice.append(
            {
                "beneficiary_name": names.get(visit.beneficiary_id) if visit else None,
                "date": visit.visit_date if visit else today,
                "language": t.language,
                "status": "processed",
            }
        )
        if len(recent_voice) >= 5:
            break

    alert_items = [
        {
            "id": a.id,
            "beneficiary_name": names.get(a.beneficiary_id, "Unknown"),
            "phrase": a.triggered_phrase,
            "message": a.message,
            "severity": a.severity,
            "status": ("new" if (a.status or "").lower() == "open" else (a.status or "").lower().replace("-", "_")),
            "created_at": a.created_at,
        }
        for a in sorted(open_alerts, key=lambda x: (x.created_at or datetime.min, x.id), reverse=True)[:5]
    ]

    # Research/public dataset counts (separate from operational records)
    research_observations = 0
    research_aggregate_indicators = 0
    research_imports = 0
    try:
        research_imports = db.execute(text("select count(*) c from dataset_imports")).scalar() or 0 if db.bind and True else 0
    except Exception:
        research_imports = 0
    try:
        research_observations = db.execute(text("select count(*) c from public_dataset_observations")).scalar() or 0
        research_aggregate_indicators = db.execute(text("select count(*) c from public_dataset_observations where record_type='aggregate'")).scalar() or 0
    except Exception:
        research_observations = 0
        research_aggregate_indicators = 0

    asha_stats = {
        # Visible in current mode (normal excludes synthetic demo; explicit demo mode includes it).
        "total_beneficiaries": len(all_local_beneficiaries_visible),
        "total_households": len(all_local_households_visible),
        "todays_visits": todays_visits + todays_household_visits,
        "upcoming_followups": len(upcoming),
        "due_followups": len(due_rows),
        "overdue_followups": overdue,
        "completed_followups": completed_count,
        "active_alerts": len(open_alerts),
    }
    return {
        "stats": asha_stats,
        "asha_beneficiary_statistics": {
            **asha_stats,
            "label": "ASHA Beneficiary Statistics",
            "scope": "Operational registered ASHA records are counted separately from synthetic demo records and public research datasets (counts reflect DB by origin).",
            "registered_beneficiaries": int(registered_beneficiaries_count or 0),
            "operational_households": int(registered_households_count or 0),
            "synthetic_demo_beneficiaries": int(synthetic_demo_beneficiaries_count or 0),
            "synthetic_demo_households": int(synthetic_demo_households_count or 0),
            "synthetic_demo_records": int(synthetic_demo_beneficiaries_count or 0) + int(synthetic_demo_households_count or 0),
            "local_beneficiaries_including_synthetic_demo": int(local_beneficiaries_total_db or 0),
            "local_households_including_synthetic_demo": int(local_households_total_db or 0),
            "visible_local_beneficiaries": len(all_local_beneficiaries_visible),
            "visible_local_households": len(all_local_households_visible),
        },
        "research_data_statistics": {
            "label": "Public Research Data (separate)",
            "scope": "Recovered research observations/indicators. Not ASHA beneficiary or household records; never included in registered counts.",
            "imports": int(research_imports or 0),
            "observations": int(research_observations or 0),
            "aggregate_indicators": int(research_aggregate_indicators or 0),
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


@router.get("/dashboard/modules")
def dashboard_modules(db: Session = Depends(get_db), _worker=Depends(get_current_worker)):
    """Counts for notification and voice-visit modules.

    One request instead of multiple, so the dashboard renders in a single
    round-trip.
    """
    from app.models import (
        ExtractedVisit,
        PdfReport,
        SmsNotification,
        VoiceRecordingSession,
    )
    from app.services import notifications as notify
    from app.services.textbee import textbee_enabled

    # ---- notifications (SMS only) ----
    sms_rows = db.query(SmsNotification).all()
    pdf_count = db.query(PdfReport).count()

    # ---- voice visits (local ASHA/beneficiary records only) ----
    local_beneficiaries = visible_beneficiaries(
        db.query(Beneficiary).filter(Beneficiary.data_origin.in_(LOCAL_BENEFICIARY_ORIGINS))
    ).all()
    local_ids = {b.id for b in local_beneficiaries}
    local_names = {b.id: b.name for b in local_beneficiaries}
    voice_visits = (
        db.query(VisitRecord)
        .filter(VisitRecord.source == "voice", VisitRecord.beneficiary_id.in_(local_ids) if local_ids else VisitRecord.beneficiary_id == -1)
        .all()
    )
    all_visits = (
        db.query(VisitRecord)
        .filter(VisitRecord.beneficiary_id.in_(local_ids) if local_ids else VisitRecord.beneficiary_id == -1)
        .all()
    )
    visited_ids = {v.beneficiary_id for v in all_visits}
    pending_identity = (
        db.query(ExtractedVisit)
        .filter(
            ExtractedVisit.status == "pending",
            ExtractedVisit.identity_status.in_(("ambiguous", "unresolved", "new")),
        )
        .count()
    )
    sessions = db.query(VoiceRecordingSession).all()
    session_visits = db.query(ExtractedVisit).all()

    # Recent voice-visit activity for the widget list.
    recent = (
        db.query(VisitRecord)
        .filter(VisitRecord.source == "voice", VisitRecord.beneficiary_id.in_(local_ids) if local_ids else VisitRecord.beneficiary_id == -1)
        .order_by(VisitRecord.visit_date.desc(), VisitRecord.id.desc())
        .limit(6)
        .all()
    )
    names = {bid: local_names.get(bid, "Unknown") for bid in visited_ids} if visited_ids else {}

    local_household_ids = {
        h.id for h in visible_households(
            db.query(Household).filter(Household.data_origin.in_(LOCAL_HOUSEHOLD_ORIGINS))
        ).all()
    }
    upcoming_followups_count = (
        db.query(FollowUp)
        .filter(
            FollowUp.status.in_(["upcoming", "due"]),
            (
                (FollowUp.beneficiary_id.in_(local_ids) if local_ids else FollowUp.beneficiary_id == -1)
                | (FollowUp.household_id.in_(local_household_ids) if local_household_ids else FollowUp.household_id == -1)
            ),
        )
        .count()
    )
    # Research/public datasets (separate; never part of registered operational counts)
    research_imports = 0
    research_observations = 0
    research_aggregate_indicators = 0
    research_by_key = {}
    try:
        research_imports = db.execute(text("select count(*) c from dataset_imports")).scalar() or 0
        research_observations = db.execute(text("select count(*) c from public_dataset_observations")).scalar() or 0
        research_aggregate_indicators = db.execute(text("select count(*) c from public_dataset_observations where record_type='aggregate'")).scalar() or 0
        rows = db.execute(text("select dataset_key, count(*) c from public_dataset_observations group by dataset_key")).fetchall()
        research_by_key = {r[0]: int(r[1]) for r in rows}
    except Exception:
        pass

    # DB-origin counts for separated reporting (consistent with stored records)
    registered_beneficiaries_count = db.query(Beneficiary).filter(Beneficiary.data_origin == "registered").count()
    synthetic_demo_beneficiaries_count = db.query(Beneficiary).filter(Beneficiary.data_origin == "synthetic_demo").count()
    registered_households_count = db.query(Household).filter(Household.data_origin == "registered").count()
    synthetic_demo_households_count = db.query(Household).filter(Household.data_origin == "synthetic_demo").count()

    return {
        "notifications": {
            "sms_total": len(sms_rows),
            "sms_demo": sum(1 for r in sms_rows if r.is_demo),
            "sms_real": sum(1 for r in sms_rows if not r.is_demo),
            "pending": sum(1 for r in sms_rows if r.status == "pending"),
            "failed": sum(1 for r in sms_rows if r.status == "failed"),
            "pdf_reports": pdf_count,
            "upcoming_followups": upcoming_followups_count,
            "sms_provider_configured": notify.sms_provider_configured(),
            "sms_enabled": textbee_enabled(),
            "sms_provider": notify.sms_provider_name(),
        },
        "voice_visits": {
            "visits_saved": len(voice_visits),
            "total_visits": len(all_visits),
            "beneficiaries_visited": len(visited_ids),
            "pending_identity": pending_identity,
            "sessions": len(sessions),
            "extracted_visits": len(session_visits),
            "recent": [
                {
                    "id": v.id,
                    "beneficiary_id": v.beneficiary_id,
                    "beneficiary_name": names.get(v.beneficiary_id, "Unknown"),
                    "date": v.visit_date,
                    "category": v.category,
                }
                for v in recent
            ],
        },
        "operational_counts": {
            "registered_beneficiaries": int(registered_beneficiaries_count or 0),
            "operational_households": int(registered_households_count or 0),
            "synthetic_demo_beneficiaries": int(synthetic_demo_beneficiaries_count or 0),
            "synthetic_demo_households": int(synthetic_demo_households_count or 0),
            "synthetic_demo_records": int(synthetic_demo_beneficiaries_count or 0) + int(synthetic_demo_households_count or 0),
        },
        "research_data": {
            "imports": int(research_imports or 0),
            "observations": int(research_observations or 0),
            "aggregate_indicators": int(research_aggregate_indicators or 0),
            "by_dataset_key": research_by_key,
            "badge": "PUBLIC RESEARCH DATA – NOT AN ASHA BENEFICIARY RECORD",
        },
    }
