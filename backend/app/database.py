"""SQLAlchemy engine / session setup for the ASHA SWAR NIRANTAR backend."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import get_env

# SQLite by default; DATABASE_URL can point elsewhere.
DATABASE_URL = get_env("DATABASE_URL", "sqlite:///./asha_swar.db")

# Relative SQLite URLs must resolve from backend/.env even when the backend
# is launched from the repository root.
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:////"):
    _sqlite_path = DATABASE_URL[len("sqlite:///"):].replace("/", "\\")
    _resolved_path = (Path(__file__).resolve().parent.parent / _sqlite_path).resolve()
    DATABASE_URL = f"sqlite:///{str(_resolved_path).replace(chr(92), '/')}"

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
    """Idempotent column additions for existing databases.

    `create_all` never ALTERs an existing table, so any column added to a
    model after the database was first created has to be added explicitly.
    Each step is skipped when the column already exists.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements = []

    def add_col(table, col, ddl, existing):
        if table in tables and col not in existing:
            statements.append(ddl)

    if "asha_workers" in tables:
        cols = {c["name"] for c in inspector.get_columns("asha_workers")}
        add_col("asha_workers", "is_active", "ALTER TABLE asha_workers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1", cols)
        add_col("asha_workers", "role", "ALTER TABLE asha_workers ADD COLUMN role VARCHAR(16) DEFAULT 'asha'", cols)

    if "beneficiaries" in tables:
        cols = {c["name"] for c in inspector.get_columns("beneficiaries")}
        add_col("beneficiaries", "gender", "ALTER TABLE beneficiaries ADD COLUMN gender VARCHAR(16) DEFAULT ''", cols)
        add_col("beneficiaries", "address", "ALTER TABLE beneficiaries ADD COLUMN address VARCHAR(256) DEFAULT ''", cols)
        add_col("beneficiaries", "email", "ALTER TABLE beneficiaries ADD COLUMN email VARCHAR(160)", cols)
        add_col("beneficiaries", "date_of_birth", "ALTER TABLE beneficiaries ADD COLUMN date_of_birth DATE", cols)
        add_col("beneficiaries", "emergency_contact", "ALTER TABLE beneficiaries ADD COLUMN emergency_contact VARCHAR(64) DEFAULT ''", cols)
        add_col("beneficiaries", "emergency_contact_consent", "ALTER TABLE beneficiaries ADD COLUMN emergency_contact_consent BOOLEAN NOT NULL DEFAULT 0", cols)
        add_col("beneficiaries", "assigned_worker_id", "ALTER TABLE beneficiaries ADD COLUMN assigned_worker_id INTEGER", cols)
        add_col("beneficiaries", "data_origin", "ALTER TABLE beneficiaries ADD COLUMN data_origin VARCHAR(24) DEFAULT 'registered'", cols)
        add_col("beneficiaries", "registration_notes", "ALTER TABLE beneficiaries ADD COLUMN registration_notes TEXT DEFAULT ''", cols)

    if "households" in tables:
        cols = {c["name"] for c in inspector.get_columns("households")}
        add_col("households", "data_origin", "ALTER TABLE households ADD COLUMN data_origin VARCHAR(24) DEFAULT 'registered'", cols)
        add_col("households", "latitude", "ALTER TABLE households ADD COLUMN latitude FLOAT", cols)
        add_col("households", "longitude", "ALTER TABLE households ADD COLUMN longitude FLOAT", cols)
        add_col("households", "location_source", "ALTER TABLE households ADD COLUMN location_source VARCHAR(32) DEFAULT ''", cols)
        add_col("households", "location_updated_at", "ALTER TABLE households ADD COLUMN location_updated_at DATETIME", cols)

    if "sms_reminders" in tables:
        cols = {c["name"] for c in inspector.get_columns("sms_reminders")}
        add_col("sms_reminders", "sms_status", "ALTER TABLE sms_reminders ADD COLUMN sms_status VARCHAR(16) DEFAULT 'pending'", cols)

    if "danger_alerts" in tables:
        cols = {c["name"] for c in inspector.get_columns("danger_alerts")}
        for col, ddl in [
            ("alert_category", "ALTER TABLE danger_alerts ADD COLUMN alert_category VARCHAR(64) DEFAULT ''"),
            ("trigger_detail", "ALTER TABLE danger_alerts ADD COLUMN trigger_detail TEXT DEFAULT ''"),
            ("trigger_value", "ALTER TABLE danger_alerts ADD COLUMN trigger_value VARCHAR(128) DEFAULT ''"),
            ("reason", "ALTER TABLE danger_alerts ADD COLUMN reason TEXT DEFAULT ''"),
            ("recommended_action", "ALTER TABLE danger_alerts ADD COLUMN recommended_action TEXT DEFAULT ''"),
            ("assigned_worker_id", "ALTER TABLE danger_alerts ADD COLUMN assigned_worker_id INTEGER"),
            ("escalation_note", "ALTER TABLE danger_alerts ADD COLUMN escalation_note TEXT DEFAULT ''"),
            ("resolved_note", "ALTER TABLE danger_alerts ADD COLUMN resolved_note TEXT DEFAULT ''"),
            ("updated_at", "ALTER TABLE danger_alerts ADD COLUMN updated_at DATETIME"),
            ("resolved_at", "ALTER TABLE danger_alerts ADD COLUMN resolved_at DATETIME"),
            ("rule_version", "ALTER TABLE danger_alerts ADD COLUMN rule_version VARCHAR(64) DEFAULT 'draft-unreviewed-v1'"),
            ("clinical_source", "ALTER TABLE danger_alerts ADD COLUMN clinical_source TEXT DEFAULT ''"),
            ("referral_facility", "ALTER TABLE danger_alerts ADD COLUMN referral_facility VARCHAR(256) DEFAULT ''"),
            ("referral_date", "ALTER TABLE danger_alerts ADD COLUMN referral_date DATE"),
            ("referral_note", "ALTER TABLE danger_alerts ADD COLUMN referral_note TEXT DEFAULT ''"),
            ("referred_at", "ALTER TABLE danger_alerts ADD COLUMN referred_at DATETIME"),
            ("referred_by_worker_id", "ALTER TABLE danger_alerts ADD COLUMN referred_by_worker_id INTEGER"),
        ]:
            add_col("danger_alerts", col, ddl, cols)

    if "follow_ups" in tables:
        cols = {c["name"] for c in inspector.get_columns("follow_ups")}
        for col, ddl in [
            ("priority", "ALTER TABLE follow_ups ADD COLUMN priority VARCHAR(16) DEFAULT 'normal'"),
            ("reason", "ALTER TABLE follow_ups ADD COLUMN reason TEXT DEFAULT ''"),
            ("recommended_action", "ALTER TABLE follow_ups ADD COLUMN recommended_action TEXT DEFAULT ''"),
            ("assigned_worker_id", "ALTER TABLE follow_ups ADD COLUMN assigned_worker_id INTEGER"),
            ("notes", "ALTER TABLE follow_ups ADD COLUMN notes TEXT DEFAULT ''"),
            ("completed_at", "ALTER TABLE follow_ups ADD COLUMN completed_at DATETIME"),
            ("rescheduled_from", "ALTER TABLE follow_ups ADD COLUMN rescheduled_from DATE"),
            ("updated_at", "ALTER TABLE follow_ups ADD COLUMN updated_at DATETIME"),
            ("category", "ALTER TABLE follow_ups ADD COLUMN category VARCHAR(48) DEFAULT ''"),
            ("description", "ALTER TABLE follow_ups ADD COLUMN description TEXT DEFAULT ''"),
            ("completion_notes", "ALTER TABLE follow_ups ADD COLUMN completion_notes TEXT DEFAULT ''"),
            ("cancellation_reason", "ALTER TABLE follow_ups ADD COLUMN cancellation_reason TEXT DEFAULT ''"),
            ("cancelled_at", "ALTER TABLE follow_ups ADD COLUMN cancelled_at DATETIME"),
            ("source_type", "ALTER TABLE follow_ups ADD COLUMN source_type VARCHAR(32) DEFAULT ''"),
            ("source_id", "ALTER TABLE follow_ups ADD COLUMN source_id INTEGER"),
            ("source_ref", "ALTER TABLE follow_ups ADD COLUMN source_ref VARCHAR(128) DEFAULT ''"),
            ("dedup_key", "ALTER TABLE follow_ups ADD COLUMN dedup_key VARCHAR(160) DEFAULT ''"),
        ]:
            add_col("follow_ups", col, ddl, cols)

    # Decommissioned-feature table removal is intentionally NOT performed automatically at startup.
    # If obsolete tables still exist in another environment, use the separate explicitly invoked
    # one-time script: backend/scripts/remove_decommissioned_feature_tables.py (backup/dependency/marker checks required).

    # Beneficiary profile extensions (additive, safe for existing records)
    if "beneficiaries" in tables:
        cols = {c["name"] for c in inspector.get_columns("beneficiaries")}
        for col, ddl in [
            ("household_id", "ALTER TABLE beneficiaries ADD COLUMN household_id INTEGER"),
            ("pregnancy_status", "ALTER TABLE beneficiaries ADD COLUMN pregnancy_status VARCHAR(32) DEFAULT ''"),
            ("medical_conditions", "ALTER TABLE beneficiaries ADD COLUMN medical_conditions TEXT DEFAULT ''"),
            ("allergies", "ALTER TABLE beneficiaries ADD COLUMN allergies TEXT DEFAULT ''"),
            ("current_medications", "ALTER TABLE beneficiaries ADD COLUMN current_medications TEXT DEFAULT ''"),
            ("verification_status", "ALTER TABLE beneficiaries ADD COLUMN verification_status VARCHAR(32) DEFAULT 'asha_verified'"),
            ("child_health_notes", "ALTER TABLE beneficiaries ADD COLUMN child_health_notes TEXT DEFAULT ''"),
        ]:
            add_col("beneficiaries", col, ddl, cols)

    # Measurement/document audit-friendly extensions
    if "health_measurements" in tables:
        cols = {c["name"] for c in inspector.get_columns("health_measurements")}
        for col, ddl in [
            ("verification_status", "ALTER TABLE health_measurements ADD COLUMN verification_status VARCHAR(24) DEFAULT 'recorded'"),
            ("is_deleted", "ALTER TABLE health_measurements ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"),
        ]:
            add_col("health_measurements", col, ddl, cols)

    if "uploaded_documents" in tables:
        cols = {c["name"] for c in inspector.get_columns("uploaded_documents")}
        for col, ddl in [
            ("category", "ALTER TABLE uploaded_documents ADD COLUMN category VARCHAR(64) DEFAULT 'other'"),
            ("is_deleted", "ALTER TABLE uploaded_documents ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"),
            ("deleted_at", "ALTER TABLE uploaded_documents ADD COLUMN deleted_at DATETIME"),
            ("deleted_by", "ALTER TABLE uploaded_documents ADD COLUMN deleted_by INTEGER"),
            ("delete_reason", "ALTER TABLE uploaded_documents ADD COLUMN delete_reason TEXT DEFAULT ''"),
        ]:
            add_col("uploaded_documents", col, ddl, cols)

    if "visit_records" in tables:
        cols = {c["name"] for c in inspector.get_columns("visit_records")}
        add_col("visit_records", "idempotency_key", "ALTER TABLE visit_records ADD COLUMN idempotency_key VARCHAR(128) DEFAULT ''", cols)

    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
