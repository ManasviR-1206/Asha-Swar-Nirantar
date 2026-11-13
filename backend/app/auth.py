"""Authentication: password hashing (stdlib pbkdf2), opaque bearer tokens,
and the get_current_worker FastAPI dependency.
"""
import hashlib
import secrets
from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken, AshaWorker

_PBKDF2_ITERATIONS = 100_000


# ---------- Password hashing (stdlib only, no external deps) ----------
def hash_password(password: str) -> str:
    """Return "salt_hex$hash_hex" using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison of a password against a stored hash."""
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS
    )
    return secrets.compare_digest(digest.hex(), digest_hex)


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

    Raises 401 when the header is missing or the token is unknown.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    row = db.query(ApiToken).filter(ApiToken.token == token).first()
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    worker = db.query(AshaWorker).filter(AshaWorker.id == row.worker_id).first()
    if worker is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return worker
