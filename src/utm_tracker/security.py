"""API keys.

Keys are random 256-bit tokens, so a fast SHA-256 is enough to store them:
there is nothing to brute-force. (Passwords would need a slow hash.)
"""

import hashlib
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from utm_tracker.db import get_session
from utm_tracker.models import ApiKey

KEY_PREFIX = "utm_"

_header = APIKeyHeader(
    name="X-API-Key", auto_error=False, description="Create one with `utm-tracker create-key`."
)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(session: Session, name: str) -> tuple[ApiKey, str]:
    """Returns the stored row and the plain key, which is shown once and never again."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ApiKey(name=name, prefix=key[:12], key_hash=hash_key(key))
    session.add(row)
    session.commit()
    return row, key


def require_api_key(
    key: str | None = Depends(_header),
    session: Session = Depends(get_session),
) -> ApiKey:
    row = (
        session.scalar(
            select(ApiKey).where(ApiKey.key_hash == hash_key(key), ApiKey.revoked_at.is_(None))
        )
        if key
        else None
    )
    if row is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return row
