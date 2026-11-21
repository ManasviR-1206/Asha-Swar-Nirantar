import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend package is importable when running from repo root or backend/
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Prevent accidental loading of real project .env values from interfering with tests.
os.environ.setdefault("GNANI_MODE", "demo")

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402  # register all models with Base metadata
from app.models import Beneficiary, SmsNotification, SmsReminder  # noqa: E402
from app.services import notifications as notify  # noqa: E402
from app.services.textbee import normalize_indian_phone_to_e164, send_sms_via_textbee  # noqa: E402
from app.services import textbee as textbee_service  # noqa: E402


@contextmanager
def temp_env(**updates):
    old = {k: os.environ.get(k) for k in updates}
    try:
        for k, v in updates.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return Session()


def seed_beneficiary(db, **overrides):
    data = {
        "qr_id": overrides.pop("qr_id", "ASN-TEST-0001"),
        "name": overrides.pop("name", "Test Beneficiary"),
        "age": overrides.pop("age", 30),
        "category": overrides.pop("category", "general"),
        "gender": overrides.pop("gender", "female"),
        "village": overrides.pop("village", "Test Village"),
        "phone": overrides.pop("phone", "9876543210"),
        "email": overrides.pop("email", None),
    }
    ben = Beneficiary(**data)
    for k, v in overrides.items():
        setattr(ben, k, v)
    db.add(ben)
    db.commit()
    db.refresh(ben)
    return ben


class MockResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {"content-type": "application/json"}
        self.text = "" if json_data is None else str(json_data)

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


class MockAsyncClient:
    """Minimal async context manager/client mock for httpx.AsyncClient."""
    def __init__(self, post_impl=None, response=None, exc=None, *args, **kwargs):
        self._post_impl = post_impl
        self._response = response
        self._exc = exc
        self.post = AsyncMock()

        async def _post(*a, **kw):
            if self._exc is not None:
                raise self._exc
            if self._post_impl is not None:
                return self._post_impl(*a, **kw)
            return self._response

        self.post.side_effect = _post

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TextBeeServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_normalize_indian_phone_to_e164(self):
        self.assertEqual(normalize_indian_phone_to_e164("9876543210"), "+919876543210")
        self.assertEqual(normalize_indian_phone_to_e164("+91 98765 43210"), "+919876543210")
        self.assertEqual(normalize_indian_phone_to_e164("919876543210"), "+919876543210")
        self.assertEqual(normalize_indian_phone_to_e164("09876543210"), "+919876543210")
        self.assertIsNone(normalize_indian_phone_to_e164(""))
        self.assertIsNone(normalize_indian_phone_to_e164(None))
        self.assertIsNone(normalize_indian_phone_to_e164("12345"))
        self.assertIsNone(normalize_indian_phone_to_e164("1234567890"))  # invalid starting digit

    async def test_send_success_mocked_textbee(self):
        with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="test_key", TEXTBEE_DEVICE_ID="dev_1", TEXTBEE_BASE_URL="https://api.textbee.dev"):
            mock_resp = MockResponse(200, {"success": True, "data": {"id": "msg_123", "message": "Queued"}})
            with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(response=mock_resp)) as client_cls:
                res = await send_sms_via_textbee(to_e164="+919876543210", message="Hello")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "submitted")
        self.assertIn("msg_123", res.get("provider_ref", ""))
        # Verify request contract (backend-only, correct endpoint/header/payload)
        _, kwargs = client_cls.return_value.post.call_args
        self.assertEqual(kwargs["headers"].get("x-api-key"), "test_key")
        self.assertEqual(kwargs["json"]["deviceId"], "dev_1")
        self.assertEqual(kwargs["json"]["recipients"], ["+919876543210"])
        self.assertEqual(kwargs["json"]["message"], "Hello")
        self.assertTrue(str(client_cls.return_value.post.call_args[0][0]).endswith("/api/v1/gateway/send-sms"))

    async def test_missing_api_key_handling(self):
        with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY=None, TEXTBEE_DEVICE_ID="dev_1"):
            res = await send_sms_via_textbee(to_e164="+919876543210", message="Hello")
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "failed")
        self.assertIn("API key", res.get("error", "") + res.get("provider_note", ""))

    async def test_disabled_sms_configuration(self):
        with temp_env(TEXTBEE_ENABLED="false", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="d"):
            res = await send_sms_via_textbee(to_e164="+919876543210", message="Hello")
        self.assertFalse(res["ok"])
        self.assertIn("disabled", (res.get("error", "") + res.get("provider_note", "")).lower())

    async def test_invalid_api_key_handling(self):
        with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="bad", TEXTBEE_DEVICE_ID="dev_1"):
            mock_resp = MockResponse(401, {"message": "Unauthorized"})
            with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(response=mock_resp)):
                res = await send_sms_via_textbee(to_e164="+919876543210", message="Hello")
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "failed")
        note = (res.get("provider_note") or res.get("error") or "").lower()
        self.assertTrue("invalid" in note or "unauthorized" in note or "api key" in note)

    async def test_device_offline_or_api_failure_handling(self):
        import httpx
        with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="dev_1"):
            # device offline indicated by API error payload
            mock_resp = MockResponse(400, {"message": "Device is offline"})
            with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(response=mock_resp)):
                res = await send_sms_via_textbee(to_e164="+919876543210", message="Hello")
            self.assertFalse(res["ok"])
            self.assertIn("offline", (res.get("provider_note") or res.get("error") or "").lower())

            # network/connect failure (transient) -> limited retries then failure
            with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(exc=httpx.ConnectError("boom"))):
                res2 = await send_sms_via_textbee(to_e164="+919876543210", message="Hello", max_retries=1)
            self.assertFalse(res2["ok"])
            self.assertTrue(res2.get("provider_note") or res2.get("error"))


class NotificationSmsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_phone_number_handling(self):
        db = make_session()
        try:
            ben = seed_beneficiary(db, phone="12345")
            with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="d"):
                res = await notify.send_sms_notification(db, beneficiary=ben, follow_up_type="follow_up", language="en", allow_duplicate=True)
            self.assertFalse(res["ok"])
            self.assertIn("valid mobile", (res.get("note") or "").lower())
            self.assertEqual(db.query(SmsNotification).count(), 0)
        finally:
            db.close()

    async def test_disabled_sms_configuration_records_demo_not_sent(self):
        db = make_session()
        try:
            ben = seed_beneficiary(db, phone="9876543210")
            with temp_env(TEXTBEE_ENABLED="false", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="d"):
                res = await notify.send_sms_notification(db, beneficiary=ben, follow_up_type="appointment", language="en", allow_duplicate=True)
            self.assertTrue(res["ok"])
            self.assertTrue(res["is_demo"])
            self.assertEqual(res["status"], "demo")
            row = db.query(SmsNotification).first()
            self.assertIsNotNone(row)
            self.assertTrue(row.is_demo)
            self.assertEqual(row.status, "demo")
            self.assertEqual(row.phone, "+919876543210")
        finally:
            db.close()

    async def test_successful_sms_records_submitted_notification(self):
        db = make_session()
        try:
            ben = seed_beneficiary(db, phone="919876543210")
            mock_resp = MockResponse(200, {"id": "abc123", "message": "accepted"})
            with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="d"):
                with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(response=mock_resp)):
                    res = await notify.send_sms_notification(db, beneficiary=ben, follow_up_type="medication", language="en", allow_duplicate=True)
            self.assertTrue(res["ok"])
            self.assertFalse(res["is_demo"])
            self.assertEqual(res["status"], "submitted")
            row = db.query(SmsNotification).first()
            self.assertIsNotNone(row)
            self.assertEqual(row.status, "submitted")
            self.assertFalse(row.is_demo)
            self.assertEqual(row.phone, "+919876543210")
            self.assertIn("abc123", row.provider_ref)
        finally:
            db.close()

    async def test_duplicate_notification_prevention(self):
        db = make_session()
        try:
            ben = seed_beneficiary(db, phone="9876543210")
            mock_resp = MockResponse(200, {"id": "once"})
            with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="d"):
                with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(response=mock_resp)):
                    first = await notify.send_sms_notification(
                        db, beneficiary=ben, follow_up_type="follow_up", language="en", follow_up_id=42, allow_duplicate=False
                    )
                    second = await notify.send_sms_notification(
                        db, beneficiary=ben, follow_up_type="follow_up", language="en", follow_up_id=42, allow_duplicate=False
                    )
            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertTrue(second.get("duplicate"))
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(db.query(SmsNotification).count(), 1)
        finally:
            db.close()

    async def test_consent_record_respected_for_notification_workflow(self):
        """Existing notification workflow records explicit consent; SMS send path accepts recorded consent and stores linkage."""
        db = make_session()
        try:
            ben = seed_beneficiary(db, phone="9876543210")
            consent = notify.record_consent(db, ben, "sms", True, purpose="follow_up_reminder", worker_id=1)
            mock_resp = MockResponse(200, {"id": "consented"})
            with temp_env(TEXTBEE_ENABLED="true", SMS_COMPLIANCE_APPROVED="true", TEXTBEE_API_KEY="k", TEXTBEE_DEVICE_ID="d"):
                with patch.object(textbee_service.httpx, "AsyncClient", return_value=MockAsyncClient(response=mock_resp)):
                    res = await notify.send_sms_notification(
                        db, beneficiary=ben, follow_up_type="important_alert", language="en", consent=consent, allow_duplicate=True
                    )
            self.assertTrue(res["ok"])
            row = db.query(SmsNotification).filter(SmsNotification.id == res["id"]).first()
            self.assertIsNotNone(row)
            self.assertEqual(row.consent_id, consent.id)
        finally:
            db.close()

    async def test_templates_are_generic_and_language_supported(self):
        # Meaningful event types should return generic, non-empty templates in supported languages
        for lang in ["en", "kn", "hi", "te", "ta"]:
            for etype in ["appointment", "follow_up", "medication", "care_plan", "important_alert"]:
                body = notify.build_sms_body(etype, lang)
                self.assertTrue(body)
                self.assertIsInstance(body, str)
                # Privacy: no diagnosis/test/result keywords in our templates
                lower = body.lower()
                for forbidden in ["diagnos", "hiv", "cancer", "result", "positive", "negative test"]:
                    self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
