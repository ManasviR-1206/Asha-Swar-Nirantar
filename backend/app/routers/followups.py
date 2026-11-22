"""Follow-up task management APIs for Pulse Drift.

Persisted follow-up tasks with lifecycle, history, filtering, and worker authorization.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.data_scope import visible_beneficiaries, visible_followups, visible_households
from app.database import get_db
from app.models import AshaWorker, Beneficiary, FollowUp, FollowUpHistory, Household, VisitRecord
from app.schemas import (
    FollowUpCreate,
    FollowUpHistoryResponse,
    FollowUpListResponse,
    FollowUpOut,
    FollowUpStatusAction,
    FollowUpUpdate,
)
from app.services.followups import (
    VALID_PRIORITIES,
    add_history,
    apply_filters,
    ensure_history_for_legacy,
    followup_to_dict,
    is_admin,
    normalize_status,
    refresh_followup_statuses,
    require_access,
    status_for_due,
)

router = APIRouter(prefix="/api/follow-ups", tags=["follow-ups"], dependencies=[Depends(get_current_worker)])


def _validate_refs(db: Session, payload, existing: FollowUp | None = None):
    ben_id = payload.beneficiary_id if payload.beneficiary_id is not None else (existing.beneficiary_id if existing else None)
    hh_id = payload.household_id if payload.household_id is not None else (existing.household_id if existing else None)
    visit_id = payload.visit_id if payload.visit_id is not None else (existing.visit_id if existing else None)
    worker_id = payload.assigned_worker_id if payload.assigned_worker_id is not None else (existing.assigned_worker_id if existing else None)
    if ben_id is not None and visible_beneficiaries(db.query(Beneficiary.id)).filter(Beneficiary.id == ben_id).first() is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if hh_id is not None and visible_households(db.query(Household.id)).filter(Household.id == hh_id).first() is None:
        raise HTTPException(status_code=404, detail="Household not found")
    if visit_id is not None and db.query(VisitRecord.id).filter(VisitRecord.id == visit_id).first() is None:
        raise HTTPException(status_code=404, detail="Visit record not found")
    if worker_id is not None and db.query(AshaWorker.id).filter(AshaWorker.id == worker_id).first() is None:
        raise HTTPException(status_code=404, detail="Assigned worker not found")
    if ben_id is None and hh_id is None:
        raise HTTPException(status_code=400, detail="Either beneficiary_id or household_id is required")


def _get_or_404(db: Session, followup_id: int) -> FollowUp:
    fu = visible_followups(db.query(FollowUp), db).filter(FollowUp.id == followup_id).first()
    if fu is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return fu


@router.get("", response_model=FollowUpListResponse)
def list_followups(
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = "",
    category: str = "",
    type: str = "",
    priority: str = "",
    beneficiary_id: int | None = None,
    household_id: int | None = None,
    assigned_worker_id: int | None = None,
    worker_id: int | None = None,
    due_from: str = "",
    due_to: str = "",
    q: str = "",
):
    refresh_followup_statuses(db)
    args = {
        "status": status, "category": category, "type": type, "priority": priority,
        "beneficiary_id": beneficiary_id, "household_id": household_id,
        "assigned_worker_id": assigned_worker_id, "worker_id": worker_id,
        "due_from": due_from, "due_to": due_to, "q": q,
    }
    base = apply_filters(visible_followups(db.query(FollowUp), db), args)
    if not is_admin(worker):
        # Restrict to follow-ups assigned to worker or for beneficiaries assigned to worker; household tasks without other assignment visible to team
        base = base.outerjoin(Beneficiary, FollowUp.beneficiary_id == Beneficiary.id)
        base = base.filter(
            (FollowUp.assigned_worker_id == worker.id)
            | (Beneficiary.assigned_worker_id == worker.id)
            | ((FollowUp.assigned_worker_id.is_(None)) & (FollowUp.household_id.isnot(None)))
            | ((FollowUp.assigned_worker_id.is_(None)) & (FollowUp.beneficiary_id.is_(None)))
        )

    # Counts across all statuses for current filter context (except status filter)
    count_args = dict(args)
    count_args.pop("status", None)
    count_base = apply_filters(visible_followups(db.query(FollowUp), db), count_args)
    if not is_admin(worker):
        count_base = count_base.outerjoin(Beneficiary, FollowUp.beneficiary_id == Beneficiary.id)
        count_base = count_base.filter(
            (FollowUp.assigned_worker_id == worker.id)
            | (Beneficiary.assigned_worker_id == worker.id)
            | ((FollowUp.assigned_worker_id.is_(None)) & (FollowUp.household_id.isnot(None)))
            | ((FollowUp.assigned_worker_id.is_(None)) & (FollowUp.beneficiary_id.is_(None)))
        )
    counts = {"upcoming": 0, "due": 0, "overdue": 0, "completed": 0, "cancelled": 0}
    for st, cnt in count_base.with_entities(FollowUp.status, func.count(FollowUp.id)).group_by(FollowUp.status).all():
        norm = normalize_status(st)
        if norm in counts:
            counts[norm] += int(cnt)

    total = base.with_entities(func.count(func.distinct(FollowUp.id))).scalar() or 0
    rows = (
        base.order_by(
            # active before terminal, overdue first, then due, upcoming, by due date
            FollowUp.status.in_(["overdue"]).desc(),
            FollowUp.status.in_(["due"]).desc(),
            FollowUp.status.in_(["upcoming"]).desc(),
            FollowUp.due_date.asc().nullslast(),
            FollowUp.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # de-dup in case joins created duplicates
    seen = set()
    uniq = []
    for r in rows:
        if r.id in seen:
            continue
        seen.add(r.id)
        uniq.append(r)
    ben_cache, hh_cache, worker_cache = {}, {}, {}
    items = [followup_to_dict(db, fu, ben_cache, hh_cache, worker_cache) for fu in uniq]
    return {"items": items, "total": int(total), "page": page, "page_size": page_size, "counts": counts}


@router.post("", response_model=FollowUpOut)
def create_followup(payload: FollowUpCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    _validate_refs(db, payload)
    if payload.priority and payload.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    status = normalize_status(payload.status)
    if status not in {"upcoming", "due", "overdue"}:
        status = status_for_due(payload.due_date)
    cat = (payload.category or payload.type or "general").strip().lower()
    assigned = payload.assigned_worker_id
    if assigned is None and payload.beneficiary_id:
        ben = visible_beneficiaries(db.query(Beneficiary)).filter(Beneficiary.id == payload.beneficiary_id).first()
        if ben and ben.assigned_worker_id:
            assigned = ben.assigned_worker_id
    fu = FollowUp(
        beneficiary_id=payload.beneficiary_id,
        household_id=payload.household_id,
        visit_id=payload.visit_id,
        type=(payload.type or "general").strip().lower(),
        category=cat,
        due_date=payload.due_date,
        status=status,
        priority=(payload.priority or "normal"),
        reason=(payload.reason or "").strip(),
        description=(payload.description or "").strip(),
        recommended_action=(payload.recommended_action or "").strip(),
        assigned_worker_id=assigned,
        notes=(payload.notes or "").strip(),
        completion_notes="",
        cancellation_reason="",
        source_type=(payload.source_type or "manual"),
        source_id=payload.source_id,
        source_ref=(payload.source_ref or "").strip(),
        dedup_key="",  # manual tasks are not auto-deduped by rule key
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(fu)
    db.flush()
    add_history(db, fu, "created", from_status="", to_status=fu.status, note="Manually created.", actor=worker)
    db.commit()
    db.refresh(fu)
    return followup_to_dict(db, fu)


@router.get("/{followup_id}", response_model=FollowUpOut)
def get_followup(followup_id: int, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    refresh_followup_statuses(db)
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    ensure_history_for_legacy(db, fu)
    db.commit()
    return followup_to_dict(db, fu)


@router.patch("/{followup_id}", response_model=FollowUpOut)
def update_followup(followup_id: int, payload: FollowUpUpdate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    _validate_refs(db, payload, existing=fu)
    old_status = normalize_status(fu.status)
    for field in ("type", "category", "reason", "description", "recommended_action", "notes", "source_type", "source_ref"):
        val = getattr(payload, field)
        if val is not None:
            setattr(fu, field, val.strip() if isinstance(val, str) else val)
    for field in ("beneficiary_id", "household_id", "visit_id", "assigned_worker_id", "source_id"):
        val = getattr(payload, field)
        if val is not None:
            setattr(fu, field, val)
    if payload.priority is not None:
        if payload.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority")
        fu.priority = payload.priority
    if payload.due_date is not None:
        fu.due_date = payload.due_date
    # status handling: only allow direct set to active states here; terminal via actions
    if payload.status is not None:
        st = normalize_status(payload.status)
        if st in ("completed", "cancelled"):
            raise HTTPException(status_code=400, detail="Use complete/cancel actions for terminal statuses")
        fu.status = status_for_due(fu.due_date) if fu.due_date else st
    elif fu.status in ("upcoming", "due", "overdue"):
        fu.status = status_for_due(fu.due_date)
    fu.updated_at = datetime.utcnow()
    if normalize_status(fu.status) != old_status:
        add_history(db, fu, "status_changed", from_status=old_status, to_status=fu.status, note="Updated.", actor=worker)
    else:
        add_history(db, fu, "updated", from_status=old_status, to_status=fu.status, note="Follow-up updated.", actor=worker)
    db.commit()
    db.refresh(fu)
    return followup_to_dict(db, fu)


@router.post("/{followup_id}/complete", response_model=FollowUpOut)
def complete_followup(followup_id: int, payload: FollowUpStatusAction | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    old_status = normalize_status(fu.status)
    note = (payload.notes or payload.note) if payload else ""
    fu.status = "completed"
    fu.completed_at = datetime.utcnow()
    fu.cancelled_at = None
    fu.cancellation_reason = ""
    fu.completion_notes = (note or "").strip()
    if note:
        fu.notes = (note or "").strip()
    fu.updated_at = datetime.utcnow()
    add_history(db, fu, "completed", from_status=old_status, to_status="completed", note=note or "Marked completed.", actor=worker)
    db.commit()
    db.refresh(fu)
    return followup_to_dict(db, fu)


@router.post("/{followup_id}/cancel", response_model=FollowUpOut)
def cancel_followup(followup_id: int, payload: FollowUpStatusAction | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    old_status = normalize_status(fu.status)
    reason = ((payload.reason or payload.notes or payload.note) if payload else "").strip()
    fu.status = "cancelled"
    fu.cancelled_at = datetime.utcnow()
    fu.cancellation_reason = reason
    fu.updated_at = datetime.utcnow()
    add_history(db, fu, "cancelled", from_status=old_status, to_status="cancelled", note=reason or "Cancelled.", actor=worker)
    db.commit()
    db.refresh(fu)
    return followup_to_dict(db, fu)


@router.post("/{followup_id}/reschedule", response_model=FollowUpOut)
def reschedule_followup(followup_id: int, payload: FollowUpStatusAction, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    if payload.due_date is None:
        raise HTTPException(status_code=400, detail="due_date is required")
    old_status = normalize_status(fu.status)
    old_due = fu.due_date
    fu.rescheduled_from = old_due
    fu.due_date = payload.due_date
    fu.status = status_for_due(fu.due_date)
    note = (payload.notes or payload.note or "").strip()
    if note:
        fu.notes = note
    fu.completed_at = None
    fu.completion_notes = ""
    fu.cancelled_at = None
    fu.cancellation_reason = ""
    fu.updated_at = datetime.utcnow()
    add_history(db, fu, "rescheduled", from_status=old_status, to_status=fu.status, note=f"Rescheduled from {old_due} to {fu.due_date}. {note}".strip(), actor=worker)
    db.commit()
    db.refresh(fu)
    return followup_to_dict(db, fu)


@router.post("/{followup_id}/assign", response_model=FollowUpOut)
@router.post("/{followup_id}/reassign", response_model=FollowUpOut)
def assign_followup(followup_id: int, payload: FollowUpStatusAction, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    if payload.assigned_worker_id is None:
        raise HTTPException(status_code=400, detail="assigned_worker_id is required")
    if db.query(AshaWorker.id).filter(AshaWorker.id == payload.assigned_worker_id).first() is None:
        raise HTTPException(status_code=404, detail="Assigned worker not found")
    old_worker = fu.assigned_worker_id
    fu.assigned_worker_id = payload.assigned_worker_id
    fu.updated_at = datetime.utcnow()
    note = (payload.notes or payload.note or "").strip()
    add_history(db, fu, "assigned", from_status=normalize_status(fu.status), to_status=fu.status, note=f"Assigned worker {old_worker} -> {fu.assigned_worker_id}. {note}".strip(), actor=worker)
    db.commit()
    db.refresh(fu)
    return followup_to_dict(db, fu)


@router.get("/{followup_id}/history", response_model=FollowUpHistoryResponse)
def followup_history(followup_id: int, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    fu = _get_or_404(db, followup_id)
    require_access(db, worker, fu)
    ensure_history_for_legacy(db, fu)
    db.commit()
    rows = (
        db.query(FollowUpHistory)
        .filter(FollowUpHistory.followup_id == fu.id)
        .order_by(FollowUpHistory.changed_at.asc(), FollowUpHistory.id.asc())
        .all()
    )
    return {
        "followup_id": fu.id,
        "history": [
            {
                "id": h.id,
                "followup_id": h.followup_id,
                "action": h.action,
                "from_status": h.from_status or "",
                "to_status": h.to_status or "",
                "note": h.note or "",
                "actor_id": h.actor_id,
                "actor_label": h.actor_label or "system",
                "changed_at": h.changed_at,
            }
            for h in rows
        ],
    }
