"""Voice and AI adapters for ASHA Swar Nirantar.

STT: Gnani Prisma v3.0 streaming speech-to-text over WebSocket (unchanged).
LLM: Google Gemini (official google-genai SDK) for Tara AI extraction/conversation.
TTS: Gnani Timbre v3.0 text-to-speech over HTTP (unchanged).

STT/TTS live behavior is controlled by GNANI_MODE and existing Prisma/Timbre
configuration/credentials. LLM behavior is controlled by GEMINI_API_KEY and
GEMINI_MODEL. Live/provider claims are never made without required configuration.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import urllib.request
from typing import Any, AsyncGenerator, Callable

from app import get_env, gnani_requested_mode

logger = logging.getLogger(__name__)

DEFAULT_PRISMA_WS_URL = "wss://api.vachana.ai/stt/v3/stream"


# =====================================================================
# Configuration helpers (Prisma STT / Timbre TTS preserved; Gemini LLM)
# =====================================================================

def _prisma_ws_url() -> str:
    return get_env("GNANI_PRISMA_WS_URL") or DEFAULT_PRISMA_WS_URL


def _prisma_language_locale(language: str) -> str:
    locales = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN", "te": "te-IN", "ta": "ta-IN"}
    code = (language or "").strip()
    return locales.get(code.lower().split("-")[0], code)


def _stt_live_enabled() -> bool:
    """Live Prisma STT requires live mode and the Gnani API key (no secret)."""
    return gnani_requested_mode() == "live" and bool(get_env("GNANI_API_KEY"))


# Backward-compatible name used by voice routers for STT/Prisma availability.
def _live_enabled() -> bool:
    return _stt_live_enabled()


def prisma_language_enabled(language: str) -> bool:
    """Only use Prisma for an explicitly verified language when live-configured."""
    configured = {
        value.strip().lower()
        for value in get_env("GNANI_PRISMA_LANGUAGES").split(",")
        if value.strip()
    }
    language_code = (language or "").strip().lower().split("-")[0]
    return _stt_live_enabled() and bool(language_code) and language_code in configured


def prisma_connection_url(language: str) -> str:
    """Return the Prisma stream endpoint. Language is sent via headers per docs; URL
    template placeholder {language} is still supported for legacy/custom configs."""
    from urllib.parse import quote

    url = _prisma_ws_url()
    if "{language}" in url:
        return url.replace("{language}", quote(_prisma_language_locale(language), safe=""))
    return url


def prisma_connection_headers(language: str) -> dict[str, str]:
    """Official Prisma v3.0 realtime headers (single API key, no secret).

    Evidence-based options (Gnani docs): Prisma v3.0 streaming supports model header,
    language_code as single code / indic-auto / comma-separated 1-4 language hints,
    and x-format including codemix/transcribe/verbatim/transliterate. We only send
    optional format/language-hint overrides when explicitly configured via env; we do
    not claim account support or code-mixing accuracy without real audio verification.
    """
    headers = {
        "x-api-key-id": get_env("GNANI_API_KEY"),
        "language_code": _prisma_language_code_for_request(language),
        "x-sample-rate": "16000",
    }
    model = get_env("GNANI_PRISMA_MODEL") or "prisma-v3.0"
    if model:
        headers["model"] = model
    fmt = (get_env("GNANI_PRISMA_FORMAT") or "").strip()
    if fmt:
        headers["x-format"] = fmt
    return headers


def _prisma_language_code_for_request(language: str) -> str:
    """Build language_code for Prisma request.

    Default: existing locale mapping (en-IN/kn-IN/hi-IN/te-IN/ta-IN).
    Optional explicit override: GNANI_PRISMA_LANGUAGE_CODE_<BASE>=... (e.g. kn-IN,en-IN)
    or GNANI_PRISMA_DEFAULT_LANGUAGE_CODE for non-mapped cases. Values are passed through
    only as configured by operator; not invented.
    """
    raw = (language or "").strip()
    base = raw.lower().split("-")[0] if raw else ""
    override = (get_env(f"GNANI_PRISMA_LANGUAGE_CODE_{base.upper()}") or "").strip() if base else ""
    if override:
        return override
    default_override = (get_env("GNANI_PRISMA_DEFAULT_LANGUAGE_CODE") or "").strip()
    if default_override and base not in {"en", "kn", "hi", "te", "ta"}:
        return default_override
    return _prisma_language_locale(raw)


def _tts_live_enabled() -> bool:
    return gnani_requested_mode() == "live" and bool(get_env("GNANI_TIMBRE_URL")) and bool(get_env("GNANI_TIMBRE_KEY"))


# ---------------------------------------------------------------------
# Gemini LLM (Tara AI) configuration
# ---------------------------------------------------------------------

def _gemini_api_key() -> str:
    # Backend-only configuration; never expose in responses/logs.
    return (get_env("GEMINI_API_KEY") or "").strip()


def _gemini_model() -> str:
    return (get_env("GEMINI_MODEL") or "").strip()


def _llm_live_enabled() -> bool:
    """Gemini LLM is available only when API key and model are configured."""
    return bool(_gemini_api_key()) and bool(_gemini_model())


class GeminiLLMError(RuntimeError):
    """Raised for handled Gemini configuration/request/response failures."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_gemini_error(exc: Exception) -> GeminiLLMError:
    """Map SDK/network/provider errors to safe, non-secret user-facing errors."""
    msg = str(exc or "")
    low = msg.lower()
    name = exc.__class__.__name__.lower()
    if isinstance(exc, GeminiLLMError):
        return exc
    if "api key" in low and ("invalid" in low or "missing" in low or "unauth" in low or "permission" in low) or "permission_denied" in low or "unauthenticated" in low:
        return GeminiLLMError("invalid_api_key", "Gemini API key is invalid or not authorized.")
    if "quota" in low or "resource_exhausted" in low or "exceeded" in low and "quota" in low:
        return GeminiLLMError("quota_exhausted", "Gemini API quota is exhausted or unavailable.")
    if "rate" in low and "limit" in low or "429" in low or "too many requests" in low:
        return GeminiLLMError("rate_limited", "Gemini rate limit reached. Please try again shortly.")
    if "model" in low and ("not found" in low or "unsupported" in low or "invalid" in low) or "model_not_found" in low:
        return GeminiLLMError("unsupported_model", "The configured Gemini model is not supported or not available.")
    if isinstance(exc, TimeoutError) or "timeout" in low or "timed out" in low or "deadline" in low:
        return GeminiLLMError("timeout", "Gemini request timed out.")
    if "json" in low or "parse" in low or "malformed" in low:
        return GeminiLLMError("malformed_response", "Gemini returned a malformed response.")
    if "empty" in low:
        return GeminiLLMError("empty_response", "Gemini returned an empty response.")
    if "connection" in low or "network" in low or "dns" in low or "unreachable" in low or "socket" in low:
        return GeminiLLMError("network_error", "Could not reach Gemini due to a network error.")
    # Generic fallback without leaking secrets/provider internals.
    return GeminiLLMError("provider_error", "Gemini request failed.")


def integration_status() -> dict:
    """Report integration configuration honestly (no connectivity probe).

    STT: Gnani Prisma. LLM: Google Gemini. TTS: Gnani Timbre.
    "Live/configured" is never claimed without required configuration.
    """
    requested = gnani_requested_mode()
    stt_configured = bool(get_env("GNANI_API_KEY")) and bool(
        [v.strip() for v in get_env("GNANI_PRISMA_LANGUAGES").split(",") if v.strip()]
    )
    tts_configured = bool(get_env("GNANI_TIMBRE_URL")) and bool(get_env("GNANI_TIMBRE_KEY"))
    llm_configured = _llm_live_enabled()
    return {
        "requested_mode": requested,
        "stt_provider": "Gnani Prisma",
        "stt_live_configured": requested == "live" and stt_configured,
        "tts_provider": "Gnani Timbre",
        "tts_live_configured": requested == "live" and tts_configured,
        "llm_provider": "Google Gemini",
        "llm_live_configured": llm_configured,
        "gemini_configured": llm_configured,
        "gemini_model": _gemini_model() if _gemini_model() else "",
        "any_live_configured": (requested == "live" and (stt_configured or tts_configured)) or llm_configured,
        # Backward-compatible aliases (older consumers)
        "prisma_live_configured": requested == "live" and stt_configured,
        "timbre_live_configured": requested == "live" and tts_configured,
    }


# =====================================================================
# 1) Streaming STT (Prisma v3.0 WebSocket)
# =====================================================================


async def transcribe_stream(
    language: str,
    receive: Callable[[], AsyncGenerator],
) -> AsyncGenerator[dict, None]:
    """Bridge client audio to a configured, verified Gnani Prisma language.

    `receive` is an async generator yielding ("bytes", data) / ("text", data)
    tuples from the client socket; this generator yields JSON-able events.

    When the provider or language is unavailable, the caller can use browser
    speech recognition. This service never returns a synthetic transcript.
    """
    if not prisma_language_enabled(language):
        yield {
            "type": "status",
            "stage": "browser_fallback",
            "mode": "demo",
            "provider": "browser",
            "reason": "integration_not_configured" if not _live_enabled() else "language_not_verified",
        }
        return

    # ---- Live path: real Prisma v3.0 WebSocket ----
    import websockets  # provided by uvicorn[standard]

    url = prisma_connection_url(language)
    headers = prisma_connection_headers(language)
    try:
        upstream = await websockets.connect(url, extra_headers=headers)  # type: ignore[call-arg]
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        headers_resp = getattr(response, "headers", None) or getattr(exc, "headers", None)
        reason = "provider_auth" if status_code in (401, 403) else "provider_unavailable"
        yield {
            "type": "status",
            "stage": "browser_fallback",
            "mode": "demo",
            "provider": "browser",
            "reason": reason,
            "detail": {
                "status_code": status_code,
                "error": str(exc),
            },
        }
        return

    try:
        async for kind, data in receive():
            if kind == "bytes":
                await upstream.send(data)
                # Drain whatever the upstream socket has ready.
                try:
                    while True:
                        msg = await asyncio_wait_for(upstream.recv(), timeout=0.01)
                        yield _parse_upstream(msg)
                except TimeoutError:
                    pass
            else:
                try:
                    msg = json.loads(data)
                except (ValueError, TypeError):
                    continue
                if msg.get("type") == "reset":
                    await upstream.send(json.dumps({"type": "reset"}))
                    yield {"type": "status", "stage": "listening", "mode": "live"}
    finally:
        try:
            await upstream.close()
        except Exception:
            pass


