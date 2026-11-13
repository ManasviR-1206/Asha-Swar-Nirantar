import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.auth import hash_password
from app.models import AshaWorker
from app.routers.visits import create_batch_visits
from app.schemas import BatchVisitCreate, BatchVisitItem
from app.services.gnani import extract_fields_multi, parse_corrections
from app.database import SessionLocal


def test_all():
    print("=== TEST 1: SCENARIO A (Single Beneficiary) ===")
    t_a = "I visited Lakshmi today. She is 28 weeks pregnant. Her weight is 53 kg and her blood pressure is 120 over 80."
    res_a, flags_a = extract_fields_multi(t_a, "en")
    print("Scenario:", res_a["scenario"])
    print("Visits count:", len(res_a["visits"]))
    assert len(res_a["visits"]) == 1
    v = res_a["visits"][0]
    print("Beneficiary:", v["beneficiary_name"], "| Category:", v["category"])
    print("Raw structured:", v["raw_structured"])
    assert v["beneficiary_name"] == "Lakshmi"
    assert v["category"] == "pregnancy"
    assert v["raw_structured"]["weeks_pregnant"] == 28
    assert v["raw_structured"]["weight_kg"] == 53.0
    print("[OK] Scenario A Passed\n")

    print("=== TEST 2: SCENARIO B (Household Family Members) ===")
    t_b = "I visited Lakshmi's household. Lakshmi is 28 weeks pregnant and weighs 53 kg. Her husband Ravi is 30 years old. Their daughter Anu is two years old and weighs 11 kg. The family uses borewell water and has a toilet."
    res_b, flags_b = extract_fields_multi(t_b, "en")
    print("Scenario:", res_b["scenario"])
    print("Visits count:", len(res_b["visits"]))
    assert res_b["scenario"] == "household_members"
    assert len(res_b["visits"]) == 3
    names = [v["beneficiary_name"] for v in res_b["visits"]]
    print("Members:", names)
    assert "Lakshmi" in names
    assert "Ravi" in names
    assert "Anu" in names
    print("[OK] Scenario B Passed\n")

    print("=== TEST 3: SCENARIO C (Multiple Beneficiaries Across Households) ===")
    t_c = "Today I visited Lakshmi. She is 28 weeks pregnant and weighs 53 kg. Then I visited Ravi, who is 65 years old and needs a blood pressure follow-up. After that I visited Anu, who is two years old and needs a vaccination follow-up."
    res_c, flags_c = extract_fields_multi(t_c, "en")
    print("Scenario:", res_c["scenario"])
    print("Visits count:", len(res_c["visits"]))
    assert res_c["scenario"] == "multiple_beneficiaries"
    assert len(res_c["visits"]) == 3
    cats = {v["beneficiary_name"]: v["category"] for v in res_c["visits"]}
    print("Categories:", cats)
    assert cats["Lakshmi"] == "pregnancy"
    assert cats["Ravi"] == "elderly"
    assert cats["Anu"] == "child"
    print("[OK] Scenario C Passed\n")

    print("=== TEST 4: UNIVERSAL VOICE CORRECTIONS ===")
    t_corr = "Correct Lakshmi's weight to 59 kg and BP to 120 over 80. Ravi is 66, not 65. Anu has already received her vaccination."
    corrs = parse_corrections(t_corr)
    print("Parsed corrections:", corrs)
    corr_fields = [c.get("field") for c in corrs]
    assert "weight_kg" in corr_fields or "weight" in corr_fields
    assert "age" in corr_fields
    print("[OK] Universal Corrections Passed\n")

    print("=== TEST 5: BATCH VISIT TRANSACTIONAL PERSISTENCE ===")
    db = SessionLocal()
    try:
        worker = db.query(AshaWorker).filter(AshaWorker.worker_id == "TEST-WORKER-001").first()
        if not worker:
            worker = AshaWorker(
                worker_id="TEST-WORKER-001",
                name="Test Worker",
                password_hash=hash_password("testpass"),
                phc="Test PHC",
                language="en",
            )
            db.add(worker)
            db.commit()

        batch_payload = BatchVisitCreate(
            visits=[
                BatchVisitItem(
                    beneficiary_name="Batch Test Lakshmi",
                    category="pregnancy",
                    create_if_missing=True,
                    structured={"weeks_pregnant": 30, "weight_kg": 54.0, "bp_sys": 120, "bp_dia": 80},
                    transcript=t_c,
                ),
                BatchVisitItem(
                    beneficiary_name="Batch Test Ravi",
                    category="elderly",
                    create_if_missing=True,
                    structured={"age": 65, "blood_sugar": 140.0},
                    transcript=t_c,
                ),
                BatchVisitItem(
                    beneficiary_name="Batch Test Anu",
                    category="child",
                    create_if_missing=True,
                    structured={"age": 2, "weight_kg": 11.5, "vaccine_name": "OPV-1"},
                    transcript=t_c,
                ),
            ],
            household_visits=[],
        )

        resp = create_batch_visits(batch_payload, db=db, worker=worker)
        print("Batch save response - Total saved:", resp.total_saved)
        assert resp.total_saved == 3
        print("[OK] Batch Visit Persistence Passed\n")
    finally:
        db.close()

    print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_all()
