import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_worker
from app.database import Base, get_db
from app.models import AshaWorker, Beneficiary, Household, HouseholdMember
from app.routers import geopulse, households


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'geopulse.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    worker = AshaWorker(name="Test ASHA", worker_id="ASHA-TEST", password_hash="test-hash", is_active=True, role="asha")
    db.add(worker)
    db.commit()
    db.refresh(worker)

    app = FastAPI()
    app.include_router(geopulse.router)
    app.include_router(households.router)

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_worker] = lambda: worker
    client = TestClient(app)
    try:
        yield {"db": db, "client": client, "worker": worker}
    finally:
        client.close()
        db.close()
        engine.dispose()


def test_household_location_update_gps_and_manual(ctx):
    db = ctx["db"]
    client = ctx["client"]
    h = Household(qr_id="HH-TEST-1", village="V1", address="A1", member_count=0, data_origin="registered")
    db.add(h)
    db.commit()
    db.refresh(h)

    # GPS capture (permission-based is handled by browser; endpoint stores provided coords only)
    res = client.patch(f"/api/households/{h.id}/location", json={
        "latitude": 12.9716, "longitude": 77.5946, "location_source": "gps", "verification_note": "device gps"
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["latitude"] == 12.9716
    assert body["longitude"] == 77.5946
    assert body["location_source"] == "gps"
    assert body["location_updated_at"]

    # Manual verified update
    res2 = client.patch(f"/api/households/{h.id}/location", json={
        "latitude": 12.9700, "longitude": 77.5900, "location_source": "manual_verified", "verification_note": "verified on map"
    })
    assert res2.status_code == 200
    assert res2.json()["location_source"] == "manual_verified"


def test_household_location_rejects_invalid(ctx):
    db = ctx["db"]
    client = ctx["client"]
    h = Household(qr_id="HH-TEST-2", village="V1", member_count=0, data_origin="registered")
    db.add(h)
    db.commit()
    db.refresh(h)

    bad = client.patch(f"/api/households/{h.id}/location", json={"latitude": 123, "longitude": 77, "location_source": "gps"})
    assert bad.status_code == 400
    bad_src = client.patch(f"/api/households/{h.id}/location", json={"latitude": 12, "longitude": 77, "location_source": "fabricated"})
    assert bad_src.status_code == 400


def test_geopulse_households_no_fake_coords(ctx):
    db = ctx["db"]
    client = ctx["client"]
    h1 = Household(qr_id="HH-MAP-1", village="V1", member_count=1, data_origin="registered", latitude=12.9, longitude=77.5, location_source="gps")
    h2 = Household(qr_id="HH-MAP-2", village="V2", member_count=1, data_origin="registered")  # no coords
    b = Beneficiary(qr_id="B-1", name="Test Beneficiary", age=25, category="pregnancy", village="V1", data_origin="registered")
    db.add_all([h1, h2, b])
    db.commit()
    db.refresh(b)
    db.add(HouseholdMember(household_id=h1.id, beneficiary_id=b.id, name=b.name, age=b.age, gender="female", relation="self"))
    db.commit()

    res = client.get("/api/geopulse/households?filter=all")
    assert res.status_code == 200
    body = res.json()
    assert body["total_households"] == 2
    assert body["mapped_households"] == 1
    mapped = body["mapped_items"]
    assert len(mapped) == 1
    assert mapped[0]["household_id"] == h1.id
    assert mapped[0]["latitude"] == 12.9
    assert mapped[0]["longitude"] == 77.5
    # Household without coords must not be fabricated
    no_coord = [i for i in body["items"] if i["household_id"] == h2.id][0]
    assert no_coord["has_coordinates"] is False
    assert no_coord["latitude"] is None
    assert no_coord["longitude"] is None


def test_facilities_verified_only(ctx):
    client = ctx["client"]
    # Create verified facility
    ok = client.post("/api/geopulse/facilities", json={
        "name": "PHC Test", "facility_type": "PHC", "address": "Addr", "village": "V1",
        "latitude": 12.95, "longitude": 77.55, "location_source": "manual_verified", "verification_status": "verified"
    })
    assert ok.status_code == 200, ok.text
    # Create pending facility - should not appear on GET
    pending = client.post("/api/geopulse/facilities", json={
        "name": "Pending Clinic", "facility_type": "Clinic", "address": "Addr2", "village": "V1",
        "latitude": 12.96, "longitude": 77.56, "location_source": "manual_verified", "verification_status": "pending"
    })
    assert pending.status_code == 200

    res = client.get("/api/geopulse/facilities")
    assert res.status_code == 200
    body = res.json()
    names = [i["name"] for i in body["items"]]
    assert "PHC Test" in names
    assert "Pending Clinic" not in names
    assert all(i["verification_status"] == "verified" for i in body["items"])


def test_facility_import(ctx):
    client = ctx["client"]
    res = client.post("/api/geopulse/facilities/import", json={
        "facilities": [
            {"name": "Imported PHC", "facility_type": "PHC", "latitude": 12.1, "longitude": 77.1, "location_source": "verified_import", "verification_status": "verified"},
            {"name": "Bad", "facility_type": "PHC", "latitude": 999, "longitude": 77.1, "location_source": "verified_import", "verification_status": "verified"},
        ]
    })
    assert res.status_code == 200
    body = res.json()
    assert body["created_count"] == 1
    assert body["error_count"] == 1