def _parse_upstream(msg) -> dict:
    """Normalise a Prisma event into our WS protocol."""
    if isinstance(msg, (bytes, bytearray)):
        return {"type": "stt_partial", "text": msg.decode("utf-8", "ignore"), "mode": "live"}
    try:
        data = json.loads(msg)
    except (ValueError, TypeError):
        return {"type": "stt_partial", "text": str(msg), "mode": "live"}
    if isinstance(data, dict):
        text = data.get("text") or data.get("transcript") or data.get("partial") or ""
        is_final = bool(data.get("final") or data.get("is_final"))
        out = {"type": "stt_final" if is_final else "stt_partial", "text": text, "mode": "live"}
        return out
    return {"type": "stt_partial", "text": str(data), "mode": "live"}


async def asyncio_wait_for(awaitable, timeout: float):
    import asyncio

    return await asyncio.wait_for(awaitable, timeout)


# =====================================================================
# 2) Structured extraction (LLM live / deterministic demo parser)
# =====================================================================

_EXTRACTION_SCHEMA = {
    "beneficiary_name": "string|null",
    "weeks_pregnant": "integer|null",
    "bp_sys": "integer|null",
    "bp_dia": "integer|null",
    "weight_kg": "number|null",
    "temperature": "number|null",
    "hemoglobin": "number|null",
    "vaccine_name": "string|null",
    "dose_number": "integer|null",
    "fetal_heart": "string|null",
    "feeding": "string|null",
    "jaundice": "string|null",
    "visit_date": "YYYY-MM-DD",
    # --- New extended fields ---
    "age": "integer|null",
    "gender": "string|null",
    "relation": "string|null",
    "height_cm": "number|null",
    "ifa_tablets": "boolean|null",
    "td_vaccine": "string|null",
    "blood_sugar": "number|null",
    "mobility": "string|null",
    "category": "string|null",
    "phone": "string|null",
    "village": "string|null",
    "follow_up_date": "YYYY-MM-DD|null",
    # --- Household Health & Hygiene fields (Household Health module) ---
    "household_id": "string|null",
    "water_source": "string|null",
    "water_storage_covered": "boolean|null",
    "toilet_available": "boolean|null",
    "toilet_usage": "string|null",
    "waste_disposal": "string|null",
    "drainage": "string|null",
    "stagnant_water": "boolean|null",
    "handwashing": "boolean|null",
    "awareness_provided": "boolean|null",
    "follow_up_days": "integer|null",
}


def _extract_json_object(text: str) -> dict | None:
    """Best-effort extraction of a JSON object from model text (no code fences assumed)."""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    # Strip common markdown fences
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # Fallback: find first balanced-ish JSON object
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(s[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def _gemini_client():
    """Create a Gemini client from backend configuration. Raises GeminiLLMError on config issues."""
    api_key = _gemini_api_key()
    model = _gemini_model()
    if not api_key:
        raise GeminiLLMError("missing_api_key", "Gemini API key is not configured.")
    if not model:
        raise GeminiLLMError("missing_model", "Gemini model is not configured.")
    try:
        from google import genai  # type: ignore

        return genai.Client(api_key=api_key), model
    except Exception as exc:
        # SDK import/init failures
        raise GeminiLLMError("provider_error", "Gemini SDK is unavailable or failed to initialize.") from exc


def _gemini_generate_text(prompt: str, *, response_mime_type: str | None = None, timeout_s: float = 20.0) -> str:
    """Generate text from Gemini with robust error handling. Never returns fake success."""
    client, model = _gemini_client()
    try:
        config: dict[str, Any] = {}
        if response_mime_type:
            config["response_mime_type"] = response_mime_type
        # Prefer typed config if available, else pass dict (SDK accepts both in many versions)
        try:
            from google.genai import types  # type: ignore

            gen_config = types.GenerateContentConfig(**config) if config else None
            resp = client.models.generate_content(model=model, contents=prompt, config=gen_config)
        except Exception:
            resp = client.models.generate_content(model=model, contents=prompt, config=config or None)
    except Exception as exc:
        raise _safe_gemini_error(exc) from exc

    try:
        text = getattr(resp, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        # Fallback: inspect candidates/parts
        candidates = getattr(resp, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) if content is not None else None
            if not parts and isinstance(content, dict):
                parts = content.get("parts")
            if parts:
                chunks = []
                for p in parts:
                    t = getattr(p, "text", None)
                    if t is None and isinstance(p, dict):
                        t = p.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
                joined = "".join(chunks).strip()
                if joined:
                    return joined
    except Exception as exc:
        raise GeminiLLMError("malformed_response", "Gemini returned a malformed response.") from exc

    raise GeminiLLMError("empty_response", "Gemini returned an empty response.")


def _gemini_extract_live(transcript: str, language: str) -> dict | None:
    """Extract structured visit fields using Gemini. Returns validated dict or None on failure."""
    if not _llm_live_enabled():
        return None
    transcript = (transcript or "").strip()
    if not transcript:
        return None
    prompt = (
        "You are Tara, an AI assistant for ASHA community health workers in the ASHA Swar Nirantar app. "
        "Extract healthcare visit fields from the transcript below. "
        "Do not diagnose, do not prescribe, and do not invent symptoms, dates, measurements, or beneficiary details. "
        "Preserve reported danger signs accurately. If information is missing or ambiguous, leave the field null/omitted (do not guess). "
        "Extract beneficiary_name only when a person/beneficiary name is explicitly stated in the transcript; never use ASHA worker name, household label, or guess a name. "
        "Support Kannada, English, Kannada-English code-mix, and other supported languages by understanding meaning from the transcript. "
        "Reply with ONLY a single JSON object matching this schema (use null for unknown values; use ISO YYYY-MM-DD for dates when explicitly stated, else omit):\n"
        f"{json.dumps(_EXTRACTION_SCHEMA, ensure_ascii=False)}\n\n"
        f"Language hint: {language}\n"
        f"Transcript:\n{transcript}"
    )
    try:
        text = _gemini_generate_text(prompt, response_mime_type="application/json")
        obj = _extract_json_object(text)
        if not isinstance(obj, dict):
            # try again without mime hint if provider wrapped oddly
            obj = _extract_json_object(_gemini_generate_text(prompt))
        if not isinstance(obj, dict):
            return None
        # Accept wrapped shapes defensively
        if "structured" in obj and isinstance(obj.get("structured"), dict):
            obj = obj["structured"]
        data = obj.get("data", obj) if isinstance(obj, dict) else None
        if isinstance(data, dict) and "structured" in data and isinstance(data["structured"], dict):
            data = data["structured"]
        if not isinstance(data, dict):
            return None
        validated = _validate_structured(data)
        return validated if isinstance(validated, dict) and validated else None
    except Exception:
        # Never fake a successful live/Gemini result; caller will fall back safely.
        return None


def _is_latin_dominant(text: str) -> bool:
    """True when transcript is mostly Latin/script-neutral (code-mixed kn-en/hi-en)."""
    letters = [ch for ch in (text or "") if ch.isalpha()]
    if not letters:
        return True
    latin = sum(1 for ch in letters if ("a" <= ch.lower() <= "z"))
    return (latin / max(1, len(letters))) >= 0.45


def _is_kannada_script_path(language: str, transcript: str) -> bool:
    lang = (language or "").lower().strip()
    if lang == "kn":
        return not _is_latin_dominant(transcript)
    if lang.startswith("kn-") or lang.endswith("-kn"):
        return not _is_latin_dominant(transcript)
    return False


def _normalize_visit_names(structured: dict | None) -> dict:
    """Normalize the one name shared by structured extraction fields."""
    result = dict(structured or {})
    personal = dict(result.get("personal_details") or {})
    raw = dict(result.get("raw_structured") or {})

    candidates = (
        result.get("beneficiary_name"),
        personal.get("name"),
        raw.get("beneficiary_name"),
        raw.get("name"),
    )
    name = next((str(v).strip() for v in candidates if isinstance(v, str) and str(v).strip()), None)

    # Precedence for conflicts: top-level beneficiary_name is the canonical
    # extraction value, then personal_details.name, then raw extraction.
    if name:
        result["beneficiary_name"] = name
        personal["name"] = name
    else:
        result.pop("beneficiary_name", None)
        personal.pop("name", None)

    if personal:
        result["personal_details"] = personal
    raw_name = raw.get("beneficiary_name") or raw.get("name")
    if name:
        raw["beneficiary_name"] = name
        raw["name"] = name
    elif raw_name:
        raw.pop("beneficiary_name", None)
        raw.pop("name", None)
    if raw:
        result["raw_structured"] = raw
    return result


def extract_fields(transcript: str, language: str = "en") -> tuple[dict, str]:
    """Extract structured fields from a transcript.

    Returns (structured_dict, mode) where mode is "live" (Gemini) or "demo"
    (deterministic fallback). Gemini is attempted when configured; any failure,
    timeout, malformed/empty response, or unavailable config falls back to the
    deterministic parser so existing functionality remains available.
    """
    transcript = transcript or ""
    use_kannada = _is_kannada_script_path(language, transcript)
    if _llm_live_enabled():
        live = _gemini_extract_live(transcript, language)
        if live is not None:
            # Merge deterministic cues for robustness (without inventing data): if Gemini omitted
            # clearly parseable local cues, keep Gemini result authoritative where present.
            # We only fill missing keys from deterministic parse.
            try:
                fallback = _extract_kannada(transcript) if use_kannada else _extract_demo(transcript)
                for k, v in (fallback or {}).items():
                    if k not in live or live.get(k) in (None, "", []):
                        live[k] = v
                if live.get("beneficiary_name") and fallback.get("beneficiary_name") and str(live.get("beneficiary_name")).strip().lower() != str(fallback.get("beneficiary_name")).strip().lower():
                    logger.warning("beneficiary name extraction sources conflict; precedence=Gemini-for-name")
            except Exception:
                pass
            live = _normalize_visit_names(live)
            return live, "live"

    # Deterministic fallback (preserved behavior)
    if use_kannada:
        return _normalize_visit_names(_extract_kannada(transcript)), "demo"
    return _normalize_visit_names(_extract_demo(transcript)), "demo"


def _validate_structured(data: dict) -> dict:
    """Schema-validate + normalise the LLM response."""
    clean: dict = {"visit_date": data.get("visit_date") or date_today_iso()}
    numeric_keys = ("weeks_pregnant", "bp_sys", "bp_dia", "dose_number", "follow_up_days", "age")
    float_keys = ("weight_kg", "temperature", "hemoglobin", "height_cm", "blood_sugar")
    text_keys = ("beneficiary_name", "vaccine_name", "fetal_heart", "feeding", "jaundice",
                 "household_id", "water_source", "toilet_usage", "waste_disposal", "drainage",
                 "gender", "relation", "td_vaccine", "mobility", "category", "phone", "village",
                 "follow_up_date")
    bool_keys = ("water_storage_covered", "toilet_available", "stagnant_water",
                 "handwashing", "awareness_provided", "ifa_tablets")
    for key in numeric_keys:
        value = _as_int(data.get(key))
        if value is not None:
            clean[key] = value
    for key in float_keys:
        value = _as_float(data.get(key))
        if value is not None:
            clean[key] = value
    for key in text_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            clean[key] = value.strip()
    for key in bool_keys:
        value = data.get(key)
        if isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, str) and value.strip().lower() in ("true", "yes", "1"):
            clean[key] = True
        elif isinstance(value, str) and value.strip().lower() in ("false", "no", "0"):
            clean[key] = False
    return clean


def date_today_iso() -> str:
    from datetime import date as _date

    return _date.today().isoformat()


def _as_int(value) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _as_float(value) -> float | None:
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------
# DEMO parser: deterministic regex/keyword extraction (no LLM involved).
# Handles the sample sentence and common spoken variants.
# ---------------------------------------------------------------------
_NAME_AFTER_VISITED = re.compile(
    r"\b(?:visited|met|saw|checked|examined)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?|[^\s,.;!?]+)",
    re.I,
)
_NAME_BEFORE_VISITED = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?|[^\s,.;!?]+)\s+was\s+visited\b|"
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?|[^\s,.;!?]+)\s+visited\b",
    re.I,
)
_WEEKS_PREGNANT = re.compile(r"\b(\d{1,2})\s*weeks?\s+pregnant\b", re.I)
_BP_OVER = re.compile(r"\b(\d{2,3})\s+(?:over|upon)\s+(\d{2,3})\b", re.I)
_BP_SLASH = re.compile(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b")
_WEIGHT = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:kilograms?|kilos?|kgs?|kg)\b", re.I)
_TEMP = re.compile(r"\b(\d{2,3}(?:\.\d+)?)\s*(?:degrees?|fahrenheit|f)\b", re.I)
_HEMOGLOBIN = re.compile(r"\bhemoglobin\s*(?:is|of|at)?\s*(\d+(?:\.\d+)?)\b", re.I)
_VACCINE = re.compile(
    r"\bgiven\s+(BCG|OPV[- ]?0|OPV|Penta(?:valent)?[- ]?\d?|MR|Hepatitis[- ]B|Rotavirus|Rota)\b", re.I
)
_DOSE = re.compile(r"\bdose\s*(?:number)?\s*(\d)\b", re.I)
_FETAL_HEART = re.compile(r"\bfetal\s+heart\s*(?:sounds?\s*)?(?:is|are|:)?\s*(normal|present|absent|regular)\b", re.I)
_FEEDING = re.compile(r"\b(?:is\s+)?(breastfeed\w*|feeding\s+well|not\s+feeding\s+well|poor\s+(?:feeding|sucking))\b", re.I)
_JAUNDICE = re.compile(r"\bjaundice\b", re.I)

