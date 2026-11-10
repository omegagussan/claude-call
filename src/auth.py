import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from src.config import settings

# Prefix cc_ followed by live_ or test_, then at least 16 hex/alphanumeric characters
# e.g., cc_live_0123456789abcdef0123 or cc_test_1234567890abcdef
API_KEY_PATTERN = re.compile(r"^cc_(?:live|test)_[A-Za-z0-9_-]{16,}$")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def validate_api_key_format(key: str) -> bool:
    """Validate that the given key conforms to the expected API key format."""
    return bool(API_KEY_PATTERN.match(key))


def get_configured_api_keys(request: Request | None = None) -> set[str]:
    """Parse configured valid API keys from request scope['env'] or fallback settings."""
    keys_str = ""
    if request is not None:
        scope_env = request.scope.get("env")
        if scope_env:
            if isinstance(scope_env, dict):
                keys_str = scope_env.get("API_KEYS", "")
            elif hasattr(scope_env, "API_KEYS"):
                keys_str = getattr(scope_env, "API_KEYS", "") or ""

    if not keys_str:
        keys_str = settings.api_keys

    if not keys_str:
        return set()
    return {k.strip() for k in keys_str.split(",") if k.strip()}


def is_auth_enabled(request: Request | None = None) -> bool:
    """Check if API key auth is enabled from request scope['env'] or settings."""
    if request is not None:
        scope_env = request.scope.get("env")
        if scope_env:
            val = None
            if isinstance(scope_env, dict):
                val = scope_env.get("API_KEY_AUTH_ENABLED")
            elif hasattr(scope_env, "API_KEY_AUTH_ENABLED"):
                val = scope_env.API_KEY_AUTH_ENABLED

            if val is not None:
                if isinstance(val, bool):
                    return val
                return str(val).lower() in ("true", "1", "yes")

    return settings.api_key_auth_enabled


async def verify_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Depends(api_key_header)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """
    Verify incoming API key authentication.
    Supports either 'X-API-Key' header or 'Authorization: Bearer <key>'.

    If API_KEY_AUTH_ENABLED is False, authentication is bypassed.
    """
    if not is_auth_enabled(request):
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

    configured_keys = get_configured_api_keys(request)
    if candidate_key not in configured_keys:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or inactive API key.",
        )

    return candidate_key
