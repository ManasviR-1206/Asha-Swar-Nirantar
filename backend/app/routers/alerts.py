"""Danger alert endpoints: list, summary aggregates, detail/history, lifecycle actions.

Design goals:
- Return factual, DB-backed alert data and aggregates (no hardcoded counts, no silent empty-on-error).
- Apply object-level/worker scope authorization consistently.
- Support rule-based danger-sign alerts linked to actual visit/observation records for
  registered and synthetic demo beneficiaries (clearly labeled).
- Preserve audit history for lifecycle actions.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.auth import get_current_worker
from app.data_scope import beneficiary_visible_expression
from app.database import get_db
from app.models import AlertAuditLog, AshaWorker, Beneficiary, DangerAlert, Household
from app.routers.visits import _alert_dict
from app.schemas import AckResponse, AlertListResponse, AlertSummaryResponse

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_worker)])


class AlertActionRequest(BaseModel):
    note: str = Field(default="", max_length=2000)
    reason: str = Field(default="", max_length=2000)
    referral_facility: str = Field(default="", max_length=256)
    referral_date: str = Field(default="", max_length=32)
    referral_note: str = Field(default="", max_length=2000)


TERMINAL_STATUSES = {"resolved", "dismissed"}
UNRESOLVED_STATUSES = {"new", "open", "acknowledged", "in_progress", "escalated"}
VALID_ACTIONS = {
    "acknowledge": "acknowledged",
    "in_progress": "in_progress",
    "escalate": "escalated",
    "resolve": "resolved",
    "dismiss": "dismissed",
}


def _norm_status(raw: str | None) -> str:
    s = (raw or "open").strip().lower().replace("-", "_")
    if s == "open":
        return "new"
    return s or "new"


def _is_admin(worker: AshaWorker | None) -> bool:
    return bool(worker and getattr(worker, "role", "asha") == "admin")


def _beneficiary_for_alert(db: Session, alert: DangerAlert) -> Beneficiary | None:
    return db.query(Beneficiary).filter(Beneficiary.id == alert.beneficiary_id).first()


def _can_access_alert(db: Session, worker: AshaWorker, alert: DangerAlert, ben: Beneficiary | None = None) -> bool:
    if _is_admin(worker):
        return True
    if alert.assigned_worker_id == worker.id:
        return True
    ben = ben or _beneficiary_for_alert(db, alert)
    if ben and ben.assigned_worker_id == worker.id:
        return True
    # If explicitly assigned to another worker, deny.
    if alert.assigned_worker_id and alert.assigned_worker_id != worker.id:
        return False
    # If beneficiary explicitly assigned to another worker, deny.
    if ben and ben.assigned_worker_id and ben.assigned_worker_id != worker.id:
        return False
    # Unassigned/team-visible records remain accessible to authenticated workers.
    return True


def _require_access(db: Session, worker: AshaWorker, alert: DangerAlert) -> Beneficiary | None:
    ben = _beneficiary_for_alert(db, alert)
    if not _can_access_alert(db, worker, alert, ben):
        raise HTTPException(status_code=403, detail="Not authorized to access this alert")
    return ben


def _action_text(payload: AlertActionRequest | None) -> tuple[str, str]:
    if not payload:
        return "", ""
    note = (payload.note or "").strip()
    reason = (payload.reason or "").strip()
    return note, reason


def _history_item(row: AlertAuditLog) -> dict:
    return {
        "id": row.id,
        "alert_id": row.alert_id,
        "action": row.action or "",
        "actor_id": row.actor_id,
        "actor_label": row.actor_label or "system",
        "note": row.note or "",
        "created_at": row.created_at,
    }


def _status_match_set(raw_status: str) -> set[str]:
    wanted = [s.strip().lower().replace("-", "_") for s in (raw_status or "").split(",") if s.strip()]
    out: set[str] = set()
    for s in wanted:
        if s in ("active", "unresolved"):
            out.update(UNRESOLVED_STATUSES)
        elif s == "resolved_dismissed":
            out.update(TERMINAL_STATUSES)
        elif s in ("referral_pending","referred_pending","referred"):
            out.add("__referral_pending__")
        elif s == "open":
            out.update({"open", "new"})
        elif s == "new":
            out.update({"new", "open"})
        else:
            out.add(s)
    return out


def _build_filtered_query(
    db: Session,
    worker: AshaWorker,
    status: str = "",
    severity: str = "",
    category: str = "",
    q: str = "",
    beneficiary_id: int | None = None,
    household_id: int | None = None,
):
    """Build a scoped, filtered DangerAlert query with a single Beneficiary join when needed."""
    ben_alias = aliased(Beneficiary)
    qy = db.query(DangerAlert).outerjoin(ben_alias, ben_alias.id == DangerAlert.beneficiary_id)
    # Apply normal/demo visibility rules consistently with other modules.
    qy = qy.filter(
        or_(
            DangerAlert.beneficiary_id.is_(None),
            beneficiary_visible_expression(ben_alias),
        )
    )

    if not _is_admin(worker):
        qy = qy.filter(
            or_(
                DangerAlert.assigned_worker_id == worker.id,
                ben_alias.assigned_worker_id == worker.id,
                and_scope_unassigned(ben_alias),
            )
        )

    if beneficiary_id is not None:
        qy = qy.filter(DangerAlert.beneficiary_id == beneficiary_id)
    if household_id is not None:
        # household filter requires beneficiary link
        qy = qy.filter(ben_alias.household_id == household_id)
    if status:
        statuses = _status_match_set(status)
        wants_referral_pending = "__referral_pending__" in statuses
        statuses = {s for s in statuses if s != "__referral_pending__"}
        if statuses:
            qy = qy.filter(func.lower(DangerAlert.status).in_(list(statuses)))
        if wants_referral_pending:
            qy = qy.filter(
                func.coalesce(DangerAlert.referral_facility, "") != "",
                ~func.lower(func.coalesce(DangerAlert.status, "")).in_(list(TERMINAL_STATUSES)),
            )
    if severity:
        sevs = [s.strip().lower() for s in severity.split(",") if s.strip()]
        if sevs:
            qy = qy.filter(func.lower(func.coalesce(DangerAlert.severity, "")).in_(sevs))
    if category:
        cats = [s.strip().lower() for s in category.split(",") if s.strip()]
        if cats:
            qy = qy.filter(func.lower(func.coalesce(DangerAlert.alert_category, "")).in_(cats))
    if q:
        term = f"%{q.strip().lower()}%"
        qy = qy.filter(
            or_(
                func.lower(func.coalesce(ben_alias.name, "")).like(term),
                func.lower(func.coalesce(DangerAlert.triggered_phrase, "")).like(term),
                func.lower(func.coalesce(DangerAlert.rule_id, "")).like(term),
                func.lower(func.coalesce(DangerAlert.message, "")).like(term),
                func.lower(func.coalesce(DangerAlert.reason, "")).like(term),
                func.lower(func.coalesce(DangerAlert.recommended_action, "")).like(term),
                func.lower(func.coalesce(DangerAlert.trigger_detail, "")).like(term),
            )
        )
    return qy, ben_alias, True


def and_scope_unassigned(ben_alias):
    # team-visible only when neither alert nor beneficiary is assigned to someone else
    return (DangerAlert.assigned_worker_id.is_(None)) & (ben_alias.assigned_worker_id.is_(None))


def _serialize_alerts(db: Session, alerts: list[DangerAlert]) -> list[dict]:
    ben_ids = list({a.beneficiary_id for a in alerts if a.beneficiary_id is not None})
    bens = db.query(Beneficiary).filter(Beneficiary.id.in_(ben_ids)).all() if ben_ids else []
    ben_map = {b.id: b for b in bens}
    hh_ids = list({b.household_id for b in bens if b.household_id})
    hh_map = {h.id: h for h in db.query(Household).filter(Household.id.in_(hh_ids)).all()} if hh_ids else {}
    return [
        _alert_dict(
            a,
            (ben_map.get(a.beneficiary_id).name if ben_map.get(a.beneficiary_id) else "Unknown"),
            ben_map.get(a.beneficiary_id),
            hh_map,
        )
        for a in alerts
    ]


def _summary_counts(db: Session, worker: AshaWorker) -> dict:
    qy, _, _ = _build_filtered_query(db, worker)
    # Distinct to be safe if joins ever produce multiplicity; load only needed columns.
    rows = qy.with_entities(
        DangerAlert.id,
        DangerAlert.status,
        DangerAlert.severity,
    ).distinct().all()
    counts = {
        "total": 0,
        "new": 0,
        "unresolved": 0,
        "in_progress": 0,
        "escalated": 0,
        "referred": 0,
        "referral_pending": 0,
        "resolved": 0,
        "dismissed": 0,
        "high_critical_unresolved": 0,
    }
    for _id, status, severity, referral_facility, referred_at in qy.with_entities(
        DangerAlert.id, DangerAlert.status, DangerAlert.severity, DangerAlert.referral_facility, DangerAlert.referred_at
    ).distinct().all():
        st = _norm_status(status)
        sev = (severity or "").strip().lower()
        counts["total"] += 1
        if st in counts:
            counts[st] += 1
        has_ref = bool((referral_facility or "").strip() or referred_at)
        if has_ref and st not in TERMINAL_STATUSES:
            counts["referral_pending"] += 1
        if st in UNRESOLVED_STATUSES or st not in TERMINAL_STATUSES:
            counts["unresolved"] += 1
            if sev in ("high", "critical") or "high" in sev or "crit" in sev:
                counts["high_critical_unresolved"] += 1
    counts["active"] = counts["unresolved"]
    counts["open"] = counts["new"]
    return counts


@router.get("/summary", response_model=AlertSummaryResponse)
def alerts_summary(db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    """Real DB-backed aggregate counts for Danger Alerts summary cards (scoped)."""
    c = _summary_counts(db, worker)
    return {
        "total": c.get("total", 0),
        "new": c.get("new", 0),
        "unresolved": c.get("unresolved", 0),
        "in_progress": c.get("in_progress", 0),
        "escalated": c.get("escalated", 0),
        "referred": c.get("referred", 0),
        "referral_pending": c.get("referral_pending", 0),
        "resolved": c.get("resolved", 0),
        "dismissed": c.get("dismissed", 0),
        "high_critical_unresolved": c.get("high_critical_unresolved", 0),
        "counts": c,
    }


@router.get("", response_model=AlertListResponse)
def list_alerts(
    db: Session = Depends(get_db),
    worker: AshaWorker = Depends(get_current_worker),
    status: str = Query("", description="Comma-separated statuses or active/unresolved/resolved_dismissed"),
    severity: str = Query("", description="Comma-separated severities"),
    category: str = Query("", description="Comma-separated alert categories"),
    q: str = Query("", description="Search beneficiary name/phrase/reason/rule"),
    beneficiary_id: int | None = Query(None),
    household_id: int | None = Query(None),
):
    qy, _, _ = _build_filtered_query(
        db, worker,
        status=status, severity=severity, category=category, q=q,
        beneficiary_id=beneficiary_id, household_id=household_id,
    )
    # Avoid duplicate rows if joins produce multiplicity (defensive)
    alerts = qy.distinct().order_by(DangerAlert.created_at.desc(), DangerAlert.id.desc()).all()
    serialized = _serialize_alerts(db, alerts)
    counts = _summary_counts(db, worker)
    return {
        "alerts": serialized,
        "total": len(serialized),
        "counts": counts,
    }


@router.get("/{alert_id}")
def get_alert(alert_id: int, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    alert = db.query(DangerAlert).filter(DangerAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    ben = _require_access(db, worker, alert)
    hh = db.query(Household).filter(Household.id == ben.household_id).first() if ben and ben.household_id else None
    history = (
        db.query(AlertAuditLog)
        .filter(AlertAuditLog.alert_id == alert.id)
        .order_by(AlertAuditLog.created_at.asc(), AlertAuditLog.id.asc())
        .all()
    )
    data = _alert_dict(alert, ben.name if ben else "Unknown", ben, {hh.id: hh} if hh else {})
    data["history"] = [_history_item(h) for h in history]
    return data


@router.get("/{alert_id}/history")
def alert_history(alert_id: int, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    alert = db.query(DangerAlert).filter(DangerAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    _require_access(db, worker, alert)
    rows = (
        db.query(AlertAuditLog)
        .filter(AlertAuditLog.alert_id == alert.id)
        .order_by(AlertAuditLog.created_at.asc(), AlertAuditLog.id.asc())
        .all()
    )
    return {"alert_id": alert.id, "history": [_history_item(r) for r in rows]}


def _set_status(alert: DangerAlert, status: str, note: str, worker: AshaWorker, db: Session, action: str):
    alert.status = status
    alert.updated_at = datetime.utcnow()
    if action == "escalated":
        alert.escalation_note = note or alert.escalation_note or ""
    if action == "resolved":
        alert.resolved_note = note or alert.resolved_note or ""
        alert.resolved_at = datetime.utcnow()
    if action == "dismissed":
        alert.resolved_note = note or alert.resolved_note or ""
        alert.resolved_at = datetime.utcnow()
    db.add(
        AlertAuditLog(
            alert_id=alert.id,
            action=action,
            actor_id=worker.id if worker else None,
            actor_label=(worker.name if worker else "worker"),
            note=note or "",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(alert)
    return {"status": _norm_status(alert.status)}


def _perform_action(alert_id: int, payload: AlertActionRequest | None, db: Session, worker: AshaWorker, action: str) -> AckResponse:
    alert = db.query(DangerAlert).filter(DangerAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    _require_access(db, worker, alert)
    current = _norm_status(alert.status)
    target = VALID_ACTIONS[action]
    if current in TERMINAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Alert is already {current} and cannot be modified")
    if current == target and action not in ("escalate",):
        return AckResponse(status=current)
    note, reason = _action_text(payload)
    text = note or reason
    if action in ("escalate", "resolve", "dismiss") and not text:
        raise HTTPException(status_code=400, detail="A note or reason is required for this action")
    if action == "dismiss" and reason and not note:
        text = reason
    return AckResponse(**_set_status(alert, target, text, worker, db, target))


@router.post("/{alert_id}/ack", response_model=AckResponse)
def acknowledge(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    return _perform_action(alert_id, payload, db, worker, "acknowledge")


@router.post("/{alert_id}/in-progress", response_model=AckResponse)
@router.post("/{alert_id}/in_progress", response_model=AckResponse)
def mark_in_progress(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    return _perform_action(alert_id, payload, db, worker, "in_progress")


@router.post("/{alert_id}/escalate", response_model=AckResponse)
def escalate(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    return _perform_action(alert_id, payload, db, worker, "escalate")


@router.post("/{alert_id}/resolve", response_model=AckResponse)
def resolve(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    return _perform_action(alert_id, payload, db, worker, "resolve")


@router.post("/{alert_id}/referral-initiated", response_model=AckResponse)
@router.post("/{alert_id}/mark-referral-initiated", response_model=AckResponse)
def mark_referral_initiated(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    alert = db.query(DangerAlert).filter(DangerAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    _require_access(db, worker, alert)
    current = _norm_status(alert.status)
    if current in TERMINAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Alert is already {current} and cannot be modified")
    note, reason = _action_text(payload)
    alert.status = "in_progress"
    alert.referred_at = alert.referred_at or datetime.utcnow()
    alert.referred_by_worker_id = alert.referred_by_worker_id or worker.id
    if note:
        alert.referral_note = (alert.referral_note + "\n" if alert.referral_note else "") + f"Referral initiated: {note}"
    alert.updated_at = datetime.utcnow()
    db.add(AlertAuditLog(alert_id=alert.id, action="referral_initiated", actor_id=worker.id, actor_label=worker.name, note=note or "Referral initiated", created_at=datetime.utcnow()))
    db.commit()
    db.refresh(alert)
    return AckResponse(status=_norm_status(alert.status))


@router.post("/{alert_id}/referral", response_model=AckResponse)
@router.post("/{alert_id}/record-referral", response_model=AckResponse)
def record_referral(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    alert = db.query(DangerAlert).filter(DangerAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    _require_access(db, worker, alert)
    current = _norm_status(alert.status)
    if current in TERMINAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Alert is already {current} and cannot be modified")
    note, reason = _action_text(payload)
    facility = ((payload.referral_facility if payload else "") or "").strip()
    ref_note = ((payload.referral_note if payload else "") or note or reason).strip()
    ref_date_raw = ((payload.referral_date if payload else "") or "").strip()
    if not facility:
        raise HTTPException(status_code=400, detail="Referral facility is required")
    ref_date = None
    if ref_date_raw:
        try:
            ref_date = date.fromisoformat(ref_date_raw[:10])
        except Exception:
            raise HTTPException(status_code=400, detail="referral_date must be YYYY-MM-DD")
    alert.referral_facility = facility
    alert.referral_date = ref_date
    alert.referral_note = ref_note
    alert.referred_at = datetime.utcnow()
    alert.referred_by_worker_id = worker.id
    if current in ("new", "open", "acknowledged"):
        alert.status = "in_progress"
    alert.updated_at = datetime.utcnow()
    db.add(AlertAuditLog(alert_id=alert.id, action="referral_recorded", actor_id=worker.id, actor_label=worker.name, note=f"Referral recorded: {facility}{f' on {ref_date.isoformat()}' if ref_date else ''}. {ref_note}".strip(), created_at=datetime.utcnow()))
    db.commit()
    db.refresh(alert)
    return AckResponse(status=_norm_status(alert.status))


@router.post("/{alert_id}/dismiss", response_model=AckResponse)
def dismiss(alert_id: int, payload: AlertActionRequest | None = None, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    return _perform_action(alert_id, payload, db, worker, "dismiss")