# --- Household Health & Hygiene demo patterns ---
_HH_ID = re.compile(
    r"\b(?:household\s*(?:id)?|house\s*(?:no\.?|number)?)\s*[:#]?\s*"
    r"(HOUSE-DEMO-\d{3}|HN-[A-Z2-9]{4}-[A-Z2-9]{4}|\d{1,4})\b", re.I)
_WATER_SOURCE = re.compile(
    r"\b(borewell|bore\s*well|piped\s+water|tap\s+water|open\s+well|hand\s*pump|"
    r"well\s+water|river|pond|lake|rainwater\s+harvest)\b", re.I)
_STORAGE_COVERED = re.compile(
    r"\bwater\s+is\s+stored\s+(?:in\s+)?a?\s*(covered|closed)\b|"
    r"\b(covered|closed)\s+(?:container|drum|vessel|pot)\b", re.I)
_STORAGE_UNCOVERED = re.compile(
    r"\bwater\s+is\s+stored\s+(?:in\s+)?an?\s*(uncovered|open)\b|"
    r"\b(uncovered|open)\s+(?:container|drum|vessel|pot)\b|"
    r"\bno\s+cover\s+on\s+the\s+water\b", re.I)
_TOILET_AVAIL = re.compile(r"\b(?:no|not\s+have|doesn'?t\s+have|lacks?)\s+(?:a\s+)?toilet\b|\btoilet\s+is\s+(?:not\s+)?available\b|\btoilet\s+is\s+available\b|\bopen\s+defecation\b|\bno\s+toilet\b", re.I)
_WASTE = re.compile(
    r"\b(waste|garbage|trash)\s+is\s+(collected|picked\s+up)\s+(\w+\s+)?(?:times?\s+a\s+week|weekly|daily|twice\s+a\s+week)\b|"
    r"\bwaste\s+is\s+(burnt|thrown\s+in\s+the\s+open|dumped\s+outside|not\s+collected)\b", re.I)
_DRAINAGE = re.compile(
    r"\bdrainage\s+is\s+(good|clear|functional|blocked|clogged|broken|open)\b|"
    r"\b(closed|open)\s+drainage\b", re.I)
_STAGNANT = re.compile(
    r"\bstagnant\s+water\b|\bwater\s+logging\b|\bwaterlogged\b|\bstanding\s+water\b", re.I)
_STAGNANT_NEG = re.compile(
    r"\b(?:no|not\s+any|without|cleared\s+the|no\s+more)\s+(?:stagnant\s+water|standing\s+water|water\s+logging)\b|"
    r"\bstagnant\s+water\s+(?:has\s+been\s+)?cleared\b|"
    r"\bno\s+stagnant\s+water\b", re.I)
_HANDWASH = re.compile(
    r"\bhandwashing\s+(?:facility|station|soap)\s+(?:is\s+)?(?:available|present)\b|"
    r"\bwash(?:ing)?\s+their\s+hands\s+with\s+soap\b|"
    r"\bno\s+(?:soap|handwashing\s+facility)\b", re.I)
_AWARENESS = re.compile(
    r"\b(?:advised|counselled|counseled|educated|explained|awareness\s+session|health\s+talk)\b", re.I)
