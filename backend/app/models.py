"""Database tables for ASHA SWAR NIRANTAR.

Design notes:
- Only necessary information is stored; no raw audio or sensitive IDs.
- Beneficiary.qr_id is a random, non-sensitive identifier used on printed
  QR cards (it is NOT an Aadhaar or any government ID).
- Structured visit data is duplicated into ExtractedField rows (one per
  field) and also kept as JSON text on the visit's `notes` column.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class AshaWorker(Base):
    __tablename__ = "asha_workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # e.g. "ASHA-DEMO-001"
    name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))  # pbkdf2_hmac: "salt_hex$hash_hex"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # "asha" | "admin" role for access-controlled administrative areas where applicable.
    role: Mapped[str] = mapped_column(String(16), default="asha")
    language: Mapped[str] = mapped_column(String(16), default="en")
    phc: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tokens: Mapped[list["ApiToken"]] = relationship(back_populates="worker", cascade="all, delete-orphan")


class ApiToken(Base):
    """Opaque bearer tokens (secrets.token_hex). Not a JWT — simple and revocable."""
    __tablename__ = "api_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("asha_workers.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    worker: Mapped[AshaWorker] = relationship(back_populates="tokens")


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qr_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # e.g. "ASN-7F2K-9QMD"
    name: Mapped[str] = mapped_column(String(128))
    age: Mapped[int] = mapped_column(Integer)
    # "pregnancy" | "newborn" | "child" | "immunisation"
    category: Mapped[str] = mapped_column(String(32), index=True)
    gender: Mapped[str] = mapped_column(String(16), default="")
    village: Mapped[str] = mapped_column(String(128), default="")
    address: Mapped[str] = mapped_column(String(256), default="")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Optional contact email for the beneficiary (kept; not a notification delivery channel).
    email: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    lmp_date: Mapped[date | None] = mapped_column(Date, nullable=True)      # last menstrual period (pregnancy)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)    # extra optional field (newborn)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    emergency_contact: Mapped[str] = mapped_column(String(64), default="")
    emergency_contact_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    assigned_worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True, index=True)
    # 'registered' | 'demo' | 'public_sample' — never conflated in UI/queries.
    data_origin: Mapped[str] = mapped_column(String(24), default="registered", index=True)
    # e.g. registered | pending_verification | asha_verified | demo
    verification_status: Mapped[str] = mapped_column(String(32), default="asha_verified")
    pregnancy_status: Mapped[str] = mapped_column(String(32), default="")
    medical_conditions: Mapped[str] = mapped_column(Text, default="")
    allergies: Mapped[str] = mapped_column(Text, default="")
    current_medications: Mapped[str] = mapped_column(Text, default="")
    child_health_notes: Mapped[str] = mapped_column(Text, default="")
    registration_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    visits: Mapped[list["VisitRecord"]] = relationship(back_populates="beneficiary")
    alerts: Mapped[list["DangerAlert"]] = relationship(back_populates="beneficiary")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="beneficiary")
    reminders: Mapped[list["SmsReminder"]] = relationship(back_populates="beneficiary")
    member_of: Mapped["HouseholdMember | None"] = relationship(back_populates="beneficiary", uselist=False)
    sms_notifications: Mapped[list["SmsNotification"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    consent_records: Mapped[list["ConsentRecord"]] = relationship(
        cascade="all, delete-orphan"
    )
    pdf_reports: Mapped[list["PdfReport"]] = relationship(
        cascade="all, delete-orphan"
    )
    measurements: Mapped[list["HealthMeasurement"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    documents: Mapped[list["UploadedDocument"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    care_plan_tasks: Mapped[list["CarePlanTask"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    requests: Mapped[list["PatientRequest"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )


class VisitRecord(Base):
    __tablename__ = "visit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("asha_workers.id"), index=True)
    visit_date: Mapped[date] = mapped_column(Date, default=date.today)
    category: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")   # stores the structured JSON as TEXT
    # "voice" | "manual"
    source: Mapped[str] = mapped_column(String(16), default="manual")
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="visits")
    transcripts: Mapped[list["VoiceTranscript"]] = relationship(back_populates="visit")
    fields: Mapped[list["ExtractedField"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    pregnancy: Mapped["PregnancyRecord | None"] = relationship(back_populates="visit", uselist=False)
    newborn: Mapped["NewbornRecord | None"] = relationship(back_populates="visit", uselist=False)
    immunisation: Mapped["ImmunisationRecord | None"] = relationship(back_populates="visit", uselist=False)
    measurements: Mapped[list["HealthMeasurement"]] = relationship(back_populates="visit")


class PregnancyRecord(Base):
    __tablename__ = "pregnancy_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit_records.id"), index=True)
    weeks_pregnant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bp_sys: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bp_dia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    hemoglobin: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetal_heart: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    visit: Mapped[VisitRecord] = relationship(back_populates="pregnancy")


class NewbornRecord(Base):
    __tablename__ = "newborn_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit_records.id"), index=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    feeding: Mapped[str | None] = mapped_column(String(64), nullable=True)   # e.g. "breastfeeding well"
    jaundice: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "no" / "mild"
    notes: Mapped[str] = mapped_column(Text, default="")

    visit: Mapped[VisitRecord] = relationship(back_populates="newborn")


class ImmunisationRecord(Base):
    __tablename__ = "immunisation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit_records.id"), index=True)
    vaccine_name: Mapped[str] = mapped_column(String(64))
    dose_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_given: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    visit: Mapped[VisitRecord] = relationship(back_populates="immunisation")


class VoiceTranscript(Base):
    __tablename__ = "voice_transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit_records.id"), nullable=True, index=True)
    transcript: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    visit: Mapped[VisitRecord | None] = relationship(back_populates="transcripts")


class ExtractedField(Base):
    """One row per extracted field per visit. Also stores the whole structured
    JSON under field_name "_structured_json" so the visit keeps its full payload."""
    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit_records.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    field_value: Mapped[str] = mapped_column(Text, default="")

    visit: Mapped[VisitRecord] = relationship(back_populates="fields")


class DangerAlert(Base):
    __tablename__ = "danger_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit_records.id"), nullable=True)
    triggered_phrase: Mapped[str] = mapped_column(String(256))
    rule_id: Mapped[str] = mapped_column(String(32))
    # Version/reference for the rule logic that generated this alert (factual, may be draft/unreviewed).
    rule_version: Mapped[str] = mapped_column(String(64), default="draft-unreviewed-v1")
    # Factual provenance/source description for the rule/trigger (not a clinical endorsement).
    clinical_source: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(String(256))  # "Refer to PHC as per approved guidelines."
    # "high" | "medium"
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    # "new"/"open" | "acknowledged" | "in_progress" | "escalated" | "resolved" | "dismissed"
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    alert_category: Mapped[str] = mapped_column(String(64), default="")
    trigger_detail: Mapped[str] = mapped_column(Text, default="")
    trigger_value: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    assigned_worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    escalation_note: Mapped[str] = mapped_column(Text, default="")
    resolved_note: Mapped[str] = mapped_column(Text, default="")
    referral_facility: Mapped[str] = mapped_column(String(256), default="")
    referral_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    referral_note: Mapped[str] = mapped_column(Text, default="")
    referred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    referred_by_worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="alerts")
    audit_events: Mapped[list["AlertAuditLog"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Beneficiary follow-ups have beneficiary_id set; household hygiene
    # follow-ups have household_id set instead.
    beneficiary_id: Mapped[int | None] = mapped_column(ForeignKey("beneficiaries.id"), nullable=True, index=True)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit_records.id"), nullable=True)
    # "anc" | "vaccination" | "newborn" | "nutrition" | "household" | "community" etc.
    type: Mapped[str] = mapped_column(String(32))
    # UI/task category (can mirror type; kept additive for task management).
    category: Mapped[str] = mapped_column(String(48), default="")
    due_date: Mapped[date] = mapped_column(Date, index=True)
    # Canonical lifecycle: upcoming | due | overdue | completed | cancelled
    # (legacy values like done/missed/rescheduled are normalized by refresh/migrations).
    status: Mapped[str] = mapped_column(String(16), default="upcoming", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    reason: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    assigned_worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    # General notes; completion notes are also stored here for compatibility.
    notes: Mapped[str] = mapped_column(Text, default="")
    completion_notes: Mapped[str] = mapped_column(Text, default="")
    cancellation_reason: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rescheduled_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Source reference (visit/record/rule) for traceability and idempotent generation.
    source_type: Mapped[str] = mapped_column(String(32), default="")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ref: Mapped[str] = mapped_column(String(128), default="")
    # Idempotency key for generated follow-ups (prevents duplicates).
    dedup_key: Mapped[str] = mapped_column(String(160), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    beneficiary: Mapped["Beneficiary | None"] = relationship(back_populates="followups")
    household: Mapped["Household | None"] = relationship(back_populates="household_followups")
    history: Mapped[list["FollowUpHistory"]] = relationship(
        back_populates="followup", cascade="all, delete-orphan"
    )


class FollowUpHistory(Base):
    """Status/action history for persisted follow-up tasks."""

    __tablename__ = "follow_up_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    followup_id: Mapped[int] = mapped_column(ForeignKey("follow_ups.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))  # created/updated/completed/cancelled/rescheduled/assigned/status_changed
    from_status: Mapped[str] = mapped_column(String(16), default="")
    to_status: Mapped[str] = mapped_column(String(16), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(64), default="system")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    followup: Mapped[FollowUp] = relationship(back_populates="history")


class SmsReminder(Base):
    __tablename__ = "sms_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    follow_up_id: Mapped[int | None] = mapped_column(ForeignKey("follow_ups.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(32))            # e.g. "anc" | "vaccination" | "newborn"
    message: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date] = mapped_column(Date)
    # Schedule state of the reminder: "scheduled" | "overdue" | "cancelled".
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    # Delivery state of the message: "pending" | "sent" | "delivered" |
    # "failed" | "cancelled" | "demo_sent" (demo mode never really sends).
    sms_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    sms_consent: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="reminders")


# =====================================================================
# HOUSEHOLDS — Household Health & Hygiene module
# =====================================================================

class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qr_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # e.g. "HN-4KDP-7RWM"
    village: Mapped[str] = mapped_column(String(128), default="")
    address: Mapped[str] = mapped_column(String(256), default="")
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    # 'registered' | 'demo' | 'public_sample'
    data_origin: Mapped[str] = mapped_column(String(24), default="registered", index=True)
    # Optional actual coordinates for GeoPulse map. Never fabricate.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_source: Mapped[str] = mapped_column(String(32), default="")  # gps|manual_verified|imported_verified|synthetic_demo
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["HouseholdMember"]] = relationship(back_populates="household", cascade="all, delete-orphan")
    visits: Mapped[list["HouseholdVisit"]] = relationship(back_populates="household", cascade="all, delete-orphan")
    household_followups: Mapped[list["FollowUp"]] = relationship(back_populates="household")
    documents: Mapped[list["UploadedDocument"]] = relationship(back_populates="household")
    requests: Mapped[list["PatientRequest"]] = relationship(back_populates="household")


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    age: Mapped[int] = mapped_column(Integer, default=0)
    gender: Mapped[str] = mapped_column(String(16), default="")
    relation: Mapped[str] = mapped_column(String(32), default="")   # "head" | "spouse" | "child" | ...
    # Optional link to a registered beneficiary profile.
    beneficiary_id: Mapped[int | None] = mapped_column(ForeignKey("beneficiaries.id"), nullable=True, index=True)

    household: Mapped[Household] = relationship(back_populates="members")
    beneficiary: Mapped["Beneficiary | None"] = relationship(back_populates="member_of")


class HouseholdVisit(Base):
    """A Household Health & Hygiene observation visit.

    Structured fields (JSON TEXT in `notes`): water_source, water_storage,
    toilet_available, toilet_usage, waste_disposal, drainage,
    stagnant_water, handwashing, hygiene_observations, awareness_provided,
    follow_up_days. No scores, no shaming — observations and counselling only.
    """
    __tablename__ = "household_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("asha_workers.id"), index=True)
    visit_date: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str] = mapped_column(Text, default="")   # structured JSON as TEXT
    source: Mapped[str] = mapped_column(String(16), default="manual")  # "voice" | "manual"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    household: Mapped[Household] = relationship(back_populates="visits")


# =====================================================================
# VOICE RECORDING SESSIONS & EXTRACTED VISITS
# =====================================================================

class VoiceRecordingSession(Base):
    __tablename__ = "voice_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("asha_workers.id"), index=True)
    # Client-supplied id so a reconnecting client reuses its session.
    client_session_id: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16), default="en")
    # "recording" | "extracted" | "saved" | "discarded"
    status: Mapped[str] = mapped_column(String(16), default="recording", index=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(32), default="")
    mode: Mapped[str] = mapped_column(String(8), default="demo")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    visits: Mapped[list["ExtractedVisit"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ExtractedVisit(Base):
    """One beneficiary's visit, as extracted from a recording session."""

    __tablename__ = "extracted_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("voice_sessions.id"), index=True)
    # Stable temporary id used by the client until the visit is saved.
    temp_id: Mapped[str] = mapped_column(String(64), index=True)
    beneficiary_id: Mapped[int | None] = mapped_column(
        ForeignKey("beneficiaries.id"), nullable=True, index=True
    )
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id"), nullable=True, index=True
    )
    beneficiary_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visit_date: Mapped[date] = mapped_column(Date, default=date.today)
    category: Mapped[str] = mapped_column(String(32), default="general")
    structured: Mapped[str] = mapped_column(Text, default="{}")   # JSON
    # "resolved" | "ambiguous" | "unresolved" | "new"
    identity_status: Mapped[str] = mapped_column(String(16), default="unresolved", index=True)
    identity_reason: Mapped[str] = mapped_column(String(256), default="")
    # JSON list of candidate beneficiaries for an ambiguous identity.
    candidates: Mapped[str] = mapped_column(Text, default="[]")
    clarification_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    saved_visit_id: Mapped[int | None] = mapped_column(
        ForeignKey("visit_records.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped["VoiceRecordingSession"] = relationship(back_populates="visits")


class FieldAudit(Base):
    """Audit trail for every field correction applied to a record."""

    __tablename__ = "field_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    field_name: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    source: Mapped[str] = mapped_column(String(32), default="voice")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SmsNotification(Base):
    """Notification history for SMS messages sent to beneficiaries."""

    __tablename__ = "sms_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    follow_up_id: Mapped[int | None] = mapped_column(ForeignKey("follow_ups.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(32), default="anc")
    phone: Mapped[str] = mapped_column(String(32), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(16), default="en")
    # "pending" | "submitted" | "delivered" | "failed" | "unknown" | "demo"
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    provider_ref: Mapped[str] = mapped_column(String(128), default="")
    provider_note: Mapped[str] = mapped_column(String(256), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    consent_id: Mapped[int | None] = mapped_column(
        ForeignKey("consent_records.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    beneficiary: Mapped["Beneficiary"] = relationship(back_populates="sms_notifications")


class PdfReport(Base):
    """Metadata for a generated follow-up PDF report."""

    __tablename__ = "pdf_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    filename: Mapped[str] = mapped_column(String(256), default="")
    storage_path: Mapped[str] = mapped_column(String(512), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConsentRecord(Base):
    """Consent captured before a notification is sent to a beneficiary."""

    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    # "sms" | "email"
    channel: Mapped[str] = mapped_column(String(16), default="sms")
    purpose: Mapped[str] = mapped_column(String(64), default="follow_up_reminder")
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# =====================================================================
# New: measurements, documents, care plans, communication, alerts audit,
# and dataset provenance (additive extensions)
# =====================================================================

class HealthMeasurement(Base):
    """Dated health measurement history for a beneficiary (not just latest)."""

    __tablename__ = "health_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit_records.id"), nullable=True, index=True)
    # e.g. height_cm, weight_kg, bmi, bp_sys, bp_dia, pulse_bpm, temperature_c, spo2, blood_glucose_mgdl
    measurement_type: Mapped[str] = mapped_column(String(48), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str] = mapped_column(String(64), default="")  # e.g. "120/80"
    unit: Mapped[str] = mapped_column(String(32), default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # voice/manual/ocr/import/device
    recorded_by_worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # recorded | pending_verification | verified | entered_in_error (historical/audited; not deleted)
    verification_status: Mapped[str] = mapped_column(String(24), default="recorded")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="measurements")
    visit: Mapped["VisitRecord | None"] = relationship(back_populates="measurements")
    audits: Mapped[list["MeasurementAudit"]] = relationship(
        back_populates="measurement", cascade="all, delete-orphan"
    )


class MeasurementAudit(Base):
    """Audit history for measurement edits."""

    __tablename__ = "measurement_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    measurement_id: Mapped[int] = mapped_column(ForeignKey("health_measurements.id"), index=True)
    action: Mapped[str] = mapped_column(String(16), default="update")  # create/update
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    measurement: Mapped[HealthMeasurement] = relationship(back_populates="audits")


class UploadedDocument(Base):
    """Uploaded health cards/documents with review metadata."""

    __tablename__ = "uploaded_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int | None] = mapped_column(ForeignKey("beneficiaries.id"), nullable=True, index=True)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(256), default="")
    stored_filename: Mapped[str] = mapped_column(String(256), default="")
    storage_path: Mapped[str] = mapped_column(String(512), default="")
    mime_type: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(64), default="other")  # prescription/lab_report/blood_test/scan/vaccination_card/pregnancy_record/other
    # upload | camera
    upload_source: Mapped[str] = mapped_column(String(16), default="upload")
    ocr_status: Mapped[str] = mapped_column(String(24), default="not_run")  # not_run/pending/done/failed/not_available
    extracted_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    qr_data: Mapped[str] = mapped_column(String(256), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    delete_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped["Beneficiary | None"] = relationship(back_populates="documents")
    household: Mapped["Household | None"] = relationship(back_populates="documents")


class CarePlanTask(Base):
    """My Health Plan tasks for a beneficiary."""

    __tablename__ = "care_plan_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("beneficiaries.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(48), default="general")  # checkup/followup/vaccination/education/referral
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low/normal/high
    responsible: Mapped[str] = mapped_column(String(32), default="asha")  # asha/beneficiary/household/doctor
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)  # pending/completed/missed/cancelled/rescheduled
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="care_plan_tasks")


