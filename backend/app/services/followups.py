"""Follow-up task service: lifecycle, authorization, history, and generation helpers."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import AshaWorker, Beneficiary, FollowUp, FollowUpHistory, Household

VALID_STATUSES = {"upcoming", "due", "overdue", "completed", "cancelled"}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
ACTIVE_STATUSES = {"upcoming", "due", "overdue"}


def normalize_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in ("done", "completed"):
        return "completed"
    if s in ("cancelled", "canceled"):
        return "cancelled"
    if s in ("missed",):
        return "overdue"
    if s in ("rescheduled",):
        return "upcoming"
    if s == "due":
        return "due"
    if s == "overdue":
        return "overdue"
    if s == "upcoming":
        return "upcoming"
    return "upcoming"


def status_for_due(due: date | None, today: date | None = None) -> str:
    today = today or date.today()
    if due is None:
        return "upcoming"
    if due < today:
        return "overdue"
    if due == today:
        return "due"
    return "upcoming"


def is_admin(worker: AshaWorker | None) -> bool:
    return bool(worker and getattr(worker, "role", "asha") == "admin")


def _beneficiary_for_followup(db: Session, fu: FollowUp) -> Beneficiary | None:
    if fu.beneficiary_id:
        return db.query(Beneficiary).filter(Beneficiary.id == fu.beneficiary_id).first()
    return None


def can_access_followup(db: Session, worker: AshaWorker, fu: FollowUp) -> bool:
    if is_admin(worker):
        return True
    if fu.assigned_worker_id == worker.id:
        return True
    ben = _beneficiary_for_followup(db, fu)
    if ben and ben.assigned_worker_id == worker.id:
        return True
    # Household follow-ups without explicit assignment: allow if worker created/assigned context unavailable
    # but keep access conservative for explicitly assigned-to-other records.
    if fu.assigned_worker_id and fu.assigned_worker_id != worker.id:
        return False
    if fu.household_id and not fu.assigned_worker_id:
        # household has no explicit owner field; allow authenticated workers (shared team view) unless assigned elsewhere
        return True
    if not fu.assigned_worker_id and not ben:
        return True
    return False


def require_access(db: Session, worker: AshaWorker, fu: FollowUp) -> None:
    if not can_access_followup(db, worker, fu):
        raise HTTPException(status_code=403, detail="Not authorized to access this follow-up")


def add_history(
    db: Session,
    fu: FollowUp,
    action: str,
    from_status: str = "",
    to_status: str = "",
    note: str = "",
    actor: AshaWorker | None = None,
) -> FollowUpHistory:
    h = FollowUpHistory(
        followup_id=fu.id,
        action=action,
        from_status=from_status or "",
        to_status=to_status or (fu.status or ""),
        note=(note or "").strip(),
        actor_id=actor.id if actor else None,
        actor_label=(actor.name if actor else "system"),
        changed_at=datetime.utcnow(),
    )
    db.add(h)
    return h


def subject_label(db: Session, fu: FollowUp, ben_cache: dict[int, Beneficiary] | None = None, hh_cache: dict[int, Household] | None = None) -> tuple[str | None, str | None]:
    ben_name = None
    hh_label = None
    if fu.beneficiary_id:
        ben = (ben_cache or {}).get(fu.beneficiary_id) or db.query(Beneficiary).filter(Beneficiary.id == fu.beneficiary_id).first()
        if ben:
            if ben_cache is not None:
                ben_cache[fu.beneficiary_id] = ben
            ben_name = ben.name
            if ben.household_id and not fu.household_id:
                hh = (hh_cache or {}).get(ben.household_id) or db.query(Household).filter(Household.id == ben.household_id).first()
                if hh:
                    if hh_cache is not None:
                        hh_cache[hh.id] = hh
                    hh_label = f"{hh.village} household ({hh.qr_id})" if hh.village else f"Household {hh.qr_id}"
    if fu.household_id:
        hh = (hh_cache or {}).get(fu.household_id) or db.query(Household).filter(Household.id == fu.household_id).first()
        if hh:
            if hh_cache is not None:
                hh_cache[fu.household_id] = hh
            hh_label = f"{hh.village} household ({hh.qr_id})" if hh.village else f"Household {hh.qr_id}"
    return ben_name, hh_label


def overdue_days(fu: FollowUp, today: date | None = None) -> int:
    today = today or date.today()
    if not fu.due_date:
        return 0
    if fu.status in ("completed", "cancelled"):
        return 0
    if fu.due_date >= today:
        return 0
    return (today - fu.due_date).days


def followup_to_dict(db: Session, fu: FollowUp, ben_cache=None, hh_cache=None, worker_cache=None) -> dict[str, Any]:
    ben_name, hh_label = subject_label(db, fu, ben_cache, hh_cache)
    worker_name = None
    if fu.assigned_worker_id:
        if worker_cache is not None and fu.assigned_worker_id in worker_cache:
            worker_name = worker_cache[fu.assigned_worker_id]
        else:
            w = db.query(AshaWorker).filter(AshaWorker.id == fu.assigned_worker_id).first()
            worker_name = w.name if w else None
            if worker_cache is not None and worker_name:
                worker_cache[fu.assigned_worker_id] = worker_name
    cat = (getattr(fu, "category", "") or fu.type or "")
    desc = getattr(fu, "description", "") or ""
    comp = getattr(fu, "completion_notes", "") or ""
    canc = getattr(fu, "cancellation_reason", "") or ""
    return {
        "id": fu.id,
        "beneficiary_id": fu.beneficiary_id,
        "beneficiary_name": ben_name,
        "household_id": fu.household_id,
        "household_label": hh_label,
        "visit_id": fu.visit_id,
        "type": fu.type or "",
        "category": cat,
        "reason": fu.reason or "",
        "description": desc,
        "recommended_action": fu.recommended_action or "",
        "due_date": fu.due_date,
        "priority": fu.priority or "normal",
        "assigned_worker_id": fu.assigned_worker_id,
        "assigned_worker_name": worker_name,
        "status": fu.status or "upcoming",
        "created_at": fu.created_at,
        "updated_at": fu.updated_at,
        "completed_at": fu.completed_at,
        "cancelled_at": getattr(fu, "cancelled_at", None),
        "completion_notes": comp or fu.notes or "",
        "cancellation_reason": canc,
        "notes": fu.notes or "",
        "source_type": getattr(fu, "source_type", "") or "",
        "source_id": getattr(fu, "source_id", None),
        "source_ref": getattr(fu, "source_ref", "") or "",
        "rescheduled_from": fu.rescheduled_from,
        "overdue_days": overdue_days(fu),
    }


def ensure_history_for_legacy(db: Session, fu: FollowUp) -> None:
    # If no history exists (legacy rows), create an initial created event.
    exists = db.query(FollowUpHistory.id).filter(FollowUpHistory.followup_id == fu.id).first()
    if exists:
        return
    db.add(
        FollowUpHistory(
            followup_id=fu.id,
            action="created",
            from_status="",
            to_status=fu.status or "upcoming",
            note="Imported/legacy follow-up record.",
            actor_label="system",
            changed_at=fu.created_at or datetime.utcnow(),
        )
    )


def refresh_followup_statuses(db: Session, actor: AshaWorker | None = None) -> int:
    today = date.today()
    changed = 0
    rows = db.query(FollowUp).filter(FollowUp.status.in_(["upcoming", "due", "overdue", "rescheduled", "missed", "done", "completed", "cancelled", "canceled"])).all()
    for fu in rows:
        old = normalize_status(fu.status)
        # normalize legacy terminal/values first
        if old in ("completed", "cancelled"):
            if fu.status != old:
                fu.status = old
                fu.updated_at = datetime.utcnow()
                changed += 1
            ensure_history_for_legacy(db, fu)
            continue
        new = status_for_due(fu.due_date, today)
        if fu.status != new:
            fu.status = new
            fu.updated_at = datetime.utcnow()
            ensure_history_for_legacy(db, fu)
            add_history(db, fu, "status_changed", from_status=old, to_status=new, note="Automatic due-date status refresh.", actor=None)
            changed += 1
        else:
            # ensure legacy normalized in place
            if fu.status in ("missed", "rescheduled"):
                fu.status = new
                fu.updated_at = datetime.utcnow()
                changed += 1
        if not getattr(fu, "category", "") and fu.type:
            fu.category = fu.type
        ensure_history_for_legacy(db, fu)
    if changed:
        db.commit()
    else:
        # commit legacy history normalization if any added
        db.commit()
    return changed


def apply_filters(query, args: dict[str, Any]):
    if args.get("beneficiary_id"):
        query = query.filter(FollowUp.beneficiary_id == int(args["beneficiary_id"]))
    if args.get("household_id"):
        query = query.filter(FollowUp.household_id == int(args["household_id"]))
    if args.get("assigned_worker_id") or args.get("worker_id"):
        wid = int(args.get("assigned_worker_id") or args.get("worker_id"))
        query = query.filter(FollowUp.assigned_worker_id == wid)
    if args.get("status"):
        statuses = [normalize_status(s) for s in str(args["status"]).split(",") if s.strip()]
        query = query.filter(FollowUp.status.in_(statuses))
    if args.get("priority"):
        prs = [s.strip().lower() for s in str(args["priority"]).split(",") if s.strip()]
        query = query.filter(FollowUp.priority.in_(prs))
    if args.get("category") or args.get("type"):
        val = str(args.get("category") or args.get("type")).strip().lower()
        cats = [s.strip().lower() for s in val.split(",") if s.strip()]
        query = query.filter(or_(FollowUp.category.in_(cats), FollowUp.type.in_(cats)))
    if args.get("due_from"):
        try:
            query = query.filter(FollowUp.due_date >= date.fromisoformat(str(args["due_from"])[:10]))
        except Exception:
            pass
    if args.get("due_to"):
        try:
            query = query.filter(FollowUp.due_date <= date.fromisoformat(str(args["due_to"])[:10]))
        except Exception:
            pass
    if args.get("q"):
        term = f"%{str(args['q']).strip()}%"
        query = query.outerjoin(Beneficiary, FollowUp.beneficiary_id == Beneficiary.id).outerjoin(Household, FollowUp.household_id == Household.id)
        query = query.filter(or_(
            FollowUp.reason.ilike(term),
            FollowUp.description.ilike(term),
            FollowUp.recommended_action.ilike(term),
            FollowUp.notes.ilike(term),
            FollowUp.type.ilike(term),
            FollowUp.category.ilike(term),
            Beneficiary.name.ilike(term),
            Household.village.ilike(term),
            Household.qr_id.ilike(term),
        ))
    return query


def upsert_generated_followup(
    db: Session,
    *,
    dedup_key: str,
    beneficiary_id: int | None = None,
    household_id: int | None = None,
    visit_id: int | None = None,
    type_: str,
    category: str | None = None,
    reason: str,
    description: str = "",
    recommended_action: str = "",
    due_date: date | None,
    priority: str = "normal",
    source_type: str = "rule",
    source_id: int | None = None,
    source_ref: str = "",
    assigned_worker_id: int | None = None,
) -> FollowUp | None:
    if not dedup_key or not due_date:
        return None
    existing = db.query(FollowUp).filter(FollowUp.dedup_key == dedup_key).order_by(FollowUp.id.desc()).first()
    if existing:
        if existing.status in ("completed", "cancelled"):
            return existing
        old_status = normalize_status(existing.status)
        # Update system-managed schedule fields without overwriting user notes/completion/cancellation
        existing.due_date = due_date
        existing.type = type_ or existing.type
        existing.category = (category or type_ or existing.category or "")
        existing.reason = reason or existing.reason
        existing.description = description or existing.description
        existing.recommended_action = recommended_action or existing.recommended_action
        existing.priority = priority or existing.priority or "normal"
        if not existing.assigned_worker_id and assigned_worker_id:
            existing.assigned_worker_id = assigned_worker_id
        if visit_id and not existing.visit_id:
            existing.visit_id = visit_id
        existing.source_type = source_type or existing.source_type
        existing.source_id = source_id if source_id is not None else existing.source_id
        existing.source_ref = source_ref or existing.source_ref
        new_status = status_for_due(existing.due_date)
        if existing.status != new_status:
            existing.status = new_status
            add_history(db, existing, "status_changed", from_status=old_status, to_status=new_status, note="System schedule refresh.", actor=None)
        existing.updated_at = datetime.utcnow()
        ensure_history_for_legacy(db, existing)
        return existing

    fu = FollowUp(
        beneficiary_id=beneficiary_id,
        household_id=household_id,
        visit_id=visit_id,
        type=type_ or "general",
        category=(category or type_ or "general"),
        due_date=due_date,
        status=status_for_due(due_date),
        priority=priority or "normal",
        reason=reason or "",
        description=description or "",
        recommended_action=recommended_action or "",
        assigned_worker_id=assigned_worker_id,
        notes="",
        completion_notes="",
        cancellation_reason="",
        source_type=source_type or "rule",
        source_id=source_id,
        source_ref=source_ref or "",
        dedup_key=dedup_key,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(fu)
    db.flush()
    add_history(db, fu, "created", from_status="", to_status=fu.status, note="Auto-generated from approved rule/record.", actor=None)
    return fu
