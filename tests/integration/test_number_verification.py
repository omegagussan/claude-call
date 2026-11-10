import json

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app

NUMBER = {"country_code": "+46", "area_code": "70", "subscriber_number": "1234567"}
PHONE = "+46701234567"
BASE = "https://api.telnyx.com/v2"
VERIFIED = {"data": {"phone_number": PHONE, "verified_at": "2026-11-10T20:00:00Z"}}
ENDPOINTS = ["/numbers/verifications", "/numbers/verifications/confirm", "/numbers/verifications/status"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["sms", "call"])
@respx.mock
async def test_explicit_verification_flow(method):
    start = respx.post(f"{BASE}/verified_numbers").respond(200, json={"data": {"phone_number": PHONE}})
    confirm = respx.post(f"{BASE}/verified_numbers/{PHONE}/actions/verify").respond(200, json=VERIFIED)
    status = respx.get(f"{BASE}/verified_numbers/{PHONE}").respond(200, json=VERIFIED)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(ENDPOINTS[0], json={"phone_number": NUMBER, "verification_method": method})
        assert response.status_code == 200
        assert response.json() == {"phone_number": PHONE, "status": "verification_requested"}
        response = await client.post(ENDPOINTS[1], json={"phone_number": NUMBER, "verification_code": "123456"})
        assert response.status_code == 200
        assert response.json()["verified"] is True
        response = await client.post(ENDPOINTS[2], json={"phone_number": NUMBER})
        assert response.status_code == 200
        assert response.json()["verified"] is True
    assert json.loads(start.calls.last.request.content) == {"phone_number": PHONE, "verification_method": method}
    assert json.loads(confirm.calls.last.request.content) == {"verification_code": "123456"}
    assert status.call_count == 1
    assert len(respx.calls) == 3


@pytest.mark.asyncio
@respx.mock
async def test_unverified_status_does_not_send_code():
    respx.get(f"{BASE}/verified_numbers/{PHONE}").respond(
        404, json={"errors": [{"code": "10005", "title": "Resource not found"}]}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(ENDPOINTS[2], json={"phone_number": NUMBER})
    assert response.status_code == 200
    assert response.json() == {"phone_number": PHONE, "verified": False, "verified_at": None}
    assert len(respx.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ENDPOINTS)
@respx.mock
async def test_verification_endpoints_require_api_key(endpoint, monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(endpoint, json={"phone_number": NUMBER})
    assert response.status_code == 401
    assert not respx.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "extra"),
    [
        (ENDPOINTS[0], {"verification_method": "email"}),
        (ENDPOINTS[1], {"verification_code": ""}),
        (ENDPOINTS[1], {"verification_code": 123456}),
        (ENDPOINTS[1], {"verification_code": "not-digits"}),
    ],
)
@respx.mock
async def test_invalid_verification_input_never_reaches_provider(endpoint, extra):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(endpoint, json={"phone_number": NUMBER} | extra)
    assert response.status_code == 422
    assert not respx.calls


@pytest.mark.asyncio
@respx.mock
async def test_incorrect_code_returns_provider_error_without_echoing_code():
    respx.post(f"{BASE}/verified_numbers/{PHONE}/actions/verify").respond(
        422, json={"errors": [{"code": "10015", "detail": "Invalid code 123456"}]}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(ENDPOINTS[1], json={"phone_number": NUMBER, "verification_code": "123456"})
    assert response.status_code == 502
    assert response.json()["provider_status"] == 422
    assert "123456" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/calls/dial", "/calls/froken-ur", "/calls/todo"])
@pytest.mark.parametrize("restricted", [False, True])
@respx.mock
async def test_only_specific_trial_restriction_becomes_verification_error(endpoint, restricted):
    detail = (
        "Can not make calls to non-verified numbers at this account level D60."
        if restricted
        else "You do not have permission to perform this action."
    )
    respx.post(f"{BASE}/calls").respond(403, json={"errors": [{"code": "10010", "detail": detail}]})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(endpoint, json={"to_number": NUMBER})
    assert response.status_code == (403 if restricted else 502)
    assert response.json()["provider_error_codes"] == ["10010"]
    if restricted:
        assert response.json()["code"] == "destination_verification_required"
        assert "whitelist" in response.json()["detail"]
    else:
        assert "code" not in response.json()
    assert len(respx.calls) == 1


def test_verification_schema_release():
    schema = app.openapi()
    assert schema["info"]["version"] == "0.4.0"
    for endpoint in ENDPOINTS:
        operation = schema["paths"][endpoint]["post"]
        assert operation["security"]
        assert "200" in operation["responses"]
    assert "403" in schema["paths"]["/calls/froken-ur"]["post"]["responses"]
