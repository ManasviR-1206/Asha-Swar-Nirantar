"""Authentication: password hashing (stdlib pbkdf2), opaque bearer tokens,
and the get_current_worker FastAPI dependency.
"""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import get_env
from app.database import get_db
from app.models import ApiToken, AshaWorker

_PBKDF2_ITERATIONS = 100_000

# Bearer tokens expire after this many hours (default: 7 days). A zero/negative
# value disables expiry, which is useful only for controlled local demos.
_TOKEN_TTL_HOURS = float(get_env("TOKEN_TTL_HOURS", "168") or "168")


# ---------- Password hashing (stdlib only, no external deps) ----------
def hash_password(password: str) -> str:
    """Return "salt_hex$hash_hex" using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison of a password against a stored hash."""
    if not stored or not isinstance(stored, str):
        return False
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    if not salt or len(expected) != 32:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return secrets.compare_digest(digest, expected)


# ---------- Tokens ----------
def create_token(db: Session, worker: AshaWorker) -> str:
    """Create a random opaque token (secrets.token_hex(32)), persist, return."""
    token = secrets.token_hex(32)
    db.add(ApiToken(token=token, worker_id=worker.id, created_at=datetime.utcnow()))
    db.commit()
    return token


def get_current_worker(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AshaWorker:
    """Resolve the "Authorization: Bearer <token>" header to an AshaWorker.

    Raises 401 when the header is missing, the token is unknown, or the
    session token has expired.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    row = db.query(ApiToken).filter(ApiToken.token == token).first()
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if _TOKEN_TTL_HOURS > 0 and row.created_at is not None:
        expires_at = row.created_at + timedelta(hours=_TOKEN_TTL_HOURS)
        if datetime.utcnow() > expires_at:
            db.delete(row)
            db.commit()
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

    worker = db.query(AshaWorker).filter(AshaWorker.id == row.worker_id).first()
    if worker is None or not worker.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return worker


# ---------- Short-lived WS tokens (voice streaming auth) ----------
def _ws_secret() -> bytes:
    secret = get_env("APP_SECRET_KEY") or get_env("SECRET_KEY") or "asha-swar-nirantar-dev-secret-change-me"
    return secret.encode("utf-8")


def create_ws_token(worker_id: int, ttl_seconds: int = 300) -> str:
    payload = {"wid": int(worker_id), "exp": int(datetime.utcnow().timestamp()) + int(ttl_seconds)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(_ws_secret(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_ws_token(token: str) -> int | None:
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expected = hmac.new(_ws_secret(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not secrets.compare_digest(expected, sig):
        return None
    pad = "=" * (-len(b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode((b64 + pad).encode("ascii")).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.utcnow().timestamp()):
            return None
        wid = int(payload.get("wid"))
        return wid if wid > 0 else None
    except Exception:
        return None
