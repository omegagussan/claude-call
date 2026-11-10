from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telnyx Settings
    telnyx_api_key: str = "KEY_MOCK_TEST"
    telnyx_connection_id: str = "conn_mock_123"
    telnyx_from_number: str = "+15551234567"
    telnyx_api_base: str = "https://api.telnyx.com/v2"

    # Postgres & Database Settings
    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/claude_call"
    todo_table_name: str = "user_todos"
    todo_db_schema: str = "public"
    db_app_role: str = "claude_call_app"
    auto_apply_migrations: bool = True

    # Account / External Provider Keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Claude Call API Authentication
    api_key_auth_enabled: bool = False
    api_keys: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
