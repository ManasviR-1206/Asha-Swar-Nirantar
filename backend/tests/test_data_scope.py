from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import data_scope
from app.database import Base
from app.models import AshaWorker, Beneficiary, FollowUp, Household, HouseholdMember, VisitRecord
from app.routers import beneficiaries, households
from app.schemas import BeneficiaryCreate, HouseholdCreate, HouseholdMemberCreate


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'data-scope.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _beneficiary(db, *, name, qr_id, village, email=None, origin="registered"):
    record = Beneficiary(
        qr_id=qr_id,
        name=name,
        age=24,
        category="pregnancy",
        village=village,
        email=email,
        data_origin=origin,
    )
    db.add(record)
    db.flush()
    return record


def test_normal_mode_hides_legacy_demo_beneficiaries_and_direct_lookups(db, monkeypatch):
    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: False)
    genuine = _beneficiary(db, name="Genuine", qr_id="ASN-REAL-0001", village="Village A")
    marker = _beneficiary(
        db,
        name="Marker",
        qr_id="ASN-DEMO-0001",
        village="Kolar [SYNTHETIC_DEMO]",
    )
    reserved_email = _beneficiary(
        db,
        name="Old seed",
        qr_id="ASN-DEMO-0002",
        village="Village B",
        email="old.seed@example.invalid",
    )
    explicit_demo = _beneficiary(
        db,
        name="Explicit demo",
        qr_id="ASN-DEMO-0003",
        village="Village C",
        origin="demo",
    )
    db.commit()

    listed = beneficiaries.list_beneficiaries(db=db)["beneficiaries"]
    assert [row["id"] for row in listed] == [genuine.id]
    for hidden in (marker, reserved_email, explicit_demo):
        with pytest.raises(HTTPException) as error:
            beneficiaries.get_beneficiary(hidden.id, db=db)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException):
            beneficiaries.resolve_beneficiary(hidden.qr_id, db=db)


def test_normal_mode_hides_demo_households_but_filters_mixed_members(db, monkeypatch):
    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: False)
    real = _beneficiary(db, name="Registered", qr_id="ASN-REAL-0002", village="Village A")
    synthetic = _beneficiary(
        db,
        name="Synthetic",
        qr_id="ASN-DEMO-0004",
        village="Kishanganj [SYNTHETIC_DEMO]",
    )
    hidden_household = Household(
        qr_id="HN-DEMO-0001", village="Village B", address="", member_count=1,
        data_origin="registered",
    )
    mixed_household = Household(
        qr_id="HN-REAL-0001", village="Village A", address="", member_count=2,
        data_origin="registered",
    )
    db.add_all([hidden_household, mixed_household])
    db.flush()
    db.add_all(
        [
            HouseholdMember(
                household_id=hidden_household.id,
                name=synthetic.name,
                beneficiary_id=synthetic.id,
            ),
            HouseholdMember(
                household_id=mixed_household.id,
                name=real.name,
                beneficiary_id=real.id,
            ),
            HouseholdMember(
                household_id=mixed_household.id,
                name=synthetic.name,
                beneficiary_id=synthetic.id,
            ),
        ]
    )
    db.commit()

    listed = households.list_households(db=db)["households"]
    assert [row["id"] for row in listed] == [mixed_household.id]
    detail = households.get_household(mixed_household.id, db=db)
    assert [member["beneficiary_id"] for member in detail["members"]] == [real.id]
    with pytest.raises(HTTPException) as error:
        households.get_household(hidden_household.id, db=db)
    assert error.value.status_code == 404


def test_explicit_demo_setup_can_show_demo_records(db, monkeypatch):
    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: True)
    demo = _beneficiary(
        db,
        name="Demo",
        qr_id="ASN-DEMO-0005",
        village="Kishanganj [SYNTHETIC_DEMO]",
        origin="demo",
    )
    db.commit()

    listed = beneficiaries.list_beneficiaries(db=db)["beneficiaries"]
    assert [row["id"] for row in listed] == [demo.id]


