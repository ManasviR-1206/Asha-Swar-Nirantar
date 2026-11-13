"""POST /api/auth/login — ASHA worker login issuing an opaque bearer token."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import create_token, verify_password
from app.database import get_db
from app.models import AshaWorker
from app.seed import DEMO_WORKER_ID
from app.schemas import LoginRequest, LoginResponse, WorkerOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    worker_id = payload.worker_id.strip()
    worker_ids = [worker_id]
    if worker_id == DEMO_WORKER_ID:
        worker_ids.append("ASHA-DEMO-001")
    elif worker_id == "ASHA-DEMO-001":
        worker_ids.append(DEMO_WORKER_ID)

    worker = None
    for candidate_id in worker_ids:
        candidate = db.query(AshaWorker).filter(AshaWorker.worker_id == candidate_id).first()
        if candidate is not None:
            worker = candidate
            break
    if worker is None or not verify_password(payload.password, worker.password_hash):
        raise HTTPException(status_code=401, detail="Invalid ASHA Worker ID or password")
    # Language is a per-login preference; persist it on the worker profile.
    if payload.language:
        worker.language = payload.language
        db.commit()
    token = create_token(db, worker)
    return {
        "token": token,
        "worker": WorkerOut(
            id=worker.id, name=worker.name, worker_id=worker.worker_id,
            language=worker.language, phc=worker.phc,
        ).model_dump(),
    }
