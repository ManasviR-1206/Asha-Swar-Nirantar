import os, tempfile, unittest
from datetime import date

os.environ.setdefault("GNANI_MODE", "demo")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
import app.models  # noqa: F401
from app.models import AshaWorker, Household, Beneficiary, DangerAlert, AlertAuditLog
from app.auth import hash_password, create_token
from app.main import app


class AlertsWorkflowTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False})
        TestingSession = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSession()
        self.worker = AshaWorker(name="Test", worker_id="W1", password_hash=hash_password("pw"), role="asha", is_active=True)
        self.db.add(self.worker)
        self.db.flush()
        self.hh = Household(village="V", qr_id="HN-TST1-0001", member_count=1)
        self.db.add(self.hh)
        self.db.flush()
        self.ben = Beneficiary(name="Lakshmi", age=25, category="pregnancy", qr_id="ASN-TST1-0001", household_id=self.hh.id, assigned_worker_id=self.worker.id)
        self.db.add(self.ben)
        self.db.commit()
        self.db.refresh(self.ben)
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

    def _create_confirmed_danger_visit(self):
        payload = {
            "beneficiary_id": self.ben.id,
            "structured": {"category": "pregnancy"},
            "transcript": "She has heavy bleeding and severe headache",
            "language": "en",
            "visit_type": "pregnancy",
            "confirmation": {"confirmed": True, "method": "ui_fallback"},
        }
        r = self.client.post("/api/visits", json=payload, headers=self.auth())
        return r

    def test_confirmed_danger_visit_generates_alerts(self):
        r = self._create_confirmed_danger_visit()
        self.assertIn(r.status_code, (200, 201), r.text)
        alerts = self.db.query(DangerAlert).filter(DangerAlert.beneficiary_id == self.ben.id).all()
        self.assertGreaterEqual(len(alerts), 1)
        rule_ids = {a.rule_id for a in alerts}
        self.assertTrue({"PREG-01", "PREG-02"}.intersection(rule_ids))

    def test_no_danger_no_alert(self):
        payload = {
            "beneficiary_id": self.ben.id,
            "structured": {"category": "pregnancy"},
            "transcript": "Mother and baby are doing well. No complaints today.",
            "language": "en",
            "visit_type": "pregnancy",
            "confirmation": {"confirmed": True, "method": "ui_fallback"},
        }
        r = self.client.post("/api/visits", json=payload, headers=self.auth())
        self.assertIn(r.status_code, (200, 201), r.text)
        self.assertEqual(self.db.query(DangerAlert).count(), 0)

    def test_duplicate_prevention(self):
        r1 = self._create_confirmed_danger_visit()
        r2 = self._create_confirmed_danger_visit()
        self.assertIn(r1.status_code, (200, 201))
        self.assertIn(r2.status_code, (200, 201))
        # same unresolved rule+beneficiary should not duplicate
        alerts = self.db.query(DangerAlert).filter(DangerAlert.beneficiary_id == self.ben.id).all()
        rule_ids = [a.rule_id for a in alerts]
        self.assertEqual(len(rule_ids), len(set(rule_ids)))

    def test_ack_referral_resolve_persist(self):
        self._create_confirmed_danger_visit()
        alert = self.db.query(DangerAlert).filter(DangerAlert.beneficiary_id == self.ben.id).first()
        self.assertIsNotNone(alert)
        aid = alert.id

        r = self.client.post(f"/api/alerts/{aid}/ack", json={"note": "seen"}, headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        self.db.expire_all()
        a = self.db.query(DangerAlert).filter(DangerAlert.id == aid).first()
        self.assertEqual(a.status, "acknowledged")

        r = self.client.post(f"/api/alerts/{aid}/referral-initiated", json={"note": "ref started"}, headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post(f"/api/alerts/{aid}/record-referral", json={"referral_facility": "PHC", "referral_date": "2026-11-22", "referral_note": "sent"}, headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(f"/api/alerts/{aid}/resolve", json={"note": "resolved safely"}, headers=self.auth())
        self.assertEqual(r.status_code, 200, r.text)
        self.db.expire_all()
        a = self.db.query(DangerAlert).filter(DangerAlert.id == aid).first()
        self.assertEqual(a.status, "resolved")
        audits = self.db.query(AlertAuditLog).filter(AlertAuditLog.alert_id == aid).all()
        self.assertGreaterEqual(len(audits), 2)
