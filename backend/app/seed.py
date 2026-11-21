"""Opt-in demo data seeder.

Called only when demo setup is explicitly enabled and the database is empty.
All dates are computed relative to date.today() so demo records stay current
for development and demonstration.

DEMO LOGIN (clearly labelled, printed in the startup log):
    Worker ID: ASHA001
    Password:  Demo@123
"""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import (
    AshaWorker,
    Beneficiary,
    DangerAlert,
    FollowUp,
    Household,
    HouseholdMember,
    HouseholdVisit,
    ImmunisationRecord,
    NewbornRecord,
    PregnancyRecord,
    SmsReminder,
    VisitRecord,
    VoiceTranscript,
)
from app.rules import (
    REFERRAL_MESSAGE,
    anc_interval_days,
    next_anc_due,
    weeks_pregnant_on,
)

DEMO_WORKER_ID = "ASHA001"
DEMO_PASSWORD = "Demo@123"


def _days(n: int) -> date:
    return date.today() + timedelta(days=n)


def _qr_id() -> str:
    """Random, non-sensitive QR identifier like ASN-7F2K-9QMD."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars
    part = lambda: "".join(secrets.choice(alphabet) for _ in range(4))
    return f"ASN-{part()}-{part()}"


def ensure_demo_worker(db: Session) -> AshaWorker:
    """Create the demo worker if missing; keep the demo account usable for admin-only demo areas."""
    worker = db.query(AshaWorker).filter(AshaWorker.worker_id == DEMO_WORKER_ID).first()
    if worker is not None:
        changed = False
        if getattr(worker, "role", "asha") != "admin":
            worker.role = "admin"
            changed = True
        if not getattr(worker, "is_active", True):
            worker.is_active = True
            changed = True
        if changed:
            db.commit()
            db.refresh(worker)
        return worker

    worker = AshaWorker(
        worker_id=DEMO_WORKER_ID,
        name="Meena Kulkarni",
        password_hash=hash_password(DEMO_PASSWORD),
        language="en",
        phc="PHC Rampur",
        role="admin",
        is_active=True,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


def is_db_empty(db: Session) -> bool:
    return db.query(Beneficiary).count() == 0


def seed(db: Session) -> None:
    """Populate an empty database with labelled demo data."""
    if not is_db_empty(db):
        return

    worker_kwargs = dict(
        worker_id=DEMO_WORKER_ID,
        name="Meena Kulkarni",
        language="en",
        phc="PHC Rampur",
        role="admin",
        is_active=True,
    )
    worker = db.query(AshaWorker).filter(AshaWorker.worker_id == DEMO_WORKER_ID).first()
    if worker is None:
        worker = AshaWorker(password_hash=hash_password(DEMO_PASSWORD), **worker_kwargs)
        db.add(worker)
        db.flush()
    elif getattr(worker, "role", "asha") != "admin":
        worker.role = "admin"

    # ------------------------------------------------------------------
    # Beneficiaries
    # ------------------------------------------------------------------
    lakshmi = Beneficiary(qr_id=_qr_id(), name="Lakshmi Devi", age=24, category="pregnancy",
                          village="Rampur", phone="9876500001",
                          lmp_date=_days(-28 * 7), data_origin="demo")
    ananya = Beneficiary(qr_id=_qr_id(), name="Ananya", age=0, category="newborn",
                         village="Rampur", phone="9876500002",
                         birth_date=_days(-12), data_origin="demo")
    rohit = Beneficiary(qr_id=_qr_id(), name="Rohit Kumar", age=2, category="child",
                        village="Kishanganj", phone="9876500003", data_origin="demo")
    priya = Beneficiary(qr_id=_qr_id(), name="Priya Sharma", age=26, category="pregnancy",
                        village="Rampur", phone="9876500004",
                        lmp_date=_days(-32 * 7), data_origin="demo")
    sunita = Beneficiary(qr_id=_qr_id(), name="Sunita Bai", age=30, category="pregnancy",
                         village="Devgarh", phone="9876500005",
                         lmp_date=_days(-36 * 7), data_origin="demo")
    aarav = Beneficiary(qr_id=_qr_id(), name="Aarav", age=0, category="newborn",
                        village="Devgarh", phone="9876500006",
                        birth_date=_days(-10), data_origin="demo")
    chetan = Beneficiary(qr_id=_qr_id(), name="Chetan Singh", age=1, category="child",
                         village="Kishanganj", phone="9876500007",
                         birth_date=_days(-365), data_origin="demo")
    kavita = Beneficiary(qr_id=_qr_id(), name="Kavita Devi", age=22, category="pregnancy",
                         village="Rampur", phone="9876500008",
                         lmp_date=_days(-12 * 7), data_origin="demo")
    ishaan = Beneficiary(qr_id=_qr_id(), name="Ishaan", age=0, category="newborn",
                         village="Rampur", phone="9876500009",
                         birth_date=_days(-40), data_origin="demo")
    ira = Beneficiary(qr_id=_qr_id(), name="Ira Mishra", age=1, category="immunisation",
                      village="Kishanganj", phone="9876500010",
                      birth_date=_days(-250), data_origin="demo")
    kamala = Beneficiary(qr_id=_qr_id(), name="Kamala Devi", age=68, category="elderly",
                         village="Devgarh", phone="9876500011", data_origin="demo")
    db.add_all([lakshmi, ananya, rohit, priya, sunita, aarav, chetan, kavita, ishaan, ira, kamala])
    db.flush()

    # ------------------------------------------------------------------
    # Visit helper
    # ------------------------------------------------------------------
    def _jsonable(structured: dict) -> dict:
        """Convert date values to ISO strings so the JSON TEXT column works."""
        return {
            k: (v.isoformat() if isinstance(v, (date, datetime)) else v)
            for k, v in structured.items()
        }

    def add_visit(b: Beneficiary, visit_date: date, structured: dict, *, source: str = "voice",
                  transcript: str | None = None, language: str = "en") -> VisitRecord:
        visit = VisitRecord(
            beneficiary_id=b.id, worker_id=worker.id, visit_date=visit_date,
            category=b.category, notes=json.dumps(_jsonable(structured)), source=source,
        )
        db.add(visit)
        db.flush()
        if transcript:
            db.add(VoiceTranscript(visit_id=visit.id, transcript=transcript, language=language))
        return visit

    def add_pregnancy(visit: VisitRecord, b: Beneficiary, weeks: int | None = None, **fields) -> PregnancyRecord:
        record = PregnancyRecord(
            beneficiary_id=b.id, visit_id=visit.id,
            weeks_pregnant=weeks if weeks is not None else (
                weeks_pregnant_on(b.lmp_date, visit.visit_date) if b.lmp_date else None),
            notes="",
            **fields,
        )
        db.add(record)
        return record

    def add_newborn(visit: VisitRecord, b: Beneficiary, **fields) -> NewbornRecord:
        record = NewbornRecord(beneficiary_id=b.id, visit_id=visit.id, notes="", **fields)
        db.add(record)
        return record

    def add_followup(b: Beneficiary, type_: str, due: date, status: str = "upcoming",
                     visit: VisitRecord | None = None) -> FollowUp:
        fu = FollowUp(beneficiary_id=b.id, visit_id=visit.id if visit else None,
                      type=type_, due_date=due, status=status)
        db.add(fu)
        return fu

    def add_reminder(b: Beneficiary, type_: str, due: date, status: str,
                     message: str, fu: FollowUp | None = None) -> SmsReminder:
        # `status` is the schedule state; `sms_status` is the delivery state.
        # Seeded history is demo data — no real SMS was ever sent, so it is
        # labelled "demo_sent" rather than claiming a real delivery.
        if status == "sent":
            sms_status = "demo_sent"
        elif status == "overdue":
            sms_status = "pending"
        else:
            sms_status = "pending"
        rem = SmsReminder(beneficiary_id=b.id, follow_up_id=fu.id if fu else None,
                          type=type_, message=message, due_date=due, status=status,
                          sms_status=sms_status, sms_consent=True)
        db.add(rem)
        return rem

    # ------------------------------------------------------------------
    # 1) Lakshmi Devi — 28 weeks, ANC visit TODAY (the sample sentence).
    # ------------------------------------------------------------------
    today_struct = {"beneficiary_name": "Lakshmi Devi", "weeks_pregnant": 28,
                    "bp_sys": 120, "bp_dia": 80, "weight_kg": 53.0,
                    "visit_date": _days(0)}
    v = add_visit(lakshmi, _days(0), today_struct, transcript=
                  "Visited Lakshmi today. She is 28 weeks pregnant. Blood pressure is 120 over 80. "
                  "Weight is 53 kilograms.")
    add_pregnancy(v, lakshmi, bp_sys=120, bp_dia=80, weight_kg=53.0)
    fu = add_followup(lakshmi, "anc", next_anc_due(_days(0), 28), visit=v)
    add_reminder(lakshmi, "anc", next_anc_due(_days(0), 28), "sent",
                 "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.", fu=fu)
    # Earlier ANC history
    v2 = add_visit(lakshmi, _days(-28), {"beneficiary_name": "Lakshmi Devi", "weeks_pregnant": 24,
                                         "bp_sys": 112, "bp_dia": 74, "weight_kg": 51.5,
                                         "visit_date": _days(-28)}, source="manual")
    add_pregnancy(v2, lakshmi, bp_sys=112, bp_dia=74, weight_kg=51.5)

    # ------------------------------------------------------------------
    # 2) Ananya — newborn, 12 days old. Birth + day-3 visits done;
    #    day-7 checkup overdue.
    # ------------------------------------------------------------------
    v = add_visit(ananya, ananya.birth_date, {"beneficiary_name": "Ananya", "weight_kg": 2.7,
                                              "temperature": 98.2, "feeding": "breastfeeding well",
                                              "jaundice": "no", "visit_date": ananya.birth_date},
                  transcript="Ananya born today. Weight 2.7 kg. Temperature 98.2 degrees. "
                             "Breastfeeding well. No jaundice.")
    add_newborn(v, ananya, weight_kg=2.7, temperature=98.2, feeding="breastfeeding well", jaundice="no")
    v3 = add_visit(ananya, ananya.birth_date + timedelta(days=3),
                   {"beneficiary_name": "Ananya", "weight_kg": 2.75, "temperature": 98.0,
                    "feeding": "breastfeeding well", "jaundice": "no",
                    "visit_date": ananya.birth_date + timedelta(days=3)}, source="manual")
    add_newborn(v3, ananya, weight_kg=2.75, temperature=98.0, feeding="breastfeeding well", jaundice="no")
    add_followup(ananya, "newborn", ananya.birth_date + timedelta(days=7), status="overdue")

    # ------------------------------------------------------------------
    # 3) Rohit — child, growth monitoring 10 days ago; monthly FU upcoming.
    # ------------------------------------------------------------------
    v = add_visit(rohit, _days(-10), {"beneficiary_name": "Rohit Kumar", "weight_kg": 11.2,
                                      "temperature": 98.6, "visit_date": _days(-10)},
                  transcript="Rohit visited. Weight is 11.2 kilograms. Temperature 98.6 degrees.")
    add_newborn(v, rohit, weight_kg=11.2, temperature=98.6, feeding="eating well", jaundice="no")
    add_followup(rohit, "newborn", _days(20))

    # ------------------------------------------------------------------
    # 4) Priya — 32 weeks; ANC 5 days ago; next ANC upcoming in ~9 days.
    # ------------------------------------------------------------------
    v = add_visit(priya, _days(-5), {"beneficiary_name": "Priya Sharma", "weeks_pregnant": 31,
                                     "bp_sys": 118, "bp_dia": 76, "weight_kg": 58.0,
                                     "hemoglobin": 11.2, "visit_date": _days(-5)},
                  transcript="Visited Priya today. She is 31 weeks pregnant. BP 118 over 76. "
                             "Weight is 58 kilograms. Hemoglobin is 11.2.")
    add_pregnancy(v, priya, bp_sys=118, bp_dia=76, weight_kg=58.0, hemoglobin=11.2)
    due = _days(-5) + timedelta(days=anc_interval_days(31))
    fu = add_followup(priya, "anc", due, visit=v)
    add_reminder(priya, "anc", due, "scheduled", "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.", fu=fu)

    # ------------------------------------------------------------------
    # 5) Sunita — 36 weeks; last ANC 21 days ago (weekly interval required
    #    at 36+ weeks -> ANC overdue). Past visit reported "severe headache"
    #    -> one OPEN danger alert.
    # ------------------------------------------------------------------
    v = add_visit(sunita, _days(-21), {"beneficiary_name": "Sunita Bai", "weeks_pregnant": 33,
                                       "bp_sys": 138, "bp_dia": 88, "weight_kg": 61.0,
                                       "visit_date": _days(-21)},
                  transcript="Visited Sunita today. She is 33 weeks pregnant. She reports "
                             "severe headache since morning. BP 138 over 88. Weight is 61 kilograms.")
    add_pregnancy(v, sunita, bp_sys=138, bp_dia=88, weight_kg=61.0)
    db.add(DangerAlert(beneficiary_id=sunita.id, visit_id=v.id,
                       triggered_phrase="severe headache", rule_id="PREG-02",
                       message=REFERRAL_MESSAGE, severity="high", status="open",
                       created_at=datetime.combine(_days(-21), datetime.min.time())))
    add_followup(sunita, "anc", _days(-21) + timedelta(days=anc_interval_days(33)), status="overdue", visit=v)
    add_reminder(sunita, "anc", _days(-7), "overdue", "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.")

    # ------------------------------------------------------------------
    # 6) Aarav — newborn 10 days old; birth visit done, day-7 visit missed.
    # ------------------------------------------------------------------
    v = add_visit(aarav, aarav.birth_date, {"beneficiary_name": "Aarav", "weight_kg": 2.9,
                                            "temperature": 98.4, "feeding": "breastfeeding well",
                                            "jaundice": "no", "visit_date": aarav.birth_date},
                  source="manual")
    add_newborn(v, aarav, weight_kg=2.9, temperature=98.4, feeding="breastfeeding well", jaundice="no")
    add_followup(aarav, "newborn", aarav.birth_date + timedelta(days=7), status="overdue", visit=v)

    # ------------------------------------------------------------------
    # 7) Chetan — child, 1 year old, 14-week PENTA-3 vaccination missed
    #    (due ~week 14 after birth, never given -> FollowUp missed).
    # ------------------------------------------------------------------
    penta1_date = chetan.birth_date + timedelta(days=42)
    v = add_visit(chetan, penta1_date, {"beneficiary_name": "Chetan Singh",
                                        "vaccine_name": "PENTA-1", "visit_date": penta1_date},
                  source="manual")
    db.add(ImmunisationRecord(beneficiary_id=chetan.id, visit_id=v.id, vaccine_name="PENTA-1",
                              dose_number=1, date_given=penta1_date,
                              next_due_date=chetan.birth_date + timedelta(days=70)))
    db.add(ImmunisationRecord(beneficiary_id=chetan.id, visit_id=v.id, vaccine_name="BCG",
                              dose_number=1, date_given=chetan.birth_date,
                              next_due_date=chetan.birth_date + timedelta(days=42)))
    # PENTA-3 (14 weeks) never recorded -> missed vaccination follow-up.
    add_followup(chetan, "vaccination", chetan.birth_date + timedelta(days=98), status="missed")
    add_reminder(chetan, "vaccination", _days(-3), "overdue",
                 "Reminder: A community health visit is scheduled. Please coordinate with your local ASHA worker.")

    # ------------------------------------------------------------------
    # 8) Kavita — 12 weeks; ANC 10 days ago; next ANC upcoming.
    #    Latest visit is MISSING weight -> drift engine flags
    #    "missing record for verification" (a record gap, not a medical claim).
    # ------------------------------------------------------------------
    v = add_visit(kavita, _days(-10), {"beneficiary_name": "Kavita Devi", "weeks_pregnant": 10,
                                       "bp_sys": 110, "bp_dia": 70,
                                       "visit_date": _days(-10)},
                  transcript="Visited Kavita today. She is 10 weeks pregnant. BP 110 over 70. "
                             "She denies severe headache and there is no heavy bleeding.")
    add_pregnancy(v, kavita, bp_sys=110, bp_dia=70)  # no weight recorded on purpose
    due = _days(-10) + timedelta(days=anc_interval_days(10))
    fu = add_followup(kavita, "anc", due, visit=v)
    add_reminder(kavita, "anc", due, "scheduled", "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.", fu=fu)

    # ------------------------------------------------------------------
    # 9) Ishaan — newborn 40 days old; 6-week checkup due 2 days ago.
    # ------------------------------------------------------------------
    v = add_visit(ishaan, ishaan.birth_date, {"beneficiary_name": "Ishaan", "weight_kg": 3.1,
                                              "temperature": 98.0, "feeding": "breastfeeding well",
                                              "jaundice": "no", "visit_date": ishaan.birth_date},
                  source="manual")
    add_newborn(v, ishaan, weight_kg=3.1, temperature=98.0, feeding="breastfeeding well", jaundice="no")
    add_followup(ishaan, "newborn", ishaan.birth_date + timedelta(days=42), status="overdue", visit=v)

    # ------------------------------------------------------------------
    # 10) Ira — immunisation category; MR due at 9 months = upcoming in ~20 days.
    #      BCG + PENTA-1 recorded.
    # ------------------------------------------------------------------
    bcg_date = ira.birth_date
    v = add_visit(ira, bcg_date, {"beneficiary_name": "Ira Mishra", "vaccine_name": "BCG",
                                  "visit_date": bcg_date}, source="manual")
    db.add(ImmunisationRecord(beneficiary_id=ira.id, visit_id=v.id, vaccine_name="BCG",
                              dose_number=1, date_given=bcg_date,
                              next_due_date=ira.birth_date + timedelta(days=42)))
    penta1 = ira.birth_date + timedelta(days=42)
    v = add_visit(ira, penta1, {"beneficiary_name": "Ira Mishra", "vaccine_name": "PENTA-1",
                                "visit_date": penta1}, source="manual")
    db.add(ImmunisationRecord(beneficiary_id=ira.id, visit_id=v.id, vaccine_name="PENTA-1",
                              dose_number=1, date_given=penta1,
                              next_due_date=ira.birth_date + timedelta(days=270)))
    mr_due = ira.birth_date + timedelta(days=270)
    fu = add_followup(ira, "vaccination", mr_due)
    add_reminder(ira, "vaccination", mr_due, "scheduled", "Reminder: A community health visit is scheduled. Please coordinate with your local ASHA worker.", fu=fu)

    # ------------------------------------------------------------------
    # 11) Kamala Devi — elderly beneficiary; general health visit 25 days
    #     ago; community (VHSND) follow-up upcoming in ~5 days.
    # ------------------------------------------------------------------
    v = add_visit(kamala, _days(-25), {"beneficiary_name": "Kamala Devi", "bp_sys": 146,
                                       "bp_dia": 90, "visit_date": _days(-25), "type": "community"},
                  source="manual")
    add_followup(kamala, "community", _days(5), visit=v)

    # ------------------------------------------------------------------
    # 12) Rohit — nutrition follow-up visit 40 days ago (counselling +
    #     weight check); 30-day nutrition follow-up now OVERDUE.
    # ------------------------------------------------------------------
    v = add_visit(rohit, _days(-40), {"beneficiary_name": "Rohit Kumar", "weight_kg": 10.9,
                                      "type": "nutrition", "visit_date": _days(-40),
                                      "counselling": "complementary feeding and diet diversity"},
                  transcript="Nutrition follow-up for Rohit. Weight 10.9 kilograms. "
                             "Counselled the family on complementary feeding and diet diversity.")
    add_followup(rohit, "nutrition", _days(-10), visit=v)

    # ------------------------------------------------------------------
    # HOUSEHOLDS — Household Health & Hygiene
    # ------------------------------------------------------------------
    hh1 = Household(qr_id="HN-4KDP-7RWM", village="Rampur", address="House 24, Ward 3, Near Anganwadi", member_count=5, data_origin="demo")
    hh2 = Household(qr_id="HN-9MWK-2QXF", village="Kishanganj", address="House 11, Ward 1", member_count=4, data_origin="demo")
    hh3 = Household(qr_id="HN-7TSP-5CJB", village="Devgarh", address="House 7, Hill Road", member_count=6, data_origin="demo")
    db.add_all([hh1, hh2, hh3])
    db.flush()

    db.add_all([
        HouseholdMember(household_id=hh1.id, name="Ramesh Yadav", age=31, gender="male", relation="head"),
        HouseholdMember(household_id=hh1.id, name="Lakshmi Devi", age=24, gender="female", relation="spouse",
                        beneficiary_id=lakshmi.id),
        HouseholdMember(household_id=hh1.id, name="Ananya", age=0, gender="female", relation="child",
                        beneficiary_id=ananya.id),
        HouseholdMember(household_id=hh2.id, name="Savitri Kumari", age=38, gender="female", relation="head"),
        HouseholdMember(household_id=hh2.id, name="Rohit Kumar", age=2, gender="male", relation="son",
                        beneficiary_id=rohit.id),
        HouseholdMember(household_id=hh2.id, name="Ira Mishra", age=1, gender="female", relation="daughter",
                        beneficiary_id=ira.id),
        HouseholdMember(household_id=hh3.id, name="Harish Bai", age=45, gender="male", relation="head"),
        HouseholdMember(household_id=hh3.id, name="Sunita Bai", age=30, gender="female", relation="spouse",
                        beneficiary_id=sunita.id),
        HouseholdMember(household_id=hh3.id, name="Aarav", age=0, gender="male", relation="son",
                        beneficiary_id=aarav.id),
        HouseholdMember(household_id=hh3.id, name="Kamala Devi", age=68, gender="female", relation="grandmother",
                        beneficiary_id=kamala.id),
    ])

    # HH1 (Rampur) — hygiene visit 12 days ago; stagnant water reported and
    # counselling given; 7-day verification follow-up is now OVERDUE.
    hh1_struct = {
        "water_source": "borewell", "water_storage_covered": True,
        "toilet_available": True, "toilet_usage": "used",
        "waste_disposal": "waste is collected twice a week", "drainage": "open",
        "stagnant_water": True, "handwashing": True, "awareness_provided": True,
        "visit_date": _days(-12).isoformat(),
    }
    hh1_visit = HouseholdVisit(household_id=hh1.id, worker_id=worker.id, visit_date=_days(-12),
                               notes=json.dumps(hh1_struct), source="voice")
    db.add(hh1_visit)
    db.add(VoiceTranscript(transcript=(
        "Visited household 24 today. They use borewell water. Water is stored in a covered container. "
        "Toilet is available. Waste is collected twice a week. There is stagnant water near the drainage. "
        "I advised the family to clear it and prevent mosquito breeding."), language="en"))
    db.add(FollowUp(household_id=hh1.id, type="household", due_date=_days(-5), status="overdue"))

    # HH2 (Kishanganj) — clean observation 6 days ago; next follow-up in 8 days.
    hh2_struct = {
        "water_source": "piped water", "water_storage_covered": True,
        "toilet_available": True, "toilet_usage": "used",
        "waste_disposal": "waste is collected twice a week", "drainage": "closed",
        "stagnant_water": False, "handwashing": True, "awareness_provided": True,
        "visit_date": _days(-6).isoformat(),
    }
    db.add(HouseholdVisit(household_id=hh2.id, worker_id=worker.id, visit_date=_days(-6),
                          notes=json.dumps(hh2_struct), source="manual"))
    db.add(FollowUp(household_id=hh2.id, type="household", due_date=_days(8), status="upcoming"))

    # HH3 (Devgarh) — visit today: water safe, but waste is burnt (counselled).
    hh3_struct = {
        "water_source": "piped water", "water_storage_covered": True,
        "toilet_available": True, "toilet_usage": "used",
        "waste_disposal": "waste is burnt", "drainage": "good",
        "stagnant_water": False, "handwashing": True, "awareness_provided": True,
        "follow_up_days": 14, "visit_date": _days(0).isoformat(),
    }
    db.add(HouseholdVisit(household_id=hh3.id, worker_id=worker.id, visit_date=_days(0),
                          notes=json.dumps(hh3_struct), source="voice"))
    db.add(VoiceTranscript(transcript=(
        "Visited household 7 today. They use piped water. Water is stored in a covered container. "
        "Toilet is available and used. Waste is burnt, I advised them to use waste collection instead. "
        "Handwashing facility is available with soap. Follow up in 14 days."), language="en"))
    db.add(FollowUp(household_id=hh3.id, type="household", due_date=_days(14), status="upcoming"))

    db.commit()

    # ------------------------------------------------------------------
    # Extended demo dataset: 50 households, 150 beneficiaries
    # ------------------------------------------------------------------
    seed_extended(db, worker)

    # Demo contact addresses so the SMS / email notification workflows
    # have something to work with. Real deployments leave this empty.
    backfill_emails(db)


# ---------------------------------------------------------------------------
# Demo email addresses
#
# The demo dataset is for demonstration, so addresses use the reserved
# "example.invalid" domain (RFC 2606) and can never reach a real mailbox.
# ---------------------------------------------------------------------------

def _demo_email(b: Beneficiary) -> str:
    """A deterministic, non-deliverable address for a demo beneficiary."""
    import re
    import unicodedata

    base = unicodedata.normalize("NFKD", b.name or "").encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", ".", base).strip(".").lower()
    if not base:
        base = "beneficiary"
    return f"{base}.{b.id}@example.invalid"


def backfill_emails(db: Session) -> int:
    """Give every beneficiary without an address a demo one.

    Idempotent — beneficiaries that already have an address keep it.
    """
    updated = 0
    for b in db.query(Beneficiary).all():
        if b.email:
            continue
        b.email = _demo_email(b)
        updated += 1
    if updated:
        db.commit()
    return updated


# ---------------------------------------------------------------------------
# Extended seed — 50 households, 150 beneficiaries (demo data)
# ---------------------------------------------------------------------------

def _hh_qr_id() -> str:
    """Random QR for households — same alphabet, HN prefix."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part = lambda: "".join(secrets.choice(alphabet) for _ in range(4))
    return f"HN-{part()}-{part()}"


