"""My Health Plan: care/follow-up plan tasks for beneficiaries."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import AshaWorker, Beneficiary, CarePlanTask

router = APIRouter(prefix="/api/care-plans", tags=["care-plans"], dependencies=[Depends(get_current_worker)])


class TaskCreate(BaseModel):
    beneficiary_id: int
    title: str
    description: str = ""
    category: str = "general"
    due_date: str | None = None
    priority: str = "normal"
    responsible: str = "asha"
    status: str = "pending"
    notes: str = ""


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    due_date: str | None = None
    priority: str | None = None
    responsible: str | None = None
    status: str | None = None
    notes: str | None = None


def _parse_date(v):
    if not v:
        return None
    from datetime import date
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _out(t: CarePlanTask) -> dict:
    return {
        "id": t.id,
        "beneficiary_id": t.beneficiary_id,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "due_date": t.due_date,
        "priority": t.priority,
        "responsible": t.responsible,
        "status": t.status,
        "notes": t.notes,
        "created_by": t.created_by,
        "completed_at": t.completed_at,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.get("/beneficiary/{beneficiary_id}")
def list_tasks(beneficiary_id: int, db: Session = Depends(get_db)):
    if db.query(Beneficiary).filter(Beneficiary.id == beneficiary_id).first() is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    rows = (
        db.query(CarePlanTask)
        .filter(CarePlanTask.beneficiary_id == beneficiary_id)
        .order_by(CarePlanTask.due_date.is_(None), CarePlanTask.due_date, CarePlanTask.id.desc())
        .all()
    )
    return {"tasks": [_out(r) for r in rows]}


@router.post("")
def create_task(payload: TaskCreate, db: Session = Depends(get_db), worker: AshaWorker = Depends(get_current_worker)):
    if db.query(Beneficiary).filter(Beneficiary.id == payload.beneficiary_id).first() is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    t = CarePlanTask(
        beneficiary_id=payload.beneficiary_id,
        title=(payload.title or "").strip() or "Health plan task",
        description=(payload.description or "").strip(),
        category=payload.category or "general",
        due_date=_parse_date(payload.due_date),
        priority=payload.priority or "normal",
        responsible=payload.responsible or "asha",
        status=payload.status or "pending",
        notes=(payload.notes or "").strip(),
        created_by=worker.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"task": _out(t)}


@router.patch("/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    t = db.query(CarePlanTask).filter(CarePlanTask.id == task_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Task not found")
    for field in ("title", "description", "category", "priority", "responsible", "status", "notes"):
        val = getattr(payload, field)
        if val is not None:
            setattr(t, field, val.strip() if isinstance(val, str) else val)
    if payload.due_date is not None:
        t.due_date = _parse_date(payload.due_date)
    if payload.status == "completed" and t.completed_at is None:
        t.completed_at = datetime.utcnow()
    if payload.status and payload.status != "completed":
        t.completed_at = None
    t.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    return {"task": _out(t)}
