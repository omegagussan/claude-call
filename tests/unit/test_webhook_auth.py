import base64
import time
from types import SimpleNamespace

import pytest
from ecdsa import Ed25519, SigningKey
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import active_calls, app
from src.webhook_auth import verify_telnyx_signature

BODY = b'{"data": {"event_type": "call.initiated", "payload": {"call_control_id": "signed-webhook"}}}'


@pytest.fixture
def signing_key(monkeypatch):
    app.dependency_overrides.pop(verify_telnyx_signature)
    key = SigningKey.generate(curve=Ed25519)
    monkeypatch.setattr(settings, "telnyx_public_key", base64.b64encode(key.verifying_key.to_string()).decode())
    yield key
    active_calls.pop("signed-webhook", None)


def headers(key, timestamp=None, body=BODY):
    timestamp = str(int(time.time())) if timestamp is None else timestamp
    signature = key.sign(timestamp.encode() + b"|" + body)
    return {
        "content-type": "application/json",
        "telnyx-timestamp": timestamp,
        "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
    }


@pytest.mark.asyncio
async def test_valid_raw_body_signature_requires_no_api_key(signing_key, monkeypatch):
    monkeypatch.setattr(settings, "api_key_auth_enabled", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhooks/telnyx", content=BODY, headers=headers(signing_key))
    assert response.status_code == 200
    assert active_calls["signed-webhook"]["status"] == "ringing"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "base64", "tampered", "wrong_key", "stale", "future", "timestamp"])
async def test_invalid_signature_has_no_side_effects(signing_key, failure):
    h = headers(signing_key)
    body = BODY
    if failure == "missing":
        h = {"content-type": "application/json"}
    elif failure == "base64":
        h["telnyx-signature-ed25519"] = "not-base64!"
    elif failure == "tampered":
        body = BODY.replace(b"call.initiated", b"call.answered")
    elif failure == "wrong_key":
        h = headers(SigningKey.generate(curve=Ed25519))
    elif failure in ("stale", "future"):
        h = headers(signing_key, str(int(time.time()) + (-600 if failure == "stale" else 600)))
    else:
        h["telnyx-timestamp"] = "nan"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhooks/telnyx", content=body, headers=h)
    assert response.status_code == 401
    assert "signed-webhook" not in active_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("public_key", [None, "", "invalid!", base64.b64encode(b"short").decode()])
async def test_unconfigured_key_fails_closed(signing_key, monkeypatch, public_key):
    monkeypatch.setattr(settings, "telnyx_public_key", public_key)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhooks/telnyx", content=BODY, headers=headers(signing_key))
    assert response.status_code == 503
    assert "signed-webhook" not in active_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("object_env", [False, True])
async def test_worker_key_used_instead_of_local_key(signing_key, object_env):
    worker_key = SigningKey.generate(curve=Ed25519)
    env = {
        "TELNYX_PUBLIC_KEY": base64.b64encode(worker_key.verifying_key.to_string()).decode(),
        "TELNYX_API_KEY": "test-provider-key",
        "TELNYX_CONNECTION_ID": "test-connection",
        "TELNYX_FROM_NUMBER": "+12025550199",
    }

    async def bound_app(scope, receive, send):
        await app(dict(scope, env=SimpleNamespace(**env) if object_env else env), receive, send)

    async with AsyncClient(transport=ASGITransport(app=bound_app), base_url="http://test") as client:
        response = await client.post("/webhooks/telnyx", content=BODY, headers=headers(worker_key))
    assert response.status_code == 200
