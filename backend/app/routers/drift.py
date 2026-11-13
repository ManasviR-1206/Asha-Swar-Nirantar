"""GET /api/drift — Pulse Drift: follow-up drift engine across all beneficiaries."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.rules import run_drift_engine
from app.schemas import DriftResponse

router = APIRouter(prefix="/api", tags=["drift"], dependencies=[Depends(get_current_worker)])


@router.get("/drift", response_model=DriftResponse)
def drift(db: Session = Depends(get_db)):
    return {"items": run_drift_engine(db)}
