import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"


def _prehash(password: str) -> bytes:
    # bcrypt only reads the first 72 bytes (and newer versions reject longer input).
    # SHA-256 + base64 gives a fixed 44-byte input, so long passphrases work safely.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except ValueError:
        return False


# Used to burn the same CPU time when an email doesn't exist (blunts user enumeration by timing).
DUMMY_HASH = hash_password("not-a-real-password")


def _encode(sub: str, token_type: str, expires: timedelta, jti: str | None = None) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + expires
    jti = jti or str(uuid.uuid4())
    payload = {"sub": sub, "type": token_type, "jti": jti, "iat": now, "exp": exp}
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM), jti, exp


def create_access_token(user_id: str) -> str:
    token, _, _ = _encode(user_id, "access", timedelta(minutes=get_settings().access_token_minutes))
    return token


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    return _encode(user_id, "refresh", timedelta(days=get_settings().refresh_token_days))


def decode_token(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type or not payload.get("sub") or not payload.get("jti"):
        return None
    return payload
