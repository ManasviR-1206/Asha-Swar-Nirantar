"""Deterministic rules engines for ASHA SWAR NIRANTAR.

IMPORTANT DESIGN RULE: the LLM (Gnani extraction) NEVER decides alerts.
Only these deterministic, fully auditable rule lists can raise a danger
alert or a follow-up flag. Both engines are pure functions over the DB /
transcript so they are reproducible and reviewable by health officials.

Engines:
1. Danger-sign engine   — approved phrase lists + negation handling.
2. Follow-up drift engine — ANC / immunisation / newborn schedules,
   plus "missing record for verification" flags (these are record-keeping
   gaps, NOT medical claims).
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

# =====================================================================
# 1) DANGER-SIGN ENGINE
# =====================================================================

# Approved phrase lists (documented constants). Each entry is a variant of
# a danger sign; tuple = (rule_id, exact phrase to match, severity).
# rule_id groups variants of the same clinical sign.
PREGNANCY_DANGER_PHRASES: list[tuple[str, str, str]] = [
    ("PREG-01", "heavy bleeding", "high"),
    ("PREG-01", "bleeding heavily", "high"),
    ("PREG-02", "severe headache", "high"),
    ("PREG-03", "blurred vision", "medium"),
    ("PREG-04", "convulsions", "high"),
    ("PREG-04", "fits", "high"),
    ("PREG-05", "swelling of hands or face", "medium"),
    ("PREG-05", "swelling of hands", "medium"),
    ("PREG-05", "swelling of face", "medium"),
    ("PREG-05", "swelling on face", "medium"),
    ("PREG-06", "difficulty breathing", "high"),
    ("PREG-07", "fever for more than two days", "high"),
    ("PREG-07", "fever for two days", "medium"),
    ("PREG-07", "fever for 2 days", "medium"),
    ("PREG-08", "severe abdominal pain", "high"),
    ("PREG-09", "reduced fetal movement", "high"),
    ("PREG-09", "reduced fetal movements", "high"),
    ("PREG-10", "persistent vomiting", "medium"),
    ("PREG-11", "leaking fluid", "high"),
    ("PREG-12", "labour pains before 37 weeks", "high"),
    ("PREG-12", "labor pains before 37 weeks", "high"),
]

NEWBORN_DANGER_PHRASES: list[tuple[str, str, str]] = [
    ("NEWB-01", "fever", "high"),
    ("NEWB-02", "poor feeding", "high"),
    ("NEWB-02", "poor sucking", "high"),
    ("NEWB-03", "lethargy", "high"),
    ("NEWB-03", "very sleepy", "high"),
    ("NEWB-04", "fast breathing", "high"),
    ("NEWB-05", "chest indrawing", "high"),
    ("NEWB-06", "cyanosis", "high"),
    ("NEWB-06", "bluish body", "high"),
    ("NEWB-07", "jaundice within 24 hours of birth", "high"),
    ("NEWB-07", "jaundice within 24 hours", "high"),
    ("NEWB-08", "umbilical stump discharge", "medium"),
    ("NEWB-08", "umbilical stump redness", "medium"),
    ("NEWB-09", "cold body", "high"),
    ("NEWB-09", "hypothermia", "high"),
    ("NEWB-10", "fewer than 5 wet diapers a day", "medium"),
    ("NEWB-10", "fewer than 5 wet diapers", "medium"),
    ("NEWB-10", "less than 5 wet diapers", "medium"),
    ("NEWB-11", "persistent crying", "medium"),
]

REFERRAL_MESSAGE = "Refer to PHC as per approved guidelines."

# Negation words: if any appears within NEGATION_WINDOW tokens *before* the
# matched phrase, the phrase is treated as NOT reported.
NEGATION_TOKENS = {"no", "not", "without", "denies", "never", "none", "nothing"}
NEGATION_WINDOW = 6  # tokens before the phrase

_TOKEN_SPLIT = re.compile(r"[\s,.;:!?()\-]+")


def _negated(text_lower: str, match_start: int) -> bool:
    """True when a negation word sits within the last ~6 tokens before the match."""
    prefix_tokens = [t for t in _TOKEN_SPLIT.split(text_lower[:match_start]) if t]
    window = prefix_tokens[-NEGATION_WINDOW:]
    return any(tok in NEGATION_TOKENS for tok in window)


def detect_danger_signs(transcript: str, category: str | None = None) -> list[dict]:
    """Scan a transcript for approved danger-sign phrases.

    Matching: case-insensitive whole-word/phrase matching (word boundaries,
    so "fits" does not match "benefits"). Negation within the previous 6
    tokens suppresses the match ("no fever", "denies severe headache").

    Returns a list of:
        {rule_id, phrase, message, severity}
    where `phrase` is the EXACT triggering text as it appeared in the input.
    """
    if not transcript or not transcript.strip():
        return []
    text_lower = transcript.lower()

    if category == "pregnancy":
        phrase_lists = [PREGNANCY_DANGER_PHRASES]
    elif category in ("newborn", "child", "immunisation"):
        phrase_lists = [NEWBORN_DANGER_PHRASES]
    else:
        phrase_lists = [PREGNANCY_DANGER_PHRASES, NEWBORN_DANGER_PHRASES]

    flags: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    for phrases in phrase_lists:
        for rule_id, phrase, severity in phrases:
            pattern = rf"\b{re.escape(phrase)}\b"
            for m in re.finditer(pattern, text_lower):
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                if _negated(text_lower, m.start()):
                    continue  # negated — do NOT trigger
                flags.append(
                    {
                        "rule_id": rule_id,
                        "phrase": transcript[m.start():m.end()],
                        "message": REFERRAL_MESSAGE,
                        "severity": severity,
                    }
                )
    # Stable order: as they appear in the transcript.
    flags.sort(key=lambda f: text_lower.find(f["phrase"].lower()))
    return flags


# =====================================================================
# 2) FOLLOW-UP DRIFT ENGINE
# =====================================================================

# --- Schedule constants (documented, deterministic) ------------------
ANC_INTERVAL_WEEKS_LT_28 = 4      # checkups every 4 weeks until 28 weeks
ANC_INTERVAL_WEEKS_28_36 = 2      # every 2 weeks between 28 and 36 weeks
ANC_INTERVAL_WEEKS_36_40 = 1      # every week between 36 and 40 weeks

NEWBORN_CHECKUP_DAYS = [3, 7, 42]                  # day 3, day 7, 6 weeks
NEWBORN_MONTHLY_DAYS = list(range(72, 366, 30))    # then monthly until 1 year
NEWBORN_ALL_CHECKUP_DAYS = sorted(set(NEWBORN_CHECKUP_DAYS + NEWBORN_MONTHLY_DAYS))

# Immunisation schedule (days after birth):
#   BCG + OPV-0 at birth; Penta/OPV/Rota at 6, 10, 14 weeks; MR at 9-12 months.
VACCINE_SCHEDULE_DAYS: dict[str, int] = {
    "BCG": 0,
    "OPV-0": 0,
    "PENTA-1": 42,
    "PENTA-2": 70,
    "PENTA-3": 98,
    "MR": 270,
}

VACCINE_NEXT: dict[str, tuple[str, int] | None] = {
    # vaccine (uppercase) -> (next vaccine, next due day after birth)
    "BCG": ("PENTA-1", 42),
    "OPV-0": ("PENTA-1", 42),
    "PENTA-1": ("PENTA-2", 70),
    "PENTA-2": ("PENTA-3", 98),
    "PENTA-3": ("MR", 270),
    "MR": None,
}


def anc_interval_days(weeks_pregnant: int) -> int:
    """Required gap between ANC checkups at a given gestational age (days)."""
    if weeks_pregnant < 28:
        return ANC_INTERVAL_WEEKS_LT_28 * 7
    if weeks_pregnant < 36:
        return ANC_INTERVAL_WEEKS_28_36 * 7
    return ANC_INTERVAL_WEEKS_36_40 * 7


def next_anc_due(visit_date: date, weeks_pregnant: int) -> date:
    """Next ANC due date after a visit at a given gestational week."""
    return visit_date + timedelta(days=anc_interval_days(weeks_pregnant))


def next_newborn_due(birth_date: date, last_visit_date: date) -> date | None:
    """Next newborn checkup due after the latest visit.

    Checkups: within 24h of birth, day 3, day 7, 6 weeks, then monthly
    to 1 year. A checkup on day D is considered covered by the last visit
    if the visit happened within D..D+2 (small grace window).
    """
    age_days = (last_visit_date - birth_date).days
    for day in NEWBORN_ALL_CHECKUP_DAYS:
        if day > age_days + 2:  # first checkup not yet covered by a visit
            return birth_date + timedelta(days=day)
    return None  # past 1 year — routine child care takes over


def next_vaccine_due(vaccine_name: str, birth_date: date) -> date | None:
    """Next vaccination due date after a given vaccine was administered."""
    nxt = VACCINE_NEXT.get(vaccine_name.strip().upper())
    if not nxt:
        return None
    _, days = nxt
    return birth_date + timedelta(days=days)


def weeks_pregnant_on(birth_or_lmp: date, on_date: date) -> int:
    """Gestational weeks on a given date, computed from the LMP date."""
    return max(0, (on_date - birth_or_lmp).days // 7)


def run_drift_engine(db) -> list[dict]:
    """Follow-up drift engine across ALL beneficiaries.

    Output item shape (matches the API contract):
        {beneficiary_id, name, category, issue, due_date, overdue_days,
         recommended_action}
    """
    from app.models import Beneficiary, FollowUp, ImmunisationRecord, NewbornRecord, PregnancyRecord, VisitRecord

    today = date.today()
    items: list[dict] = []

    beneficiaries = db.query(Beneficiary).all()
    for b in beneficiaries:
        visit_dates = sorted(
            (v.visit_date for v in db.query(VisitRecord).filter(VisitRecord.beneficiary_id == b.id).all()),
        )

        def add(issue: str, due: date | None, action: str, code: str, params: dict | None = None,
                action_code: str | None = None):
            overdue_days = max(0, (today - due).days) if due else 0
            items.append(
                {
                    "beneficiary_id": b.id,
                    "household_id": None,
                    "name": b.name,
                    "category": b.category,
                    "issue": issue,
                    # Machine-readable so the UI can localise the message.
                    "issue_code": code,
                    "issue_params": params or {},
                    "issue_action_code": action_code or code,
                    "due_date": due,
                    "overdue_days": overdue_days,
                    "recommended_action": action,
                }
            )

        if b.category == "pregnancy":
            if b.lmp_date is None:
                continue
            preg = (
                db.query(PregnancyRecord)
                .join(VisitRecord, PregnancyRecord.visit_id == VisitRecord.id)
                .filter(PregnancyRecord.beneficiary_id == b.id)
                .order_by(VisitRecord.visit_date.desc())
                .first()
            )
            if preg is None or not visit_dates:
                add("No ANC visit recorded yet", b.lmp_date + timedelta(days=ANC_INTERVAL_WEEKS_LT_28 * 7),
                    "Schedule the first ANC checkup at the PHC",
                    "anc_no_visit", action_code="schedule_first_anc")
                continue
            last_date = visit_dates[-1]
            weeks_at_visit = preg.weeks_pregnant if preg.weeks_pregnant is not None else \
                weeks_pregnant_on(b.lmp_date, last_date)
            required_gap = anc_interval_days(weeks_at_visit)
            due = last_date + timedelta(days=required_gap)
            if today > due:
                add(
                    f"ANC checkup overdue (last visit {last_date.isoformat()}, "
                    f"required every {required_gap // 7} week(s) at {weeks_at_visit} weeks)",
                    due,
                    "Schedule an ANC visit and refer if danger signs were reported",
                    "anc_overdue",
                    {
                        "last_visit": last_date.isoformat(),
                        "gap_weeks": required_gap // 7,
                        "weeks": weeks_at_visit,
                    },
                    action_code="schedule_anc_refer",
                )
            # Missing expected records in the latest ANC visit.
            # NOTE: this is a record-keeping/verification gap, NOT a medical claim.
            if preg.weight_kg is None:
                add(
                    "Missing record for verification: weight not recorded in the latest ANC visit",
                    last_date,
                    "Complete the ANC record with the beneficiary's weight",
                    "missing_weight",
                    {"last_visit": last_date.isoformat()},
                    action_code="complete_weight",
                )
            if preg.bp_sys is None or preg.bp_dia is None:
                add(
                    "Missing record for verification: blood pressure not recorded in the latest ANC visit",
                    last_date,
                    "Complete the ANC record with blood pressure readings",
                    "missing_bp",
                    {"last_visit": last_date.isoformat()},
                    action_code="complete_bp",
                )

        elif b.category == "newborn":
            if b.birth_date is None:
                continue
            age_days = (today - b.birth_date).days
            if age_days < 0 or age_days > 365:
                continue
            covered = set()
            for vd in visit_dates:
                v_days = (vd - b.birth_date).days
                for day in NEWBORN_ALL_CHECKUP_DAYS:
                    if day <= v_days <= day + 2:  # small grace window per checkup
                        covered.add(day)
            # A late visit also covers earlier checkpoints.
            covered_expanded = set()
            for v_day in [(vd - b.birth_date).days for vd in visit_dates]:
                for day in NEWBORN_ALL_CHECKUP_DAYS:
                    if day <= v_day:
                        covered_expanded.add(day)
            next_due_day = next((d for d in NEWBORN_ALL_CHECKUP_DAYS if d not in covered_expanded), None)
            if next_due_day is not None:
                due = b.birth_date + timedelta(days=next_due_day)
                if today > due:
                    label = {3: "day-3", 7: "day-7", 42: "6-week"}.get(next_due_day, f"day-{next_due_day}")
                    add(
                        f"Newborn {label} checkup overdue",
                        due,
                        "Conduct the pending newborn home visit",
                        "newborn_checkup_overdue",
                        {"label": label},
                        action_code="conduct_newborn_visit",
                    )
            # jaundice/weight fields are checked via the latest newborn record
            latest_newborn = (
                db.query(NewbornRecord)
                .join(VisitRecord, NewbornRecord.visit_id == VisitRecord.id)
                .filter(NewbornRecord.beneficiary_id == b.id)
                .order_by(VisitRecord.visit_date.desc())
                .first()
            )
            if latest_newborn is not None and latest_newborn.weight_kg is None:
                add(
                    "Missing record for verification: weight not recorded in the latest newborn visit",
                    visit_dates[-1] if visit_dates else None,
                    "Record the newborn's weight in the visit register",
                    "missing_newborn_weight",
                    {"last_visit": visit_dates[-1].isoformat() if visit_dates else ""},
                    action_code="record_newborn_weight",
                )

        else:  # "child" / "immunisation"
            # Missed vaccination: next_due_date in the past with no later dose
            # recorded (a dose given EARLY satisfies the schedule, so we check
            # whether any record exists after this one).
            records = (
                db.query(ImmunisationRecord)
                .filter(ImmunisationRecord.beneficiary_id == b.id)
                .order_by(ImmunisationRecord.date_given.desc())
                .all()
            )
            given_dates = [r.date_given for r in records]
            pending = [
                r for r in records
                if r.next_due_date is not None
                and r.next_due_date < today
                and not any(d > r.date_given for d in given_dates)
            ]
            if pending:
                r = pending[0]
                nxt = VACCINE_NEXT.get((r.vaccine_name or "").upper())
                next_name = nxt[0] if nxt else f"{r.vaccine_name} booster"
                add(
                    f"Missed vaccination: {next_name} was due "
                    f"{r.next_due_date.isoformat()} and no dose is recorded",
                    r.next_due_date,
                    "Schedule the pending immunisation at the nearest session site",
                    "vaccination_missed",
                    {"vaccine": next_name, "due": r.next_due_date.isoformat()},
                    action_code="schedule_immunisation",
                )
            # Growth monitoring for children: monthly visit.
            if visit_dates:
                gap = (today - visit_dates[-1]).days
                if gap > 35:
                    add(
                        f"Growth monitoring overdue (last visit {visit_dates[-1].isoformat()})",
                        visit_dates[-1] + timedelta(days=30),
                        "Schedule the monthly growth-monitoring visit",
                        "growth_overdue",
                        {"last_visit": visit_dates[-1].isoformat()},
                        action_code="schedule_growth_visit",
                    )

    # ------------------------------------------------------------------
    # Household Health & Hygiene drift (deterministic rules)
    # ------------------------------------------------------------------
    from app.models import Household, HouseholdVisit

    households = db.query(Household).all()
    for h in households:
        label = f"{h.village} household ({h.qr_id})" if h.village else f"Household ({h.qr_id})"

        def hadd(issue: str, due: date | None, action: str, code: str, params: dict | None = None,
                 action_code: str | None = None):
            overdue_days = max(0, (today - due).days) if due else 0
            items.append(
                {
                    "beneficiary_id": None,
                    "household_id": h.id,
                    "name": label,
                    "category": "household",
                    "issue": issue,
                    "issue_code": code,
                    "issue_params": params or {},
                    "issue_action_code": action_code or code,
                    "due_date": due,
                    "overdue_days": overdue_days,
                    "recommended_action": action,
                }
            )

        h_fups = db.query(FollowUp).filter(FollowUp.household_id == h.id).all()
        for fu in h_fups:
            if fu.status in ("overdue", "missed"):
                hadd(
                    "Household hygiene follow-up overdue "
                    f"(scheduled {fu.due_date.isoformat()})",
                    fu.due_date,
                    "Conduct the pending household hygiene follow-up visit",
                    "household_followup_overdue",
                    {"scheduled": fu.due_date.isoformat()},
                    action_code="conduct_household_followup",
                )

        # Stagnant-water verification gap: reported but no follow-up exists.
        h_visits = (
            db.query(HouseholdVisit)
            .filter(HouseholdVisit.household_id == h.id)
            .order_by(HouseholdVisit.visit_date.desc(), HouseholdVisit.id.desc())
            .all()
        )
        if h_visits:
            try:
                latest = json.loads(h_visits[0].notes) if h_visits[0].notes else {}
            except Exception:
                latest = {}
            if latest.get("stagnant_water") and not h_fups:
                hadd(
                    "Stagnant water reported on "
                    f"{h_visits[0].visit_date.isoformat()} — verification follow-up not scheduled",
                    h_visits[0].visit_date,
                    "Verify the family cleared the stagnation and record the follow-up visit",
                    "stagnant_unverified",
                    {"date": h_visits[0].visit_date.isoformat()},
                    action_code="verify_stagnation",
                )

    # ------------------------------------------------------------------
    # Generic nutrition / community follow-ups (deterministic)
    # ------------------------------------------------------------------
    nutrition_fups = (
        db.query(FollowUp)
        .filter(FollowUp.status.in_(["overdue", "missed"]),
                FollowUp.type.in_(["nutrition", "community"]))
        .all()
    )
    ben_names = {b.id: b.name for b in beneficiaries}
    for fu in nutrition_fups:
        if fu.beneficiary_id is None:
            continue
        b = next((x for x in beneficiaries if x.id == fu.beneficiary_id), None)
        if b is None:
            continue
        overdue_days = max(0, (today - fu.due_date).days)
        is_nutrition = fu.type == "nutrition"
        items.append(
            {
                "beneficiary_id": b.id,
                "household_id": None,
                "name": b.name,
                "category": b.category,
                "issue": (
                    "Nutrition follow-up overdue" if is_nutrition
                    else "Community health follow-up overdue"
                ) + f" (scheduled {fu.due_date.isoformat()})",
                "issue_code": "nutrition_overdue" if is_nutrition else "community_overdue",
                "issue_params": {"scheduled": fu.due_date.isoformat()},
                "issue_action_code": (
                    "conduct_nutrition_followup" if is_nutrition else "complete_community_followup"
                ),
                "due_date": fu.due_date,
                "overdue_days": overdue_days,
                "recommended_action": (
                    "Conduct the pending nutrition follow-up and counselling visit"
                    if is_nutrition
                    else "Complete the pending community health follow-up"
                ),
            }
        )

    # Deduplicate identical issues for the same beneficiary.
    seen: set[tuple] = set()
    unique: list[dict] = []
    for it in items:
        key = (it["beneficiary_id"], it["household_id"], it["issue"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    unique.sort(key=lambda it: (-it["overdue_days"], it["name"]))
    return unique


def refresh_statuses(db) -> None:
    """Hourly maintenance: mark overdue follow-ups and reminders.

    Called by the background scheduler in main.py. Deterministic and idempotent.
    """
    from app.models import FollowUp, SmsReminder

    today = date.today()

    followups = db.query(FollowUp).filter(FollowUp.status == "upcoming").all()
    for fu in followups:
        if fu.due_date < today:
            # Missed vaccinations get the dedicated "missed" status per the
            # immunisation schedule rule; ANC/newborn get "overdue".
            fu.status = "missed" if fu.type == "vaccination" else "overdue"

    reminders = db.query(SmsReminder).filter(SmsReminder.status == "scheduled").all()
    for rem in reminders:
        if rem.due_date < today:
            rem.status = "overdue"

    db.commit()