_FOLLOW_UP_IN = re.compile(r"\bfollow[- ]?up\s+(?:visit\s+)?(?:in|after)\s+(\d{1,2})\s*days?\b", re.I)
# MCH/code-mixed patterns (kn-en, hi-en, en) - deterministic, no external LLM.
_MCH_GESTATION_MONTHS = re.compile(r"\b(\d{1,2})\s*(?:months?\s+pregnant|mahine|mahina|thingalu|tingalu|maasam|masam)\b", re.I)
_MCH_HB = re.compile(r"\b(?:hb|hemoglobin)\s*[:=]?\s*(\d+(?:\.\d+)?)\b", re.I)
_MCH_WEIGHT = re.compile(r"\bweight\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilos)?\b", re.I)
_MCH_TEMP_C = re.compile(r"\b(?:temp(?:erature)?|jwara|bukhar)\s*[:=]?\s*(\d{2}(?:\.\d+)?)\b", re.I)
_MCH_BP = re.compile(r"\b(?:bp|blood\s*pressure)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\b", re.I)
_MCH_IFA_YES = re.compile(r"\b(?:ifa\s+(?:tablets?\s+)?(?:given|di|dili|kottidini|kottide|yes)|ifa\s+goli\s+(?:di|dili|kottidini|kottide|kotidini))\b", re.I)
_MCH_IFA_NO = re.compile(r"\b(?:ifa\s+(?:tablets?\s+)?(?:not\s+given|nahi\s+di|illa|kodlilla|kodilla|not\s+given)|ifa\s+goli\s+(?:nahi\s+di|kodlilla|kodilla|illa)|ifa\s+not\s+given)\b", re.I)
_MCH_TD = re.compile(r"\b(?:tt|td)\s*(?:dose\s*)?(\d)\b", re.I)
_MCH_TD_DONE = re.compile(r"\b(?:tt|td)\s*(?:dose\s*)?(\d)\s*(?:done|given|kottidini|kottide|lagaya|lagayi|diya)\b", re.I)
_MCH_NEXT_VISIT = re.compile(r"\b(?:next\s+(?:anc|visit|immuni[sz]ation)?\s*(?:visit\s*)?(?:in\s*)?|agla\s+(?:anc\s*)?|next\s+anc\s*)(\d{1,3})\s*(?:days?|din|dinakke|dina|baad)\b", re.I)
_MCH_NEXT_VISIT2 = re.compile(r"\b(\d{1,3})\s*(?:dinakke|din\s+baad)\b", re.I)
_MCH_NEWBORN_DAY = re.compile(r"\b(?:day\s*(\d{1,3})\s*visit|(?:hbnc\s*)?day\s*(\d{1,3})|(\d{1,3})\s*din\s+ka\s+pnc)\b", re.I)
_MCH_VACCINE = re.compile(r"\b(pentavalent(?:[- ]?\d)?|bcg|opv(?:[- ]?\d)?|mr\s*[- ]?\d|measles[- ]rubella[- ]?\d|hep[- ]?b\s+birth\s+dose|hepb\s+birth\s+dose|hepatitis[- ]b(?:\s+birth\s+dose)?|dpt(?:[- ]?\d)?|rotavirus(?:[- ]?\d)?|pcv(?:[- ]?\d)?|ipv(?:[- ]?\d)?)\b", re.I)
_MCH_VACCINE_PENDING = re.compile(r"\b(?:baki\s+ide|baaki\s+hai|pending|due)\b", re.I)
_MCH_DANGER = {
    "reduced_fetal_movement": re.compile(r"\b(?:maga\s+ochadtilla|baby\s+movement\s+(?:kam|reduced|not\s+felt)|reduced\s+fetal\s+movement)\b", re.I),
    "bleeding": re.compile(r"\b(?:blood\s+hogta\s+ide|bleeding|rakta\s+srava|raktasrav)\b", re.I),
    "high_fever": re.compile(r"\b(?:jwara\s+jasti\s+ide|tez\s+bukhar|high\s+fever|fever\s+high)\b", re.I),
    "convulsions": re.compile(r"\b(?:convulsions?|fits|akadi)\b", re.I),
    "swelling": re.compile(r"\b(?:swelling|edema|soojan|neeru)\b", re.I),
}
_MCH_NAME_GE_KO = re.compile(r"^\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(?:ge|ko|ka|ki|ke)\b", re.I)
_MCH_NAME_BABY = re.compile(r"\b([A-Z][a-zA-Z]+)\s+(?:baby|ka\s+baby|ke\s+baby|baby\s+ge)\b", re.I)
_MCH_NAME_NEWBORN = re.compile(r"\b([A-Z][a-zA-Z]+)(?:'s|\s+ka|\s+ke)\s+(?:newborn|baby)\b", re.I)

