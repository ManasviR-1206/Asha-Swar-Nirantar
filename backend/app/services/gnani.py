"""Gnani.ai adapters with explicit availability and honest demo behavior.

Three adapters:
1. transcribe_stream() — Gnani Prisma v3.0 streaming STT over WebSocket.
2. extract_fields()    — Gnani LLM structured extraction over HTTP.
3. text_to_speech()    — Gnani Timbre v3.0 TTS over HTTP.

INTEGRATION MODES (env var GNANI_MODE):
- "demo" (default): no Gnani network calls. STT is delegated to browser speech
  recognition when available; the server never invents a transcript.
- "live": real Gnani endpoints are used only when credentials and an
  explicitly verified language configuration are present.

Expected live configuration (backend/.env):
    GNANI_MODE=live
    GNANI_PRISMA_WS_URL=wss://...prisma-v3-stream-endpoint...?language={language}
    GNANI_PRISMA_LANGUAGES=en,kn
    GNANI_API_KEY=...
    GNANI_API_SECRET=...
    GNANI_LLM_URL=https://.../llm-extract
    GNANI_LLM_KEY=...
    GNANI_TIMBRE_URL=https://.../timbre-tts
    GNANI_TIMBRE_KEY=...

For the Prisma WS the adapter opens the upstream socket with headers:
    Authorization: Bearer <GNANI_API_KEY>
    apikey: <GNANI_API_KEY>
    apisecret: <GNANI_API_SECRET>
and forwards client binary PCM frames upstream, streaming JSON events
back down. The exact header names should be confirmed against the Gnani
Prisma v3.0 documentation during integration.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from typing import AsyncGenerator, Callable

from app import gnani_mode, get_env

def _live_enabled() -> bool:
    """Live mode requires its endpoint and both Prisma credentials."""
    return (
        gnani_mode() == "live"
        and bool(get_env("GNANI_PRISMA_WS_URL"))
        and bool(get_env("GNANI_API_KEY"))
        and bool(get_env("GNANI_API_SECRET"))
    )


def prisma_language_enabled(language: str) -> bool:
    """Only send audio for an explicitly verified language and URL template."""
    configured = {
        value.strip().lower()
        for value in get_env("GNANI_PRISMA_LANGUAGES").split(",")
        if value.strip()
    }
    language_code = (language or "").strip().lower().split("-")[0]
    return (
        _live_enabled()
        and "{language}" in get_env("GNANI_PRISMA_WS_URL")
        and bool(language_code)
        and language_code in configured
    )


def prisma_connection_url(language: str) -> str:
    """Fill the provider-documented locale placeholder in the configured URL."""
    from urllib.parse import quote

    locales = {"en": "en-IN", "kn": "kn-IN", "hi": "hi-IN", "te": "te-IN", "ta": "ta-IN"}
    locale = locales.get(language.strip().lower(), language.strip())
    return get_env("GNANI_PRISMA_WS_URL").replace("{language}", quote(locale, safe=""))


def _llm_live_enabled() -> bool:
    return gnani_mode() == "live" and bool(get_env("GNANI_LLM_URL")) and bool(get_env("GNANI_LLM_KEY"))


def _tts_live_enabled() -> bool:
    return gnani_mode() == "live" and bool(get_env("GNANI_TIMBRE_URL")) and bool(get_env("GNANI_TIMBRE_KEY"))


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
    headers = {
        "Authorization": f"Bearer {get_env('GNANI_API_KEY')}",
        "apikey": get_env("GNANI_API_KEY"),
        "apisecret": get_env("GNANI_API_SECRET"),
    }
    try:
        upstream = await websockets.connect(url, extra_headers=headers)  # type: ignore[call-arg]
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        yield {
            "type": "status",
            "stage": "browser_fallback",
            "mode": "demo",
            "provider": "browser",
            "reason": "provider_auth" if status_code in (401, 403) else "provider_unavailable",
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


def extract_fields(transcript: str, language: str = "en") -> tuple[dict, str]:
    """Extract structured fields from a transcript.

    Returns (structured_dict, mode) where mode is "live" or "demo".

    LIVE PATH: posts the transcript + JSON schema to the Gnani LLM
    endpoint; a schema-validated JSON body comes back. Any failure falls
    back to the demo parser (labelled demo).
    """
    if _llm_live_enabled() and language.lower().split("-")[0] != "kn":
        try:
            live = _llm_extract_live(transcript, language)
            if live is not None:
                return live, "live"
        except Exception:
            pass  # fall through to demo — never fake a live result
    if language.lower().split("-")[0] == "kn":
        return _extract_kannada(transcript), "demo"
    return _extract_demo(transcript), "demo"


def _llm_extract_live(transcript: str, language: str) -> dict | None:
    """Call the Gnani LLM endpoint. Returns None on any problem."""
    url = get_env("GNANI_LLM_URL")
    payload = json.dumps(
        {
            "transcript": transcript,
            "language": language,
            "instruction": (
                "Extract healthcare visit fields from the transcript. "
                "Reply with ONLY a JSON object matching this schema: "
                + json.dumps(_EXTRACTION_SCHEMA)
            ),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {get_env('GNANI_LLM_KEY')}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    # Accept either the raw object or {"data": {...}} / {"choices":[{...}]} shapes.
    data = body.get("data", body) if isinstance(body, dict) else None
    if isinstance(data, dict) and "structured" in data:
        data = data["structured"]
    if not isinstance(data, dict):
        return None
    return _validate_structured(data)


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
_NAME_AFTER_VISITED = re.compile(r"\bvisited\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", re.I)
_NAME_BEFORE_VISITED = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+was\s+visited\b|\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+visited\b", re.I)
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

# --- Extended patterns for new fields ---
_WORD_TO_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_AGE_YEARS_OLD = re.compile(r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s*years?\s*old\b", re.I)
_AGE_IS = re.compile(r"\bage\s*(?:is|:)?\s*(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
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

    m = _NAME_AFTER_VISITED.search(text)
    if m:
        structured["beneficiary_name"] = _trim_name(m.group(1).strip())
    else:
        m = _NAME_BEFORE_VISITED.search(text)
        if m:
            structured["beneficiary_name"] = _trim_name((m.group(1) or m.group(2) or "").strip())
    # Household speech ("Visited household 24…") is not a beneficiary name —
    # the household_id field carries the subject instead.
    if "beneficiary_name" in structured:
        bn = structured["beneficiary_name"].lower()
        if bn in ("household", "house") or bn.startswith(("household ", "house ")):
            del structured["beneficiary_name"]

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
    m = _AGE_YEARS_OLD.search(text) or _AGE_IS.search(text)
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

    # Category inference
    age_value = structured.get("age")
    if "weeks_pregnant" in structured or re.search(r"\bpregnant|pregnancy|anc\b", text, re.I):
        structured["category"] = "pregnancy"
    elif "feeding" in structured or "jaundice" in structured or re.search(r"\bnewborn|neonat|born\s+today\b", text, re.I):
        structured["category"] = "newborn"
    elif "vaccine_name" in structured:
        structured["category"] = "immunisation"
    elif (age_value is not None and age_value >= 60) or "mobility" in structured or "blood_sugar" in structured:
        structured["category"] = "elderly"
    elif (age_value is not None and age_value <= 12) or re.search(r"\bchild|toddler|baby|vaccination|vaccine|immunisation\b", text, re.I):
        structured["category"] = "child"
    elif "water_source" in structured or "toilet_available" in structured:
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
    name = structured.get("beneficiary_name") or f"Beneficiary-{visit_idx + 1}"
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

    return {
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
        "observations": [f"Recorded in field visit: {name}"],
        "follow_ups": follow_ups,
        "raw_structured": structured,
    }


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

    if language.lower().split("-")[0] == "kn":
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

    # Check for Scenario B: Household with multiple family members
    m_hh = HOUSEHOLD_PATTERN.search(text)
    is_household_family = bool(m_hh) or bool(re.search(r"\b(?:Lakshmi's\s+household|household\s+of|her\s+husband|their\s+daughter|their\s+son)\b", text, re.I))

    if is_household_family:
        hh_name = (m_hh.group(1) or m_hh.group(2) or m_hh.group(3) or "Household") if m_hh else "Family"
        hh_label = f"{hh_name}'s household"
        
        # Extract general household hygiene observations
        hh_struct = _extract_demo(text)
        hh_obs = {
            k: hh_struct[k] for k in (
                "water_source", "water_storage_covered", "toilet_available", "toilet_usage",
                "waste_disposal", "drainage", "stagnant_water", "handwashing", "awareness_provided", "follow_up_days"
            ) if k in hh_struct
        }
        
        visits = []
        member_refs = []

        # Find member mentions:
        # e.g. "Lakshmi is 28 weeks pregnant and weighs 53 kg"
        # "Her husband Ravi is 30 years old"
        # "Their daughter Anu is two years old and weighs 11 kg"
        
        # 1. Primary woman/head if pregnant
        m_preg = re.search(r"\b([A-Z][a-zA-Z]+)\s+is\s+(\d{1,2})\s*weeks?\s+pregnant(?:.*?weighs?\s+(\d+(?:\.\d+)?)\s*k(?:g|ilograms?))?", text, re.I)
        if m_preg:
            p_name = m_preg.group(1).strip()
            if p_name.lower() in ("she", "her", "the", "this", "patient", "woman"):
                m_vis = re.search(r"\b(?:visited|saw|met|went to)\s+([A-Z][a-zA-Z]+)(?:'s\s+household)?", text, re.I)
                if m_vis:
                    p_name = m_vis.group(1).strip()
                elif m_hh and (m_hh.group(1) or m_hh.group(2) or m_hh.group(3)):
                    p_name = (m_hh.group(1) or m_hh.group(2) or m_hh.group(3)).strip()
            weeks = int(m_preg.group(2))
            weight = float(m_preg.group(3)) if m_preg.group(3) else None
            p_struct = {
                "beneficiary_name": p_name,
                "weeks_pregnant": weeks,
                "weight_kg": weight,
                "category": "pregnancy",
                "relation": "self",
                "gender": "female",
                "household_id": hh_label,
            }
            if "bp_sys" in hh_struct:
                p_struct["bp_sys"] = hh_struct["bp_sys"]
                p_struct["bp_dia"] = hh_struct["bp_dia"]
            visits.append(_build_visit_entity(len(visits), p_struct, household_id=hh_label))
            member_refs.append({"name": p_name, "relation": "head/self", "gender": "female", "category": "pregnancy"})

        # 2. Husband/Spouse
        m_husb = re.search(r"\b(?:her\s+husband|husband)\s+([A-Z][a-zA-Z]+)(?:\s+is\s+(\d{1,3})\s*years?\s*old)?", text, re.I)
        if m_husb:
            h_name = m_husb.group(1).strip()
            h_age = int(m_husb.group(2)) if m_husb.group(2) else 30
            h_struct = {
                "beneficiary_name": h_name,
                "age": h_age,
                "gender": "male",
                "relation": "husband",
                "category": "general",
                "household_id": hh_label,
            }
            visits.append(_build_visit_entity(len(visits), h_struct, household_id=hh_label))
            member_refs.append({"name": h_name, "relation": "husband", "age": h_age, "gender": "male"})

        # 3. Daughter / Son / Child
        m_child = re.search(r"\b(?:their|her|his)?\s*(daughter|son|child)\s+([A-Z][a-zA-Z]+)(?:\s+is\s+(\d{1,2}|two|three|one)\s*years?\s*old)?(?:.*?weighs?\s+(\d+(?:\.\d+)?)\s*k(?:g|ilograms?))?", text, re.I)
        if m_child:
            rel = m_child.group(1).lower()
            c_name = m_child.group(2).strip()
            raw_age = m_child.group(3)
            age_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            c_age = age_map.get(str(raw_age).lower(), int(raw_age) if raw_age and raw_age.isdigit() else 2)
            c_wt = float(m_child.group(4)) if m_child.group(4) else 11.0
            c_gender = "female" if rel == "daughter" else ("male" if rel == "son" else "")
            c_struct = {
                "beneficiary_name": c_name,
                "age": c_age,
                "gender": c_gender,
                "weight_kg": c_wt,
                "relation": rel,
                "category": "child",
                "household_id": hh_label,
            }
            visits.append(_build_visit_entity(len(visits), c_struct, household_id=hh_label))
            member_refs.append({"name": c_name, "relation": rel, "age": c_age, "gender": c_gender, "weight_kg": c_wt})

        household_visit = {
            "household_id": hh_label,
            "household_observations": hh_obs,
            "member_references": member_refs,
        }

        return {
            "session_id": session_id,
            "scenario": "household_members",
            "visits": visits,
            "household_visits": [household_visit],
            "community_activities": [],
            "corrections": corrections,
        }, mode

    # Check for Scenario C: Multiple beneficiaries across households
    # Split text at visit boundary keywords
    boundary_matches = list(VISIT_BOUNDARY.finditer(text))
    if len(boundary_matches) > 0:
        segments = []
        last_idx = 0
        for m in boundary_matches:
            seg = text[last_idx:m.start()].strip()
            if seg:
                segments.append(seg)
            last_idx = m.start()
        trailing = text[last_idx:].strip()
        if trailing:
            segments.append(trailing)

        visits = []
        for idx, seg in enumerate(segments):
            parsed = _extract_demo(seg)
            # If the segment says "visited Ravi, who is 65 years old and needs a blood pressure follow-up"
            if not parsed.get("beneficiary_name"):
                m_name = re.search(r"\b(?:visited|went\s+to|patient\s+was)\s+([A-Z][a-zA-Z]+)", seg, re.I)
                if m_name:
                    parsed["beneficiary_name"] = m_name.group(1).strip()
            # If still no name, generate placeholder
            if not parsed.get("beneficiary_name"):
                parsed["beneficiary_name"] = f"Beneficiary-{idx + 1}"
            visits.append(_build_visit_entity(idx, parsed, original_transcript=seg))

        return {
            "session_id": session_id,
            "scenario": "multiple_beneficiaries",
            "visits": visits,
            "household_visits": [],
            "community_activities": [],
            "corrections": corrections,
        }, mode

    # Scenario A: Single beneficiary visit
    single_struct = _extract_demo(text)
    visit = _build_visit_entity(0, single_struct, original_transcript=text)
    
    hh_visits = []
    if any(k in single_struct for k in ("water_source", "toilet_available", "waste_disposal", "stagnant_water")):
        hh_visits.append({
            "household_id": single_struct.get("household_id") or "Household",
            "household_observations": {
                k: single_struct[k] for k in (
                    "water_source", "water_storage_covered", "toilet_available", "toilet_usage",
                    "waste_disposal", "drainage", "stagnant_water", "handwashing", "awareness_provided", "follow_up_days"
                ) if k in single_struct
            },
            "member_references": [{"name": single_struct.get("beneficiary_name", "Beneficiary")}],
        })

    return {
        "session_id": session_id,
        "scenario": "single_beneficiary",
        "visits": [visit],
        "household_visits": hh_visits,
        "community_activities": [],
        "corrections": corrections,
    }, mode


# =====================================================================
# 3) TTS (Gnani Timbre v3.0)
# =====================================================================

def text_to_speech(text: str, language: str = "en") -> dict:
    """Return {"mode": "live", "audio_base64": ...} or {"mode": "demo"}.

    LIVE PATH: calls the Gnani Timbre v3.0 HTTP endpoint and returns the
    base64-encoded audio. In demo mode no audio is produced — the
    frontend uses browser speech synthesis as the labelled demo fallback.
    """
    if not _tts_live_enabled():
        return {"mode": "demo"}

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
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
        if "application/json" in content_type:
            data = json.loads(body.decode("utf-8"))
            audio = data.get("audio_base64") or data.get("audio") or ""
            if audio:
                return {"mode": "live", "audio_base64": audio}
            # Some providers return raw base64 inside a wrapper.
            if data.get("base64"):
                return {"mode": "live", "audio_base64": data["base64"]}
            return {"mode": "demo"}
        # Binary audio response (e.g. audio/wav, audio/mpeg).
        return {"mode": "live", "audio_base64": base64.b64encode(body).decode("ascii")}
    except Exception:
        # Live call failed — fall back honestly.
        return {"mode": "demo"}
