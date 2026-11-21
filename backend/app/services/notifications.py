"""Healthcare notifications: SMS (TextBee / legacy provider / demo).

Delivery modes (always visible in UI/history):
* **demo**  — no SMS provider is configured/enabled. The message is generated and stored as
  ``DEMO – NOT ACTUALLY SENT``. Nothing is claimed as delivered.
* **live**  — a provider is configured and reached. ``submitted`` means the provider accepted the
  message; ``delivered`` is only used when a provider explicitly reports delivery; ``failed`` when
  an error is reported. Nothing is claimed beyond what the provider confirmed.

SMS is sent from the backend only. API keys/credentials and full sensitive message contents are
never logged. SMS content is kept generic and privacy-preserving (no diagnoses, test results, or
confidential beneficiary details).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app import get_env
from app.models import Beneficiary, ConsentRecord, SmsNotification
from app.services.textbee import (
    normalize_indian_phone_to_e164,
    send_sms_via_textbee,
    sms_compliance_approved,
    textbee_active,
    textbee_configured,
    textbee_enabled,
)

logger = logging.getLogger(__name__)

DEMO_LABEL = "DEMO – NOT ACTUALLY SENT"

# Generic, privacy-preserving templates. No diagnoses, test results, or confidential details.
# Keys are event/message types used by the app; values are per-language bodies.
SMS_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "appointment": "Reminder: You have an upcoming health appointment. Please contact your ASHA worker for assistance.",
        "follow_up": "This is a reminder for your scheduled health follow-up. Please contact your ASHA worker.",
        "medication": "Reminder: Please follow your care plan as advised. Contact your ASHA worker if you need help.",
        "care_plan": "Reminder: Please follow your care plan as advised. Contact your ASHA worker if you need help.",
        "important_alert": "You have an important health-related notification. Please contact your ASHA worker for more information.",
        "asha_notification": "You have an important health-related notification. Please contact your ASHA worker for more information.",
        "beneficiary_reminder": "This is a reminder from your ASHA worker. Please contact your ASHA worker for assistance.",
        # Existing/domain types
        "anc": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
        "vaccination": "Reminder: A community health visit is scheduled. Please coordinate with your local ASHA worker.",
        "newborn": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
        "nutrition": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
        "community": "Reminder: A community health visit is scheduled. Please coordinate with your local ASHA worker.",
        "household": "Reminder: Your scheduled health visit is approaching. Please contact your ASHA worker.",
        "general": "This is a reminder from your ASHA worker. Please contact your ASHA worker for assistance.",
    },
    "kn": {
        "appointment": "ಜ್ಞಾಪನೆ: ನಿಮ್ಮ ಮುಂದಿನ ಆರೋಗ್ಯ ನೇಮಕಾತಿ ಇದೆ. ಸಹಾಯಕ್ಕಾಗಿ ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "follow_up": "ಇದು ನಿಮ್ಮ ನಿಗದಿತ ಆರೋಗ್ಯ ಅನುಸರಣೆ ಭೇಟಿಗಾಗಿ ಜ್ಞಾಪನೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "medication": "ಜ್ಞಾಪನೆ: ಸಲಹೆ ನೀಡಿದಂತೆ ನಿಮ್ಮ ಆರೈಕೆ ಯೋಜನೆಯನ್ನು ಅನುಸರಿಸಿ. ಸಹಾಯ ಬೇಕಾದರೆ ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "care_plan": "ಜ್ಞಾಪನೆ: ಸಲಹೆ ನೀಡಿದಂತೆ ನಿಮ್ಮ ಆರೈಕೆ ಯೋಜನೆಯನ್ನು ಅನುಸರಿಸಿ. ಸಹಾಯ ಬೇಕಾದರೆ ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "important_alert": "ನಿಮಗಾಗಿ ಪ್ರಮುಖ ಆರೋಗ್ಯ ಸಂಬಂಧಿತ ಸೂಚನೆ ಇದೆ. ಹೆಚ್ಚಿನ ಮಾಹಿತಿಗಾಗಿ ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "asha_notification": "ನಿಮಗಾಗಿ ಪ್ರಮುಖ ಆರೋಗ್ಯ ಸಂಬಂಧಿತ ಸೂಚನೆ ಇದೆ. ಹೆಚ್ಚಿನ ಮಾಹಿತಿಗಾಗಿ ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "beneficiary_reminder": "ಇದು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರಿಂದ ಜ್ಞಾಪನೆ. ಸಹಾಯಕ್ಕಾಗಿ ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "anc": "ಜ್ಞಾಪನೆ: ನಿಮ್ಮ ನಿಗದಿತ ಆರೋಗ್ಯ ಭೇಟಿ ಹತ್ತಿರವಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "vaccination": "ಜ್ಞಾಪನೆ: ಸಮುದಾಯ ಆರೋಗ್ಯ ಭೇಟಿ ನಿಗದಿಪಡಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸ್ಥಳೀಯ ASHA ಕಾರ್ಯಕರ್ತರೊಂದಿಗೆ ಸಮನ್ವಯಗೊಳಿಸಿ.",
        "newborn": "ಜ್ಞಾಪನೆ: ನಿಮ್ಮ ನಿಗದಿತ ಆರೋಗ್ಯ ಭೇಟಿ ಹತ್ತಿರವಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "nutrition": "ಜ್ಞಾಪನೆ: ನಿಮ್ಮ ನಿಗದಿತ ಆರೋಗ್ಯ ಭೇಟಿ ಹತ್ತಿರವಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "community": "ಜ್ಞಾಪನೆ: ಸಮುದಾಯ ಆರೋಗ್ಯ ಭೇಟಿ ನಿಗದಿಪಡಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸ್ಥಳೀಯ ASHA ಕಾರ್ಯಕರ್ತರೊಂದಿಗೆ ಸಮನ್ವಯಗೊಳಿಸಿ.",
        "household": "ಜ್ಞಾಪನೆ: ನಿಮ್ಮ ನಿಗದಿತ ಆರೋಗ್ಯ ಭೇಟಿ ಹತ್ತಿರವಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        "general": "ಇದು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರಿಂದ ಜ್ಞಾಪನೆ. ಸಹಾಯಕ್ಕಾಗಿ ದಯವಿಟ್ಟು ನಿಮ್ಮ ASHA ಕಾರ್ಯಕರ್ತರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
    },
    "hi": {
        "appointment": "स्मरण: आपकी आगामी स्वास्थ्य नियुक्ति है। सहायता के लिए कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "follow_up": "यह आपकी निर्धारित स्वास्थ्य फॉलो-अप के लिए स्मरण है। कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "medication": "स्मरण: कृपया सलाह अनुसार अपनी देखभाल योजना का पालन करें। सहायता के लिए अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "care_plan": "स्मरण: कृपया सलाह अनुसार अपनी देखभाल योजना का पालन करें। सहायता के लिए अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "important_alert": "आपके लिए एक महत्वपूर्ण स्वास्थ्य संबंधी सूचना है। अधिक जानकारी के लिए कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "asha_notification": "आपके लिए एक महत्वपूर्ण स्वास्थ्य संबंधी सूचना है। अधिक जानकारी के लिए कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "beneficiary_reminder": "यह आपकी ASHA कार्यकर्ता की ओर से स्मरण है। सहायता के लिए कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "anc": "स्मरण: आपकी निर्धारित स्वास्थ्य यात्रा निकट है। कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "vaccination": "स्मरण: सामुदायिक स्वास्थ्य यात्रा निर्धारित है। कृपया अपनी स्थानीय ASHA कार्यकर्ता से समन्वय करें।",
        "newborn": "स्मरण: आपकी निर्धारित स्वास्थ्य यात्रा निकट है। कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "nutrition": "स्मरण: आपकी निर्धारित स्वास्थ्य यात्रा निकट है। कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "community": "स्मरण: सामुदायिक स्वास्थ्य यात्रा निर्धारित है। कृपया अपनी स्थानीय ASHA कार्यकर्ता से समन्वय करें।",
        "household": "स्मरण: आपकी निर्धारित स्वास्थ्य यात्रा निकट है। कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
        "general": "यह आपकी ASHA कार्यकर्ता की ओर से स्मरण है। सहायता के लिए कृपया अपनी ASHA कार्यकर्ता से संपर्क करें।",
    },
    "te": {
        "appointment": "గుర్తింపు: మీకు రాబోయే ఆరోగ్య అపాయింట్‌మెంట్ ఉంది. సహాయం కోసం దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "follow_up": "ఇది మీ నిర్ణీత ఆరోగ్య ఫాలో-అప్ కోసం గుర్తింపు. దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "medication": "గుర్తింపు: సూచించిన విధంగా మీ సంరక్షణ ప్రణాళికను అనుసరించండి. సహాయం అవసరమైతే మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "care_plan": "గుర్తింపు: సూచించిన విధంగా మీ సంరక్షణ ప్రణాళికను అనుసరించండి. సహాయం అవసరమైతే మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "important_alert": "మీకు ఒక ముఖ్యమైన ఆరోగ్య సంబంధిత సమాచారం ఉంది. మరింత సమాచారం కోసం దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "asha_notification": "మీకు ఒక ముఖ్యమైన ఆరోగ్య సంబంధిత సమాచారం ఉంది. మరింత సమాచారం కోసం దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "beneficiary_reminder": "ఇది మీ ASHA కార్యకర్త నుండి గుర్తింపు. సహాయం కోసం దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "anc": "గుర్తింపు: మీ నిర్ణీత ఆరోగ్య సందర్శన సమీపిస్తోంది. దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "vaccination": "గుర్తింపు: సముదాయ ఆరోగ్య సందర్శన నిర్ణయించబడింది. దయచేసి మీ స్థానిక ASHA కార్యకర్తతో సమన్వయం చేయండి.",
        "newborn": "గుర్తింపు: మీ నిర్ణీత ఆరోగ్య సందర్శన సమీపిస్తోంది. దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "nutrition": "గుర్తింపు: మీ నిర్ణీత ఆరోగ్య సందర్శన సమీపిస్తోంది. దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "community": "గుర్తింపు: సముదాయ ఆరోగ్య సందర్శన నిర్ణయించబడింది. దయచేసి మీ స్థానిక ASHA కార్యకర్తతో సమన్వయం చేయండి.",
        "household": "గుర్తింపు: మీ నిర్ణీత ఆరోగ్య సందర్శన సమీపిస్తోంది. దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
        "general": "ఇది మీ ASHA కార్యకర్త నుండి గుర్తింపు. సహాయం కోసం దయచేసి మీ ASHA కార్యకర్తను సంప్రదించండి.",
    },
    "ta": {
        "appointment": "நினைவூட்டல்: உங்களுக்கு வரவிருக்கும் சுகாதார சந்திப்பு உள்ளது. உதவிக்கு தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "follow_up": "இது உங்கள் திட்டமிடப்பட்ட சுகாதார தொடர்ச்சி சந்திப்புக்கான நினைவூட்டல். தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "medication": "நினைவூட்டல்: அறிவுரைப்படி உங்கள் பராமரிப்பு திட்டத்தை பின்பற்றவும். உதவி தேவைப்பட்டால் உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "care_plan": "நினைவூட்டல்: அறிவுரைப்படி உங்கள் பராமரிப்பு திட்டத்தை பின்பற்றவும். உதவி தேவைப்பட்டால் உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "important_alert": "உங்களுக்கு ஒரு முக்கியமான சுகாதார தொடர்பான அறிவிப்பு உள்ளது. மேலும் தகவலுக்கு தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "asha_notification": "உங்களுக்கு ஒரு முக்கியமான சுகாதார தொடர்பான அறிவிப்பு உள்ளது. மேலும் தகவலுக்கு தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "beneficiary_reminder": "இது உங்கள் ASHA பணியாளரிடமிருந்து நினைவூட்டல். உதவிக்கு தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "anc": "நினைவூட்டல்: உங்கள் திட்டமிடப்பட்ட சுகாதார வருகை நெருங்குகிறது. தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "vaccination": "நினைவூட்டல்: சமூக சுகாதார வருகை திட்டமிடப்பட்டுள்ளது. தயவுசெய்து உங்கள் உள்ளூர் ASHA பணியாளருடன் ஒருங்கிணைக்கவும்.",
        "newborn": "நினைவூட்டல்: உங்கள் திட்டமிடப்பட்ட சுகாதார வருகை நெருங்குகிறது. தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "nutrition": "நினைவூட்டல்: உங்கள் திட்டமிடப்பட்ட சுகாதார வருகை நெருங்குகிறது. தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "community": "நினைவூட்டல்: சமூக சுகாதார வருகை திட்டமிடப்பட்டுள்ளது. தயவுசெய்து உங்கள் உள்ளூர் ASHA பணியாளருடன் ஒருங்கிணைக்கவும்.",
        "household": "நினைவூட்டல்: உங்கள் திட்டமிடப்பட்ட சுகாதார வருகை நெருங்குகிறது. தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
        "general": "இது உங்கள் ASHA பணியாளரிடமிருந்து நினைவூட்டல். உதவிக்கு தயவுசெய்து உங்கள் ASHA பணியாளரை தொடர்பு கொள்ளவும்.",
    },
}


# ---------------------------------------------------------------------------
# Validation / provider configuration
# ---------------------------------------------------------------------------

def validate_phone(phone: Optional[str]) -> Optional[str]:
    """Return a normalized Indian mobile number in E.164 (+91XXXXXXXXXX), or None if invalid."""
    return normalize_indian_phone_to_e164(phone)


def _legacy_sms_provider_configured() -> bool:
    return bool(get_env("SMS_PROVIDER_URL")) and bool(get_env("SMS_PROVIDER_KEY"))


def sms_provider_configured() -> bool:
    """True when any live SMS provider is configured, enabled, and compliance-approved."""
    if not sms_compliance_approved():
        return False
    return textbee_active() or _legacy_sms_provider_configured()


def sms_provider_name() -> str:
    if sms_compliance_approved() and textbee_active():
        return "textbee"
    if sms_compliance_approved() and _legacy_sms_provider_configured():
        return "generic"
    return "demo"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _lang(language: str | None) -> str:
    return (language or "en").lower().split("-")[0].strip() or "en"


def build_sms_body(event_type: str, language: str = "en") -> str:
    """Return a generic, privacy-preserving SMS body for an event/type."""
    lang = _lang(language)
    key = (event_type or "general").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "appointment_reminder": "appointment",
        "followup": "follow_up",
        "follow_up_reminder": "follow_up",
        "medication_reminder": "medication",
        "careplan": "care_plan",
        "care_plan_reminder": "care_plan",
        "health_alert": "important_alert",
        "important_health_alert": "important_alert",
        "danger_alert": "important_alert",
        "asha_worker": "asha_notification",
        "asha": "asha_notification",
        "beneficiary": "beneficiary_reminder",
    }
    key = aliases.get(key, key)
    table = SMS_TEMPLATES.get(lang) or SMS_TEMPLATES["en"]
    if key in table:
        return table[key]
    en_table = SMS_TEMPLATES["en"]
    if key in en_table:
        return en_table[key]
    return table.get("general") or en_table["general"]


# ---------------------------------------------------------------------------
# Duplicate prevention (SMS)
# ---------------------------------------------------------------------------

def _recent_duplicate_sms(
    db: Session,
    *,
    beneficiary_id: int,
    follow_up_id: int | None,
    event_type: str,
    body: str,
    window_minutes: int = 10,
) -> SmsNotification | None:
    """Return an existing SMS record if a duplicate should be prevented."""
    # Strong dedupe: same beneficiary + follow-up + event type and not failed
    if follow_up_id is not None:
        existing = (
            db.query(SmsNotification)
            .filter(SmsNotification.beneficiary_id == beneficiary_id)
            .filter(SmsNotification.follow_up_id == follow_up_id)
            .filter(SmsNotification.type == (event_type or "general"))
            .filter(SmsNotification.status.in_(["pending", "submitted", "delivered", "demo", "sent"]))
            .order_by(desc(SmsNotification.created_at))
            .first()
        )
        if existing:
            return existing
    # Fallback: identical content to same beneficiary recently and not failed
    cutoff = datetime.utcnow() - timedelta(minutes=max(1, window_minutes))
    recent = (
        db.query(SmsNotification)
        .filter(SmsNotification.beneficiary_id == beneficiary_id)
        .filter(SmsNotification.status.in_(["pending", "submitted", "delivered", "demo", "sent"]))
        .filter(SmsNotification.created_at >= cutoff)
        .order_by(desc(SmsNotification.created_at))
        .limit(20)
        .all()
    )
    norm_body = (body or "").strip()
    norm_type = (event_type or "").strip().lower()
    for row in recent:
        if (row.body or "").strip() == norm_body and (row.type or "").strip().lower() == norm_type:
            return row
    return None


# ---------------------------------------------------------------------------
# SMS sending
# ---------------------------------------------------------------------------

async def send_sms_notification(
    db: Session,
    *,
    beneficiary: Beneficiary,
    follow_up_type: str,
    language: str = "en",
    body: Optional[str] = None,
    worker_id: Optional[int] = None,
    follow_up_id: Optional[int] = None,
    consent: Optional[ConsentRecord] = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Create and (in live mode) submit an SMS notification.

    Respects configuration/enablement, phone validity, and duplicate prevention.
    Never sends when SMS delivery is disabled or unconfigured (demo recorded instead).
    """
    event_type = (follow_up_type or "general").strip().lower() or "general"
    lang = _lang(language)
    phone = validate_phone(getattr(beneficiary, "phone", None))
    text = (body or "").strip() or build_sms_body(event_type, lang)

    if not phone:
        return {
            "ok": False,
            "status": "failed",
            "note": "No valid mobile number is on file for this beneficiary.",
            "body": text,
            "phone": getattr(beneficiary, "phone", "") or "",
            "is_demo": not sms_provider_configured(),
            "duplicate": False,
        }

    if not allow_duplicate:
        dup = _recent_duplicate_sms(db, beneficiary_id=beneficiary.id, follow_up_id=follow_up_id, event_type=event_type, body=text)
        if dup:
            return {
                "ok": True,
                "id": dup.id,
                "status": dup.status,
                "note": dup.provider_note or "Duplicate SMS prevented (already sent or pending).",
                "body": dup.body,
                "phone": dup.phone or phone,
                "is_demo": bool(dup.is_demo),
                "duplicate": True,
            }

    # Disabled or not configured => demo (explicit, not sent)
    if not sms_provider_configured():
        note = DEMO_LABEL
        if textbee_configured() and not textbee_enabled():
            note = "SMS delivery is disabled (TEXTBEE_ENABLED=false). " + DEMO_LABEL
        notification = SmsNotification(
            beneficiary_id=beneficiary.id,
            follow_up_id=follow_up_id,
            type=event_type,
            phone=phone,
            body=text,
            language=lang,
            status="demo",
            provider_note=note[:256],
            is_demo=True,
            consent_id=consent.id if consent else None,
            sent_at=datetime.utcnow(),
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return {
            "ok": True,
            "id": notification.id,
            "status": "demo",
            "note": note,
            "body": text,
            "phone": phone,
            "is_demo": True,
            "duplicate": False,
        }

    # Live provider path (TextBee preferred, legacy generic fallback)
    if textbee_active():
        result = await send_sms_via_textbee(to_e164=phone, message=text)
    elif _legacy_sms_provider_configured():
        result = await _send_via_legacy_provider(phone_e164=phone, text=text)
    else:
        result = {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "No SMS provider is configured.", "error": "No SMS provider is configured."}

    ok = bool(result.get("ok"))
    status = (result.get("status") or ("submitted" if ok else "failed")).strip().lower()
    provider_note = (result.get("provider_note") or result.get("error") or ("Submitted to SMS provider." if ok else "SMS delivery failed."))
    provider_ref = (result.get("provider_ref") or "")[:120]

    notification = SmsNotification(
        beneficiary_id=beneficiary.id,
        follow_up_id=follow_up_id,
        type=event_type,
        phone=phone,
        body=text,
        language=lang,
        status=status,
        provider_note=str(provider_note)[:256],
        provider_ref=provider_ref,
        is_demo=False,
        consent_id=consent.id if consent else None,
        sent_at=datetime.utcnow() if ok else None,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    return {
        "ok": ok,
        "id": notification.id,
        "status": notification.status,
        "note": notification.provider_note or provider_note,
        "body": text,
        "phone": phone,
        "is_demo": False,
        "duplicate": False,
    }


async def _send_via_legacy_provider(*, phone_e164: str, text: str) -> dict[str, Any]:
    """Legacy generic SMS provider (SMS_PROVIDER_URL/KEY) via HTTP POST, kept for compatibility."""
    url = get_env("SMS_PROVIDER_URL")
    key = get_env("SMS_PROVIDER_KEY")
    if not url or not key:
        return {"ok": False, "status": "failed", "provider_ref": "", "provider_note": "SMS provider is not configured.", "error": "SMS provider is not configured."}

    payload = json.dumps({"to": phone_e164, "message": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        def _do():
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore")

        provider_status, provider_body = await asyncio.to_thread(_do)
        return {
            "ok": True,
            "status": "submitted",
            "provider_ref": (provider_body or "")[:120],
            "provider_note": f"Provider accepted the message (HTTP {provider_status}).",
            "error": "",
        }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": "failed",
            "provider_ref": "",
            "provider_note": f"Provider error: {exc.code}",
            "error": f"Provider error: {exc.code}",
        }
    except Exception as exc:
        logger.warning("Legacy SMS provider request failed (%s)", type(exc).__name__)
        return {
            "ok": False,
            "status": "failed",
            "provider_ref": "",
            "provider_note": "Provider unreachable.",
            "error": "Provider unreachable.",
        }


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

def record_consent(
    db: Session,
    beneficiary: Beneficiary,
    channel: str,
    granted: bool,
    purpose: str = "follow_up_reminder",
    worker_id: Optional[int] = None,
) -> ConsentRecord:
    """Record the worker's consent decision for a notification channel."""
    consent = ConsentRecord(
        beneficiary_id=beneficiary.id,
        channel=channel,
        purpose=purpose,
        granted=granted,
        worker_id=worker_id,
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent
