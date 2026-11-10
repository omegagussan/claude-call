import io
import json
import logging

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from src.log_config import configure_logging
from src.main import active_calls, app
from src.telnyx_client import TelnyxClient
from tests.mock_telnyx import build_telnyx_event


@pytest.fixture
def application_output(monkeypatch):
    configure_logging()
    handler = next(h for h in logging.getLogger("src").handlers if h.get_name() == "application-json")
    output = io.StringIO()
    monkeypatch.setattr(handler, "stream", output)
    return output


def records(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_logging_setup_is_idempotent_and_streams_json(application_output):
    configure_logging()
    configure_logging()
    logging.getLogger("src.test").info("test_event", extra={"action": "test"})
    assert len(records(application_output)) == 1
    assert records(application_output)[0]["action"] == "test"


@pytest.mark.asyncio
@respx.mock
async def test_provider_rejection_logs_status_and_codes_without_sensitive_data(application_output):
    respx.post("https://api.telnyx.com/v2/calls").respond(
        403,
        json={
            "errors": [
                {"code": "10010", "detail": "private provider detail +46812345678"},
                {"code": "private-value"},
            ]
        },
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/calls/froken-ur",
            json={"to_number": {"country_code": "+46", "area_code": "8", "subscriber_number": "12345678"}},
        )
    assert response.status_code == 500
    rejection = next(record for record in records(application_output) if record["message"] == "telnyx_rejected")
    assert rejection["status_code"] == 403
    assert rejection["provider_error_codes"] == ["10010"]
    text = application_output.getvalue()
    for private in ("+46812345678", "private provider detail", "private-value", "Authorization"):
        assert private not in text


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_is_logged_and_reraised(application_output):
    respx.post("https://api.telnyx.com/v2/calls").mock(side_effect=httpx.ConnectError("private connection detail"))
    with pytest.raises(httpx.ConnectError):
        await TelnyxClient(api_key="private-test-key").dial("+46812345678")
    error = records(application_output)[-1]
    assert error["message"] == "telnyx_transport_error"
    assert error["error_type"] == "ConnectError"
    assert "private" not in application_output.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_webhook_application_events_stream_without_payload(application_output):
    call_id = "logging-test-call"
    event = build_telnyx_event("call.initiated", call_id, to="+46812345678")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/webhooks/telnyx", json=event)
        assert response.status_code == 200
        logs = records(application_output)
        assert [record["message"] for record in logs] == ["webhook_received", "webhook_processed"]
        assert logs[-1]["call_status"] == "ringing"
        assert logs[-1]["call_control_id"] == call_id
        assert "+46812345678" not in application_output.getvalue()
    finally:
        active_calls.pop(call_id, None)
