"""Pydantic v2 schemas: request bodies and response models for the REST API."""
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------- Auth ----------
class LoginRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    language: Optional[str] = None


class WorkerOut(BaseModel):
    id: int
    name: str
    worker_id: str
    role: str = "asha"
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
    email: Optional[str] = None
    lmp_date: Optional[date] = None
    birth_date: Optional[date] = None
    date_of_birth: Optional[date] = None
    household_id: Optional[int] = None
    assigned_worker_id: Optional[int] = None
    pregnancy_status: str = ""
    medical_conditions: str = ""
    allergies: str = ""
    current_medications: str = ""
    child_health_notes: str = ""
    registration_notes: str = ""
    emergency_contact: str = ""
    emergency_contact_consent: bool = False
    verification_status: str = "asha_verified"


class BeneficiaryUpdate(BaseModel):
    """Profile edits made by the ASHA worker (review/add/update)."""

    name: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=120)
    category: Optional[str] = None
    gender: Optional[str] = None
    village: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    lmp_date: Optional[date] = None
    birth_date: Optional[date] = None
    date_of_birth: Optional[date] = None
    household_id: Optional[int] = None
    assigned_worker_id: Optional[int] = None
    pregnancy_status: Optional[str] = None
    medical_conditions: Optional[str] = None
    allergies: Optional[str] = None
    current_medications: Optional[str] = None
    child_health_notes: Optional[str] = None
    registration_notes: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_contact_consent: Optional[bool] = None
    verification_status: Optional[str] = None

    @field_validator("category")
    @classmethod
    def _normalise_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cat = (v or "").strip().lower()
        if cat not in BENEFICIARY_CATEGORIES:
            raise ValueError(
                "category must be one of: " + ", ".join(BENEFICIARY_CATEGORIES)
            )
        return cat


class BeneficiaryOut(BaseModel):
    id: int
    qr_id: str
    name: str
    age: int
    category: str
    gender: str = ""
    village: str
    address: str = ""
    phone: Optional[str] = None
    email: Optional[str] = None
    date_of_birth: Optional[date] = None
    birth_date: Optional[date] = None
    lmp_date: Optional[date] = None
    household_id: Optional[int] = None
    assigned_worker_id: Optional[int] = None
    pregnancy_status: str = ""
    medical_conditions: str = ""
    allergies: str = ""
    current_medications: str = ""
    child_health_notes: str = ""
    registration_notes: str = ""
    emergency_contact: str = ""
    emergency_contact_consent: bool = False
    data_origin: str = "registered"
    verification_status: str = "asha_verified"
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
    measurements: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    pregnancy_records: list[dict[str, Any]] = Field(default_factory=list)
    newborn_records: list[dict[str, Any]] = Field(default_factory=list)
    immunisation_records: list[dict[str, Any]] = Field(default_factory=list)
    household: Optional[dict[str, Any]] = None
    care_plan_tasks: list[dict[str, Any]] = Field(default_factory=list)
    requests: list[dict[str, Any]] = Field(default_factory=list)


class QrResponse(BaseModel):
    qr_id: str
    data_url: str


# ---------- Visits ----------
class SaveConfirmation(BaseModel):
    confirmed: bool = False
    method: str = "voice"  # "voice" | "ui_fallback"
    phrase: str = ""
    confirmed_at: Optional[str] = None


class VisitCreate(BaseModel):
    beneficiary_id: int
    structured: dict[str, Any] = Field(default_factory=dict)
    transcript: str = ""
    language: str = "en"
    # Optional visit type override for community-wide visits recorded for a
    # registered beneficiary: "nutrition" | "community" | "followup".
    visit_type: Optional[str] = None
    confirmation: Optional[SaveConfirmation] = None
    idempotency_key: Optional[str] = None
    corrections: list[dict[str, Any]] = Field(default_factory=list)


