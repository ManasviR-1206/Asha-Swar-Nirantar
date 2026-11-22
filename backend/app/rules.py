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

REFERRAL_MESSAGE = "Refer to the nearest PHC per approved guidelines."

# Rule metadata for evidence/audit. Citations are public guideline references;
# clinical deployment should confirm the exact local/provincial approved wording.
RULE_METADATA: dict[str, dict[str, str]] = {
    "PREG-01": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; refer for obstetric emergency evaluation", "referral": REFERRAL_MESSAGE},
    "PREG-02": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; severe headache may indicate hypertensive disorder", "referral": REFERRAL_MESSAGE},
    "PREG-03": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; blurred vision may indicate hypertensive disorder", "referral": REFERRAL_MESSAGE},
    "PREG-04": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; convulsions/fits are emergency danger signs", "referral": REFERRAL_MESSAGE},
    "PREG-05": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; swelling of hands/face may indicate hypertensive disorder", "referral": REFERRAL_MESSAGE},
    "PREG-06": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; difficulty breathing is an emergency danger sign", "referral": REFERRAL_MESSAGE},
    "PREG-07": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; persistent fever requires urgent evaluation", "referral": REFERRAL_MESSAGE},
    "PREG-08": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; severe abdominal pain requires urgent evaluation", "referral": REFERRAL_MESSAGE},
    "PREG-09": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; reduced fetal movement requires urgent evaluation", "referral": REFERRAL_MESSAGE},
    "PREG-10": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; persistent vomiting requires evaluation", "referral": REFERRAL_MESSAGE},
    "PREG-11": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; leaking fluid requires urgent evaluation", "referral": REFERRAL_MESSAGE},
    "PREG-12": {"applies_to": "mother", "guideline": "MoHFW/WHO ANC danger signs; preterm labour symptoms require urgent evaluation", "referral": REFERRAL_MESSAGE},
    "NEWB-01": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; fever requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-02": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; poor feeding/sucking requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-03": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; lethargy/unconsciousness requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-04": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; fast breathing requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-05": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; chest indrawing requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-06": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; cyanosis/bluish body requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-07": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; early jaundice requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-08": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; umbilical infection signs require referral", "referral": REFERRAL_MESSAGE},
    "NEWB-09": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; hypothermia/cold body requires urgent referral", "referral": REFERRAL_MESSAGE},
    "NEWB-10": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; poor urine output requires evaluation/referral", "referral": REFERRAL_MESSAGE},
    "NEWB-11": {"applies_to": "newborn", "guideline": "MoHFW HBNC/IMNCI newborn danger signs; persistent crying requires evaluation", "referral": REFERRAL_MESSAGE},
}

# Negation words: if any appears within NEGATION_WINDOW tokens *before* the
# matched phrase, the phrase is treated as NOT reported.
NEGATION_TOKENS = {"no", "not", "without", "denies", "never", "none", "nothing"}
NEGATION_WINDOW = 6  # tokens before the phrase
CONTRAST_TOKENS = {"but", "however", "although", "though", "except", "yet"}

_TOKEN_SPLIT = re.compile(r"[\s,.;:!?()\-]+")


def _negated(text_lower: str, match_start: int) -> bool:
    """True when a negation word sits within the last ~6 tokens before the match,
    unless a contrast/boundary breaks the negation scope."""
    prefix_tokens = [t for t in _TOKEN_SPLIT.split(text_lower[:match_start]) if t]
    window = prefix_tokens[-NEGATION_WINDOW:]
    # If a contrast token appears after the negation in the window, treat as not negated.
    neg_idxs = [i for i, tok in enumerate(window) if tok in NEGATION_TOKENS]
    if not neg_idxs:
        return False
    last_neg = max(neg_idxs)
    after_neg = window[last_neg + 1:]
    if any(tok in CONTRAST_TOKENS for tok in after_neg):
        return False
    return True


def _collect_structured_text(structured: dict | None) -> str:
    """Collect human-entered/verified textual observations from structured data.

    Only text-like fields are scanned with the same approved phrase rules.
    This does not invent thresholds; it allows verified structured observations
    (e.g. danger signs, symptoms, notes) to trigger existing deterministic rules.
    """
    if not isinstance(structured, dict):
        return ""
    parts: list[str] = []
    for k, v in structured.items():
        if v is None:
            continue
        key = str(k).lower()
        # Prefer observation/symptom/note-like fields; avoid IDs/codes/dates/names.
        if not any(tok in key for tok in ("danger", "symptom", "complaint", "note", "observation", "finding", "concern", "problem", "remark")):
            continue
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    for vv in item.values():
                        if isinstance(vv, str) and vv.strip():
                            parts.append(vv.strip())
    # de-dup while preserving order
    seen = set()
    out = []
    for p in parts:
        n = p.lower()
        if n in seen:
            continue
        seen.add(n)
        out.append(p)
    return "\n".join(out)


