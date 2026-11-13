import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.gnani import (
    extract_fields,
    extract_fields_multi,
    parse_corrections,
    prisma_language_enabled,
    transcribe_stream,
)


def test_kannada_examples():
    maternal = extract_fields(
        "ಲಕ್ಷ್ಮಿ ಅವರಿಗೆ 24 ವಾರಗಳ ಗರ್ಭಧಾರಣೆ ಇದೆ. ಮುಂದಿನ ANC ಭೇಟಿ ಮುಂದಿನ ವಾರ ಇದೆ.",
        "kn",
    )[0]
    assert maternal["beneficiary_name"] == "ಲಕ್ಷ್ಮಿ"
    assert maternal["weeks_pregnant"] == 24
    assert maternal["follow_up_days"] == 7

    measurements = extract_fields("ತೂಕ 53 ಕಿಲೋ. ರಕ್ತದೊತ್ತಡ 120 ಮೇಲೆ 80.", "kn")[0]
    assert measurements["weight_kg"] == 53.0
    assert (measurements["bp_sys"], measurements["bp_dia"]) == (120, 80)

    elderly = extract_fields(
        "ರವಿ ಅವರಿಗೆ 66 ವರ್ಷ. ಅವರಿಗೆ ನಡೆಯಲು ಸ್ವಲ್ಪ ತೊಂದರೆ ಇದೆ.",
        "kn",
    )[0]
    assert elderly["beneficiary_name"] == "ರವಿ"
    assert elderly["age"] == 66
    assert elderly["mobility"] == "difficulty walking"

    vaccine = extract_fields("ಅನುವಿಗೆ ಮುಂದಿನ ಲಸಿಕೆ ದಿನಾಂಕ ಹದಿನೈದು ನವೆಂಬರ್.", "kn")[0]
    assert vaccine["beneficiary_name"] == "ಅನು"
    assert "follow_up_date" not in vaccine

    household = extract_fields(
        "ಈ ಮನೆಯಲ್ಲಿ ಶೌಚಾಲಯ ಇದೆ. ಕುಡಿಯುವ ನೀರನ್ನು ಟ್ಯಾಂಕ್‌ನಲ್ಲಿ ಸಂಗ್ರಹಿಸುತ್ತಾರೆ.",
        "kn",
    )[0]
    assert household["toilet_available"] is True
    assert "water_source" not in household
    assert "water_storage_covered" not in household

    correction_text = "ಇಲ್ಲ, ತೂಕ 53 ಅಲ್ಲ, 55 ಕಿಲೋ."
    correction = extract_fields(correction_text, "kn")[0]
    assert correction["weight_kg"] == 55.0
    assert parse_corrections(correction_text)[0]["previous_value"] == "53"

    multi = extract_fields_multi(
        "ಲಕ್ಷ್ಮಿ ಅವರಿಗೆ 24 ವಾರಗಳ ಗರ್ಭಧಾರಣೆ ಇದೆ.",
        "kn",
    )[0]
    assert multi["visits"][0]["raw_structured"]["weeks_pregnant"] == 24


def test_prisma_language_requires_verified_template():
    values = {
        "GNANI_MODE": "live",
        "GNANI_PRISMA_WS_URL": "wss://example.test/stream?language={language}",
        "GNANI_PRISMA_LANGUAGES": "en,kn",
        "GNANI_API_KEY": "configured-for-test",
        "GNANI_API_SECRET": "test-placeholder",
    }
    with patch.dict("os.environ", values):
        assert prisma_language_enabled("kn")
        assert not prisma_language_enabled("ta")
    with patch.dict("os.environ", {**values, "GNANI_PRISMA_WS_URL": "wss://example.test/stream"}):
        assert not prisma_language_enabled("kn")


def test_demo_transcription_never_fabricates_text():
    async def receive():
        yield "bytes", b"\x01\x00" * 32000
        yield "text", '{"type":"finalize"}'

    async def collect():
        return [event async for event in transcribe_stream("en", receive)]

    values = {
        "GNANI_MODE": "demo",
        "GNANI_PRISMA_WS_URL": "",
        "GNANI_PRISMA_LANGUAGES": "",
        "GNANI_API_KEY": "",
        "GNANI_API_SECRET": "",
    }
    with patch.dict("os.environ", values):
        events = asyncio.run(collect())
    assert events == [{
        "type": "status",
        "stage": "browser_fallback",
        "mode": "demo",
        "provider": "browser",
        "reason": "integration_not_configured",
    }]


if __name__ == "__main__":
    test_kannada_examples()
    test_prisma_language_requires_verified_template()
    test_demo_transcription_never_fabricates_text()
    print("Kannada voice extraction tests passed.")
