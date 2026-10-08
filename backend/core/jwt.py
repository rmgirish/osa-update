"""JWT access-token creation and decoding helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from backend.core.config import settings


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Create a signed bearer token.

    ``expires_minutes`` overrides the default lifetime (used by 'Remember me'
    logins to issue a 1-day session instead of the two-hour default).
    """
    lifetime = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expires_at = datetime.now(UTC) + timedelta(minutes=lifetime)
    payload: dict[str, Any] = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode a token, returning None for invalid or expired credentials."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None