"""Danger alert endpoints: list all, acknowledge one."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_worker
from app.database import get_db
from app.models import Beneficiary, DangerAlert
from app.schemas import AckResponse, AlertListResponse
from app.routers.visits import _alert_dict

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_worker)])


@router.get("", response_model=AlertListResponse)
def list_alerts(db: Session = Depends(get_db)):
    alerts = (
        db.query(DangerAlert)
        .order_by(DangerAlert.created_at.desc(), DangerAlert.id.desc())
        .all()
    )
    names = {b.id: b.name for b in db.query(Beneficiary).all()}
    return {"alerts": [_alert_dict(a, names.get(a.beneficiary_id, "Unknown")) for a in alerts]}


@router.post("/{alert_id}/ack", response_model=AckResponse)
def acknowledge(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(DangerAlert).filter(DangerAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = "acknowledged"
    db.commit()
    return {"status": "acknowledged"}
