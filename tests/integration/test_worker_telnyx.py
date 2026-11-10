import asyncio
import json
from types import SimpleNamespace

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import active_calls, app
from tests.mock_telnyx import build_telnyx_event

NUMBER = {"country_code": "+46", "area_code": "8", "subscriber_number": "12345678"}
ENV = {
    "TELNYX_API_KEY": "test-worker-provider-key",
    "TELNYX_CONNECTION_ID": "worker-application",
    "TELNYX_FROM_NUMBER": "+12025550199",
}


def bound_app(env):
    async def worker_app(scope, receive, send):
        await app(dict(scope, env=env), receive, send)

    return worker_app


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/calls/dial", "/calls/froken-ur", "/calls/todo"])
@pytest.mark.parametrize("object_binding", [False, True])
@respx.mock
async def test_worker_dial_uses_request_bindings(endpoint, object_binding):
    call_id = f"worker-{endpoint}-{object_binding}"
    route = respx.post("https://api.telnyx.com/v2/calls").respond(200, json={"data": {"call_control_id": call_id}})
    env = SimpleNamespace(**ENV) if object_binding else ENV
    try:
        async with AsyncClient(transport=ASGITransport(app=bound_app(env)), base_url="http://test") as client:
            response = await client.post(endpoint, json={"to_number": NUMBER})
        assert response.status_code in (200, 201)
        request = route.calls.last.request
        assert request.headers["Authorization"] == f"Bearer {ENV['TELNYX_API_KEY']}"
        payload = json.loads(request.content)
        assert payload["from"] == ENV["TELNYX_FROM_NUMBER"]
        assert payload["connection_id"] == ENV["TELNYX_CONNECTION_ID"]
        assert "webhook_url" not in payload
    finally:
        active_calls.pop(call_id, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", list(ENV))
@respx.mock
async def test_missing_worker_setting_returns_503_without_provider_request(missing):
    env = {key: value for key, value in ENV.items() if key != missing}
    async with AsyncClient(transport=ASGITransport(app=bound_app(env)), base_url="http://test") as client:
        response = await client.post("/calls/froken-ur", json={"to_number": NUMBER})
    assert response.status_code == 503
    assert response.json()["detail"] == f"Missing Worker configuration: {missing}"
    assert not respx.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call_type", "event_type", "action"),
    [
        ("generic", "call.answered", "speak"),
        ("generic", "call.speak.ended", "hangup"),
        ("froken_ur", "call.answered", "speak"),
        ("froken_ur", "call.speak.ended", "speak"),
        ("todo_list", "call.answered", "gather_using_speak"),
        ("todo_list", "call.gather.ended", "gather_using_speak"),
    ],
)
@respx.mock
async def test_concurrent_webhooks_keep_worker_credentials_isolated(call_type, event_type, action):
    ids = ["worker-config-a", "worker-config-b"]
    keys = ["test-provider-a", "test-provider-b"]
    routes = [
        respx.post(f"https://api.telnyx.com/v2/calls/{cid}/actions/{action}").respond(200, json={"data": {}})
        for cid in ids
    ]
    for cid in ids:
        active_calls[cid] = {"type": call_type, "pause_seconds": 0}
    try:
        async with (
            AsyncClient(
                transport=ASGITransport(app=bound_app(ENV | {"TELNYX_API_KEY": keys[0]})), base_url="http://test"
            ) as first,
            AsyncClient(
                transport=ASGITransport(app=bound_app(ENV | {"TELNYX_API_KEY": keys[1]})), base_url="http://test"
            ) as second,
        ):
            responses = await asyncio.gather(
                first.post("/webhooks/telnyx", json=build_telnyx_event(event_type, ids[0])),
                second.post("/webhooks/telnyx", json=build_telnyx_event(event_type, ids[1])),
            )
        assert all(response.status_code == 200 for response in responses)
        for route, key in zip(routes, keys, strict=True):
            assert route.calls.last.request.headers["Authorization"] == f"Bearer {key}"
    finally:
        for cid in ids:
            active_calls.pop(cid, None)


@pytest.mark.asyncio
@respx.mock
async def test_local_dial_reads_current_settings(monkeypatch):
    monkeypatch.setattr(settings, "telnyx_api_key", "test-local-provider-key")
    monkeypatch.setattr(settings, "telnyx_connection_id", "local-application")
    monkeypatch.setattr(settings, "telnyx_from_number", "+12025550198")
    route = respx.post("https://api.telnyx.com/v2/calls").respond(200, json={"data": {}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/calls/dial", json={"to_number": NUMBER})
    assert response.status_code == 201
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-local-provider-key"
    payload = json.loads(request.content)
    assert payload["connection_id"] == "local-application"
    assert payload["from"] == "+12025550198"
