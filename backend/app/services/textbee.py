"""TextBee SMS Gateway integration (backend-only).

Sends SMS via the TextBee REST API using an API key and a registered Android device.
No credentials or sensitive message content are logged. Never expose this service to the frontend.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app import get_env

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.textbee.dev"
SEND_PATH = "/api/v1/gateway/send-sms"
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_TRANSIENT_RETRIES = 2  # limited retries (total attempts = 1 + MAX_TRANSIENT_RETRIES)
RETRY_BACKOFF_SECONDS = 1.0


def _clean(value: str | None) -> str:
    return (value or "").strip()


def sms_compliance_approved() -> bool:
    """Hackathon/compliance gate: SMS stays disabled until explicitly approved."""
    raw = _clean(get_env("SMS_COMPLIANCE_APPROVED", "false")).lower()
    return raw in {"1", "true", "yes", "on"}


def textbee_enabled() -> bool:
    # Default disabled for hackathon safety; explicit opt-in required.
    raw = _clean(get_env("TEXTBEE_ENABLED", "false")).lower()
    return raw in {"1", "true", "yes", "on"}


def textbee_configured() -> bool:
    return bool(_clean(get_env("TEXTBEE_API_KEY"))) and bool(_clean(get_env("TEXTBEE_DEVICE_ID")))


def textbee_active() -> bool:
    """TextBee is enabled, compliance-approved, and has minimum required credentials."""
    return textbee_enabled() and sms_compliance_approved() and textbee_configured()


def base_url() -> str:
    return _clean(get_env("TEXTBEE_BASE_URL")) or DEFAULT_BASE_URL


def normalize_indian_phone_to_e164(phone: str | None) -> str | None:
    """Normalize an Indian mobile number to E.164 (+91XXXXXXXXXX).

    Accepts common local forms (10 digits starting 6-9), 91-prefixed, or +91-prefixed.
    Returns None when the number is missing or invalid.
    """
    if phone is None:
        return None
    raw = str(phone).strip()
    if not raw:
        return None
    # Keep leading + only for basic sanity, then extract digits
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    # Handle 0-prefixed trunk in some inputs
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    return None


def _truncate_note(text: str, limit: int = 240) -> str:
    t = (text or "").strip()
    return t if len(t) <= limit else (t[: limit - 1] + "…")


def _classify_http_failure(status_code: int, payload: Any) -> tuple[str, str]:
    detail = ""
    if isinstance(payload, dict):
        for key in ("message", "error", "detail", "msg"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                detail = val.strip()
                break
            if isinstance(val, dict):
                nested = val.get("message") or val.get("error")
                if isinstance(nested, str) and nested.strip():
                    detail = nested.strip()
                    break
    detail_l = detail.lower()

    if status_code in (401, 403):
        return "failed", _truncate_note(f"Invalid or unauthorized TextBee API key (HTTP {status_code}).")
    if status_code == 404:
        # Could indicate wrong endpoint/device reference depending on API behavior
        if "device" in detail_l:
            return "failed", _truncate_note("TextBee device not found. Check TEXTBEE_DEVICE_ID.")
        return "failed", _truncate_note(f"TextBee endpoint or resource not found (HTTP 404).")
    if status_code == 429:
        return "failed", _truncate_note("TextBee rate limit reached (HTTP 429). Please try again later.")
    if status_code >= 500:
        return "failed", _truncate_note(f"TextBee service error (HTTP {status_code}).")
    # 4xx client/validation issues
    if "device" in detail_l and ("offline" in detail_l or "inactive" in detail_l or "disabled" in detail_l or "not enabled" in detail_l):
        return "failed", _truncate_note("TextBee device appears offline or unavailable.")
    if "invalid" in detail_l and "number" in detail_l:
        return "failed", _truncate_note("TextBee rejected the recipient phone number.")
    if detail:
        return "failed", _truncate_note(f"TextBee request failed (HTTP {status_code}): {detail}")
    return "failed", _truncate_note(f"TextBee request failed (HTTP {status_code}).")


def _success_note(status_code: int, payload: Any) -> tuple[str, str]:
    """Return (provider_ref, provider_note) for an accepted request."""
    ref = ""
    msg = ""
    if isinstance(payload, dict):
        # Try common identifiers without assuming exact schema
        for key in ("id", "messageId", "smsId", "batchId", "requestId", "trackingId"):
            val = payload.get(key)
            if val is not None and str(val).strip():
                ref = str(val).strip()
                break
        data = payload.get("data")
        if not ref and isinstance(data, dict):
            for key in ("id", "messageId", "smsId", "batchId", "requestId"):
                val = data.get(key)
                if val is not None and str(val).strip():
                    ref = str(val).strip()
                    break
            if not msg:
                m = data.get("message") or data.get("status")
                if isinstance(m, str):
                    msg = m.strip()
        if not msg:
            m = payload.get("message") or payload.get("status")
            if isinstance(m, str):
                msg = m.strip()
    note = msg or f"Accepted by TextBee (HTTP {status_code})."
    return ref[:120], _truncate_note(note)


async def send_sms_via_textbee(
    *,
    to_e164: str,
    message: str,
    max_retries: int = MAX_TRANSIENT_RETRIES,
) -> dict[str, Any]:
    """Send a single SMS via TextBee.

    Returns a dict with:
      ok: bool
      status: "submitted" | "failed"
      provider_ref: str
      provider_note: str
      error: str (safe, user-displayable classification/detail)
    """
    if not textbee_enabled():
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "SMS delivery is disabled.", "error": "SMS delivery is disabled."}
    if not sms_compliance_approved():
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "SMS compliance approval is required before delivery.", "error": "SMS compliance approval is required before delivery."}
    api_key = _clean(get_env("TEXTBEE_API_KEY"))
    device_id = _clean(get_env("TEXTBEE_DEVICE_ID"))
    if not api_key:
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "TextBee API key is not configured.", "error": "TextBee API key is not configured."}
    if not device_id:
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "TextBee device ID is not configured.", "error": "TextBee device ID is not configured."}
    if not to_e164:
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "No valid recipient phone number.", "error": "No valid recipient phone number."}
    body = (message or "").strip()
    if not body:
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "SMS message body is empty.", "error": "SMS message body is empty."}

    url = f"{base_url().rstrip('/')}{SEND_PATH}"
    payload = {
        "recipients": [to_e164],
        "message": body,
        "deviceId": device_id,
    }
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    attempts = max(0, int(max_retries)) + 1
    last_result: dict[str, Any] | None = None

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                content_type = (resp.headers.get("content-type") or "").lower()
                data: Any = None
                if "application/json" in content_type:
                    try:
                        data = resp.json()
                    except Exception:
                        data = None
                if data is None:
                    # Try JSON parse anyway; fall back to text snippet without logging body content broadly
                    try:
                        data = resp.json()
                    except Exception:
                        data = None

                if 200 <= resp.status_code < 300:
                    # Treat 2xx as provider acceptance/submission unless explicit failure indicated
                    explicit_fail = False
                    if isinstance(data, dict):
                        success_flag = data.get("success")
                        status_flag = str(data.get("status") or "").lower()
                        if success_flag is False:
                            explicit_fail = True
                        if status_flag in {"failed", "error", "failure"}:
                            explicit_fail = True
                        # Some APIs nest status
                        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
                        if isinstance(nested, dict):
                            if nested.get("success") is False:
                                explicit_fail = True
                            if str(nested.get("status") or "").lower() in {"failed", "error", "failure"}:
                                explicit_fail = True
                    if explicit_fail:
                        status, note = _classify_http_failure(resp.status_code, data)
                        return {"ok": False, "status": status, "provider_ref": "", "provider_note": note, "error": note}

                    ref, note = _success_note(resp.status_code, data)
                    return {"ok": True, "status": "submitted", "provider_ref": ref, "provider_note": note, "error": ""}

                # Non-2xx
                status, note = _classify_http_failure(resp.status_code, data)
                last_result = {"ok": False, "status": status, "provider_ref": "", "provider_note": note, "error": note}

                # Retry only transient server/rate-ish cases where a brief retry may help (not auth/validation)
                transient = resp.status_code >= 500 or resp.status_code == 429
                if transient and attempt < attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return last_result

            except httpx.TimeoutException:
                note = "TextBee request timed out."
                last_result = {"ok": False, "status": "failed", "provider_ref": "", "provider_note": note, "error": note}
                if attempt < attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return last_result
            except httpx.RequestError as exc:
                # Network/connectivity/device gateway unreachable from API side, DNS, TLS etc.
                # Do not include exception details that might carry sensitive URL/query info.
                err_type = type(exc).__name__
                note = "Could not reach TextBee SMS service."
                if "Connect" in err_type:
                    note = "Could not connect to TextBee SMS service."
                last_result = {"ok": False, "status": "failed", "provider_ref": "", "provider_note": note, "error": note}
                logger.warning("TextBee SMS request failed (%s)", err_type)
                if attempt < attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return last_result
            except Exception:
                logger.exception("Unexpected TextBee SMS integration error")
                note = "Unexpected SMS delivery error."
                return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": note, "error": note}

    return last_result or {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "SMS delivery failed.", "error": "SMS delivery failed."}
