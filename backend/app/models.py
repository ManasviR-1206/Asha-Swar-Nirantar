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
    lmp_date: Mapped[date | None] = mapped_column(Date, nullable=True)      # last menstrual period (pregnancy)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)    # extra optional field (newborn)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    visits: Mapped[list["VisitRecord"]] = relationship(back_populates="beneficiary")
    alerts: Mapped[list["DangerAlert"]] = relationship(back_populates="beneficiary")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="beneficiary")
    reminders: Mapped[list["SmsReminder"]] = relationship(back_populates="beneficiary")
    member_of: Mapped["HouseholdMember | None"] = relationship(back_populates="beneficiary", uselist=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="visits")
    transcripts: Mapped[list["VoiceTranscript"]] = relationship(back_populates="visit")
    fields: Mapped[list["ExtractedField"]] = relationship(back_populates="visit", cascade="all, delete-orphan")
    pregnancy: Mapped["PregnancyRecord | None"] = relationship(back_populates="visit", uselist=False)
    newborn: Mapped["NewbornRecord | None"] = relationship(back_populates="visit", uselist=False)
    immunisation: Mapped["ImmunisationRecord | None"] = relationship(back_populates="visit", uselist=False)


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
    message: Mapped[str] = mapped_column(String(256))  # "Refer to PHC as per approved guidelines."
    # "high" | "medium"
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    # "open" | "acknowledged"
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped[Beneficiary] = relationship(back_populates="alerts")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Beneficiary follow-ups have beneficiary_id set; household hygiene
    # follow-ups have household_id set instead.
    beneficiary_id: Mapped[int | None] = mapped_column(ForeignKey("beneficiaries.id"), nullable=True, index=True)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit_records.id"), nullable=True)
    # "anc" | "vaccination" | "newborn" | "nutrition" | "household" | "community"
    type: Mapped[str] = mapped_column(String(32))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    # "upcoming" | "overdue" | "done" | "missed"
    status: Mapped[str] = mapped_column(String(16), default="upcoming", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    beneficiary: Mapped["Beneficiary | None"] = relationship(back_populates="followups")
    household: Mapped["Household | None"] = relationship(back_populates="followups")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["HouseholdMember"]] = relationship(back_populates="household", cascade="all, delete-orphan")
    visits: Mapped[list["HouseholdVisit"]] = relationship(back_populates="household", cascade="all, delete-orphan")
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="household")


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