class PatientRequest(Base):
    """Connect with My ASHA: requests, concerns, and feedback from beneficiaries/households."""

    __tablename__ = "patient_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int | None] = mapped_column(ForeignKey("beneficiaries.id"), nullable=True, index=True)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    assigned_worker_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True, index=True)
    requester_type: Mapped[str] = mapped_column(String(24), default="beneficiary")  # beneficiary/household
    # callback|health_concern|visit_request|missed_followup|pregnancy_concern|vaccination_info|emergency|feedback|help|record_correction|contact_correction
    category: Mapped[str] = mapped_column(String(48), index=True)
    subject: Mapped[str] = mapped_column(String(256), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low/normal/high/urgent
    # submitted|received|acknowledged|in_progress|resolved|closed
    status: Mapped[str] = mapped_column(String(24), default="submitted", index=True)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 for feedback
    response_note: Mapped[str] = mapped_column(Text, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    beneficiary: Mapped["Beneficiary | None"] = relationship(back_populates="requests")
    household: Mapped["Household | None"] = relationship(back_populates="requests")


class AlertAuditLog(Base):
    """Audit trail for danger alert lifecycle actions."""

    __tablename__ = "alert_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("danger_alerts.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))  # created/acknowledged/escalated/resolved/note
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(64), default="system")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    alert: Mapped[DangerAlert] = relationship(back_populates="audit_events")


