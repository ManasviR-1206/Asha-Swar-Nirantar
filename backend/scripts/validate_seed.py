#!/usr/bin/env python3
"""
Validation script for ASHA Swar Nirantar database.
Checks integrity and minimum counts:
- >= 50 Households
- >= 150 Beneficiaries
- Visits, FollowUps, DangerAlerts
"""
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

db_path = os.path.join(BACKEND_DIR, "asha_swar.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from app.database import SessionLocal
from app.models import (
    Beneficiary,
    Household,
    HouseholdMember,
    HouseholdVisit,
    VisitRecord,
    FollowUp,
    DangerAlert,
)


def validate():
    db = SessionLocal()
    try:
        b = db.query(Beneficiary).count()
        h = db.query(Household).count()
        hm = db.query(HouseholdMember).count()
        v = db.query(VisitRecord).count()
        hv = db.query(HouseholdVisit).count()
        fu = db.query(FollowUp).count()
        da = db.query(DangerAlert).count()

        print("Dataset Validation Summary:")
        print(f"  Beneficiaries:      {b}")
        print(f"  Households:         {h}")
        print(f"  Household Members:  {hm}")
        print(f"  Visits:             {v}")
        print(f"  Household Visits:   {hv}")
        print(f"  Follow-ups:         {fu}")
        print(f"  Danger Alerts:      {da}")

        passed = True
        if b < 150:
            print(f"❌ FAIL: Expected at least 150 beneficiaries, found {b}")
            passed = False
        else:
            print("✅ PASS: Beneficiaries >= 150")

        if h < 50:
            print(f"❌ FAIL: Expected at least 50 households, found {h}")
            passed = False
        else:
            print("✅ PASS: Households >= 50")

        if v < 100:
            print(f"❌ FAIL: Expected at least 100 visits, found {v}")
            passed = False
        else:
            print("✅ PASS: Visits >= 100")

        if passed:
            print("\n🎉 ALL SEED VALIDATION CHECKS PASSED!")
            return 0
        else:
            print("\n⚠️ SEED VALIDATION FAILED!")
            return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(validate())
