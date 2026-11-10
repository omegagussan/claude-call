import pytest

from src.config import settings


@pytest.fixture(autouse=True)
def isolate_auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", False)
    monkeypatch.setattr(settings, "api_keys", "")
