import os, tempfile, unittest

os.environ.setdefault("GNANI_MODE", "demo")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
import app.models  # noqa: F401
from app.models import AshaWorker, Household, Beneficiary
from app.auth import hash_password, create_token
from app.main import app


class QrCompatibilityTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False})
        TestingSession = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSession()
        self.worker = AshaWorker(name="T", worker_id="W1", password_hash=hash_password("pw"), role="asha", is_active=True)
        self.db.add(self.worker)
        self.db.flush()
        self.hh = Household(village="V", qr_id="SDH-0001", member_count=1)
        self.db.add(self.hh)
        self.db.flush()
        self.ben = Beneficiary(name="Legacy Ben", age=30, category="pregnancy", qr_id="SDM-0001", household_id=self.hh.id, assigned_worker_id=self.worker.id)
        self.db.add(self.ben)
        self.db.commit()
        self.token = create_token(self.db, self.worker)
        self.db.commit()

        def override_get_db():
            d = TestingSession()
            try:
                yield d
            finally:
                d.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()
        try:
            os.remove(self.path)
        except Exception:
            pass

    def auth(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_legacy_household_qr_resolves(self):
        r = self.client.get("/api/households/resolve/SDH-0001", headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["household"]["qr_id"], "SDH-0001")

    def test_legacy_beneficiary_qr_resolves(self):
        r = self.client.get("/api/beneficiaries/resolve/SDM-0001", headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["beneficiary"]["qr_id"], "SDM-0001")

    def test_unknown_qr_returns_404(self):
        r = self.client.get("/api/beneficiaries/resolve/ASN-NOPE-0000", headers=self.auth())
        self.assertEqual(r.status_code, 404)
