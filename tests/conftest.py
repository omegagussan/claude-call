import pytest

from src.config import settings
from src.main import app
from src.webhook_auth import verify_telnyx_signature


@pytest.fixture(autouse=True)
def isolate_auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", False)
    monkeypatch.setattr(settings, "api_keys", "")


@pytest.fixture(autouse=True)
def isolate_webhook_verification():
    app.dependency_overrides[verify_telnyx_signature] = lambda: None
    yield
    app.dependency_overrides.pop(verify_telnyx_signature, None)
