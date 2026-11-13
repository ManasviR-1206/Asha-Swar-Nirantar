"""SQLAlchemy engine / session setup for the ASHA SWAR NIRANTAR backend."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import get_env

# SQLite by default; DATABASE_URL can point elsewhere.
DATABASE_URL = get_env("DATABASE_URL", "sqlite:///./asha_swar.db")

engine = create_engine(
    DATABASE_URL,
    # SQLite needs this because FastAPI uses the session across threads.
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all models."""


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_light_migrations() -> None:
    """Idempotent column additions for SQLite.

    `create_all` never ALTERs an existing table, so any column added to a
    model after the database was first created has to be added explicitly.
    Each step is skipped when the column already exists.
    """
    from sqlalchemy import inspect, text

    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements = []
    if "sms_reminders" in tables:
        cols = {c["name"] for c in inspector.get_columns("sms_reminders")}
        if "sms_status" not in cols:
            statements.append(
                "ALTER TABLE sms_reminders ADD COLUMN sms_status VARCHAR(16) DEFAULT 'pending'"
            )
    if "beneficiaries" in tables:
        cols = {c["name"] for c in inspector.get_columns("beneficiaries")}
        if "gender" not in cols:
            statements.append(
                "ALTER TABLE beneficiaries ADD COLUMN gender VARCHAR(16) DEFAULT ''"
            )
        if "address" not in cols:
            statements.append(
                "ALTER TABLE beneficiaries ADD COLUMN address VARCHAR(256) DEFAULT ''"
            )
    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