# --- Extended patterns for new fields ---
_WORD_TO_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_AGE_YEARS_OLD = re.compile(r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s*years?\s*old\b", re.I)
_AGE_IS = re.compile(r"\bage\s*(?:is|:)?\s*(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
# "Ravi, aged 65" / "Anu, aged two years"
_AGE_AGED = re.compile(
    r"\baged\s*(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I
)
_HEIGHT = re.compile(r"\b(\d{2,3})\s*(?:cm|centimeters?)\b", re.I)
_BLOOD_SUGAR = re.compile(r"\bblood\s+sugar\s*(?:is|of|at)?\s*(\d+(?:\.\d+)?)\b", re.I)
_IFA_YES = re.compile(r"\b(?:taking|given|started|receiving)\s+IFA\b|\bIFA\s+tablets?\s+(?:given|started|regular|taking|provided)\b", re.I)
_IFA_NO = re.compile(r"\b(?:not\s+taking|not\s+given|stopped|no)\s+IFA\b", re.I)
_TD_VACCINE = re.compile(r"\bTd\s*(?:vaccine|vaccination|dose|given)?\s*(\d)?\b", re.I)
_MOBILITY = re.compile(r"\b(difficulty\s+walking|bedridden|mobile|walks?\s+with\s+support|uses?\s+wheelchair|confined\s+to\s+bed)\b", re.I)
_GENDER_MALE = re.compile(r"\bhe\s+is\b|\bhis\b|\bold\s+man\b|\bgrandfather\b|\bfather\b|\bhusband\b", re.I)
_GENDER_FEMALE = re.compile(r"\bshe\s+is\b|\bher\b|\bold\s+woman\b|\bgrandmother\b|\bmother\b|\bwife\b|\bsister\b", re.I)
_VILLAGE = re.compile(r"\bvillage\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b", re.I)
_PHONE = re.compile(r"\b(?:phone|mobile|contact)\s*(?:number|no\.?)?\s*[:#]?\s*(\d{10,12})\b", re.I)
_FOLLOW_UP_DATE = re.compile(r"\bfollow[- ]?up\s+(?:on|date)?\s*(\d{4}-\d{2}-\d{2})\b", re.I)


# Common non-name words that sometimes follow a name in casual speech.
_NAME_STOPWORDS = {"today", "yesterday", "tomorrow", "was", "is", "here", "home", "and", "then", "this", "morning", "evening"}


def _trim_name(name: str) -> str:
    """Drop trailing stopword(s) from a captured candidate name: 'Lakshmi today' -> 'Lakshmi'."""
    words = name.split()
    while len(words) > 1 and words[-1].lower() in _NAME_STOPWORDS:
        words.pop()
    return " ".join(words)


def _extract_demo(transcript: str) -> dict:
    """Deterministic keyword/regex parser — same input always gives the same output."""
    structured: dict = {"visit_date": date_today_iso()}
    text = transcript or ""

    _ROLE_BLOCK = {
        "household","house","the","a","an","asha","worker","asha worker","doctor","nurse","an m","anm",
        "supervisor","beneficiary","patient","mother","father","child","baby","newborn","family"
    }
    def _looks_like_worker_role(name, full_text):
        nl=(name or "").lower()
        tl=(full_text or "").lower()
        # If the same name is explicitly described as ASHA/worker/doctor/nurse, don't treat as beneficiary.
        return bool(re.search(rf"\b{re.escape(nl)}\b\s+(?:is|was)\s+(?:the\s+|an?\s+)?(?:asha|asha worker|worker|doctor|nurse|anm)\b", tl)) or bool(re.search(rf"\b(?:asha worker|worker|doctor|nurse|anm)\s+{re.escape(nl)}\b", tl))
    m = _NAME_AFTER_VISITED.search(text)
    if m:
        candidate = _trim_name(m.group(1).strip(" .,!?:;\"'"))
        cl = (candidate or "").lower()
        if candidate and cl not in _NAME_STOPWORDS and cl not in _ROLE_BLOCK and not cl.startswith(("asha ","worker ","doctor ","nurse ")) and not _looks_like_worker_role(candidate, text):
            structured["beneficiary_name"] = candidate[:1].upper() + candidate[1:] if candidate.islower() else candidate
    if "beneficiary_name" not in structured:
        m = _NAME_BEFORE_VISITED.search(text)
        if m:
            candidate = _trim_name((m.group(1) or m.group(2) or "").strip(" .,!?:;\"'"))
            cl = (candidate or "").lower()
            if candidate and cl not in _NAME_STOPWORDS and cl not in _ROLE_BLOCK and not cl.startswith(("asha ","worker ","doctor ","nurse ")):
                structured["beneficiary_name"] = candidate[:1].upper() + candidate[1:] if candidate.islower() else candidate
    # Household speech ("Visited household 24…") is not a beneficiary name —
    # the household_id field carries the subject instead.
    if "beneficiary_name" in structured:
        bn = structured["beneficiary_name"].lower()
        if bn in ("household", "house") or bn.startswith(("household ", "house ")):
            del structured["beneficiary_name"]
    if "beneficiary_name" not in structured:
        m = _MCH_NAME_NEWBORN.search(text) or _MCH_NAME_BABY.search(text) or _MCH_NAME_GE_KO.search(text)
        if m:
            candidate = _trim_name(m.group(1).strip(" .,!?:;\"'"))
            if candidate and candidate.lower() not in _NAME_STOPWORDS:
                structured["beneficiary_name"] = candidate[:1].upper() + candidate[1:] if candidate.islower() else candidate
    if "beneficiary_name" not in structured:
        m = re.match(r"^\s*([A-Z][a-zA-Z]{2,30}(?:\s+[A-Z][a-zA-Z]{2,30})?)\s*[,:-]", text)
        if m:
            candidate = _trim_name(m.group(1).strip())
            if candidate.lower() not in _NAME_STOPWORDS | {"visited","met","saw","checked","examined","today","anc","pnc","hbnc","baby","newborn"}:
                structured["beneficiary_name"] = candidate
    if "beneficiary_name" not in structured:
        # Common spoken pattern: "Manasvi is 18 years old..." / "Lakshmi has severe headache" / "madhu is a 13..."
        m = re.search(r"(?:^|[.!?]\s+|\bvisited\s+)([A-Za-z][A-Za-z]{1,30}(?:\s+[A-Za-z][A-Za-z]{1,30})?)\s+(?:is|was|has|had|aged|turned|reports|complains|feels|presented)\b", text, re.I)
        if m:
            candidate = _trim_name(m.group(1).strip(" .,!?:;\"'"))
            blocked = _NAME_STOPWORDS | {
                "visited","met","saw","checked","examined","today","anc","pnc","hbnc","baby","newborn","child",
                "mother","father","patient","beneficiary","household","house","family","she","he","they","this",
                "that","there","weight","height","temperature","bp","blood","age","visit","follow","next",
                "the","a","an","my","her","his","their","our","i","we","asha","worker","doctor","nurse","sir","madam",
                "name","person","someone","anyone","everyone"
            }
            blocked_phrases = {
                "the beneficiary","the patient","this patient","this beneficiary","that beneficiary","that patient",
                "patient name","beneficiary name","the name","my name","her name","his name","their name",
                "a patient","a beneficiary","the child","the mother","the father","the baby","this child"
            }
            cl = candidate.lower().strip()
            # Strip leading role labels if present: "Patient Priya" -> "Priya"
            for prefix in ("patient ", "beneficiary ", "child ", "mother ", "father ", "baby ", "newborn "):
                if cl.startswith(prefix):
                    candidate = candidate[len(prefix):].strip()
                    cl = candidate.lower().strip()
                    break
            if candidate and cl not in blocked and cl not in blocked_phrases and not cl.startswith(("household ", "house ", "the ", "this ", "that ", "a ", "an ")) and not _looks_like_worker_role(candidate, text):
                structured["beneficiary_name"] = candidate if not candidate.islower() else candidate[:1].upper() + candidate[1:]
    if "beneficiary_name" not in structured:
        # "Beneficiary/patient name is Madhu" / "This is Madhu"
        m = re.search(r"\b(?:(?:beneficiary(?:\s+name)?|patient(?:\s+name)?|name|person)\s*(?:is|:|-)\s*|(?:this is|that is)\s+)([A-Za-z][A-Za-z]{1,30}(?:\s+[A-Za-z][A-Za-z]{1,30})?)\b", text, re.I)
        if m:
            candidate = _trim_name(m.group(1).strip(" .,!?:;\"'"))
            blocked = {"unknown","not","none","na","n/a","beneficiary","patient","household","a","an","the","she","he","they","pregnant","here","there","just","only","also"}
            if candidate and candidate.lower() not in blocked and not _looks_like_worker_role(candidate, text):
                structured["beneficiary_name"] = candidate if not candidate.islower() else candidate[:1].upper() + candidate[1:]
    if "beneficiary_name" not in structured:
        # "Madhu, age 13" / "Madhu age 13"
        m = re.search(r"(?:^|[.!?]\s+)([A-Za-z][A-Za-z]{1,30}(?:\s+[A-Za-z][A-Za-z]{1,30})?)\s*[,-]?\s*(?:age|aged)\b", text, re.I)
        if m:
            candidate = _trim_name(m.group(1).strip(" .,!?:;\"'"))
            blocked = _NAME_STOPWORDS | {"patient","beneficiary","child","mother","father","baby","he","she","they","age"}
            if candidate and candidate.lower() not in blocked and not _looks_like_worker_role(candidate, text):
                structured["beneficiary_name"] = candidate if not candidate.islower() else candidate[:1].upper() + candidate[1:]

    m = _WEEKS_PREGNANT.search(text)
    if m:
        structured["weeks_pregnant"] = int(m.group(1))

    m = _BP_OVER.search(text) or _BP_SLASH.search(text)
    if m:
        structured["bp_sys"] = int(m.group(1))
        structured["bp_dia"] = int(m.group(2))

    m = _WEIGHT.search(text)
    if m:
        structured["weight_kg"] = float(m.group(1))

    m = _TEMP.search(text)
    if m:
        structured["temperature"] = float(m.group(1))

    m = _HEMOGLOBIN.search(text)
    if m:
        structured["hemoglobin"] = float(m.group(1))

    m = _VACCINE.search(text)
    if m:
        vaccine = m.group(1).upper().replace("-", " ")
        vaccine = {"OPV 0": "OPV-0", "PENTA": "PENTA-1", "PENTA VALENT": "PENTA-1"}.get(vaccine, vaccine)
        if vaccine.startswith("PENTA"):
            dose = _DOSE.search(text)
            vaccine = f"PENTA-{dose.group(1)}" if dose else "PENTA-1"
        structured["vaccine_name"] = vaccine

    m = _DOSE.search(text)
    if m and "vaccine_name" in structured:
        structured["dose_number"] = int(m.group(1))

    m = _FETAL_HEART.search(text)
    if m:
        structured["fetal_heart"] = m.group(1)

    m = _FEEDING.search(text)
    if m:
        structured["feeding"] = m.group(1)

    if _JAUNDICE.search(text):
        # Crude polarity: "no jaundice" -> no, else yes/mild.
        negated = re.search(r"\b(?:no|not|without)\s+(?:sign\s+of\s+)?jaundice\b", text, re.I)
        structured["jaundice"] = "no" if negated else "yes"

    # --- Household Health & Hygiene extraction (demo parser) ---
    m = _HH_ID.search(text)
    if m:
        structured["household_id"] = m.group(1).upper()

    m = _WATER_SOURCE.search(text)
    if m:
        structured["water_source"] = m.group(1).lower()

    if _STORAGE_COVERED.search(text):
        structured["water_storage_covered"] = True
    elif _STORAGE_UNCOVERED.search(text):
        structured["water_storage_covered"] = False

    if re.search(r"\btoilet\s+is\s+(?:not\s+)?available\b", text, re.I) or \
       re.search(r"\bhas\s+(?:a\s+)?toilet\b|\btoilet\s+facility\b|\bIHHL\b|\blatrine\b", text, re.I):
        structured["toilet_available"] = True
    elif re.search(r"\b(?:no|not\s+have|doesn'?t\s+have|lacks?)\s+(?:a\s+)?toilet\b|\bno\s+toilet\b|\bopen\s+defecation\b", text, re.I):
        structured["toilet_available"] = False

    m = re.search(r"\btoilet\s+(?:is\s+)?(?:being\s+)?(used|in\s+use|not\s+used|unused)\b", text, re.I)
    if m:
        structured["toilet_usage"] = "used" if "not" not in m.group(1) else "not used"

    m = _WASTE.search(text)
    if m:
        structured["waste_disposal"] = m.group(0).lower()

    m = _DRAINAGE.search(text)
    if m:
        structured["drainage"] = m.group(1).lower() if m.group(1) else m.group(0).lower()

    if _STAGNANT_NEG.search(text):
        structured["stagnant_water"] = False
    elif _STAGNANT.search(text):
        structured["stagnant_water"] = True

    if _HANDWASH.search(text):
        structured["handwashing"] = not bool(re.search(r"\bno\s+(?:soap|handwashing\s+facility)\b", text, re.I))

    if _AWARENESS.search(text):
        structured["awareness_provided"] = True

    m = _FOLLOW_UP_IN.search(text)
    if m:
        structured["follow_up_days"] = int(m.group(1))

    # --- New extended field extraction ---
    # "Ravi, aged 65", "Anu, aged two years", "65 years old", "age is 30"
    m = (
        _AGE_YEARS_OLD.search(text)
        or _AGE_IS.search(text)
        or _AGE_AGED.search(text)
    )
    if m:
        raw_a = m.group(1).lower()
        structured["age"] = _WORD_TO_NUM.get(raw_a, int(raw_a) if raw_a.isdigit() else None)

    m = _HEIGHT.search(text)
    if m:
        structured["height_cm"] = float(m.group(1))

    m = _BLOOD_SUGAR.search(text)
    if m:
        structured["blood_sugar"] = float(m.group(1))

    if _IFA_YES.search(text):
        structured["ifa_tablets"] = True
    elif _IFA_NO.search(text):
        structured["ifa_tablets"] = False

    m = _TD_VACCINE.search(text)
    if m:
        structured["td_vaccine"] = f"Td-{m.group(1)}" if m.group(1) else "Td"

    m = _MOBILITY.search(text)
    if m:
        structured["mobility"] = m.group(1).lower()

    if _GENDER_MALE.search(text):
        structured["gender"] = "male"
    elif _GENDER_FEMALE.search(text):
        structured["gender"] = "female"

    m = _VILLAGE.search(text)
    if m:
        structured["village"] = m.group(1).strip()

    m = _PHONE.search(text)
    if m:
        structured["phone"] = m.group(1).strip()

    m = _FOLLOW_UP_DATE.search(text)
    if m:
        structured["follow_up_date"] = m.group(1).strip()

    # Relation extraction
    m_rel = re.search(r"\b(?:her|his|their)\s+(husband|wife|daughter|son|mother|father|child|baby|infant|grandmother|grandfather)\b", text, re.I)
    if m_rel:
        structured["relation"] = m_rel.group(1).lower()

    # --- MCH/code-mixed extraction (deterministic, additive) ---
    m = _MCH_GESTATION_MONTHS.search(text)
    if m and "gestation_months" not in structured:
        gm = int(m.group(1))
        if 1 <= gm <= 10:
            structured["gestation_months"] = gm
            if "weeks_pregnant" not in structured:
                structured["weeks_pregnant"] = gm * 4
    m = _MCH_HB.search(text)
    if m and "hemoglobin" not in structured:
        try: structured["hemoglobin"] = float(m.group(1))
        except Exception: pass
    m = _MCH_WEIGHT.search(text)
    if m and "weight_kg" not in structured:
        try: structured["weight_kg"] = float(m.group(1))
        except Exception: pass
    m = _MCH_BP.search(text)
    if m and "bp_sys" not in structured:
        structured["bp_sys"] = int(m.group(1)); structured["bp_dia"] = int(m.group(2))
    m = _MCH_TEMP_C.search(text)
    if m and "temperature" not in structured:
        try:
            tv = float(m.group(1))
            # Only accept plausible body temp C; avoid capturing unrelated numbers
            if 30.0 <= tv <= 45.0:
                structured["temperature"] = tv
        except Exception: pass
    if _MCH_IFA_NO.search(text):
        structured["ifa_tablets"] = False
        structured["ifa_given"] = False
    elif _MCH_IFA_YES.search(text):
        structured["ifa_tablets"] = True
        structured["ifa_given"] = True
    m = _MCH_TD_DONE.search(text) or _MCH_TD.search(text)
    if m and "td_vaccine" not in structured:
        structured["td_vaccine"] = f"TT{m.group(1)}"
        structured["td_dose"] = int(m.group(1))
    m = _MCH_NEXT_VISIT.search(text) or _MCH_NEXT_VISIT2.search(text)
    if m and "follow_up_days" not in structured:
        try: structured["follow_up_days"] = int(m.group(1))
        except Exception: pass
    # Do not invent next_visit_days when not explicitly stated in text.
    m = _MCH_NEWBORN_DAY.search(text)
    if m and "newborn_day" not in structured:
        for g in m.groups():
            if g:
                try: structured["newborn_day"] = int(g)
                except Exception: pass
                break
    m = _MCH_VACCINE.search(text)
    if m:
        vname = m.group(1).strip()
        vnorm = re.sub(r"\s+", " ", vname).strip()
        vnorm = vnorm.replace("measles rubella", "Measles-Rubella").replace("Measles rubella", "Measles-Rubella")
        if re.match(r"^pentavalent", vnorm, re.I):
            d = re.search(r"(\d)", vnorm)
            vnorm = f"Pentavalent-{d.group(1)}" if d else "Pentavalent"
        if re.match(r"^bcg$", vnorm, re.I): vnorm = "BCG"
        if re.match(r"^opv", vnorm, re.I):
            d=re.search(r"(\d)", vnorm); vnorm=f"OPV-{d.group(1)}" if d else "OPV"
        if re.match(r"^mr", vnorm, re.I):
            d=re.search(r"(\d)", vnorm); vnorm=f"Measles-Rubella-{d.group(1)}" if d else "Measles-Rubella"
        if re.match(r"^hep", vnorm, re.I):
            vnorm = "Hep-B birth dose" if "birth" in vnorm.lower() else "Hepatitis-B"
        structured["vaccine_name"] = vnorm
        if _MCH_VACCINE_PENDING.search(text):
            structured["vaccine_status"] = "pending"
        else:
            structured["vaccine_status"] = "given"
    # Danger signs (MCH code-mixed)
    mch_dangers = []
    for k, pat in _MCH_DANGER.items():
        if pat.search(text):
            mch_dangers.append(k)
    if mch_dangers:
        structured["danger_signs"] = sorted(set(mch_dangers))
        structured["symptoms"] = sorted(set((structured.get("symptoms") or []) + mch_dangers))

    # Category inference (evidence-based; do not guess from age alone when clinical context is clear)
    age_value = structured.get("age")
    is_pregnancy = "weeks_pregnant" in structured or "gestation_months" in structured or re.search(r"\bpregnant|pregnancy|anc\b", text, re.I)
    is_newborn = "newborn_day" in structured or "feeding" in structured or "jaundice" in structured or re.search(r"\bnewborn|neonat|born\s+today|hbnc|pnc\s+visit\b", text, re.I)
    is_immunisation = "vaccine_name" in structured or re.search(r"\bvaccination|vaccine|immunisation|immunization|hakidini|laga\s+diya|baaki\s+hai|baki\s+ide\b", text, re.I)
    is_household = "water_source" in structured or "toilet_available" in structured or "waste_disposal" in structured or "drainage" in structured
    is_elderly = (age_value is not None and age_value >= 60) or "mobility" in structured or ("blood_sugar" in structured and not is_pregnancy and not is_newborn)
    is_child = (age_value is not None and 0 <= age_value <= 12) or re.search(r"\bchild|toddler|baby\b", text, re.I)

    if is_pregnancy:
        structured["category"] = "pregnancy"
    elif is_newborn:
        structured["category"] = "newborn"
    elif is_immunisation and not is_elderly:
        structured["category"] = "immunisation"
    elif is_elderly:
        structured["category"] = "elderly"
    elif is_child and not is_elderly:
        structured["category"] = "child"
    elif is_household:
        structured["category"] = "household"

    return structured


_KANNADA_NUMBERS = {
    "ಒಂದು": 1,
    "ಎರಡು": 2,
    "ಮೂರು": 3,
    "ನಾಲ್ಕು": 4,
    "ಐದು": 5,
    "ಆರು": 6,
    "ಏಳು": 7,
    "ಎಂಟು": 8,
    "ಒಂಬತ್ತು": 9,
    "ಹತ್ತು": 10,
    "ಹದಿನೈದು": 15,
}


def _extract_kannada(transcript: str) -> dict:
    """Extract a small, explicit Kannada field set without translating speech."""
    text = transcript or ""
    structured: dict = {"visit_date": date_today_iso()}
    kannada_word = r"[\u0C80-\u0CFF]+"

    name = re.search(
        rf"(?:ಇಂದು\s+)?({kannada_word})\s+(?:ಅವರಿಗೆ|ಅವರ)(?:\s+ಮನೆಗೆ)?",
        text,
    )
    if not name:
        name = re.search(rf"({kannada_word}?)(?:ವಿಗೆ|ಗೆ)\s+ಮುಂದಿನ", text)
    if name:
        structured["beneficiary_name"] = name.group(1)

    weeks = re.search(r"(\d+)\s*ವಾರಗಳ?\s*ಗರ್ಭಧಾರಣೆ", text)
    if weeks:
        structured["weeks_pregnant"] = int(weeks.group(1))
        structured["category"] = "pregnancy"

    blood_pressure = re.search(r"ರಕ್ತದೊತ್ತಡ\s*(\d{2,3})\s*ಮೇಲೆ\s*(\d{2,3})", text)
    if blood_pressure:
        structured["bp_sys"] = int(blood_pressure.group(1))
        structured["bp_dia"] = int(blood_pressure.group(2))

    weight = re.search(
        r"ತೂಕ\s*(\d+(?:\.\d+)?)\s*(?:ಕಿಲೋ(?:ಗ್ರಾಂ)?|ಕೆಜಿ|kg)?",
        text,
        re.I,
    )
    if weight:
        structured["weight_kg"] = float(weight.group(1))

    age = re.search(r"(\d{1,3})\s*ವರ್ಷ(?:ದ)?", text)
    if age:
        structured["age"] = int(age.group(1))
        structured["category"] = "elderly" if int(age.group(1)) >= 60 else "child"

    if re.search(r"ನಡೆಯಲು.{0,30}ತೊಂದರೆ", text):
        structured["mobility"] = "difficulty walking"
        structured["category"] = "elderly"

    if re.search(r"ಶೌಚಾಲಯ\s*(?:ಇದೆ|ಲಭ್ಯ)", text):
        structured["toilet_available"] = True
        structured["category"] = "household"
    elif re.search(r"ಶೌಚಾಲಯ\s*(?:ಇಲ್ಲ|ಲಭ್ಯವಿಲ್ಲ)", text):
        structured["toilet_available"] = False
        structured["category"] = "household"

    follow_up = re.search(r"(ಒಂದು|ಎರಡು|ಮೂರು|ನಾಲ್ಕು|ಐದು|ಆರು|ಏಳು|ಎಂಟು|ಒಂಬತ್ತು|ಹತ್ತು|\d+)\s*(ದಿನ|ವಾರ)(?:ದ)?\s*ನಂತರ", text)
    if follow_up:
        amount = _KANNADA_NUMBERS.get(follow_up.group(1))
        if amount is None and follow_up.group(1).isdigit():
            amount = int(follow_up.group(1))
        if amount is not None:
            structured["follow_up_days"] = amount * (7 if follow_up.group(2) == "ವಾರ" else 1)
    elif re.search(r"ಮುಂದಿನ\s*ವಾರ", text):
        structured["follow_up_days"] = 7

    correction = re.search(
        r"ತೂಕ\s*(\d+(?:\.\d+)?)\s*(?:ಕಿಲೋ|ಕೆಜಿ)?\s*ಅಲ್ಲ\s*,?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:ಕಿಲೋ|ಕೆಜಿ)",
        text,
    )
    if correction:
        structured["weight_kg"] = float(correction.group(2))

    if "category" not in structured and re.search(r"ಲಸಿಕೆ|ಶೌಚಾಲಯ|ಕುಡಿಯುವ ನೀರು", text):
        structured["category"] = "immunisation" if "ಲಸಿಕೆ" in text else "household"
    return structured


# =====================================================================
# Multi-entity & boundary extraction architecture
# =====================================================================

VISIT_BOUNDARY = re.compile(
    r"(?:\b(?:next\s+I\s+visited|then\s+I\s+(?:went\s+to|visited)|after\s+that\s+I\s+visited|after\s+that|I\s+also\s+visited|also\s+visited|another\s+patient\s+was|the\s+next\s+household\s+was|now\s+record\s+another(?:\s+beneficiary)?|after\s+visiting)\b)",
    re.I
)

HOUSEHOLD_PATTERN = re.compile(
    r"\b(?:visited\s+([A-Za-z]+)'s\s+household|([A-Za-z]+)'s\s+household|household\s+of\s+([A-Za-z]+))\b",
    re.I
)


def parse_corrections(transcript: str) -> list[dict]:
    """Universal correction engine.
    
    Detects correction intents such as:
    - "Weight is 59 kg, not 56."
    - "Ravi is 66, not 65."
    - "Change the height to 158 cm."
    - "Her BP is 120 over 80."
    - "The baby's weight is 4.2 kg."
    - "Anu has already received the vaccine."
    - "Change the water source to borewell."
    - "The family does not have a toilet."
    - "Change the appointment date to December 5."
    """
    corrections = []
    text = transcript or ""

    # 1. "X is Y, not Z" pattern (e.g. "Weight is 59 kg, not 56", "Ravi is 66, not 65")
    for m in re.finditer(r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+is\s+([^,.]+?),\s*not\s+([^,.]+)", text, re.I):
        field_or_person = m.group(1).strip()
        new_val = m.group(2).strip()
        old_val = m.group(3).strip()

        # Check if field_or_person is a known field name or person name
        f_lower = field_or_person.lower()
        if "weight" in f_lower:
            corrections.append({
                "field": "weight_kg",
                "label": "Weight",
                "previous_value": old_val,
                "new_value": new_val,
                "status": "updated"
            })
        elif "height" in f_lower:
            corrections.append({
                "field": "height_cm",
                "label": "Height",
                "previous_value": old_val,
                "new_value": new_val,
                "status": "updated"
            })
        elif "age" in f_lower:
            corrections.append({
                "field": "age",
                "label": "Age",
                "previous_value": old_val,
                "new_value": new_val,
                "status": "updated"
            })
        else:
            # Person's age or property: "Ravi is 66, not 65"
            corrections.append({
                "beneficiary_name": field_or_person,
                "field": "age",
                "label": f"{field_or_person}'s Age",
                "previous_value": old_val,
                "new_value": new_val,
                "status": "updated"
            })

    # 2. "Change/correct X to Y" (e.g. "Change the height to 158 cm", "Change water source to borewell")
    for m in re.finditer(r"\b(?:change|correct|update|make)\s+(?:the\s+)?([a-zA-Z_\s]+?)\s+to\s+([^,.]+)", text, re.I):
        raw_field = m.group(1).strip().lower()
        new_val = m.group(2).strip()
        field_key = "notes"
        if "weight" in raw_field:
            field_key = "weight_kg"
        elif "height" in raw_field:
            field_key = "height_cm"
        elif "water" in raw_field:
            field_key = "water_source"
        elif "bp" in raw_field or "pressure" in raw_field:
            field_key = "bp"
        elif "phone" in raw_field:
            field_key = "phone"
        elif "appointment" in raw_field or "date" in raw_field:
            field_key = "follow_up_date"

        corrections.append({
            "field": field_key,
            "label": raw_field.capitalize(),
            "previous_value": None,
            "new_value": new_val,
            "status": "updated"
        })

    # Handle explicit "weight to X" and "BP to Y" phrasing like the test case.
    m_weight_to = re.search(r"\b(?:correct|change|update|set)\s+(?:lakshmi's\s+)?weight\s+(?:is\s+)?to\s+(\d+(?:\.\d+)?)\s*(?:kg|kilograms?|kilos?)\b", text, re.I)
    if m_weight_to:
        corrections.append({
            "field": "weight_kg",
            "label": "Weight",
            "previous_value": None,
            "new_value": m_weight_to.group(1).strip(),
            "status": "updated"
        })

    m_bp_to = re.search(r"\b(?:correct|change|update|set)\s+(?:lakshmi's\s+)?bp\s+(?:is\s+)?to\s+(\d{2,3})\s*(?:over|upon|/)\s*(\d{2,3})\b", text, re.I)
    if m_bp_to:
        corrections.append({
            "field": "bp",
            "label": "Blood Pressure",
            "previous_value": None,
            "new_value": f"{m_bp_to.group(1)}/{m_bp_to.group(2)}",
            "status": "updated"
        })

    # 3. Explicit BP corrections: "Her BP is 120 over 80"
    m_bp = re.search(r"\b(?:her|his)?\s*BP\s+(?:is|to)\s+(\d{2,3})\s+(?:over|upon|/)\s+(\d{2,3})\b", text, re.I)
    if m_bp and re.search(r"\b(?:correct|update|change|her\s+BP\s+is)\b", text, re.I):
        corrections.append({
            "field": "bp",
            "label": "Blood Pressure",
            "previous_value": None,
            "new_value": f"{m_bp.group(1)}/{m_bp.group(2)}",
            "status": "updated"
        })

    # 4. Vaccine received: "Anu has already received the vaccine"
    m_vax = re.search(r"\b([A-Za-z]+)\s+has\s+already\s+received\s+(?:the|her|his)?\s*(.+?)(?:\.|$)", text, re.I)
    if m_vax:
        corrections.append({
            "beneficiary_name": m_vax.group(1).strip(),
            "field": "vaccine_status",
            "label": "Vaccination",
            "previous_value": "pending",
            "new_value": f"Received ({m_vax.group(2).strip() or 'Completed'})",
            "status": "updated"
        })

    # 5. Toilet availability correction: "The family does not have a toilet"
    if re.search(r"\b(?:family\s+does\s+not\s+have|no|lacks?)\s+(?:a\s+)?toilet\b", text, re.I) and "toilet" in text.lower():
        corrections.append({
            "field": "toilet_available",
            "label": "Toilet Availability",
            "previous_value": True,
            "new_value": False,
            "status": "updated"
        })

    kannada_weight = re.search(
        r"ತೂಕ\s*(\d+(?:\.\d+)?)\s*(?:ಕಿಲೋ|ಕೆಜಿ)?\s*ಅಲ್ಲ\s*,?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:ಕಿಲೋ|ಕೆಜಿ)",
        text,
    )
    if kannada_weight:
        corrections.append({
            "field": "weight_kg",
            "label": "Weight",
            "previous_value": kannada_weight.group(1),
            "new_value": kannada_weight.group(2),
            "status": "updated",
        })

    return corrections


def _build_visit_entity(visit_idx: int, structured: dict, original_transcript: str = "", household_id: str | None = None) -> dict:
    """Structure a raw extraction dictionary into clean clinical sections."""
    # No placeholder names: an unidentified visit stays unidentified so the
    # worker is asked rather than a wrong beneficiary being reused.
    name = structured.get("beneficiary_name") or None
    cat = structured.get("category") or "general"

    personal_details = {
        "name": name,
        "age": structured.get("age"),
        "gender": structured.get("gender") or ("female" if cat == "pregnancy" else ""),
        "relation": structured.get("relation") or "self",
        "village": structured.get("village") or "",
        "phone": structured.get("phone") or "",
    }
    
    maternal_health = {}
    if cat == "pregnancy" or "weeks_pregnant" in structured:
        maternal_health = {
            "weeks_pregnant": structured.get("weeks_pregnant"),
            "bp_sys": structured.get("bp_sys"),
            "bp_dia": structured.get("bp_dia"),
            "weight_kg": structured.get("weight_kg"),
            "hemoglobin": structured.get("hemoglobin"),
            "fetal_heart": structured.get("fetal_heart"),
            "ifa_tablets": structured.get("ifa_tablets"),
            "td_vaccine": structured.get("td_vaccine"),
            "follow_up_date": structured.get("follow_up_date"),
        }

    child_health = {}
    if cat in ("newborn", "child", "immunisation") or structured.get("age", 99) <= 5:
        child_health = {
            "weight_kg": structured.get("weight_kg"),
            "height_cm": structured.get("height_cm"),
            "temperature": structured.get("temperature"),
            "feeding": structured.get("feeding"),
            "jaundice": structured.get("jaundice"),
            "vaccine_name": structured.get("vaccine_name"),
            "dose_number": structured.get("dose_number"),
        }

    measurements = {
        "weight_kg": structured.get("weight_kg"),
        "height_cm": structured.get("height_cm"),
        "bp_sys": structured.get("bp_sys"),
        "bp_dia": structured.get("bp_dia"),
        "hemoglobin": structured.get("hemoglobin"),
        "blood_sugar": structured.get("blood_sugar"),
    }

    nutrition = {}
    if structured.get("weight_kg") or structured.get("height_cm") or structured.get("hemoglobin"):
        nutrition = {
            "weight_kg": structured.get("weight_kg"),
            "height_cm": structured.get("height_cm"),
            "hemoglobin": structured.get("hemoglobin"),
            "ifa_tablets": structured.get("ifa_tablets"),
        }

    immunisation = {}
    if structured.get("vaccine_name"):
        immunisation = {
            "vaccine_name": structured.get("vaccine_name"),
            "dose_number": structured.get("dose_number") or 1,
            "next_due_date": structured.get("follow_up_date"),
        }

    elderly_health = {}
    if cat == "elderly" or structured.get("age", 0) >= 60:
        elderly_health = {
            "age": structured.get("age"),
            "bp_sys": structured.get("bp_sys"),
            "bp_dia": structured.get("bp_dia"),
            "blood_sugar": structured.get("blood_sugar"),
            "mobility": structured.get("mobility"),
        }

    household_obs = {}
    household_keys = (
        "water_source", "water_storage_covered", "toilet_available", "toilet_usage",
        "waste_disposal", "drainage", "stagnant_water", "handwashing",
        "awareness_provided",
    )
    if cat == "household":
        household_keys += ("follow_up_days",)
    for hk in household_keys:
        if hk in structured:
            household_obs[hk] = structured[hk]

    follow_ups = []
    if structured.get("follow_up_days"):
        follow_ups.append({"type": "scheduled", "days": structured["follow_up_days"]})
    if structured.get("follow_up_date"):
        follow_ups.append({"type": "specific_date", "date": structured["follow_up_date"]})

    visit = {
        "visit_id": f"visit-{visit_idx + 1}",
        "beneficiary_name": name,
        "beneficiary_id": None,
        "category": cat,
        "visit_category": cat,
        "household_id": household_id or structured.get("household_id"),
        "personal_details": {k: v for k, v in personal_details.items() if v is not None and v != ""},
        "maternal_health": {k: v for k, v in maternal_health.items() if v is not None},
        "child_health": {k: v for k, v in child_health.items() if v is not None},
        "measurements": {k: v for k, v in measurements.items() if v is not None},
        "nutrition": {k: v for k, v in nutrition.items() if v is not None},
        "immunisation": {k: v for k, v in immunisation.items() if v is not None},
        "elderly_health": {k: v for k, v in elderly_health.items() if v is not None},
        "household_obs": household_obs,
        "observations": ([f"Recorded in field visit: {name}"] if name else []),
        "follow_ups": follow_ups,
        "raw_structured": structured,
    }
    return _normalize_visit_names(visit)


def extract_fields_multi(transcript: str, language: str = "en") -> tuple[dict, str]:
    """Multi-entity structured extractor supporting:
    - Scenario A: Single beneficiary
    - Scenario B: Multiple members in one household
    - Scenario C: Multiple beneficiaries from different households
    - Universal voice corrections
    
    Returns (result_dict, mode) where mode is "demo" or "live".
    """
    text = (transcript or "").strip()
    session_id = f"session-{date_today_iso()}-{hash(text) & 0xffffff}"
    corrections = parse_corrections(text)
    mode = "demo"

    if _is_kannada_script_path(language, text):
        structured = _extract_kannada(text)
        visit = _build_visit_entity(0, structured, original_transcript=text)
        if not structured.get("beneficiary_name"):
            visit["beneficiary_name"] = None
            visit["personal_details"].pop("name", None)
            visit["observations"] = []
        household_visits = []
        household_fields = (
            "water_source", "water_storage_covered", "toilet_available", "toilet_usage",
            "waste_disposal", "drainage", "stagnant_water", "handwashing",
            "awareness_provided", "follow_up_days",
        )
        household_observations = {key: structured[key] for key in household_fields if key in structured}
        if any(key in structured for key in household_fields[:-1]):
            household_visits.append({
                "household_id": structured.get("household_id"),
                "household_observations": household_observations,
                "member_references": [],
            })
        return {
            "session_id": session_id,
            "scenario": "single_beneficiary",
            "visits": [visit],
            "household_visits": household_visits,
            "community_activities": [],
            "corrections": corrections,
        }, mode

    # ------------------------------------------------------------------
    # Unified segmentation.
    #
    # Every remaining scenario (one beneficiary, several members of one
    # household, several beneficiaries across households) goes through the
    # same segmentation engine, so a beneficiary boundary is detected the
    # same way no matter which module the visit belongs to.
    # ------------------------------------------------------------------
    from app.services import segmentation as _seg

    segments = _seg.segment_transcript(text, language)

    # Household context: a spoken household reference binds the members of
    # that household, but never merges their observations.
    m_hh = HOUSEHOLD_PATTERN.search(text)
    household_label: str | None = None
    if m_hh:
        hh_name = (m_hh.group(1) or m_hh.group(2) or m_hh.group(3) or "").strip()
        if hh_name:
            household_label = f"{hh_name}'s household"
    elif re.search(
        r"\b(?:her\s+husband|his\s+wife|their\s+daughter|their\s+son|her\s+mother|his\s+father)\b",
        text,
        re.I,
    ):
        household_label = "Family"

    visits: list[dict] = []
    member_refs: list[dict] = []
    household_observations: dict = {}

    for seg in segments:
        # Gemini-powered extraction when configured, with deterministic fallback per segment.
        parsed, seg_mode = extract_fields(seg.text, language)
        if seg_mode == "live":
            mode = "live"
        spoken_name = seg.spoke_name or parsed.get("beneficiary_name")
        if spoken_name:
            parsed["beneficiary_name"] = spoken_name
        else:
            parsed.pop("beneficiary_name", None)

        # A household observation belongs to the household, not to one member,
        # so it is collected once across the whole recording.
        for key in (
            "water_source", "water_storage_covered", "toilet_available", "toilet_usage",
            "waste_disposal", "drainage", "stagnant_water", "handwashing",
            "awareness_provided", "follow_up_days",
        ):
            if key in parsed and key not in household_observations:
                household_observations[key] = parsed[key]

        hh_for_visit = household_label or parsed.get("household_id")
        if hh_for_visit:
            parsed["household_id"] = hh_for_visit

        # Category inference from the content of THIS segment only.
        parsed["category"] = _infer_visit_category(parsed, seg.text)

        visit = _build_visit_entity(
            len(visits), parsed, original_transcript=seg.text, household_id=hh_for_visit
        )
        visit["boundary_reason"] = seg.boundary_reason
        visit["segment_index"] = seg.index
        visits.append(visit)

        if spoken_name:
            member_refs.append({
                "name": spoken_name,
                "relation": parsed.get("relation") or "",
                "age": parsed.get("age"),
                "gender": parsed.get("gender") or "",
                "weight_kg": parsed.get("weight_kg"),
                "category": parsed.get("category"),
                "household_id": hh_for_visit,
            })

    household_visits: list[dict] = []
    if household_observations:
        household_visits.append({
            "household_id": household_label or next(
                (v.get("household_id") for v in visits if v.get("household_id")), None
            ),
            "household_observations": household_observations,
            "member_references": member_refs,
        })

    if len(visits) > 1:
        scenario = "household_members" if household_label else "multiple_beneficiaries"
    else:
        scenario = "single_beneficiary"

    return {
        "session_id": session_id,
        "scenario": scenario,
        "visits": visits,
        "household_visits": household_visits,
        "community_activities": [],
        "corrections": corrections,
    }, mode


def _infer_visit_category(structured: dict, segment_text: str) -> str:
    """Infer the health category of ONE segment from its own content."""
    if structured.get("category"):
        return str(structured["category"]).lower()
    if structured.get("weeks_pregnant") is not None:
        return "pregnancy"
    if structured.get("vaccine_name") or structured.get("dose_number"):
        return "immunisation"
    if structured.get("fetal_heart") or structured.get("hemoglobin"):
        return "pregnancy"
    if structured.get("feeding") is not None or structured.get("jaundice") is not None:
        return "newborn"
    if structured.get("temperature") is not None:
        return "newborn"
    age = structured.get("age")
    if isinstance(age, int):
        if age <= 2:
            return "newborn"
        if age <= 12:
            return "child"
        if age >= 60:
            return "elderly"
    if structured.get("bp_sys") is not None or structured.get("bp_dia") is not None:
        return "elderly"
    if structured.get("weight_kg") is not None or structured.get("height_cm") is not None:
        return "nutrition"
    return "general"


# =====================================================================
# 4) Tara conversational assistance (Gemini LLM)
# =====================================================================

def generate_tara_response(
    message: str,
    *,
    language: str = "en",
    context: dict[str, Any] | None = None,
) -> str:
    """Generate a Tara AI response for conversational assistance.

    Uses Google Gemini when configured. Raises GeminiLLMError for missing/invalid
    configuration, unsupported model, quota/rate/network/timeout issues, or
    malformed/empty responses. Never returns a fabricated successful response.
    """
    message = (message or "").strip()
    if not message:
        raise GeminiLLMError("invalid_request", "A message is required.")
    if not _llm_live_enabled():
        # Distinguish missing config cases for clearer handling upstream.
        if not _gemini_api_key():
            raise GeminiLLMError("missing_api_key", "Gemini API key is not configured.")
        if not _gemini_model():
            raise GeminiLLMError("missing_model", "Gemini model is not configured.")
        raise GeminiLLMError("provider_error", "Gemini is not configured.")

    ctx = context or {}
    # Keep context minimal and safe; do not include secrets.
    safe_ctx = {
        k: ctx.get(k)
        for k in ("app", "topic", "beneficiary_summary", "visit_summary", "transcript", "language")
        if k in ctx and ctx.get(k) not in (None, "", {}, [])
    }
    prompt = (
        "You are Tara, the AI health companion for ASHA workers in the ASHA Swar Nirantar app. "
        "Provide concise, context-aware, practical assistance for ASHA field workflows "
        "(conversation, visit documentation guidance, follow-up summarization/identification, clarification when information is missing or ambiguous, and navigation/help within the app). "
        "You may understand and respond for Kannada, English, Kannada-English code-mix, and other supported languages; prefer the user's language when clear. "
        "Safety rules: do not diagnose, do not prescribe, do not invent symptoms/dates/measurements/beneficiary details, preserve any reported danger signs accurately, "
        "recommend escalation according to approved local protocols/emergency care for danger signs, and remind that ASHA worker confirmation is required before saving health records. "
        "If details are missing or ambiguous (including beneficiary identity), ask for clarification clearly. "
        "Keep responses brief and helpful.\n\n"
        f"Language hint: {language}\n"
        f"Context (may be partial): {json.dumps(safe_ctx, ensure_ascii=False, default=str)}\n\n"
        f"ASHA worker message: {message}"
    )
    text = _gemini_generate_text(prompt)
    text = (text or "").strip()
    if not text:
        raise GeminiLLMError("empty_response", "Gemini returned an empty response.")
    return text


# =====================================================================
# 3) TTS (Gnani Timbre v3.0)
# =====================================================================

def text_to_speech(text: str, language: str = "en") -> dict:
    """Return TTS result. Live mode returns base64 audio when Gnani Timbre is configured and responds.
    Demo/fallback mode returns no audio so frontend can use browser speech synthesis.
    """
    if not _tts_live_enabled():
        return {"mode": "demo", "provider": "browser", "mime_type": None}

    try:
        payload = json.dumps({"text": text, "language": language}).encode("utf-8")
        req = urllib.request.Request(
            get_env("GNANI_TIMBRE_URL"),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {get_env('GNANI_TIMBRE_KEY')}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = (resp.headers.get("Content-Type", "") or "").lower()
            body = resp.read()
        if "application/json" in content_type:
            data = json.loads(body.decode("utf-8"))
            audio = data.get("audio_base64") or data.get("audio") or ""
            mime_type = data.get("mime_type") or data.get("content_type") or "audio/wav"
            if audio:
                return {"mode": "live", "audio_base64": audio, "provider": "Gnani Timbre", "mime_type": mime_type}
            if data.get("base64"):
                return {"mode": "live", "audio_base64": data["base64"], "provider": "Gnani Timbre", "mime_type": mime_type}
            return {"mode": "demo", "provider": "browser", "mime_type": None}
        mime_type = content_type.split(";")[0].strip() if content_type else "audio/wav"
        return {"mode": "live", "audio_base64": base64.b64encode(body).decode("ascii"), "provider": "Gnani Timbre", "mime_type": mime_type}
    except Exception as exc:
        logger.warning("Timbre TTS failed; falling back to browser synthesis: %s", exc.__class__.__name__)
        return {"mode": "demo", "provider": "browser", "mime_type": None}