# =====================================================================
# RESEARCH / PUBLIC DATASET INTEGRATIONS (separate from operational records)
# =====================================================================


class DatasetImport(Base):
    """Provenance/metadata for a recovered public/research dataset import."""

    __tablename__ = "dataset_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(512))
    license_info: Mapped[str] = mapped_column(String(256))
    classification: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str] = mapped_column(Text, default="")
    mapping_info: Mapped[str] = mapped_column(Text, default="")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    dataset_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_documentation: Mapped[str] = mapped_column(String(512), default="")
    survey_year: Mapped[str] = mapped_column(String(64), default="")
    survey_cycle: Mapped[str] = mapped_column(String(64), default="")
    geographical_coverage: Mapped[str] = mapped_column(String(256), default="")
    country: Mapped[str] = mapped_column(String(64), default="")
    file_name: Mapped[str] = mapped_column(String(256), default="")
    file_format: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(24), default="completed")
    validation_errors: Mapped[str] = mapped_column(Text, default="[]")
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)

    observations: Mapped[list["PublicDatasetObservation"]] = relationship(
        back_populates="dataset_import", cascade="all, delete-orphan"
    )


class PublicDatasetObservation(Base):
    """Research/aggregate observation records recovered from public datasets.

    These are NOT operational ASHA beneficiary/household/visit records.
    """

    __tablename__ = "public_dataset_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("dataset_imports.id"), index=True)
    dataset_key: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(512))
    survey_year: Mapped[str] = mapped_column(String(64), default="")
    survey_cycle: Mapped[str] = mapped_column(String(64), default="")
    geographical_coverage: Mapped[str] = mapped_column(String(256), default="")
    country: Mapped[str] = mapped_column(String(64), default="")
    indicator_group: Mapped[str] = mapped_column(String(64), default="", index=True)
    indicator_name: Mapped[str] = mapped_column(String(256), default="")
    indicator_code: Mapped[str] = mapped_column(String(128), default="", index=True)
    record_type: Mapped[str] = mapped_column(String(32), default="")
    source_record_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    values_json: Mapped[str] = mapped_column(Text, default="{}")
    data_origin: Mapped[str] = mapped_column(String(32), default="", index=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="")
    import_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    dataset_import: Mapped[DatasetImport] = relationship(back_populates="observations")


class SyntheticVoiceAnalysis(Base):
    """Preserved historical synthetic-voice analysis records (decommissioned feature data).

    Stored for data-preservation/recovery fidelity only; not an active operational workflow.
    """

    __tablename__ = "synthetic_voice_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("asha_workers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(256), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    sample_rate: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(32), default="", index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    indicators: Mapped[str] = mapped_column(Text, default="[]")
    quality_notes: Mapped[str] = mapped_column(Text, default="[]")
    language: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)



class HealthFacility(Base):
    __tablename__ = "health_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    facility_type: Mapped[str] = mapped_column(String(64), default="PHC")  # PHC/CHC/Hospital/Clinic
    address: Mapped[str] = mapped_column(String(256), default="")
    village: Mapped[str] = mapped_column(String(128), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_source: Mapped[str] = mapped_column(String(64), default="")  # verified_import|manual_verified
    verification_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|verified|rejected
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("asha_workers.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
