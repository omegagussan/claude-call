from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telnyx_api_key: str = "KEY_MOCK_TEST"
    telnyx_connection_id: str = "conn_mock_123"
    telnyx_from_number: str = "+15551234567"
    telnyx_api_base: str = "https://api.telnyx.com/v2"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
