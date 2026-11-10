from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telnyx Settings
    telnyx_api_key: str = "KEY_MOCK_TEST"
    telnyx_connection_id: str = "conn_mock_123"
    telnyx_from_number: str = "+15551234567"
    telnyx_api_base: str = "https://api.telnyx.com/v2"
    telnyx_public_key: str | None = None

    # Database / D1 Settings
    todo_table_name: str = "user_todos"

    # Account / External Provider Keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Claude Call API Authentication
    api_key_auth_enabled: bool = False
    api_keys: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def get_worker_setting(env: Any, key: str, default: Any = None) -> Any:
    """Read a setting from Cloudflare scope['env'], falling back to default/settings."""
    if env is not None:
        if isinstance(env, dict) and key in env:
            return env[key]
        if hasattr(env, key):
            val = getattr(env, key)
            if val is not None:
                return val
    return default