def seed_extended(db: Session, worker) -> None:  # noqa: C901
    """Add 50 households and 150 beneficiaries marked as demo data."""
    import random

    rng = random.Random(42)  # deterministic so reruns are identical

    VILLAGES = [
        "Rampur", "Kishanganj", "Devgarh", "Hoskote", "Devanahalli",
        "Chikkaballapur", "Kolar", "Sidlaghatta", "Anekal",
    ]
    WOMEN_NAMES = [
        "Lakshmi", "Meera", "Savitri", "Kamala", "Radha", "Geetha",
        "Suma", "Rupa", "Nirmala", "Prema", "Kavita", "Sharada",
        "Usha", "Vani", "Asha", "Deepa", "Sujatha", "Saroja",
        "Bharathi", "Manjula", "Sudha", "Revathi", "Latha", "Pushpa",
        "Anita", "Rekha", "Leela", "Vinoda", "Rohini", "Saraswathi",
    ]
    MEN_NAMES = [
        "Ravi", "Krishna", "Suresh", "Ramesh", "Mahesh", "Naresh",
        "Ganesh", "Rajesh", "Dinesh", "Umesh", "Sathish", "Girish",
        "Harish", "Shashi", "Venkatesh", "Prakash", "Santosh",
        "Lokesh", "Manjunath", "Srinivasa",
    ]
    SURNAMES = [
        "Kumar", "Reddy", "Gowda", "Naik", "Rao", "Sharma", "Nair",
        "Pillai", "Hegde", "Joshi", "Patil", "Desai", "Shah", "Devi", "Bai",
    ]

    _used_qr: set[str] = set()

    def _unique_qr() -> str:
        for _ in range(1000):
            q = _qr_id()
            if q not in _used_qr:
                _used_qr.add(q)
                return q
        raise RuntimeError("QR collision loop")  # should never happen

    def _unique_hh_qr() -> str:
        for _ in range(1000):
            q = _hh_qr_id()
            if q not in _used_qr:
                _used_qr.add(q)
                return q
        raise RuntimeError("HH QR collision loop")

    def _female_name() -> str:
        return f"{rng.choice(WOMEN_NAMES)} {rng.choice(SURNAMES)}"

    def _male_name() -> str:
        return f"{rng.choice(MEN_NAMES)} {rng.choice(SURNAMES)}"

    def _phone() -> str:
        return f"98765{rng.randint(10000, 99999)}"

    # ------------------------------------------------------------------
    # Helper: add visit/follow-up quickly
    # ------------------------------------------------------------------
    def _jsonable(d: dict) -> dict:
        return {
            k: (v.isoformat() if isinstance(v, (date, datetime)) else v)
            for k, v in d.items()
        }

    def _add_visit(b: "Beneficiary", visit_date: date, structured: dict,
                   source: str = "voice") -> "VisitRecord":
        v = VisitRecord(
            beneficiary_id=b.id, worker_id=worker.id,
            visit_date=visit_date, category=b.category,
            notes=json.dumps(_jsonable(structured)), source=source,
        )
        db.add(v)
        db.flush()
        return v

    def _add_preg(visit: "VisitRecord", b: "Beneficiary", **kw) -> None:
        db.add(PregnancyRecord(
            beneficiary_id=b.id, visit_id=visit.id,
            weeks_pregnant=kw.pop("weeks_pregnant", None),
            notes="Demo record",
            **kw,
        ))

    def _add_newborn_rec(visit: "VisitRecord", b: "Beneficiary", **kw) -> None:
        db.add(NewbornRecord(
            beneficiary_id=b.id, visit_id=visit.id, notes="Demo record",
            **kw,
        ))

    def _add_imm(visit: "VisitRecord", b: "Beneficiary",
                 vaccine: str, dose: int, given: date, nxt: date) -> None:
        db.add(ImmunisationRecord(
            beneficiary_id=b.id, visit_id=visit.id,
            vaccine_name=vaccine, dose_number=dose,
            date_given=given, next_due_date=nxt,
        ))

    def _add_fu(b: "Beneficiary", type_: str, due: date,
                status: str = "upcoming", visit: "VisitRecord | None" = None) -> None:
        db.add(FollowUp(
            beneficiary_id=b.id,
            visit_id=visit.id if visit else None,
            type=type_, due_date=due, status=status,
        ))

    # ------------------------------------------------------------------
    # Build beneficiaries in category groups
    # ------------------------------------------------------------------
    all_bens: list["Beneficiary"] = []

    # ---- 1. Pregnant women (~40) ----------------------------------------
    for i in range(40):
        village = rng.choice(VILLAGES)
        weeks = rng.randint(8, 38)
        lmp = _days(-weeks * 7)
        age = rng.randint(19, 35)
        b = Beneficiary(
            qr_id=_unique_qr(), name=_female_name(), age=age,
            category="pregnancy", village=village,
            phone=_phone(), lmp_date=lmp,
            data_origin="demo",
        )
        db.add(b)
        db.flush()
        # Add an ANC visit
        last_visit_days = rng.randint(0, 30)
        visit_date = _days(-last_visit_days)
        v_weeks = max(4, weeks - last_visit_days // 7)
        bp_sys = rng.randint(100, 145)
        bp_dia = rng.randint(60, 95)
        wt = round(rng.uniform(45, 75), 1)
        v = _add_visit(b, visit_date, {
            "beneficiary_name": b.name, "weeks_pregnant": v_weeks,
            "bp_sys": bp_sys, "bp_dia": bp_dia, "weight_kg": wt,
            "visit_date": visit_date,
        })
        _add_preg(v, b, weeks_pregnant=v_weeks, bp_sys=bp_sys, bp_dia=bp_dia, weight_kg=wt)
        # Follow-up
        fu_due = next_anc_due(visit_date, v_weeks)
        fu_status = "overdue" if fu_due < date.today() else "upcoming"
        _add_fu(b, "anc", fu_due, fu_status, v)
        all_bens.append(b)

    # ---- 2. Newborns (~25) ----------------------------------------------
    for i in range(25):
        village = rng.choice(VILLAGES)
        days_old = rng.randint(0, 28)
        birth_date = _days(-days_old)
        b = Beneficiary(
            qr_id=_unique_qr(), name=rng.choice(["Arjun", "Tanvi", "Pooja", "Dev",
                                                   "Preethi", "Akhil", "Nisha", "Rohan",
                                                   "Divya", "Arun", "Bhavna", "Charu"]),
            age=0, category="newborn",
            village=village,
            phone=_phone(), birth_date=birth_date,
            data_origin="demo",
        )
        db.add(b)
        db.flush()
        wt = round(rng.uniform(2.3, 4.0), 2)
        temp = round(rng.uniform(97.5, 99.0), 1)
        feeding = rng.choice(["breastfeeding well", "mixed feeding", "breastfeeding well"])
        jaundice = rng.choice(["no", "no", "no", "yes"])
        v = _add_visit(b, birth_date, {
            "beneficiary_name": b.name, "weight_kg": wt,
            "temperature": temp, "feeding": feeding, "jaundice": jaundice,
            "visit_date": birth_date,
        }, source="manual")
        _add_newborn_rec(v, b, weight_kg=wt, temperature=temp,
                         feeding=feeding, jaundice=jaundice)
        # Day-7 follow-up
        d7 = birth_date + timedelta(days=7)
        d7_status = "overdue" if d7 < date.today() else "upcoming"
        _add_fu(b, "newborn", d7, d7_status, v)
        all_bens.append(b)

    # ---- 3. Children 1–5 years (~40) ------------------------------------
    VACCINES = [
        ("BCG", 1), ("PENTA-1", 1), ("PENTA-2", 2), ("PENTA-3", 3),
        ("MR-1", 1), ("OPV-1", 1), ("OPV-2", 2), ("OPV-3", 3),
    ]
    for i in range(40):
        village = rng.choice(VILLAGES)
        age_months = rng.randint(12, 60)
        birth_date = _days(-age_months * 30)
        age_years = age_months // 12
        is_immunisation = rng.random() < 0.4
        category = "immunisation" if is_immunisation else "child"
        b = Beneficiary(
            qr_id=_unique_qr(),
            name=rng.choice([
                "Aditya", "Bhavya", "Chetan", "Disha", "Esha",
                "Farhan", "Geeta", "Hari", "Indira", "Jay",
                "Kiran", "Lata", "Mohan", "Nita", "Om",
            ]),
            age=age_years, category=category,
            village=village,
            phone=_phone(), birth_date=birth_date,
            data_origin="demo",
        )
        db.add(b)
        db.flush()
        wt = round(rng.uniform(8.0, 20.0), 1)
        v = _add_visit(b, _days(-rng.randint(5, 60)), {
            "beneficiary_name": b.name, "weight_kg": wt,
            "visit_date": _days(-rng.randint(5, 60)),
        }, source="manual")
        _add_newborn_rec(v, b, weight_kg=wt, temperature=98.6,
                         feeding="eating well", jaundice="no")
        # Vaccination record
        if is_immunisation:
            vax, dose = rng.choice(VACCINES)
            given_date = birth_date + timedelta(days=rng.randint(42, 180))
            if given_date > date.today():
                given_date = date.today() - timedelta(days=1)
            nxt = given_date + timedelta(days=28)
            _add_imm(v, b, vax, dose, given_date, nxt)
            fu_status = "upcoming" if nxt > date.today() else "missed"
            _add_fu(b, "vaccination", nxt, fu_status, v)
        else:
            # Monthly growth follow-up
            due = _days(rng.randint(-15, 30))
            fu_status = "overdue" if due < date.today() else "upcoming"
            _add_fu(b, "growth", due, fu_status, v)
        all_bens.append(b)

    # ---- 4. Elderly (~20) -----------------------------------------------
    for i in range(20):
        village = rng.choice(VILLAGES)
        age = rng.randint(60, 85)
        gender = rng.choice(["female", "male"])
        name = _female_name() if gender == "female" else _male_name()
        b = Beneficiary(
            qr_id=_unique_qr(), name=name, age=age,
            category="elderly",
            village=village,
            phone=_phone(),
            data_origin="demo",
        )
        db.add(b)
        db.flush()
        bp_sys = rng.randint(120, 165)
        bp_dia = rng.randint(70, 100)
        last_days = rng.randint(5, 60)
        v = _add_visit(b, _days(-last_days), {
            "beneficiary_name": b.name, "bp_sys": bp_sys, "bp_dia": bp_dia,
            "type": "community", "visit_date": _days(-last_days),
        })
        due = _days(rng.randint(-10, 30))
        fu_status = "overdue" if due < date.today() else "upcoming"
        _add_fu(b, "community", due, fu_status, v)
        all_bens.append(b)

    # ---- 5. Adolescent/general (~15) ------------------------------------
    for i in range(15):
        village = rng.choice(VILLAGES)
        age = rng.randint(10, 19)
        gender = rng.choice(["female", "male"])
        name = _female_name() if gender == "female" else _male_name()
        b = Beneficiary(
            qr_id=_unique_qr(), name=name, age=age,
            category="adolescent",
            village=village,
            phone=_phone(),
            data_origin="demo",
        )
        db.add(b)
        db.flush()
        v = _add_visit(b, _days(-rng.randint(10, 90)), {
            "beneficiary_name": b.name, "category": "adolescent",
            "visit_date": _days(-rng.randint(10, 90)),
        })
        _add_fu(b, "community", _days(rng.randint(10, 45)))
        all_bens.append(b)

    # ---- 6. Nutrition cases (~10) ---------------------------------------
    for i in range(10):
        village = rng.choice(VILLAGES)
        age = rng.randint(0, 5)
        b = Beneficiary(
            qr_id=_unique_qr(), name=_female_name(), age=age,
            category="nutrition",
            village=village,
            phone=_phone(),
            data_origin="demo",
        )
        db.add(b)
        db.flush()
        wt = round(rng.uniform(6.0, 15.0), 1)
        v = _add_visit(b, _days(-rng.randint(5, 40)), {
            "beneficiary_name": b.name, "weight_kg": wt,
            "type": "nutrition", "counselling": "complementary feeding",
            "visit_date": _days(-rng.randint(5, 40)),
        })
        due = _days(rng.randint(-5, 30))
        fu_status = "overdue" if due < date.today() else "upcoming"
        _add_fu(b, "nutrition", due, fu_status, v)
        all_bens.append(b)

    # ------------------------------------------------------------------
    # Build 50 households and distribute beneficiaries as members
    # ------------------------------------------------------------------
    HOUSE_ADDRESSES = [
        "House {n}, Ward {w}, Near Anganwadi",
        "House {n}, Main Road",
        "House {n}, Hill Colony",
        "House {n}, River Side",
        "House {n}, Market Area",
        "House {n}, Back Lane",
    ]
    HH_RELATIONS = ["head", "spouse", "son", "daughter", "grandmother",
                     "grandfather", "mother", "father", "sibling"]

    # Shuffle beneficiaries so each category gets spread across households
    rng.shuffle(all_bens)
    ben_iter = iter(all_bens)

    households: list["Household"] = []
    for idx in range(50):
        village = rng.choice(VILLAGES)
        addr_tmpl = rng.choice(HOUSE_ADDRESSES)
        address = addr_tmpl.format(n=rng.randint(1, 200), w=rng.randint(1, 10))
        member_count = rng.randint(2, 6)

        hh = Household(
            qr_id=_unique_hh_qr(),
            village=village,
            address=address,
            member_count=member_count,
            data_origin="demo",
        )
        db.add(hh)
        db.flush()
        households.append(hh)

        # Add household head (non-registered)
        head_gender = rng.choice(["male", "female"])
        head_name = _male_name() if head_gender == "male" else _female_name()
        db.add(HouseholdMember(
            household_id=hh.id, name=head_name,
            age=rng.randint(28, 55), gender=head_gender, relation="head",
        ))

        # Add 1–3 registered beneficiaries as members
        reg_count = min(rng.randint(1, 3), member_count - 1)
        for _ in range(reg_count):
            try:
                ben = next(ben_iter)
            except StopIteration:
                break
            relation = rng.choice(HH_RELATIONS[1:])  # skip "head"
            db.add(HouseholdMember(
                household_id=hh.id,
                name=ben.name,
                age=ben.age,
                gender="female" if any(n in ben.name for n in WOMEN_NAMES) else "male",
                relation=relation,
                beneficiary_id=ben.id,
            ))

        # Household visit (some have one, some don't)
        if rng.random() < 0.7:
            water_src = rng.choice(["borewell", "piped water", "open well", "tanker"])
            has_toilet = rng.random() < 0.75
            stagnant = rng.random() < 0.25
            hh_struct = {
                "water_source": water_src,
                "water_storage_covered": rng.random() < 0.8,
                "toilet_available": has_toilet,
                "toilet_usage": "used" if has_toilet and rng.random() < 0.85 else "not used",
                "waste_disposal": rng.choice(["waste is collected twice a week",
                                              "waste is burnt", "open dump"]),
                "drainage": rng.choice(["open", "closed", "good"]),
                "stagnant_water": stagnant,
                "handwashing": rng.random() < 0.7,
                "awareness_provided": True,
                "visit_date": _days(-rng.randint(0, 60)).isoformat(),
            }
            hh_visit_date = _days(-rng.randint(0, 60))
            db.add(HouseholdVisit(
                household_id=hh.id, worker_id=worker.id,
                visit_date=hh_visit_date,
                notes=json.dumps(hh_struct), source="voice",
            ))
            fu_due = _days(rng.randint(-10, 30))
            fu_status = "overdue" if fu_due < date.today() else "upcoming"
            db.add(FollowUp(
                household_id=hh.id, type="household",
                due_date=fu_due, status=fu_status,
            ))

    db.commit()
    print(
        f"[seed_extended] Seeded {len(all_bens)} beneficiaries "
        f"across {len(households)} households (demo data)."
    )
