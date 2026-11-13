"""ASHA SWAR NIRANTAR — voice-first healthcare field register for ASHA workers.

This package loads .env on import so every module can read configuration
via get_env().
"""
import os

from dotenv import load_dotenv

# Load backend/.env (if present) once, before any module reads env vars.
load_dotenv()


def get_env(key: str, default: str = "") -> str:
    """Read an environment variable, falling back to .env values."""
    return os.environ.get(key, default)


def gnani_mode() -> str:
    """Return the configured integration mode: "demo" or "live".

    Anything other than an explicit "live" is treated as demo, so the
    system never fakes live connectivity.
    """
    mode = get_env("GNANI_MODE", "demo").strip().lower()
    return "live" if mode == "live" else "demo"