def detect_danger_signs(transcript: str, category: str | None = None, structured: dict | None = None) -> list[dict]:
    """Scan transcript and relevant verified structured observations for approved danger-sign phrases.

    Matching: case-insensitive whole-word/phrase matching (word boundaries,
    so "fits" does not match "benefits"). Negation within the previous 6
    tokens suppresses the match ("no fever", "denies severe headache").

    Returns a list of:
        {rule_id, phrase, message, severity}
    where `phrase` is the EXACT triggering text as it appeared in the input.
    """
    structured_text = _collect_structured_text(structured)
    combined = "\n".join([t for t in [transcript or "", structured_text] if t and t.strip()])
    if not combined.strip():
        return []
    text_lower = combined.lower()
    transcript = combined

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
                meta = RULE_METADATA.get(rule_id, {})
                flags.append(
                    {
                        "rule_id": rule_id,
                        "phrase": transcript[m.start():m.end()],
                        "message": meta.get("referral", REFERRAL_MESSAGE),
                        "severity": severity,
                        "applies_to": meta.get("applies_to", ""),
                        "guideline_citation": meta.get("guideline", ""),
                        "matched_text": transcript[m.start():m.end()],
                        "evidence": {
                            "matched_phrase": transcript[m.start():m.end()],
                            "rule_id": rule_id,
                            "severity": severity,
                            "applies_to": meta.get("applies_to", ""),
                            "guideline_citation": meta.get("guideline", ""),
                        },
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


def _deterministic_followup_candidates(db) -> list[dict]:
    """Compute current deterministic follow-up candidates from actual records/rules.

    Returns candidate dicts suitable for persisted task generation (idempotent via dedup_key).
    """
    from app.data_scope import visible_beneficiaries, visible_households
    from app.models import Beneficiary, FollowUp, Household, HouseholdVisit, ImmunisationRecord, NewbornRecord, PregnancyRecord, VisitRecord

    today = date.today()
    cands: list[dict] = []

    beneficiaries = visible_beneficiaries(db.query(Beneficiary)).all()
    for b in beneficiaries:
        visit_dates = sorted(
            (v.visit_date for v in db.query(VisitRecord).filter(VisitRecord.beneficiary_id == b.id).all()),
        )

        def add(issue: str, due: date | None, action: str, code: str, params: dict | None = None,
                action_code: str | None = None, dedup: str = "", type_: str | None = None, priority: str = "normal", visit_id: int | None = None):
            if not due or not dedup:
                return
            cands.append(
                {
                    "beneficiary_id": b.id,
                    "household_id": None,
                    "name": b.name,
                    "category": (type_ or b.category or "general"),
                    "type": (type_ or b.category or "general"),
                    "issue": issue,
                    "issue_code": code,
                    "issue_params": params or {},
                    "issue_action_code": action_code or code,
                    "due_date": due,
                    "recommended_action": action,
                    "dedup_key": dedup,
                    "priority": priority,
                    "visit_id": visit_id,
                    "source_type": "rule",
                    "source_ref": code,
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
                due = b.lmp_date + timedelta(days=ANC_INTERVAL_WEEKS_LT_28 * 7)
                add("No ANC visit recorded yet", due,
                    "Schedule the first ANC checkup at the PHC",
                    "anc_no_visit", action_code="schedule_first_anc",
                    dedup=f"gen:ben:{b.id}:anc_no_visit", type_="anc", priority="high")
                continue
            last_date = visit_dates[-1]
            weeks_at_visit = preg.weeks_pregnant if preg.weeks_pregnant is not None else weeks_pregnant_on(b.lmp_date, last_date)
            required_gap = anc_interval_days(weeks_at_visit)
            due = last_date + timedelta(days=required_gap)
            if today > due:
                add(
                    f"ANC checkup overdue (last visit {last_date.isoformat()}, required every {required_gap // 7} week(s) at {weeks_at_visit} weeks)",
                    due,
                    "Schedule an ANC visit and refer if danger signs were reported",
                    "anc_overdue",
                    {"last_visit": last_date.isoformat(), "gap_weeks": required_gap // 7, "weeks": weeks_at_visit},
                    action_code="schedule_anc_refer",
                    dedup=f"gen:ben:{b.id}:anc_overdue:{last_date.isoformat()}",
                    type_="anc", priority="high", visit_id=preg.visit_id,
                )
            if preg.weight_kg is None:
                add(
                    "Missing record for verification: weight not recorded in the latest ANC visit",
                    last_date,
                    "Complete the ANC record with the beneficiary's weight",
                    "missing_weight",
                    {"last_visit": last_date.isoformat()},
                    action_code="complete_weight",
                    dedup=f"gen:ben:{b.id}:missing_weight:{last_date.isoformat()}",
                    type_="anc", priority="normal", visit_id=preg.visit_id,
                )
            if preg.bp_sys is None or preg.bp_dia is None:
                add(
                    "Missing record for verification: blood pressure not recorded in the latest ANC visit",
                    last_date,
                    "Complete the ANC record with blood pressure readings",
                    "missing_bp",
                    {"last_visit": last_date.isoformat()},
                    action_code="complete_bp",
                    dedup=f"gen:ben:{b.id}:missing_bp:{last_date.isoformat()}",
                    type_="anc", priority="normal", visit_id=preg.visit_id,
                )

        elif b.category == "newborn":
            if b.birth_date is None:
                continue
            age_days = (today - b.birth_date).days
            if age_days < 0 or age_days > 365:
                continue
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
                        dedup=f"gen:ben:{b.id}:newborn_checkup:{due.isoformat()}",
                        type_="newborn", priority="high",
                    )
            latest_newborn = (
                db.query(NewbornRecord)
                .join(VisitRecord, NewbornRecord.visit_id == VisitRecord.id)
                .filter(NewbornRecord.beneficiary_id == b.id)
                .order_by(VisitRecord.visit_date.desc())
                .first()
            )
            if latest_newborn is not None and latest_newborn.weight_kg is None:
                last_d = visit_dates[-1] if visit_dates else today
                add(
                    "Missing record for verification: weight not recorded in the latest newborn visit",
                    last_d,
                    "Record the newborn's weight in the visit register",
                    "missing_newborn_weight",
                    {"last_visit": last_d.isoformat()},
                    action_code="record_newborn_weight",
                    dedup=f"gen:ben:{b.id}:missing_newborn_weight:{last_d.isoformat()}",
                    type_="newborn", priority="normal", visit_id=latest_newborn.visit_id,
                )

        else:  # child / immunisation
            records = (
                db.query(ImmunisationRecord)
                .filter(ImmunisationRecord.beneficiary_id == b.id)
                .order_by(ImmunisationRecord.date_given.desc())
                .all()
            )
            given_dates = [r.date_given for r in records if r.date_given]
            pending = [
                r for r in records
                if r.next_due_date is not None
                and r.next_due_date < today
                and not any(d and r.date_given and d > r.date_given for d in given_dates)
            ]
            if pending:
                r = pending[0]
                nxt = VACCINE_NEXT.get((r.vaccine_name or "").upper())
                next_name = nxt[0] if nxt else f"{r.vaccine_name} booster"
                add(
                    f"Missed vaccination: {next_name} was due {r.next_due_date.isoformat()} and no dose is recorded",
                    r.next_due_date,
                    "Schedule the pending immunisation at the nearest session site",
                    "vaccination_missed",
                    {"vaccine": next_name, "due": r.next_due_date.isoformat()},
                    action_code="schedule_immunisation",
                    dedup=f"gen:ben:{b.id}:vacc_missed:{next_name}:{r.next_due_date.isoformat()}",
                    type_="vaccination", priority="high", visit_id=r.visit_id,
                )
            if visit_dates:
                gap = (today - visit_dates[-1]).days
                if gap > 35:
                    due = visit_dates[-1] + timedelta(days=30)
                    add(
                        f"Growth monitoring overdue (last visit {visit_dates[-1].isoformat()})",
                        due,
                        "Schedule the monthly growth-monitoring visit",
                        "growth_overdue",
                        {"last_visit": visit_dates[-1].isoformat()},
                        action_code="schedule_growth_visit",
                        dedup=f"gen:ben:{b.id}:growth_overdue:{due.isoformat()}",
                        type_="child", priority="normal",
                    )

    # Household hygiene follow-ups
    households = visible_households(db.query(Household)).all()
    for h in households:
        label = f"{h.village} household ({h.qr_id})" if h.village else f"Household ({h.qr_id})"
        h_fups = db.query(FollowUp).filter(FollowUp.household_id == h.id).all()
        # Existing overdue/due/missed household follow-ups are already persisted tasks and are surfaced
        # directly from the active follow-ups table; do not generate duplicate copies for them.
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
            # If stagnant water reported and no active (upcoming/due/overdue) household followup exists, suggest one
            active_h = [f for f in h_fups if f.status in ("upcoming", "due", "overdue")]
            if latest.get("stagnant_water") and not active_h:
                cands.append(
                    {
                        "beneficiary_id": None,
                        "household_id": h.id,
                        "name": label,
                        "category": "household",
                        "type": "household",
                        "issue": f"Stagnant water reported on {h_visits[0].visit_date.isoformat()} — verification follow-up not scheduled",
                        "issue_code": "stagnant_unverified",
                        "issue_params": {"date": h_visits[0].visit_date.isoformat()},
                        "issue_action_code": "verify_stagnation",
                        "due_date": h_visits[0].visit_date + timedelta(days=7),
                        "recommended_action": "Verify the family cleared the stagnation and record the follow-up visit",
                        "dedup_key": f"gen:hh:{h.id}:stagnant_unverified:{h_visits[0].visit_date.isoformat()}",
                        "priority": "high",
                        "visit_id": None,
                        "source_type": "rule",
                        "source_ref": "stagnant_unverified",
                    }
                )

    # Nutrition/community overdue persisted followups are already active tasks and surfaced directly;
    # do not generate duplicate copies for existing overdue/due follow-up records.

    return cands


def sync_generated_followups(db) -> int:
    """Idempotently upsert persisted follow-up tasks from deterministic rules/records."""
    from app.services.followups import refresh_followup_statuses, upsert_generated_followup

    refresh_followup_statuses(db)
    cands = _deterministic_followup_candidates(db)
    count = 0
    for c in cands:
        fu = upsert_generated_followup(
            db,
            dedup_key=c["dedup_key"],
            beneficiary_id=c.get("beneficiary_id"),
            household_id=c.get("household_id"),
            visit_id=c.get("visit_id"),
            type_=c.get("type") or c.get("category") or "general",
            category=c.get("category") or c.get("type") or "general",
            reason=c.get("issue") or "",
            description=c.get("issue") or "",
            recommended_action=c.get("recommended_action") or "",
            due_date=c.get("due_date"),
            priority=c.get("priority") or "normal",
            source_type=c.get("source_type") or "rule",
            source_id=None,
            source_ref=c.get("source_ref") or c.get("issue_code") or "",
            assigned_worker_id=None,
        )
        if fu:
            count += 1
    db.commit()
    return count


def run_drift_engine(db) -> list[dict]:
    """Compatibility wrapper: return active persisted follow-up tasks as drift items."""
    from app.data_scope import visible_followups
    from app.services.followups import followup_to_dict, refresh_followup_statuses

    refresh_followup_statuses(db)
    try:
        sync_generated_followups(db)
    except Exception:
        db.rollback()
    followup_model = __import__('app.models', fromlist=['FollowUp']).FollowUp
    rows = (
        visible_followups(db.query(followup_model), db)
        .filter(followup_model.status.in_(["upcoming", "due", "overdue"]))
        .order_by(followup_model.status.in_(["overdue"]).desc(), followup_model.due_date.asc().nullslast())
        .all()
    )
    items = []
    ben_cache, hh_cache, worker_cache = {}, {}, {}
    for fu in rows:
        d = followup_to_dict(db, fu, ben_cache, hh_cache, worker_cache)
        name = d.get("beneficiary_name") or d.get("household_label") or "Follow-up"
        items.append(
            {
                "beneficiary_id": d.get("beneficiary_id"),
                "household_id": d.get("household_id"),
                "name": name,
                "category": d.get("category") or d.get("type") or "general",
                "issue": d.get("reason") or d.get("description") or "Follow-up required",
                "issue_code": "",
                "issue_params": {},
                "issue_action_code": "",
                "due_date": d.get("due_date"),
                "overdue_days": d.get("overdue_days") or 0,
                "recommended_action": d.get("recommended_action") or "",
            }
        )
    return items


def refresh_statuses(db) -> None:
    """Hourly maintenance: refresh follow-up statuses and reminder statuses."""
    from app.models import SmsReminder
    from app.services.followups import refresh_followup_statuses

    refresh_followup_statuses(db)
    today = date.today()
    reminders = db.query(SmsReminder).filter(SmsReminder.status == "scheduled").all()
    changed = False
    for rem in reminders:
        if rem.due_date < today:
            rem.status = "overdue"
            changed = True
    if changed:
        db.commit()
