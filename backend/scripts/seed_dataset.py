#!/usr/bin/env python3
"""
Seed script for ASHA Swar Nirantar.
Generates an India-oriented synthetic demo dataset:
- 50 fictional households
- 150+ fictional beneficiaries across all categories:
  * Maternal health & pregnancy
  * Newborn & child health
  * Immunisation
  * Nutrition & anaemia
  * Elderly health
  * Household sanitation
- Longitudinal visit records and follow-ups
- Synthetic QR codes (ASN-xxxx-xxxx and HN-xxxx-xxxx)

Run from backend directory or project root:
    python backend/scripts/seed_dataset.py
"""
import os
import sys

# Ensure backend folder is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Use absolute path to asha_swar.db in backend directory
db_path = os.path.join(BACKEND_DIR, "asha_swar.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from app.database import Base, engine, SessionLocal, apply_light_migrations
from app.models import (
    Beneficiary,
    Household,
    HouseholdMember,
    HouseholdVisit,
    VisitRecord,
    PregnancyRecord,
    NewbornRecord,
    ImmunisationRecord,
    FollowUp,
    DangerAlert,
    SmsReminder,
)
from app.seed import seed


def reset_and_seed():
    print("=" * 70)
    print("ASHA SWAR NIRANTAR — SYNTHETIC DATASET SEEDER")
    print(f"Target Database: {db_path}")
    print("=" * 70)

    # 1. Reset tables
    print("[1/4] Dropping existing tables for clean seed...")
    Base.metadata.drop_all(bind=engine)
    
    print("[2/4] Creating database schema...")
    Base.metadata.create_all(bind=engine)
    apply_light_migrations()

    # 2. Seed database
    print("[3/4] Generating synthetic demo records (50 households, 150+ beneficiaries)...")
    db = SessionLocal()
    try:
        seed(db)

        # 3. Validation & Reporting
        b_count = db.query(Beneficiary).count()
        h_count = db.query(Household).count()
        hm_count = db.query(HouseholdMember).count()
        v_count = db.query(VisitRecord).count()
        hv_count = db.query(HouseholdVisit).count()
        preg_count = db.query(PregnancyRecord).count()
        nb_count = db.query(NewbornRecord).count()
        imm_count = db.query(ImmunisationRecord).count()
        fu_count = db.query(FollowUp).count()
        alert_count = db.query(DangerAlert).count()
        rem_count = db.query(SmsReminder).count()

        print("[4/4] Seed Complete! Verification:")
        print(f"  • Total Beneficiaries:    {b_count} (target: 150+)")
        print(f"  • Total Households:       {h_count} (target: 50)")
        print(f"  • Household Members:      {hm_count}")
        print(f"  • Beneficiary Visits:     {v_count}")
        print(f"  • Household Visits:       {hv_count}")
        print(f"  • Pregnancy Records:      {preg_count}")
        print(f"  • Newborn Records:        {nb_count}")
        print(f"  • Immunisation Records:   {imm_count}")
        print(f"  • Follow-ups Scheduled:   {fu_count}")
        print(f"  • Active Danger Alerts:   {alert_count}")
        print(f"  • SMS Reminders:          {rem_count}")
        print("=" * 70)
        print("✅ SUCCESS: All records marked SYNTHETIC DEMO DATA.")
        print("   Zero personal health information (PHI) used.")
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    reset_and_seed()
