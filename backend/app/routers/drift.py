"""GET /api/drift — Pulse Drift follow-ups (persisted task management).

Returns active persisted follow-up tasks (upcoming/due/overdue) after refreshing
statuses and syncing rule/record-generated follow-ups idempotently.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.data_scope import visible_followups
from app.models import Beneficiary, FollowUp, Household
from app.rules import sync_generated_followups
from app.schemas import DriftResponse
from app.services.followups import followup_to_dict, refresh_followup_statuses

router = APIRouter(prefix="/api", tags=["drift"], dependencies=[Depends(get_current_worker)])


@router.get("/drift", response_model=DriftResponse)
def drift(db: Session = Depends(get_db)):
    refresh_followup_statuses(db)
    try:
        sync_generated_followups(db)
        db.commit()
    except Exception:
        db.rollback()
    rows = (
        visible_followups(db.query(FollowUp), db)
        .filter(FollowUp.status.in_(["upcoming", "due", "overdue"]))
        .order_by(FollowUp.status.in_(["overdue"]).desc(), FollowUp.due_date.asc().nullslast(), FollowUp.id.desc())
        .all()
    )
    ben_cache, hh_cache, worker_cache = {}, {}, {}
    items = []
    for fu in rows:
        d = followup_to_dict(db, fu, ben_cache, hh_cache, worker_cache)
        name = d.get("beneficiary_name") or d.get("household_label") or "Follow-up"
        category = d.get("category") or d.get("type") or "general"
        # Compatibility fields expected by older UI/consumers
        items.append(
            {
                "beneficiary_id": d.get("beneficiary_id"),
                "household_id": d.get("household_id"),
                "name": name,
                "category": category,
                "issue": d.get("reason") or d.get("description") or "Follow-up required",
                "issue_code": "",
                "issue_params": {},
                "issue_action_code": "",
                "due_date": d.get("due_date"),
                "overdue_days": d.get("overdue_days") or 0,
                "recommended_action": d.get("recommended_action") or "",
                # extra fields for newer consumers
                "id": d.get("id"),
                "status": d.get("status"),
                "priority": d.get("priority"),
                "assigned_worker_id": d.get("assigned_worker_id"),
                "assigned_worker_name": d.get("assigned_worker_name"),
            }
        )
    return {"items": items}
