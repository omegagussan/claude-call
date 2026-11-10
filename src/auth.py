import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import APIKeyHeader

from src.config import settings

# Prefix cc_ followed by live_ or test_, then at least 16 hex/alphanumeric characters
# e.g., cc_live_0123456789abcdef0123 or cc_test_1234567890abcdef
API_KEY_PATTERN = re.compile(r"^cc_(?:live|test)_[A-Za-z0-9_-]{16,}$")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def validate_api_key_format(key: str) -> bool:
    """Validate that the given key conforms to the expected API key format."""
    return bool(API_KEY_PATTERN.match(key))


def get_configured_api_keys() -> set[str]:
    """Parse configured valid API keys from settings."""
    if not settings.api_keys:
        return set()
    return {k.strip() for k in settings.api_keys.split(",") if k.strip()}


async def verify_api_key(
    x_api_key: Annotated[str | None, Depends(api_key_header)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """
    Verify incoming API key authentication.
    Supports either 'X-API-Key' header or 'Authorization: Bearer <key>'.

    If settings.api_key_auth_enabled is False, authentication is bypassed.
    """
    if not settings.api_key_auth_enabled:
        return None

    candidate_key: str | None = x_api_key

    if not candidate_key and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            candidate_key = parts[1]

    if not candidate_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not validate_api_key_format(candidate_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Expected 'cc_<live|test>_<key>'.",
        )

    configured_keys = get_configured_api_keys()
    if candidate_key not in configured_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or inactive API key.",
        )

    return candidate_key
