import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("GNANI_MODE", "demo")
os.environ.setdefault("ENABLE_DEMO_SETUP", "false")

from fastapi.testclient import TestClient
from app.database import Base, engine, SessionLocal
import app.models
from app.models import AshaWorker
from app.auth import hash_password
from app.services.gnani import _extract_demo, extract_fields, extract_fields_multi


def _make_client():
    fd, dbpath = tempfile.mkstemp(suffix=".db")
    os.close(fd); os.remove(dbpath)
    os.environ["DATABASE_URL"] = f"sqlite:///{dbpath.replace(chr(92), '/')}"
    # Recreate engine-bound tables for this temp DB by using fresh app TestClient context via env already set at import in many setups;
    # for safety in this project, create tables on current engine and seed a worker.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if not db.query(AshaWorker).filter(AshaWorker.worker_id == "T001").first():
        db.add(AshaWorker(name="Test", worker_id="T001", password_hash=hash_password("Test@123"), role="asha", is_active=True))
        db.commit()
    db.close()
    from app.main import app
    return TestClient(app), dbpath


def test_name_extraction_cases_demo():
    cases = [
        ("Manasvi is 12 years old and she has a severe headache.", "Manasvi"),
        ("Nandita has a severe headache.", "Nandita"),
        ("Madhu is 15 years old.", "Madhu"),
        ("Lakshmi is 28 weeks pregnant.", "Lakshmi"),
        ("Patient Priya has a headache.", "Priya"),
        ("nandita has fever.", "Nandita"),
        ("She has fever and cough.", None),
        ("Today I visited Kavya. She has fever.", "Kavya"),
    ]
    for transcript, expected in cases:
        d = _extract_demo(transcript)
        name = d.get("beneficiary_name")
        if expected is None:
            assert not name, f"Expected no name for: {transcript}, got {name}"
        else:
            assert (name or "").lower() == expected.lower(), f"{transcript} => {name}"
            assert d.get("beneficiary_name") == expected or (name or "").lower() == expected.lower()


def test_extract_fields_multi_preserves_name():
    m, _ = extract_fields_multi("Nandita has a severe headache.", "en")
    v = m["visits"][0]
    assert (v.get("beneficiary_name") or "").lower() == "nandita"
    assert (v.get("personal_details") or {}).get("name", "").lower() == "nandita"


def test_extract_direct_api_returns_spoken_name_without_db_match():
    client, dbpath = _make_client()
    try:
        login = client.post("/api/auth/login", json={"worker_id": "T001", "password": "Test@123"})
        assert login.status_code == 200
        token = login.json()["token"]
        H = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/voice/sessions/extract-direct", json={
            "client_session_id": "t-nandita",
            "language": "en",
            "transcript": "Nandita has a severe headache.",
            "provider": "browser",
            "duration_ms": 1000,
            "mode": "demo",
        }, headers=H)
        assert r.status_code == 200
        v = r.json()["visits"][0]
        assert (v.get("beneficiary_name") or "").lower() == "nandita"
        assert v.get("beneficiary_id") is None
        assert v.get("identity_status") in ("unresolved", "extracted_unlinked", "name_missing")
        assert (v.get("personal_details") or {}).get("name", "").lower() == "nandita"
    finally:
        try:
            engine.dispose(); os.remove(dbpath)
        except Exception:
            pass


def test_manasvi_extract_direct_api_and_name_fields_agree():
    client, dbpath = _make_client()
    try:
        login = client.post("/api/auth/login", json={"worker_id": "T001", "password": "Test@123"})
        assert login.status_code == 200
        H = {"Authorization": f"Bearer {login.json()['token']}"}
        r = client.post("/api/voice/sessions/extract-direct", json={
            "client_session_id": "t-manasvi",
            "language": "en",
            "transcript": "Manasvi is 12 years old and she has a severe headache.",
            "provider": "browser",
            "duration_ms": 1000,
            "mode": "demo",
        }, headers=H)
        assert r.status_code == 200
        body = r.json()
        v = body["visits"][0]
        assert v["beneficiary_name"] == "Manasvi"
        assert v["personal_details"]["name"] == "Manasvi"
        assert v["category"] == "child"
        assert v["raw_structured"]["beneficiary_name"] == "Manasvi"
        assert v["raw_structured"]["age"] == 12
        assert v["beneficiary_id"] is None
    finally:
        try:
            engine.dispose(); os.remove(dbpath)
        except Exception:
            pass


def test_extract_direct_api_required_cases():
    client, dbpath = _make_client()
    try:
        login = client.post("/api/auth/login", json={"worker_id": "T001", "password": "Test@123"})
        assert login.status_code == 200
        H = {"Authorization": f"Bearer {login.json()['token']}"}
        cases = [
            ("Manasvi is 12 years old and she has a severe headache.", "Manasvi", 12, "child"),
            ("Nandita has a severe headache.", "Nandita", None, None),
            ("Madhu is 15 years old.", "Madhu", 15, None),
            ("Lakshmi is 28 weeks pregnant.", "Lakshmi", None, "pregnancy"),
            ("Patient Priya has a headache.", "Priya", None, None),
            ("nandita has fever.", "Nandita", None, None),
            ("She has fever and cough.", None, None, None),
            ("Today I visited Kavya. She has fever.", "Kavya", None, None),
        ]
        for i, (transcript, expected_name, expected_age, expected_cat) in enumerate(cases):
            r = client.post("/api/voice/sessions/extract-direct", json={
                "client_session_id": f"t-case-{i}",
                "language": "en",
                "transcript": transcript,
                "provider": "browser",
                "duration_ms": 1000,
                "mode": "demo",
            }, headers=H)
            assert r.status_code == 200, r.text
            v = r.json()["visits"][0]
            if expected_name is None:
                assert not (v.get("beneficiary_name") or "").strip(), (transcript, v.get("beneficiary_name"))
            else:
                assert (v.get("beneficiary_name") or "").lower() == expected_name.lower(), (transcript, v.get("beneficiary_name"))
                assert (v.get("personal_details") or {}).get("name", "").lower() == expected_name.lower(), (transcript, v.get("personal_details"))
                assert v.get("beneficiary_id") is None
            if expected_age is not None:
                assert int((v.get("personal_details") or {}).get("age") or v.get("raw_structured", {}).get("age") or 0) == expected_age
            if expected_cat is not None:
                assert v.get("category") == expected_cat, (transcript, v.get("category"))
    finally:
        try:
            engine.dispose(); os.remove(dbpath)
        except Exception:
            pass


def test_mocked_gemini_conflict_keeps_gemini_name_both_name_fields(monkeypatch):
    monkeypatch.setattr("app.services.gnani._llm_live_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.gnani._gemini_extract_live",
        lambda transcript, language: {
            "beneficiary_name": "Manasvi",
            "age": 12,
            "category": "child",
        },
    )
    structured, mode = extract_fields(
        "Manasvi is 12 years old and she has a severe headache.",
        "en",
    )
    assert mode == "live"
    assert structured["beneficiary_name"] == "Manasvi"
    multi, multi_mode = extract_fields_multi(
        "Manasvi is 12 years old and she has a severe headache.",
        "en",
    )
    visit = multi["visits"][0]
    assert multi_mode == "live"
    assert visit["beneficiary_name"] == "Manasvi"
    assert visit["personal_details"]["name"] == "Manasvi"
