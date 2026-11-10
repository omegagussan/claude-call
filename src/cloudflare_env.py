from typing import Any

from fastapi import Request


def get_env_var(request: Request | None, key: str, default: Any = None) -> Any:
    """
    Retrieve environment variable from Cloudflare Worker ASGI scope (`request.scope["env"]`).
    Falls back to `default` if request or scope['env'] is not present.
    """
    if request is not None:
        scope = getattr(request, "scope", {})
        env = scope.get("env")
        if env is not None:
            # env might be a dict or a JS object with getattr
            if isinstance(env, dict) and key in env:
                return env[key]
            if hasattr(env, key):
                return getattr(env, key)
    return default