class AlertOut(BaseModel):
    id: int
    beneficiary_id: int
    beneficiary_name: Optional[str] = None
    beneficiary_data_origin: str = "registered"
    is_synthetic_demo: bool = False
    household_id: Optional[int] = None
    household_name: str = ""
    visit_id: Optional[int] = None
    # Detected danger sign / triggering approved phrase (rule-based)
    phrase: str = ""
    triggering_phrase: str = ""
    detected_danger_sign: str = ""
    rule_id: str = ""
    rule_version: str = ""
    clinical_source: str = ""
    message: str = ""
    severity: str = ""
    status: str
    alert_category: str = ""
    trigger_detail: str = ""
    trigger_value: str = ""
    triggering_event: str = ""
    # Source observation or visit context (factual)
    source_observation: str = ""
    reason: str = ""
    recommended_action: str = ""
    assigned_worker_id: Optional[int] = None
    escalation_note: str = ""
    resolved_note: str = ""
    referral_facility: str = ""
    referral_date: Optional[date] = None
    referral_note: str = ""
    referred_at: Optional[datetime] = None
    referred_by_worker_id: Optional[int] = None
    referral_pending: bool = False
    dismiss_reason: str = ""
    detection_timestamp: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    generated_at: Optional[datetime] = None


class AlertListResponse(BaseModel):
    alerts: list[AlertOut] = Field(default_factory=list)
    total: Optional[int] = None
    counts: dict[str, int] = Field(default_factory=dict)


class AlertSummaryResponse(BaseModel):
    total: int = 0
    new: int = 0
    unresolved: int = 0
    in_progress: int = 0
    escalated: int = 0
    referred: int = 0
    referral_pending: int = 0
    resolved: int = 0
    dismissed: int = 0
    high_critical_unresolved: int = 0
    counts: dict[str, int] = Field(default_factory=dict)


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
    alert_generation_error: Optional[str] = None


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
    provider: Optional[str] = None
    mime_type: Optional[str] = None


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
    # Persisted task fields (for task-management integrations)
    id: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_worker_id: Optional[int] = None
    assigned_worker_name: Optional[str] = None


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
    due_followups: int = 0
    overdue_followups: int
    completed_followups: int = 0
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
    asha_beneficiary_statistics: Optional[dict[str, Any]] = None
    research_data_statistics: Optional[dict[str, Any]] = None
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
    data_origin: str = "registered"
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


# ---------- Voice recording sessions & extracted visits ----------
class SessionCreate(BaseModel):
    """Open (or re-attach to) a recording session."""
    client_session_id: str
    language: str = "en"
    provider: str = ""
    transcript: str = ""
    duration_ms: int = 0
    mode: str = "demo"


class ExtractedVisitOut(BaseModel):
    temp_id: str
    visit_id: str = ""
    beneficiary_id: Optional[int] = None
    beneficiary_name: Optional[str] = None
    household_id: Optional[int] = None
    household_label: Optional[str] = None
    category: str = "general"
    visit_date: Optional[date] = None
    raw_structured: dict[str, Any] = Field(default_factory=dict)
    personal_details: dict[str, Any] = Field(default_factory=dict)
    measurements: dict[str, Any] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    follow_ups: list[dict[str, Any]] = Field(default_factory=list)
    # "resolved" | "ambiguous" | "unresolved" | "new"
    identity_status: str = "unresolved"
    identity_reason: str = ""
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    clarification_required: bool = False
    status: str = "pending"
    boundary_reason: str = ""
    segment_index: int = 0


class SessionOut(BaseModel):
    id: int
    client_session_id: str
    language: str
    status: str
    transcript: str = ""
    mode: str = "demo"
    duration_ms: int = 0
    scenario: Optional[str] = None
    visits: list[ExtractedVisitOut] = Field(default_factory=list)
    household_visits: list[dict[str, Any]] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    danger_flags: list[dict[str, Any]] = Field(default_factory=list)


class SessionExtractResponse(SessionOut):
    """The session after segmentation, extraction and identity resolution."""


class VisitPatch(BaseModel):
    """The ASHA worker editing one extracted visit."""
    temp_id: Optional[str] = None
    beneficiary_id: Optional[int] = None
    beneficiary_name: Optional[str] = None
    household_id: Optional[int] = None
    category: Optional[str] = None
    visit_date: Optional[date] = None
    raw_structured: Optional[dict[str, Any]] = None
    status: Optional[str] = None          # "pending" | "confirmed" | "rejected"


class SessionSaveRequest(BaseModel):
    visits: list[VisitPatch] = Field(default_factory=list)
    household_visits: list[dict[str, Any]] = Field(default_factory=list)
    confirmation: Optional[SaveConfirmation] = None
    idempotency_key: Optional[str] = None


