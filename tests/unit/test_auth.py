import pytest
from httpx import ASGITransport, AsyncClient

from src.auth import validate_api_key_format
from src.config import settings
from src.main import app


def test_api_key_format_validation():
    # Valid keys
    assert validate_api_key_format("cc_live_0123456789abcdef") is True
    assert validate_api_key_format("cc_test_abcdef1234567890_test") is True
    assert validate_api_key_format("cc_live_abcdef-12345_67890") is True

    # Invalid keys
    assert validate_api_key_format("invalid_key") is False
    assert validate_api_key_format("cc_prod_0123456789abcdef") is False
    assert validate_api_key_format("cc_live_short") is False  # too short (<16 chars)
    assert validate_api_key_format("cc_test_") is False
    assert validate_api_key_format("") is False


@pytest.mark.asyncio
async def test_auth_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/todos/+123456789")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "cc_live_validkey1234567890")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/todos/+123456789")
        assert resp.status_code == 401
        assert "Missing API key" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_enabled_invalid_format(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "cc_live_validkey1234567890")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Malformed key (not matching pattern)
        resp = await client.get("/todos/+123456789", headers={"X-API-Key": "wrong-format-key"})
        assert resp.status_code == 401
        assert "Invalid API key format" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_enabled_forbidden_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "cc_live_validkey1234567890")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Well-formed format, but not in configured valid keys list
        resp = await client.get("/todos/+123456789", headers={"X-API-Key": "cc_test_unknownkey123456"})
        assert resp.status_code == 403
        assert "Forbidden" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_enabled_valid_key_via_header(monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys", "cc_live_validkey1234567890")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Valid X-API-Key
        resp = await client.get("/todos/+123456789", headers={"X-API-Key": "cc_live_validkey1234567890"})
        assert resp.status_code == 200

        # Valid Bearer token
        resp_bearer = await client.get(
            "/todos/+123456789", headers={"Authorization": "Bearer cc_live_validkey1234567890"}
        )
        assert resp_bearer.status_code == 200
