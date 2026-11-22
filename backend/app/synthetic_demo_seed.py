"""Comprehensive synthetic demonstration dataset for ASHA Swar Nirantar.

Creates clearly separated SYNTHETIC DEMO DATA (never real patient records):
- ~100 households
- ~270 beneficiaries (all linked to valid households)
- ~380 visit records (completed/upcoming-due-history/missed scenarios)
- ~90 follow-up records (upcoming/due/overdue/completed/cancelled)
- pregnancy/newborn/child/immunisation/elderly/nutrition/general records
- household members and household visits for demonstrable summaries
- health measurements and care-plan tasks for richer Pulse Thread/dashboard views

Safety:
- Uses data_origin='synthetic_demo' and synthetic-only identifiers/content
- Does not use real patient names/phone numbers/addresses
- Does not modify or delete existing real records
- Idempotent: repeated runs do not create duplicates
- Reset removes only synthetic demo records (and their dependent records)
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AlertAuditLog,
    AshaWorker,
    Beneficiary,
    CarePlanTask,
    ConsentRecord,
    DangerAlert,
    ExtractedField,
    ExtractedVisit,
    FieldAudit,
    FollowUp,
    FollowUpHistory,
    HealthMeasurement,
    Household,
    HouseholdMember,
    HouseholdVisit,
    ImmunisationRecord,
    MeasurementAudit,
    NewbornRecord,
    PatientRequest,
    PdfReport,
    PregnancyRecord,
    SmsNotification,
    SmsReminder,
    UploadedDocument,
    VisitRecord,
    VoiceRecordingSession,
    VoiceTranscript,
)

SYNTHETIC_ORIGIN = "synthetic_demo"
SYNTHETIC_LABEL = "SYNTHETIC DEMO DATA"
SEED_MARKER = "SDM-SEED-MARKER"  # beneficiary qr_id marker for idempotency
HH_QR_PREFIX = "SDH-"
BEN_QR_PREFIX = "SDM-"
TARGET_HOUSEHOLDS = 100
TARGET_BENEFICIARIES = 270
TARGET_VISITS_MIN = 300
TARGET_VISITS_MAX = 500
TARGET_FOLLOWUPS_MIN = 75
TARGET_FOLLOWUPS_MAX = 100

VILLAGES = [
    "Rampur (Demo)", "Lakshmipur (Demo)", "Devgarh (Demo)", "Kalyan Nagar (Demo)",
    "Shantinagar (Demo)", "Nandigram (Demo)", "Sundarpur (Demo)", "Haripur (Demo)",
    "Krishnapur (Demo)", "Ganeshpur (Demo)", "Shivpur (Demo)", "Madhavpur (Demo)",
]
WOMEN = ["Asha", "Bhavna", "Chitra", "Deepa", "Esha", "Farida", "Gita", "Hema", "Indu", "Jyoti", "Kavya", "Lata", "Meena", "Nisha", "Pooja", "Radha", "Sana", "Tara", "Uma", "Vani"]
MEN = ["Arjun", "Bharat", "Chetan", "Dev", "Eshan", "Farhan", "Gopal", "Harish", "Imran", "Jatin", "Kiran", "Lokesh", "Manoj", "Naveen", "Om", "Pranav", "Ravi", "Suresh", "Tarun", "Vijay"]
CHILDREN = ["Aarav", "Anaya", "Diya", "Ishaan", "Kabir", "Kiara", "Mira", "Myra", "Reyansh", "Riya", "Sara", "Vihaan"]
SURNAMES = ["DemoA", "DemoB", "DemoC", "DemoD", "DemoE", "DemoF", "DemoG", "DemoH", "DemoI", "DemoJ", "DemoK", "DemoL"]


def _today() -> date:
    return date.today()


def _d(days: int) -> date:
    return _today() + timedelta(days=days)


def _dt(days: int, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(_d(days), datetime.min.time().replace(hour=hour, minute=minute))


def _syn_name(rng: random.Random, kind: str, idx: int) -> str:
    if kind == "child":
        first = rng.choice(CHILDREN)
    elif kind == "male":
        first = rng.choice(MEN)
    elif kind == "female":
        first = rng.choice(WOMEN)
    else:
        first = rng.choice(WOMEN + MEN)
    return f"{first} {rng.choice(SURNAMES)} (SYN-{idx:03d})"


def _phone(rng: random.Random, idx: int) -> str:
    # Clearly synthetic/non-real numbering pattern.
    return f"90000{idx:05d}"[-10:]


def _hh_qr(i: int) -> str:
    return f"{HH_QR_PREFIX}{i:04d}"


def _ben_qr(i: int) -> str:
    return f"{BEN_QR_PREFIX}{i:04d}"


def _json_text(payload: dict) -> str:
    def conv(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v
    return json.dumps({k: conv(v) for k, v in payload.items()}, ensure_ascii=False)


def _existing_marker(db: Session) -> bool:
    return db.execute(select(Beneficiary.id).where(Beneficiary.qr_id == SEED_MARKER)).first() is not None


def _synthetic_beneficiary_ids(db: Session) -> list[int]:
    return [r[0] for r in db.execute(select(Beneficiary.id).where(Beneficiary.data_origin == SYNTHETIC_ORIGIN)).all()]


def _synthetic_household_ids(db: Session) -> list[int]:
    return [r[0] for r in db.execute(select(Household.id).where(Household.data_origin == SYNTHETIC_ORIGIN)).all()]


def reset_synthetic_demo(db: Session) -> dict:
    """Delete only synthetic demo records and their dependent records. Safe/no-op if none exist."""
    b_ids = _synthetic_beneficiary_ids(db)
    h_ids = _synthetic_household_ids(db)
    if not b_ids and not h_ids:
        return {"deleted": False, "beneficiaries": 0, "households": 0}

    # Collect dependent IDs first
    visit_ids = [r[0] for r in db.execute(select(VisitRecord.id).where(VisitRecord.beneficiary_id.in_(b_ids))).all()] if b_ids else []

    fu_conditions = []
    if b_ids:
        fu_conditions.append(FollowUp.beneficiary_id.in_(b_ids))
    if h_ids:
        fu_conditions.append(FollowUp.household_id.in_(h_ids))
    fu_ids = [r[0] for r in db.execute(select(FollowUp.id).where(or_(*fu_conditions))).all()] if fu_conditions else []

    meas_ids = [r[0] for r in db.execute(select(HealthMeasurement.id).where(HealthMeasurement.beneficiary_id.in_(b_ids))).all()] if b_ids else []
    alert_ids = [r[0] for r in db.execute(select(DangerAlert.id).where(DangerAlert.beneficiary_id.in_(b_ids))).all()] if b_ids else []
    try:
        session_ids = [r[0] for r in db.execute(select(VoiceRecordingSession.id).where(VoiceRecordingSession.transcript.like('%SYNTHETIC DEMO%'))).all()]
    except Exception:
        session_ids = []

    ext_conditions = []
    if b_ids:
        ext_conditions.append(ExtractedVisit.beneficiary_id.in_(b_ids))
    if h_ids:
        ext_conditions.append(ExtractedVisit.household_id.in_(h_ids))
    extracted_ids = [r[0] for r in db.execute(select(ExtractedVisit.id).where(or_(*ext_conditions))).all()] if ext_conditions else []

    # Delete leaf/dependent tables (best-effort ordering; SQLite FK constraints may be off)
    def del_where(model, cond):
        if cond is None:
            return
        db.execute(delete(model).where(cond))

    if visit_ids:
        del_where(ExtractedField, ExtractedField.visit_id.in_(visit_ids))
        del_where(VoiceTranscript, VoiceTranscript.visit_id.in_(visit_ids))
        del_where(PregnancyRecord, PregnancyRecord.visit_id.in_(visit_ids))
        del_where(NewbornRecord, NewbornRecord.visit_id.in_(visit_ids))
        del_where(ImmunisationRecord, ImmunisationRecord.visit_id.in_(visit_ids))
        del_where(DangerAlert, DangerAlert.visit_id.in_(visit_ids))
    if meas_ids:
        del_where(MeasurementAudit, MeasurementAudit.measurement_id.in_(meas_ids))
    if alert_ids:
        del_where(AlertAuditLog, AlertAuditLog.alert_id.in_(alert_ids))
    if fu_ids:
        del_where(FollowUpHistory, FollowUpHistory.followup_id.in_(fu_ids))
    if extracted_ids:
        del_where(ExtractedVisit, ExtractedVisit.id.in_(extracted_ids))
    if session_ids:
        del_where(ExtractedVisit, ExtractedVisit.session_id.in_(session_ids))
        del_where(VoiceRecordingSession, VoiceRecordingSession.id.in_(session_ids))

    if b_ids:
        del_where(VisitRecord, VisitRecord.beneficiary_id.in_(b_ids))
        del_where(FollowUp, FollowUp.beneficiary_id.in_(b_ids))
        del_where(SmsReminder, SmsReminder.beneficiary_id.in_(b_ids))
        del_where(SmsNotification, SmsNotification.beneficiary_id.in_(b_ids))
        del_where(PdfReport, PdfReport.beneficiary_id.in_(b_ids))
        del_where(ConsentRecord, ConsentRecord.beneficiary_id.in_(b_ids))
        del_where(HealthMeasurement, HealthMeasurement.beneficiary_id.in_(b_ids))
        del_where(CarePlanTask, CarePlanTask.beneficiary_id.in_(b_ids))
        del_where(PatientRequest, PatientRequest.beneficiary_id.in_(b_ids))
        del_where(UploadedDocument, UploadedDocument.beneficiary_id.in_(b_ids))
        del_where(HouseholdMember, HouseholdMember.beneficiary_id.in_(b_ids))
        del_where(DangerAlert, DangerAlert.beneficiary_id.in_(b_ids))
        del_where(ExtractedVisit, ExtractedVisit.beneficiary_id.in_(b_ids))

    if h_ids:
        del_where(HouseholdVisit, HouseholdVisit.household_id.in_(h_ids))
        del_where(HouseholdMember, HouseholdMember.household_id.in_(h_ids))
        del_where(FollowUp, FollowUp.household_id.in_(h_ids))
        del_where(PatientRequest, PatientRequest.household_id.in_(h_ids))
        del_where(UploadedDocument, UploadedDocument.household_id.in_(h_ids))
        del_where(ExtractedVisit, ExtractedVisit.household_id.in_(h_ids))

    # Finally delete synthetic entities themselves
    if b_ids:
        db.execute(delete(Beneficiary).where(Beneficiary.id.in_(b_ids)))
    if h_ids:
        db.execute(delete(Household).where(Household.id.in_(h_ids)))

    db.commit()
    return {"deleted": True, "beneficiaries": len(b_ids), "households": len(h_ids)}


def _followup(
    *, db: Session, rng: random.Random, beneficiary_id: int | None = None, household_id: int | None = None,
    type_: str, category: str, due_date: date, status: str, reason: str, action: str,
    priority: str = "normal", visit_id: int | None = None, worker_id: int | None = None,
    source_type: str = "synthetic_seed", dedup: str = "",
) -> FollowUp:
    fu = FollowUp(
        beneficiary_id=beneficiary_id,
        household_id=household_id,
        visit_id=visit_id,
        type=type_,
        category=category,
        due_date=due_date,
        status=status,
        priority=priority,
        reason=reason,
        description=reason,
        recommended_action=action,
        assigned_worker_id=worker_id,
        notes=f"{SYNTHETIC_LABEL}: demonstration follow-up record.",
        completion_notes="Completed during synthetic demonstration workflow." if status == "completed" else "",
        cancellation_reason="Cancelled for synthetic demonstration scenario." if status == "cancelled" else "",
        completed_at=_dt((due_date - _today()).days, 11, 0) if status == "completed" else None,
        cancelled_at=_dt((due_date - _today()).days, 12, 0) if status == "cancelled" else None,
        rescheduled_from=(due_date - timedelta(days=rng.randint(3, 10))) if rng.random() < 0.08 else None,
        source_type=source_type,
        source_id=visit_id,
        source_ref="synthetic_demo_seed",
        dedup_key=dedup or f"syn:{beneficiary_id or 0}:{household_id or 0}:{type_}:{due_date.isoformat()}:{rng.randint(1,10**9)}",
        created_at=_dt(-rng.randint(1, 90), 9, 30),
        updated_at=_dt(-rng.randint(0, 20), 14, 0),
    )
    db.add(fu)
    db.flush()
    db.add(FollowUpHistory(
        followup_id=fu.id,
        action="created",
        from_status="",
        to_status=status,
        note=f"{SYNTHETIC_LABEL}: created for demonstration.",
        actor_id=worker_id,
        actor_label="synthetic-seed",
        changed_at=fu.created_at,
    ))
    if status in ("completed", "cancelled"):
        db.add(FollowUpHistory(
            followup_id=fu.id,
            action=status,
            from_status="upcoming",
            to_status=status,
            note=f"{SYNTHETIC_LABEL}: {status} demonstration status.",
            actor_id=worker_id,
            actor_label="synthetic-seed",
            changed_at=fu.completed_at or fu.cancelled_at or fu.updated_at or fu.created_at,
        ))
    return fu


def seed_synthetic_demo(db: Session, *, force: bool = False) -> dict:
    """Seed comprehensive synthetic demo data (idempotent). Does not modify real records."""
    if _existing_marker(db):
        if not force:
            return {"created": False, "reason": "already_seeded", **verify_synthetic_demo(db)}
        # force reseed of synthetic dataset only
        reset_synthetic_demo(db)

    rng = random.Random(20261120)
    worker = db.query(AshaWorker).order_by(AshaWorker.id.asc()).first()
    worker_id = worker.id if worker else None

    # 1) Households (100)
    households: list[Household] = []
    for i in range(1, TARGET_HOUSEHOLDS + 1):
        village = VILLAGES[(i - 1) % len(VILLAGES)]
        hh = Household(
            qr_id=_hh_qr(i),
            village=village,
            address=f"Synthetic Demo House {i}, {village}",
            member_count=0,
            data_origin=SYNTHETIC_ORIGIN,
            created_at=_dt(-rng.randint(30, 220), 9, 0),
        )
        db.add(hh)
        households.append(hh)
    db.flush()

    # 2) Beneficiaries (270) distributed across categories, all linked to households
    plan = (
        [("pregnancy", 45)] +
        [("newborn", 35)] +
        [("child", 55)] +
        [("immunisation", 45)] +
        [("elderly", 35)] +
        [("nutrition", 30)] +
        [("general", 25)]
    )
    # adjust to exact target
    total = sum(n for _, n in plan)
    if total != TARGET_BENEFICIARIES:
        plan[-1] = (plan[-1][0], plan[-1][1] + (TARGET_BENEFICIARIES - total))

    beneficiaries: list[Beneficiary] = []
    b_idx = 0
    # assign 2-4 beneficiaries per household round-robin
    hh_cycle = households[:]
    rng.shuffle(hh_cycle)

    for cat, count in plan:
        for _ in range(count):
            b_idx += 1
            hh = households[(b_idx - 1) % len(households)]
            village = hh.village
            if cat == "pregnancy":
                age = rng.randint(19, 38)
                gender = "female"
                name = _syn_name(rng, "female", b_idx)
                lmp = _d(-rng.randint(8 * 7, 36 * 7))
                birth_date = None
                dob = _d(-(age * 365 + rng.randint(0, 300)))
                pregnancy_status = "pregnant"
                notes = f"{SYNTHETIC_LABEL}: antenatal demonstration record."
            elif cat == "newborn":
                age = 0
                gender = rng.choice(["male", "female"])
                name = f"{rng.choice(CHILDREN)} {rng.choice(SURNAMES)} (SYN-{b_idx:03d})"
                birth_date = _d(-rng.randint(1, 28))
                lmp = None
                dob = birth_date
                pregnancy_status = "not_applicable"
                notes = f"{SYNTHETIC_LABEL}: newborn/postnatal demonstration record."
            elif cat == "child":
                age = rng.randint(1, 9)
                gender = rng.choice(["male", "female"])
                name = f"{rng.choice(CHILDREN)} {rng.choice(SURNAMES)} (SYN-{b_idx:03d})"
                birth_date = _d(-(age * 365 + rng.randint(0, 300)))
                lmp = None
                dob = birth_date
                pregnancy_status = "not_applicable"
                notes = f"{SYNTHETIC_LABEL}: child health demonstration record."
            elif cat == "immunisation":
                age = rng.randint(0, 5)
                gender = rng.choice(["male", "female"])
                name = f"{rng.choice(CHILDREN)} {rng.choice(SURNAMES)} (SYN-{b_idx:03d})"
                birth_date = _d(-(age * 365 + rng.randint(20, 300))) if age > 0 else _d(-rng.randint(45, 300))
                lmp = None
                dob = birth_date
                pregnancy_status = "not_applicable"
                notes = f"{SYNTHETIC_LABEL}: immunisation demonstration record."
            elif cat == "elderly":
                age = rng.randint(60, 85)
                gender = rng.choice(["male", "female"])
                name = _syn_name(rng, "male" if gender == "male" else "female", b_idx)
                birth_date = None
                lmp = None
                dob = _d(-(age * 365 + rng.randint(0, 300)))
                pregnancy_status = "not_applicable"
                notes = f"{SYNTHETIC_LABEL}: elderly routine monitoring demonstration record."
            elif cat == "nutrition":
                age = rng.randint(2, 45)
                gender = rng.choice(["male", "female"])
                name = _syn_name(rng, "male" if gender == "male" else "female", b_idx)
                birth_date = _d(-(age * 365 + rng.randint(0, 300))) if age < 12 else None
                lmp = None
                dob = _d(-(age * 365 + rng.randint(0, 300)))
                pregnancy_status = "not_applicable"
                notes = f"{SYNTHETIC_LABEL}: nutrition demonstration record."
            else:  # general
                age = rng.randint(12, 55)
                gender = rng.choice(["male", "female"])
                name = _syn_name(rng, "male" if gender == "male" else "female", b_idx)
                birth_date = None
                lmp = None
                dob = _d(-(age * 365 + rng.randint(0, 300)))
                pregnancy_status = "not_applicable"
                notes = f"{SYNTHETIC_LABEL}: general community healthcare demonstration record."

            ben = Beneficiary(
                qr_id=_ben_qr(b_idx),
                name=name,
                age=age,
                category=cat,
                gender=gender,
                village=village,
                address=f"Synthetic Demo Address {b_idx}, {village}",
                phone=_phone(rng, b_idx),
                email=f"synthetic.demo.{b_idx}@example.demo.invalid",
                lmp_date=lmp,
                birth_date=birth_date,
                date_of_birth=dob,
                emergency_contact=f"Demo Contact {b_idx}",
                emergency_contact_consent=True,
                household_id=hh.id,
                assigned_worker_id=worker_id,
                data_origin=SYNTHETIC_ORIGIN,
                verification_status=SYNTHETIC_ORIGIN,
                pregnancy_status=pregnancy_status,
                medical_conditions="None recorded (synthetic demo)" if rng.random() < 0.7 else "Routine monitoring (synthetic demo)",
                allergies="None known (synthetic demo)",
                current_medications="None (synthetic demo)" if rng.random() < 0.8 else "As advised (synthetic demo)",
                child_health_notes="Growth monitoring (synthetic demo)" if cat in ("child", "newborn", "immunisation", "nutrition") else "",
                registration_notes=notes,
                created_at=_dt(-rng.randint(20, 200), 9, 15),
            )
            db.add(ben)
            beneficiaries.append(ben)
            if b_idx <= 3:
                # add extra marker beneficiary? no, use first as marker
                pass
    # explicit idempotency marker beneficiary (separate, clearly synthetic, linked to household 1)
    marker = Beneficiary(
        qr_id=SEED_MARKER,
        name=f"Synthetic Dataset Marker ({SYNTHETIC_LABEL})",
        age=0,
        category="general",
        gender="",
        village=households[0].village,
        address=f"Synthetic Demo Marker, {households[0].village}",
        phone="9000000000",
        email="synthetic.marker@example.demo.invalid",
        household_id=households[0].id,
        assigned_worker_id=worker_id,
        data_origin=SYNTHETIC_ORIGIN,
        verification_status=SYNTHETIC_ORIGIN,
        registration_notes=f"{SYNTHETIC_LABEL}: idempotency marker record. Safe to remove only with synthetic demo reset.",
        created_at=_dt(-210, 8, 0),
    )
    db.add(marker)
    db.flush()

    # 3) Household members (head + beneficiary members)
    by_hh: dict[int, list[Beneficiary]] = defaultdict(list)
    for b in beneficiaries:
        if b.household_id:
            by_hh[b.household_id].append(b)
    for hh in households:
        members = by_hh.get(hh.id, [])
        # head (synthetic adult not necessarily a beneficiary)
        head_gender = rng.choice(["male", "female"])
        head_name = _syn_name(rng, "male" if head_gender == "male" else "female", 1000 + hh.id)
        db.add(HouseholdMember(
            household_id=hh.id,
            name=head_name,
            age=rng.randint(28, 65),
            gender=head_gender,
            relation="head",
            beneficiary_id=None,
        ))
        for m in members[:6]:  # link beneficiary members
            rel = "self"
            if m.category == "pregnancy":
                rel = "spouse" if m.gender == "female" else "member"
            elif m.category in ("newborn", "child", "immunisation"):
                rel = "child"
            elif m.category == "elderly":
                rel = rng.choice(["parent", "grandparent"])
            db.add(HouseholdMember(
                household_id=hh.id,
                name=m.name,
                age=m.age or 0,
                gender=m.gender or "",
                relation=rel,
                beneficiary_id=m.id,
            ))
        hh.member_count = 1 + min(len(members), 6)
    db.flush()

    # 4) Visits (300-500) with varied histories and clinical records
    visits: list[VisitRecord] = []
    visit_count_target = rng.randint(TARGET_VISITS_MIN, TARGET_VISITS_MAX)
    # ensure each beneficiary gets at least 1 visit, distribute rest
    per_ben = {b.id: 1 for b in beneficiaries}
    extra = max(0, visit_count_target - len(beneficiaries))
    for _ in range(extra):
        b = rng.choice(beneficiaries)
        per_ben[b.id] += 1

    def add_visit(ben: Beneficiary, vdate: date, category: str, source: str, structured: dict, include_transcript: bool = False) -> VisitRecord:
        v = VisitRecord(
            beneficiary_id=ben.id,
            worker_id=worker_id or 1,
            visit_date=vdate,
            category=category,
            notes=_json_text(structured),
            source=source,
            created_at=datetime.combine(vdate, datetime.min.time().replace(hour=10, minute=rng.randint(0, 59))),
        )
        db.add(v)
        db.flush()
        db.add(ExtractedField(visit_id=v.id, field_name="_structured_json", field_value=_json_text(structured)))
        for k, val in list(structured.items())[:10]:
            if k == "_structured_json":
                continue
            db.add(ExtractedField(visit_id=v.id, field_name=str(k), field_value=str(val)))
        if include_transcript or source == "voice":
            db.add(VoiceTranscript(
                visit_id=v.id,
                transcript=f"{SYNTHETIC_LABEL}: voice visit summary for {ben.name} ({category}).",
                language="en",
                created_at=v.created_at,
            ))
        visits.append(v)
        return v

    for b in beneficiaries:
        n = per_ben[b.id]
        for j in range(n):
            # mix: past completed, recent, missed-related past, upcoming (represented as recent/future-dated planned context via followups; visit itself recorded)
            if j == 0:
                days_ago = rng.randint(0, 20)
            elif j == 1:
                days_ago = rng.randint(21, 75)
            else:
                days_ago = rng.randint(76, 180)
            vdate = _d(-days_ago)
            source = "voice" if rng.random() < 0.4 else "manual"
            structured = {"beneficiary_name": b.name, "category": b.category, "visit_type": b.category, "synthetic_demo": True}
            v = add_visit(b, vdate, b.category, source, structured, include_transcript=(source == "voice"))

            if b.category == "pregnancy":
                weeks = max(8, min(40, 12 + (180 - days_ago) // 7))
                bp_sys = rng.randint(100, 138)
                bp_dia = rng.randint(65, 88)
                wt = round(rng.uniform(48.0, 78.0), 1)
                hb = round(rng.uniform(9.5, 12.8), 1)
                structured.update({"weeks_pregnant": weeks, "bp_sys": bp_sys, "bp_dia": bp_dia, "weight_kg": wt, "hemoglobin": hb})
                v.notes = _json_text(structured)
                db.add(PregnancyRecord(beneficiary_id=b.id, visit_id=v.id, weeks_pregnant=weeks, bp_sys=bp_sys, bp_dia=bp_dia, weight_kg=wt, hemoglobin=hb, fetal_heart="normal", notes=f"{SYNTHETIC_LABEL}: antenatal observation"))
                db.add(HealthMeasurement(beneficiary_id=b.id, visit_id=v.id, measurement_type="bp_sys", value=float(bp_sys), unit="mmHg", recorded_at=datetime.combine(vdate, datetime.min.time().replace(hour=10)), source=source, verification_status="recorded", notes=SYNTHETIC_LABEL))
                db.add(HealthMeasurement(beneficiary_id=b.id, visit_id=v.id, measurement_type="weight_kg", value=wt, unit="kg", recorded_at=datetime.combine(vdate, datetime.min.time().replace(hour=10, minute=5)), source=source, verification_status="recorded", notes=SYNTHETIC_LABEL))
            elif b.category in ("newborn", "child", "immunisation"):
                wt = round(rng.uniform(2.8, 18.0), 2)
                temp = round(rng.uniform(97.5, 99.2), 1)
                feeding = rng.choice(["breastfeeding well", "age-appropriate diet", "mixed feeding"])
                jaundice = rng.choice(["no", "no", "mild"])
                structured.update({"weight_kg": wt, "temperature": temp, "feeding": feeding, "jaundice": jaundice})
                v.notes = _json_text(structured)
                db.add(NewbornRecord(beneficiary_id=b.id, visit_id=v.id, weight_kg=wt, temperature=temp, feeding=feeding, jaundice=jaundice, notes=f"{SYNTHETIC_LABEL}: child/newborn observation"))
                db.add(HealthMeasurement(beneficiary_id=b.id, visit_id=v.id, measurement_type="weight_kg", value=wt, unit="kg", recorded_at=datetime.combine(vdate, datetime.min.time().replace(hour=10)), source=source, verification_status="recorded", notes=SYNTHETIC_LABEL))
                if b.category == "immunisation" or (b.category == "child" and rng.random() < 0.6):
                    vaccine = rng.choice(["BCG", "OPV-1", "PENTA-1", "PENTA-2", "PENTA-3", "MR-1", "DPT-Booster"])
                    dose = rng.randint(1, 3)
                    db.add(ImmunisationRecord(beneficiary_id=b.id, visit_id=v.id, vaccine_name=vaccine, dose_number=dose, date_given=vdate, next_due_date=vdate + timedelta(days=rng.randint(28, 120))))
                    structured["vaccine_name"] = vaccine
                    v.notes = _json_text(structured)
            elif b.category == "elderly":
                bp_sys = rng.randint(110, 150)
                bp_dia = rng.randint(70, 95)
                pulse = rng.randint(62, 92)
                structured.update({"bp_sys": bp_sys, "bp_dia": bp_dia, "pulse": pulse})
                v.notes = _json_text(structured)
                db.add(HealthMeasurement(beneficiary_id=b.id, visit_id=v.id, measurement_type="bp_sys", value=float(bp_sys), unit="mmHg", recorded_at=datetime.combine(vdate, datetime.min.time().replace(hour=10)), source=source, verification_status="recorded", notes=SYNTHETIC_LABEL))
            elif b.category == "nutrition":
                muac = round(rng.uniform(11.5, 24.0), 1)
                wt = round(rng.uniform(12.0, 65.0), 1)
                structured.update({"muac_cm": muac, "weight_kg": wt})
                v.notes = _json_text(structured)
                db.add(HealthMeasurement(beneficiary_id=b.id, visit_id=v.id, measurement_type="weight_kg", value=wt, unit="kg", recorded_at=datetime.combine(vdate, datetime.min.time().replace(hour=10)), source=source, verification_status="recorded", notes=SYNTHETIC_LABEL))
            else:
                structured.update({"notes_obs": "General health check (synthetic demo)"})
                v.notes = _json_text(structured)

    # 5) Follow-ups (75-100 total): upcoming, due, overdue, completed, cancelled
    # Includes a subset of household-level follow-ups for demonstrable household summaries.
    followup_target = rng.randint(TARGET_FOLLOWUPS_MIN, TARGET_FOLLOWUPS_MAX)
    hh_followup_count = min(15, followup_target // 5)
    ben_followup_count = followup_target - hh_followup_count

    statuses_pool = (["upcoming"] * 28 + ["due"] * 12 + ["overdue"] * 20 + ["completed"] * 22 + ["cancelled"] * 8)
    rng.shuffle(statuses_pool)

    for i in range(ben_followup_count):
        b = beneficiaries[i % len(beneficiaries)]
        st = statuses_pool[i % len(statuses_pool)]
        if st == "upcoming":
            due = _d(rng.randint(2, 45))
        elif st == "due":
            due = _d(rng.randint(0, 1))
        elif st == "overdue":
            due = _d(-rng.randint(1, 30))
        elif st == "completed":
            due = _d(-rng.randint(1, 40))
        else:
            due = _d(rng.randint(-10, 20))

        if b.category == "pregnancy":
            type_, cat = "anc", "pregnancy"
            reason = "Antenatal follow-up visit (synthetic demo)"
            action = "Schedule/complete ANC check as per routine workflow."
        elif b.category == "newborn":
            type_, cat = "newborn", "newborn"
            reason = "Newborn/postnatal follow-up (synthetic demo)"
            action = "Review feeding, weight, and routine newborn care."
        elif b.category in ("child", "immunisation"):
            type_, cat = "vaccination", "immunisation"
            reason = "Immunisation/child health follow-up (synthetic demo)"
            action = "Review vaccination schedule and growth monitoring."
        elif b.category == "elderly":
            type_, cat = "followup", "elderly"
            reason = "Elderly routine health follow-up (synthetic demo)"
            action = "Review vitals, medications, and routine wellbeing."
        elif b.category == "nutrition":
            type_, cat = "nutrition", "nutrition"
            reason = "Nutrition follow-up (synthetic demo)"
            action = "Review nutrition counseling and growth indicators."
        else:
            type_, cat = "community", "general"
            reason = "General community health follow-up (synthetic demo)"
            action = "Complete routine follow-up and record observations."

        _followup(
            db=db, rng=rng, beneficiary_id=b.id, household_id=b.household_id,
            type_=type_, category=cat, due_date=due, status=st,
            reason=reason, action=action,
            priority="high" if st == "overdue" else ("normal" if st in ("upcoming", "due", "completed") else "low"),
            visit_id=None, worker_id=worker_id,
            dedup=f"synseed:fu:{b.id}:{cat}:{i}",
        )

    # Household-level follow-ups for demonstrable summaries (counted in total)
    hh_fu_statuses = ["upcoming", "due", "overdue", "completed", "cancelled"]
    for i, hh in enumerate(households[:hh_followup_count]):
        st = hh_fu_statuses[i % len(hh_fu_statuses)]
        due = _d(rng.randint(-10, 25)) if st != "upcoming" else _d(rng.randint(3, 30))
        _followup(
            db=db, rng=rng, beneficiary_id=None, household_id=hh.id,
            type_="household", category="household", due_date=due, status=st,
            reason="Household health/hygiene follow-up (synthetic demo)",
            action="Review household health observations and counselling follow-up.",
            priority="normal" if st != "overdue" else "high",
            worker_id=worker_id, dedup=f"synseed:hhfu:{hh.id}:{i}",
        )

    # 6) Household visits (for household-level summaries)
    for hh in households:
        for k in range(rng.randint(1, 3)):
            vdate = _d(-rng.randint(5, 120))
            notes = {
                "synthetic_demo": True,
                "water_source": rng.choice(["piped water", "borewell", "protected well"]),
                "toilet_available": rng.choice([True, True, False]),
                "handwashing": rng.choice([True, True, False]),
                "waste_disposal": rng.choice(["collected", "segregated", "needs improvement"]),
                "counselling": "Household hygiene counselling provided (synthetic demo)",
            }
            db.add(HouseholdVisit(
                household_id=hh.id,
                worker_id=worker_id or 1,
                visit_date=vdate,
                notes=_json_text(notes),
                source="voice" if rng.random() < 0.3 else "manual",
                created_at=datetime.combine(vdate, datetime.min.time().replace(hour=11, minute=rng.randint(0, 59))),
            ))

    # 7) Care plan tasks (support My Health Plan / Pulse Thread context)
    for b in rng.sample(beneficiaries, k=min(120, len(beneficiaries))):
        for k in range(rng.randint(1, 2)):
            st = rng.choice(["pending", "completed", "missed", "pending", "completed"])
            due = _d(rng.randint(-20, 30))
            db.add(CarePlanTask(
                beneficiary_id=b.id,
                title=f"Synthetic demo care task ({b.category})",
                description=f"{SYNTHETIC_LABEL}: routine care-plan activity for demonstration.",
                category=rng.choice(["checkup", "followup", "vaccination", "education", "referral"]),
                due_date=due,
                priority=rng.choice(["normal", "high", "low"]),
                responsible="asha",
                status=st,
                notes=f"{SYNTHETIC_LABEL}: demonstrable care plan entry.",
                created_by=worker_id,
                completed_at=_dt((due - _today()).days, 12, 0) if st == "completed" else None,
                created_at=_dt(-rng.randint(5, 60), 9, 0),
                updated_at=_dt(-rng.randint(0, 10), 13, 0),
            ))

    db.commit()
    # refresh statuses for coherence (due/overdue based on dates)
    try:
        from app.services.followups import refresh_followup_statuses
        refresh_followup_statuses(db)
        db.commit()
    except Exception:
        db.rollback()

    return {"created": True, **verify_synthetic_demo(db)}


def verify_synthetic_demo(db: Session) -> dict:
    bq = select(Beneficiary).where(Beneficiary.data_origin == SYNTHETIC_ORIGIN)
    hq = select(Household).where(Household.data_origin == SYNTHETIC_ORIGIN)
    bens = db.execute(bq).scalars().all()
    hhs = db.execute(hq).scalars().all()
    b_ids = [b.id for b in bens]
    h_ids = [h.id for h in hhs]

    def count(model, cond):
        return db.execute(select(model).where(cond)).scalars().all() if False else db.query(model).filter(cond).count()

    by_cat = defaultdict(int)
    for b in bens:
        by_cat[b.category] += 1
    visits = db.query(VisitRecord).filter(VisitRecord.beneficiary_id.in_(b_ids)).count() if b_ids else 0
    fu_conditions = []
    if b_ids:
        fu_conditions.append(FollowUp.beneficiary_id.in_(b_ids))
    if h_ids:
        fu_conditions.append(FollowUp.household_id.in_(h_ids))
    followups = db.query(FollowUp).filter(or_(*fu_conditions)).all() if fu_conditions else []
    fu_by_status = defaultdict(int)
    for f in followups:
        fu_by_status[f.status] += 1
    household_members = db.query(HouseholdMember).filter(HouseholdMember.household_id.in_(h_ids)).count() if h_ids else 0
    hh_visits = db.query(HouseholdVisit).filter(HouseholdVisit.household_id.in_(h_ids)).count() if h_ids else 0
    preg = db.query(PregnancyRecord).filter(PregnancyRecord.beneficiary_id.in_(b_ids)).count() if b_ids else 0
    newborn = db.query(NewbornRecord).filter(NewbornRecord.beneficiary_id.in_(b_ids)).count() if b_ids else 0
    imm = db.query(ImmunisationRecord).filter(ImmunisationRecord.beneficiary_id.in_(b_ids)).count() if b_ids else 0
    meas = db.query(HealthMeasurement).filter(HealthMeasurement.beneficiary_id.in_(b_ids)).count() if b_ids else 0
    care = db.query(CarePlanTask).filter(CarePlanTask.beneficiary_id.in_(b_ids)).count() if b_ids else 0
    linked_bens = sum(1 for b in bens if b.household_id in set(h_ids))
    orphan_bens = sum(1 for b in bens if not b.household_id or b.household_id not in set(h_ids))

    # relationship consistency: every synthetic beneficiary (except marker) belongs to a valid synthetic household
    marker_id = db.execute(select(Beneficiary.id).where(Beneficiary.qr_id == SEED_MARKER)).scalar()
    non_marker_bens = [b for b in bens if b.id != marker_id]
    non_marker_linked = sum(1 for b in non_marker_bens if b.household_id in set(h_ids))

    return {
        "synthetic_households": len(hhs),
        "synthetic_beneficiaries": len(bens),
        "synthetic_beneficiaries_excluding_marker": len(non_marker_bens),
        "beneficiaries_by_category": dict(sorted(by_cat.items())),
        "synthetic_visit_records": visits,
        "synthetic_followups_total": len(followups),
        "synthetic_followups_by_status": dict(sorted(fu_by_status.items())),
        "household_members": household_members,
        "household_visits": hh_visits,
        "pregnancy_records": preg,
        "newborn_records": newborn,
        "immunisation_records": imm,
        "health_measurements": meas,
        "care_plan_tasks": care,
        "beneficiaries_linked_to_synthetic_household": linked_bens,
        "beneficiaries_without_valid_synthetic_household": orphan_bens,
        "non_marker_beneficiaries_linked_to_valid_household": non_marker_linked,
        "marker_present": marker_id is not None,
    }
