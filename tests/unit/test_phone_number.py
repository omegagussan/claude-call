import json

import pytest
import respx
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.config import settings
from src.main import active_calls, app
from src.models import PhoneNumber

NUMBER = {"country_code": "+46", "area_code": "8", "subscriber_number": "12345678"}


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (NUMBER, "+46812345678"),
        ({"country_code": "+46", "area_code": "70", "subscriber_number": "1234567"}, "+46701234567"),
        ({"country_code": "+1", "area_code": "202", "subscriber_number": "5550123"}, "+12025550123"),
        ({"country_code": "+39", "area_code": "02", "subscriber_number": "12345678"}, "+390212345678"),
    ],
)
def test_phone_number_e164(parts, expected):
    assert PhoneNumber(**parts).e164 == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"country_code": "+999"},
        {"country_code": "46"},
        {"area_code": "08"},
        {"area_code": "81", "subscriber_number": "2345678"},
        {"subscriber_number": "123"},
        {"subscriber_number": "abc"},
        {"subscriber_number": "1" * 16},
        {"subscriber_number": 12345678},
        {"subscriber_number": "１２３４５６７８"},
        {"extension": "123"},
    ],
)
def test_phone_number_rejects_invalid_components(changes):
    with pytest.raises(ValidationError):
        PhoneNumber.model_validate(NUMBER | changes)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/calls/dial", "/calls/froken-ur", "/calls/todo"])
@respx.mock
async def test_call_endpoint_uses_e164_and_server_caller_id(endpoint, monkeypatch):
    monkeypatch.setattr(settings, "telnyx_from_number", "+12025550199")
    call_id = f"phone-test-{endpoint}"
    route = respx.post("https://api.telnyx.com/v2/calls").respond(200, json={"data": {"call_control_id": call_id}})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(endpoint, json={"to_number": NUMBER})
        assert response.status_code in (200, 201)
        payload = json.loads(route.calls.last.request.content)
        assert payload["to"] == "+46812345678"
        assert payload["from"] == "+12025550199"
        assert "webhook_url" not in payload
        assert active_calls[call_id]["to"] == "+46812345678"
    finally:
        active_calls.pop(call_id, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/calls/dial", "/calls/froken-ur", "/calls/todo"])
@pytest.mark.parametrize(
    "body",
    [
        {"to_number": "+46812345678"},
        {"to_number": NUMBER, "from_number": "+12025550199"},
        {"to_number": NUMBER, "webhook_url": "https://example.com/webhooks/telnyx"},
        {"to_number": NUMBER | {"area_code": "08"}},
    ],
)
@respx.mock
async def test_invalid_call_request_never_reaches_telnyx(endpoint, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(endpoint, json=body)
    assert response.status_code == 422
    assert len(respx.calls) == 0


def test_openapi_exposes_phone_object_without_caller_override():
    schema = app.openapi()
    assert schema["info"]["version"] == "0.4.0"
    for model in ("CallRequest", "FrokenUrRequest", "TodoCallRequest"):
        definition = schema["components"]["schemas"][model]
        assert definition["properties"]["to_number"]["$ref"].endswith("/PhoneNumber")
        assert "from_number" not in definition["properties"]
        assert "webhook_url" not in definition["properties"]
        assert definition["additionalProperties"] is False
