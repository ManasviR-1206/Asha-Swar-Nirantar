import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password, verify_password
from app.database import Base
from app.main import app
from app.models import AshaWorker
from app.seed import DEMO_PASSWORD, DEMO_WORKER_ID, ensure_demo_worker


def test_password_hash_round_trip():
    stored = hash_password(DEMO_PASSWORD)
    assert verify_password(DEMO_PASSWORD, stored)
    assert not verify_password("wrong-password", stored)
    assert not verify_password(DEMO_PASSWORD, "not-a-valid-hash")
    assert not verify_password(DEMO_PASSWORD, "zzzz$zzzz")


def test_demo_worker_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        first = ensure_demo_worker(db)
        second = ensure_demo_worker(db)
        assert first.id == second.id
        assert db.query(AshaWorker).filter(AshaWorker.worker_id == DEMO_WORKER_ID).count() == 1
        assert verify_password(DEMO_PASSWORD, second.password_hash)
    finally:
        db.close()
        engine.dispose()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_correct_login_and_protected_route(client):
    login = client.post(
        "/api/auth/login",
        json={"worker_id": DEMO_WORKER_ID, "password": DEMO_PASSWORD, "language": "en"},
    )
    assert login.status_code == 200
    token = login.json()["token"]
    assert token

    protected = client.get(
        "/api/auth/workers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert protected.status_code == 200


def test_invalid_credentials(client):
    response = client.post(
        "/api/auth/login",
        json={"worker_id": DEMO_WORKER_ID, "password": "wrong-password", "language": "en"},
    )
    assert response.status_code == 401


def test_unknown_worker(client):
    response = client.post(
        "/api/auth/login",
        json={"worker_id": "UNKNOWN001", "password": DEMO_PASSWORD, "language": "en"},
    )
    assert response.status_code == 401


def test_missing_token(client):
    response = client.get("/api/auth/workers")
    assert response.status_code == 401
