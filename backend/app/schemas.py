"""Pydantic v2 schemas: request bodies and response models for the REST API."""
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------- Auth ----------
class LoginRequest(BaseModel):
    worker_id: str
    password: str
    language: Optional[str] = None


class WorkerOut(BaseModel):
    id: int
    name: str
    worker_id: str
    language: str
    phc: str


class LoginResponse(BaseModel):
    token: str
    worker: WorkerOut


# ---------- Beneficiaries ----------
# Canonical health categories. The UI may send any capitalisation; we always
# normalise to lowercase so that filtering and lookups stay consistent.
BENEFICIARY_CATEGORIES: tuple[str, ...] = (
    "pregnancy",
    "newborn",
    "child",
    "immunisation",
    "elderly",
    "nutrition",
    "adolescent",
    "community",
    "general",
)


class BeneficiaryCreate(BaseModel):
    name: str
    age: int = Field(default=0, ge=0, le=120)
    category: str

    @field_validator("category")
    @classmethod
    def _normalise_category(cls, v: str) -> str:
        cat = (v or "").strip().lower()
        if cat not in BENEFICIARY_CATEGORIES:
            raise ValueError(
                "category must be one of: " + ", ".join(BENEFICIARY_CATEGORIES)
            )
        return cat

    gender: str = ""
    village: str = ""
    address: str = ""
    phone: Optional[str] = None
    lmp_date: Optional[date] = None
    birth_date: Optional[date] = None


class BeneficiaryOut(BaseModel):
    id: int
    qr_id: str
    name: str
    age: int
    category: str
    gender: str = ""
    village: str
    address: str = ""
    last_visit_date: Optional[date] = None
    next_followup_date: Optional[date] = None
    status: str = "ok"


class BeneficiaryListResponse(BaseModel):
    beneficiaries: list[BeneficiaryOut]


class BeneficiaryDetailResponse(BaseModel):
    beneficiary: BeneficiaryOut
    visits: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    followups: list[dict[str, Any]]


class QrResponse(BaseModel):
    qr_id: str
    data_url: str


# ---------- Visits ----------
class VisitCreate(BaseModel):
    beneficiary_id: int
    structured: dict[str, Any] = Field(default_factory=dict)
    transcript: str = ""
    language: str = "en"
    # Optional visit type override for community-wide visits recorded for a
    # registered beneficiary: "nutrition" | "community" | "followup".
    visit_type: Optional[str] = None


class AlertOut(BaseModel):
    id: int
    beneficiary_id: int
    beneficiary_name: Optional[str] = None
    phrase: str
    rule_id: str
    message: str
    severity: str
    status: str
    created_at: datetime


class AlertListResponse(BaseModel):
    alerts: list[AlertOut]


class VisitOut(BaseModel):
    id: int
    beneficiary_id: int
    visit_date: date
    category: str
    source: str
    structured: dict[str, Any]


class VisitCreateResponse(BaseModel):
    visit: VisitOut
    alerts: list[AlertOut]
    follow_up: Optional[dict[str, Any]] = None


class BatchVisitItem(BaseModel):
    beneficiary_id: Optional[int] = None
    beneficiary_name: Optional[str] = None
    category: Optional[str] = None
    village: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    create_if_missing: bool = True
    structured: dict[str, Any] = Field(default_factory=dict)
    transcript: str = ""
    language: str = "en"
    visit_type: Optional[str] = None
    household_id: Optional[int] = None


class BatchVisitCreate(BaseModel):
    visits: list[BatchVisitItem]
    household_visits: list[dict[str, Any]] = Field(default_factory=list)


class BatchVisitResponse(BaseModel):
    saved_visits: list[dict[str, Any]]
    saved_household_visits: list[dict[str, Any]] = Field(default_factory=list)
    total_saved: int
    alerts: list[AlertOut] = Field(default_factory=list)


# ---------- Voice ----------
class ExtractRequest(BaseModel):
    transcript: str
    language: str = "en"


class ExtractResponse(BaseModel):
    structured: dict[str, Any]
    danger_flags: list[dict[str, Any]]
    mode: str


class VisitEntityOut(BaseModel):
    visit_id: str
    beneficiary_name: Optional[str] = None
    beneficiary_id: Optional[int] = None
    category: str = "general"
    visit_category: str = "general"
    household_id: Optional[str] = None
    personal_details: dict[str, Any] = Field(default_factory=dict)
    maternal_health: dict[str, Any] = Field(default_factory=dict)
    child_health: dict[str, Any] = Field(default_factory=dict)
    measurements: dict[str, Any] = Field(default_factory=dict)
    nutrition: dict[str, Any] = Field(default_factory=dict)
    immunisation: dict[str, Any] = Field(default_factory=dict)
    elderly_health: dict[str, Any] = Field(default_factory=dict)
    household_obs: dict[str, Any] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    follow_ups: list[dict[str, Any]] = Field(default_factory=list)
    raw_structured: dict[str, Any] = Field(default_factory=dict)


class HouseholdVisitEntityOut(BaseModel):
    household_id: Optional[str] = None
    household_observations: dict[str, Any] = Field(default_factory=dict)
    member_references: list[dict[str, Any]] = Field(default_factory=list)


class ExtractMultiResponse(BaseModel):
    session_id: str
    visits: list[VisitEntityOut]
    household_visits: list[HouseholdVisitEntityOut] = Field(default_factory=list)
    community_activities: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    danger_flags: list[dict[str, Any]] = Field(default_factory=list)
    mode: str
    scenario: Optional[str] = None


class TtsRequest(BaseModel):
    text: str
    language: str = "en"


class TtsResponse(BaseModel):
    mode: str
    audio_base64: Optional[str] = None


# ---------- Drift ----------
class DriftItem(BaseModel):
    beneficiary_id: Optional[int] = None
    household_id: Optional[int] = None
    name: str
    category: str
    issue: str
    # Machine-readable issue code + parameters so the UI can localise the
    # deterministic rule message without re-implementing the rules.
    issue_code: str = ""
    issue_params: dict[str, Any] = Field(default_factory=dict)
    issue_action_code: str = ""
    due_date: Optional[date] = None
    overdue_days: int = 0
    recommended_action: str


class DriftResponse(BaseModel):
    items: list[DriftItem]


# ---------- Reminders ----------
class ReminderCreate(BaseModel):
    beneficiary_id: int
    type: str
    due_date: date


class ReminderOut(BaseModel):
    id: int
    beneficiary_id: int
    beneficiary_name: Optional[str] = None
    type: str
    message: str
    due_date: date
    status: str
    # Delivery status of the message itself (scheduled | sent | demo_sent | ...).
    sms_status: str = ""
    sms_consent: bool


class ReminderListResponse(BaseModel):
    reminders: list[ReminderOut]


# ---------- Alerts ack ----------
class AckResponse(BaseModel):
    status: str


# ---------- Dashboard ----------
class DashboardStats(BaseModel):
    total_beneficiaries: int
    total_households: int = 0
    todays_visits: int
    upcoming_followups: int
    overdue_followups: int
    active_alerts: int


class ScheduleItem(BaseModel):
    time: str
    beneficiary_name: str
    type: str
    village: str


class ActivityItem(BaseModel):
    beneficiary_name: str
    action: str
    # Machine-readable action code so the UI can localise the sentence.
    action_code: str = ""
    date: date
    category: str


class ReminderItem(BaseModel):
    id: int
    beneficiary_name: str
    type: str
    due_date: date
    sms_status: str
    status: str = ""


class AlertItem(BaseModel):
    id: int
    beneficiary_name: str
    phrase: str
    message: str
    severity: str
    created_at: datetime


class VoiceItem(BaseModel):
    beneficiary_name: Optional[str] = None
    date: date
    language: str
    status: str


class DashboardResponse(BaseModel):
    stats: DashboardStats
    schedule: list[ScheduleItem]
    recent_activity: list[ActivityItem]
    reminders: list[ReminderItem]
    alerts: list[AlertItem]
    recent_voice: list[VoiceItem]


# ---------- Households ----------
class HouseholdMemberCreate(BaseModel):
    name: str
    age: int = Field(ge=0, le=120, default=0)
    gender: str = ""
    relation: str = ""
    beneficiary_id: Optional[int] = None


class HouseholdCreate(BaseModel):
    village: str
    address: str = ""
    member_count: int = Field(ge=0, le=30, default=0)
    members: list[HouseholdMemberCreate] = Field(default_factory=list)


class HouseholdMemberOut(BaseModel):
    id: int
    name: str
    age: int
    gender: str
    relation: str
    beneficiary_id: Optional[int] = None


class HouseholdOut(BaseModel):
    id: int
    qr_id: str
    village: str
    address: str
    member_count: int
    last_visit_date: Optional[date] = None
    next_followup_date: Optional[date] = None
    status: str = "ok"


class HouseholdListResponse(BaseModel):
    households: list[HouseholdOut]


class HouseholdDetailResponse(BaseModel):
    household: HouseholdOut
    members: list[HouseholdMemberOut]
    visits: list[dict[str, Any]]
    followups: list[dict[str, Any]]


class HouseholdVisitCreate(BaseModel):
    structured: dict[str, Any] = Field(default_factory=dict)
    transcript: str = ""
    language: str = "en"
