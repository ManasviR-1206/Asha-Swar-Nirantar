"""ASHA SWAR NIRANTAR — FastAPI application entrypoint.

Run from the backend/ folder:  python run.py
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import gnani_mode
from app.database import Base, SessionLocal, apply_light_migrations, engine
from app.routers import alerts, auth_router, beneficiaries, dashboard, drift, households, reminders, visits, voice
from app.rules import refresh_statuses
from app.seed import DEMO_PASSWORD, DEMO_WORKER_ID, is_db_empty, seed

REFRESH_INTERVAL_SECONDS = 3600  # hourly maintenance


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
    # Startup: create tables, seed demo data if the DB is empty, start scheduler.
    Base.metadata.create_all(bind=engine)
    apply_light_migrations()
    db = SessionLocal()
    try:
        empty = is_db_empty(db)
        if empty:
            seed(db)
    finally:
        db.close()

    task = asyncio.create_task(_hourly_maintenance())

    mode = gnani_mode()
    print("=" * 72)
    print("ASHA SWAR NIRANTAR backend running on http://localhost:8000")
    print(f"MODE: {mode}" + ("" if mode == "demo" else " (live Gnani credentials detected)"))
    print(f"Demo login (DEMO credentials, synthetic data): {DEMO_WORKER_ID} / {DEMO_PASSWORD}")
    print("=" * 72)

    yield

    task.cancel()


app = FastAPI(
    title="ASHA SWAR NIRANTAR",
    description="Voice-first healthcare field register for ASHA workers",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: Vite dev frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router.router)
app.include_router(dashboard.router)
app.include_router(beneficiaries.router)
app.include_router(households.router)
app.include_router(visits.router)
app.include_router(voice.router)
app.include_router(drift.router)
app.include_router(alerts.router)
app.include_router(reminders.router)


@app.get("/api/health")
def health():
    """Liveness probe. Reports the honest integration mode."""
    return {"status": "ok", "mode": gnani_mode()}
