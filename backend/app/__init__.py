"""ASHA SWAR NIRANTAR — voice-first healthcare field register for ASHA workers.

This package loads .env on import so every module can read configuration
via get_env().
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env explicitly, regardless of the process working directory.
# This prevents `python backend/run.py` and `cd backend && python run.py` from
# resolving configuration and relative SQLite paths differently.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env", override=False)


def get_env(key: str, default: str = "") -> str:
    """Read an environment variable, falling back to .env values."""
    return os.environ.get(key, default)


def _env_truthy(key: str, default: str = "") -> bool:
    return get_env(key, default).strip().lower() in {"1", "true", "yes", "on"}


def demo_setup_enabled() -> bool:
    """Return True only when demo/dev setup is explicitly enabled.

    Normal application operation must not auto-seed demo beneficiaries or
    auto-create/activate the demo worker. Demo setup is opt-in for
    development/testing via explicit environment configuration.
    """
    # Preferred explicit flag. APP_MODE=demo is also accepted for convenience.
    if _env_truthy("ENABLE_DEMO_SETUP", "false"):
        return True
    return get_env("APP_MODE", "").strip().lower() == "demo"


def gnani_requested_mode() -> str:
    """Configured Gnani integration preference: "demo" or "live".

    This does NOT mean Gnani is actually live/connected; live behavior is
    only used when required credentials/configuration are present.
    """
    mode = get_env("GNANI_MODE", "demo").strip().lower()
    return "live" if mode == "live" else "demo"


def gnani_mode() -> str:
    """Backward-compatible alias for the configured Gnani integration mode.

    Kept for existing callers; health/reporting should use detailed status
    helpers so the app never claims live connectivity without configuration.
    """
    return gnani_requested_mode()