class SessionSaveResponse(BaseModel):
    session_id: int
    saved_visits: list[dict[str, Any]] = Field(default_factory=list)
    saved_household_visits: list[dict[str, Any]] = Field(default_factory=list)
    skipped_visits: list[dict[str, Any]] = Field(default_factory=list)
    total_saved: int = 0
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    alert_generation_error: Optional[str] = None


# ---------- Notifications ----------
class SmsNotificationOut(BaseModel):
    id: int
    beneficiary_id: int
    type: str = "anc"
    phone: str = ""
    body: str = ""
    language: str = "en"
    # "pending" | "submitted" | "delivered" | "failed" | "unknown" | "demo"
    status: str = "pending"
    provider_note: str = ""
    is_demo: bool = True
    created_at: datetime
    sent_at: Optional[datetime] = None


class SmsNotificationListResponse(BaseModel):
    notifications: list[SmsNotificationOut] = Field(default_factory=list)


class PdfReportOut(BaseModel):
    id: int
    beneficiary_id: int
    filename: str = ""
    size_bytes: int = 0
    generated_at: datetime


class PdfReportListResponse(BaseModel):
    reports: list[PdfReportOut] = Field(default_factory=list)


class NotificationStats(BaseModel):
    sms_total: int = 0
    sms_demo: int = 0
    sms_real: int = 0
    pending: int = 0
    failed: int = 0
    pdf_reports: int = 0
    upcoming_followups: int = 0
    sms_provider_configured: bool = False
    sms_enabled: bool = True
    sms_provider: str = "demo"


# ---------- Synthetic voice verification ----------
# ---------- Follow-ups (Pulse Drift task management) ----------
class FollowUpCreate(BaseModel):
    beneficiary_id: Optional[int] = None
    household_id: Optional[int] = None
    visit_id: Optional[int] = None
    type: str = "general"
    category: str = ""
    due_date: date
    priority: str = "normal"
    status: str = "upcoming"
    reason: str = ""
    description: str = ""
    recommended_action: str = ""
    assigned_worker_id: Optional[int] = None
    notes: str = ""
    source_type: str = "manual"
    source_id: Optional[int] = None
    source_ref: str = ""


class FollowUpUpdate(BaseModel):
    beneficiary_id: Optional[int] = None
    household_id: Optional[int] = None
    visit_id: Optional[int] = None
    type: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    description: Optional[str] = None
    recommended_action: Optional[str] = None
    assigned_worker_id: Optional[int] = None
    notes: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    source_ref: Optional[str] = None


class FollowUpStatusAction(BaseModel):
    note: str = ""
    notes: str = ""  # alias for completion/cancel/reschedule notes
    reason: str = ""  # cancellation reason
    due_date: Optional[date] = None
    priority: Optional[str] = None
    assigned_worker_id: Optional[int] = None


class FollowUpHistoryOut(BaseModel):
    id: int
    followup_id: int
    action: str
    from_status: str = ""
    to_status: str = ""
    note: str = ""
    actor_id: Optional[int] = None
    actor_label: str = "system"
    changed_at: datetime


class FollowUpOut(BaseModel):
    id: int
    beneficiary_id: Optional[int] = None
    beneficiary_name: Optional[str] = None
    household_id: Optional[int] = None
    household_label: Optional[str] = None
    visit_id: Optional[int] = None
    type: str = ""
    category: str = ""
    reason: str = ""
    description: str = ""
    recommended_action: str = ""
    due_date: Optional[date] = None
    priority: str = "normal"
    assigned_worker_id: Optional[int] = None
    assigned_worker_name: Optional[str] = None
    status: str = "upcoming"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    completion_notes: str = ""
    cancellation_reason: str = ""
    notes: str = ""
    source_type: str = ""
    source_id: Optional[int] = None
    source_ref: str = ""
    rescheduled_from: Optional[date] = None
    # Computed helpers for UI
    overdue_days: int = 0


class FollowUpListResponse(BaseModel):
    items: list[FollowUpOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    counts: dict[str, int] = Field(default_factory=dict)


class FollowUpHistoryResponse(BaseModel):
    followup_id: int
    history: list[FollowUpHistoryOut] = Field(default_factory=list)