def test_followups_and_voice_identity_ignore_hidden_beneficiaries(db, monkeypatch):
    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: False)
    genuine = _beneficiary(db, name="Genuine", qr_id="ASN-REAL-0003", village="Village A")
    synthetic = _beneficiary(
        db,
        name="Synthetic",
        qr_id="ASN-DEMO-0006",
        village="Kolar [SYNTHETIC_DEMO]",
    )
    db.add_all(
        [
            FollowUp(
                beneficiary_id=genuine.id,
                type="general",
                due_date=date.today(),
                status="upcoming",
            ),
            FollowUp(
                beneficiary_id=synthetic.id,
                type="general",
                due_date=date.today(),
                status="upcoming",
            ),
        ]
    )
    db.commit()

    visible = data_scope.visible_followups(db.query(FollowUp), db).all()
    assert [row.beneficiary_id for row in visible] == [genuine.id]
    from app.services.identity import resolve_beneficiary

    resolution = resolve_beneficiary(db, name="Synthetic")
    assert resolution["status"] == "new"
    assert resolution["candidates"] == []


def test_rule_sync_does_not_recreate_followups_for_hidden_demo_records(db, monkeypatch):
    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: False)
    worker = AshaWorker(
        worker_id="TEST002",
        name="Test Worker",
        password_hash="unused",
    )
    db.add(worker)
    db.flush()
    genuine = _beneficiary(db, name="Genuine", qr_id="ASN-REAL-0004", village="Village A")
    synthetic = _beneficiary(
        db,
        name="Synthetic",
        qr_id="ASN-DEMO-0008",
        village="Kolar [SYNTHETIC_DEMO]",
    )
    genuine.category = synthetic.category = "child"
    for beneficiary in (genuine, synthetic):
        db.add(
            VisitRecord(
                beneficiary_id=beneficiary.id,
                worker_id=worker.id,
                visit_date=date(2020, 1, 1),
                category="child",
            )
        )
    db.commit()

    from app.rules import sync_generated_followups

    sync_generated_followups(db)
    generated = db.query(FollowUp).all()
    assert [row.beneficiary_id for row in generated] == [genuine.id]


def test_new_beneficiary_registration_and_household_link_validation(db, monkeypatch):
    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: False)
    worker = AshaWorker(
        worker_id="TEST001",
        name="Test Worker",
        password_hash="unused",
    )
    db.add(worker)
    hidden = _beneficiary(
        db,
        name="Synthetic",
        qr_id="ASN-DEMO-0007",
        village="Kolar [SYNTHETIC_DEMO]",
    )
    db.commit()

    created = beneficiaries.create_beneficiary(
        BeneficiaryCreate(name="New Registered", category="child", village="Village A"),
        db=db,
        worker=worker,
    )
    assert created["beneficiaries"][0]["name"] == "New Registered"
    assert [row["name"] for row in beneficiaries.list_beneficiaries(db=db)["beneficiaries"]] == [
        "New Registered"
    ]

    with pytest.raises(HTTPException) as error:
        households.create_household(
            HouseholdCreate(
                village="Village A",
                members=[
                    HouseholdMemberCreate(name="Synthetic", beneficiary_id=hidden.id)
                ],
            ),
            db=db,
        )
    assert error.value.status_code == 404


def test_synthetic_demo_origin_hidden_in_normal_mode_visible_in_demo_mode(db, monkeypatch):
    synthetic = _beneficiary(
        db,
        name="Jyoti DemoK (SYN-001)",
        qr_id="ASN-SYN-0001",
        village="Demo Village",
        origin="synthetic_demo",
    )
    real = _beneficiary(db, name="Real", qr_id="ASN-REAL-0099", village="Village A")
    db.add(
        FollowUp(
            beneficiary_id=synthetic.id,
            type="general",
            due_date=date.today(),
            status="upcoming",
            notes="SYNTHETIC DEMO DATA: created for demonstration.",
        )
    )
    db.add(
        FollowUp(
            beneficiary_id=real.id,
            type="general",
            due_date=date.today(),
            status="upcoming",
        )
    )
    db.commit()

    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: False)
    listed = beneficiaries.list_beneficiaries(db=db)["beneficiaries"]
    assert [r["id"] for r in listed] == [real.id]
    visible_followups = data_scope.visible_followups(db.query(FollowUp), db).all()
    assert [f.beneficiary_id for f in visible_followups] == [real.id]
    with pytest.raises(HTTPException):
        beneficiaries.get_beneficiary(synthetic.id, db=db)

    monkeypatch.setattr(data_scope, "demo_setup_enabled", lambda: True)
    listed_demo = beneficiaries.list_beneficiaries(db=db)["beneficiaries"]
    assert sorted([r["id"] for r in listed_demo]) == sorted([real.id, synthetic.id])
    visible_followups_demo = data_scope.visible_followups(db.query(FollowUp), db).all()
    assert sorted([f.beneficiary_id for f in visible_followups_demo]) == sorted([real.id, synthetic.id])
