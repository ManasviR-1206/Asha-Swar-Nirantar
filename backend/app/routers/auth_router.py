"""POST /api/auth/login — ASHA worker login issuing an opaque bearer token."""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import demo_setup_enabled, get_env
from app.auth import create_token, get_current_worker, verify_password
from app.database import get_db
from app.models import ApiToken, AshaWorker
from app.schemas import LoginRequest, LoginResponse, WorkerOut
from app.seed import DEMO_WORKER_ID

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Simple in-memory login rate limiting (per client IP). This protects the demo
# and single-process deployments; multi-process deployments should front the API
# with a gateway/WAF rate limiter as well.
_RATE_WINDOW_SECONDS = int(get_env("LOGIN_RATE_WINDOW_SECONDS", "300") or "300")
_RATE_MAX_ATTEMPTS = int(get_env("LOGIN_RATE_MAX_ATTEMPTS", "10") or "10")
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


def _check_login_rate_limit(request: Request) -> None:
    if _RATE_MAX_ATTEMPTS <= 0 or _RATE_WINDOW_SECONDS <= 0:
        return
    now = time.monotonic()
    ip = (request.client.host if request.client else "unknown") or "unknown"
    bucket = _login_attempts[ip]
    cutoff = now - _RATE_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _RATE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Please wait a few minutes and try again.",
        )
    bucket.append(now)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    _check_login_rate_limit(request)
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
    if not worker.is_active:
        raise HTTPException(status_code=403, detail="This account is inactive. Contact your coordinator.")
    # Language is a per-login preference; persist it on the worker profile.
    if payload.language:
        worker.language = payload.language
        db.commit()
    token = create_token(db, worker)
    return {
        "token": token,
        "worker": WorkerOut(
            id=worker.id,
            name=worker.name,
            worker_id=worker.worker_id,
            role=getattr(worker, "role", "asha") or "asha",
            language=worker.language,
            phc=worker.phc,
        ).model_dump(),
    }


@router.post("/demo-session", response_model=LoginResponse)
def demo_session(request: Request, db: Session = Depends(get_db)):
    """Create a demo session only when explicit demo setup is enabled.

    This is a supported demo convenience; it never bypasses normal auth for
    non-demo workers and does not expose credentials.
    """
    _check_login_rate_limit(request)
    if not demo_setup_enabled():
        raise HTTPException(status_code=403, detail="Demo session is not enabled in this environment.")
    worker = db.query(AshaWorker).filter(AshaWorker.worker_id == DEMO_WORKER_ID).first()
    if worker is None:
        # Fallback to known demo id variant only within demo mode.
        worker = db.query(AshaWorker).filter(AshaWorker.worker_id == "ASHA-DEMO-001").first()
    if worker is None or not worker.is_active:
        raise HTTPException(status_code=404, detail="Demo worker is not available.")
    token = create_token(db, worker)
    return {
        "token": token,
        "worker": WorkerOut(
            id=worker.id,
            name=worker.name,
            worker_id=worker.worker_id,
            role=getattr(worker, "role", "asha") or "asha",
            language=worker.language,
            phc=worker.phc,
        ).model_dump(),
    }


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Revoke the current bearer token (best-effort). Clients should also clear local session state."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            row = db.query(ApiToken).filter(ApiToken.token == token).first()
            if row is not None:
                db.delete(row)
                db.commit()
    return {"status": "logged_out"}


@router.get("/workers")
def list_workers(db: Session = Depends(get_db), _worker: AshaWorker = Depends(get_current_worker)):
    rows = db.query(AshaWorker).filter(AshaWorker.is_active == True).order_by(AshaWorker.name).all()  # noqa: E712
    return {
        "workers": [
            {
                "id": w.id,
                "worker_id": w.worker_id,
                "name": w.name,
                "role": getattr(w, "role", "asha") or "asha",
                "phc": w.phc or "",
            }
            for w in rows
        ]
    }


@router.get("/demo-status")
def demo_status():
    """Report whether explicit demo auto-login is enabled. No secrets."""
    enabled = bool(demo_setup_enabled())
    return {"enabled": enabled}


@router.post("/demo-session", response_model=LoginResponse)
def demo_session(request: Request, db: Session = Depends(get_db)):
    """Issue a short-lived session for the dedicated demo worker only when
    demo setup is explicitly enabled. Never available in normal production mode.
    """
    if not demo_setup_enabled():
        raise HTTPException(status_code=404, detail="Demo mode is not enabled")
    _check_login_rate_limit(request)
    worker = db.query(AshaWorker).filter(AshaWorker.worker_id == DEMO_WORKER_ID).first()
    if worker is None or not worker.is_active:
        raise HTTPException(status_code=404, detail="Demo account is not available")
    token = create_token(db, worker)
    return {
        "token": token,
        "worker": WorkerOut(
            id=worker.id,
            name=worker.name,
            worker_id=worker.worker_id,
            role=getattr(worker, "role", "asha") or "asha",
            language=worker.language,
            phc=worker.phc,
        ).model_dump(),
    }
