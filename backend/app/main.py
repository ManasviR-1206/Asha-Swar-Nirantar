"""ASHA SWAR NIRANTAR — FastAPI application entrypoint.

Run from the backend/ folder:  python run.py
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import demo_setup_enabled, get_env
from app.database import Base, SessionLocal, apply_light_migrations, engine
from app.routers import (
    alerts,
    auth_router,
    beneficiaries,
    dashboard,
    documents,
    drift,
    followups,
    geopulse,
    households,
    measurements,
    notifications,
    reminders,
    visits,
    voice,
    voice_sessions,
)
from app.rules import refresh_statuses
from app.seed import DEMO_PASSWORD, DEMO_WORKER_ID, ensure_demo_worker, is_db_empty, seed
from app.services.gnani import integration_status as ai_integration_status

REFRESH_INTERVAL_SECONDS = 3600  # hourly maintenance
logger = logging.getLogger(__name__)


async def _hourly_maintenance() -> None:
    """Background loop: mark overdue follow-ups and flag missed reminders."""
    while True:
        try:
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            db = SessionLocal()
            try:
                refresh_statuses(db)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception:
            # Never crash the app because of the scheduler; retry next hour.
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create/migrate the database and initialize the demo account safely."""
    demo_setup = demo_setup_enabled()
    try:
        # Critical startup operations must fail explicitly rather than serving
        # an initialized app with a broken database.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=engine)
        apply_light_migrations()

        db = SessionLocal()
        try:
            # Demo sample records are opt-in, but the named demo login is
            # idempotently ensured because the UI and test workflow depend on it.
            if demo_setup and is_db_empty(db):
                seed(db)
            ensure_demo_worker(db)
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Critical database startup initialization failed")
        raise RuntimeError("Database initialization failed") from exc

    task = asyncio.create_task(_hourly_maintenance())

    integrations = ai_integration_status()
    print("=" * 72)
    print("ASHA SWAR NIRANTAR backend running on http://localhost:8000")
    print(f"APP DEMO SETUP: {'enabled' if demo_setup else 'disabled (normal operation)'}")
    print(
        "INTEGRATIONS: "
        f"stt={integrations.get('stt_provider')} configured={integrations.get('stt_live_configured')} "
        f"llm={integrations.get('llm_provider')} configured={integrations.get('llm_live_configured')} "
        f"tts={integrations.get('tts_provider')} configured={integrations.get('tts_live_configured')}"
    )
    if demo_setup:
        print(f"Demo login (explicit demo setup only): {DEMO_WORKER_ID} / {DEMO_PASSWORD}")
    print("=" * 72)

    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    task.cancel()


app = FastAPI(
    title="ASHA SWAR NIRANTAR",
    description="Voice-first healthcare field register for ASHA workers",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning("Request validation failed for %s", request.url.path)
    return JSONResponse(status_code=422, content={"detail": "Invalid request data"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error while processing %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# CORS: explicit, configurable origins (comma-separated). Defaults suit local dev.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allow_origins = [
    origin.strip()
    for origin in get_env("CORS_ORIGINS", _default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins or ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# Routers
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(beneficiaries.router)
app.include_router(households.router)
app.include_router(visits.router)
app.include_router(voice.router)
app.include_router(voice_sessions.router)
app.include_router(notifications.router)
app.include_router(drift.router)
app.include_router(followups.router)
app.include_router(alerts.router)
app.include_router(reminders.router)
app.include_router(measurements.router)
app.include_router(documents.router)
app.include_router(geopulse.router)


@app.get("/api/health")
def health():
    """Report backend/database availability and honest runtime integration status.

    STT: Gnani Prisma. LLM: Google Gemini. TTS: Gnani Timbre.
    Live/configured is never claimed without required configuration.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Health check could not reach the database")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    demo_setup = demo_setup_enabled()
    integrations = ai_integration_status()
    return {
        "status": "ok",
        "database": "ok",
        # Overall application/demo setup status (drives demo UI labels/badges).
        "app": {"demo_setup": demo_setup},
        # Honest integration configuration status (no connectivity probe).
        "integrations": integrations,
        # Backward-compatible key retained for older clients; STT/TTS remain Gnani, LLM is Gemini.
        "gnani": integrations,
        # Backward-compatible top-level mode for older clients: demo setup vs normal app.
        "mode": "demo" if demo_setup else "normal",
    }
