"""Seed, reset, or verify the comprehensive synthetic demo dataset.

Usage (run from backend/):
  python scripts/seed_synthetic_demo.py --seed
  python scripts/seed_synthetic_demo.py --verify
  python scripts/seed_synthetic_demo.py --reset

Safety:
- Only creates/updates synthetic demo records (data_origin='synthetic_demo')
- --reset removes ONLY synthetic demo records and their dependent records
- Does not delete/overwrite existing real records
- Idempotent: repeated --seed does not create duplicates
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure backend package is importable when running as a script
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import SessionLocal  # noqa: E402
from app.synthetic_demo_seed import reset_synthetic_demo, seed_synthetic_demo, verify_synthetic_demo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic demo dataset seeding/reset/verification")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--seed", action="store_true", help="Seed synthetic demo dataset (idempotent)")
    group.add_argument("--reset", action="store_true", help="Reset ONLY synthetic demo records")
    group.add_argument("--verify", action="store_true", help="Verify/report synthetic demo dataset counts")
    parser.add_argument("--force", action="store_true", help="With --seed, reset synthetic demo data first then reseed")
    args = parser.parse_args()

    action = "seed"
    if args.reset:
        action = "reset"
    elif args.verify:
        action = "verify"

    db = SessionLocal()
    try:
        if action == "reset":
            result = reset_synthetic_demo(db)
            print(json.dumps({"action": "reset", **result, "verification": verify_synthetic_demo(db)}, indent=2, default=str))
            return 0
        if action == "verify":
            print(json.dumps({"action": "verify", "verification": verify_synthetic_demo(db)}, indent=2, default=str))
            return 0
        # seed
        result = seed_synthetic_demo(db, force=args.force)
        print(json.dumps({"action": "seed", **result}, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
