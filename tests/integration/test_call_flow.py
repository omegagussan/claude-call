import pytest
import respx
from httpx import ASGITransport, AsyncClient

from src.main import active_calls, app
from tests.mock_telnyx import build_telnyx_event

MOCK_BASE_URL = "https://api.telnyx.com/v2"


@pytest.fixture(autouse=True)
def clear_active_calls():
    active_calls.clear()


@pytest.mark.asyncio
@respx.mock
async def test_full_call_lifecycle_mocked():
    """Simulate complete call cycle: dial -> initiated -> answered -> speak ended -> hangup."""
    call_control_id = "v3:mock-call-id-999"

    # 1. Mock Telnyx API outbound endpoints
    respx.post(f"{MOCK_BASE_URL}/calls").respond(
        status_code=200,
        json={
            "data": {
                "call_control_id": call_control_id,
                "call_leg_id": "leg_111",
                "call_session_id": "sess_111",
                "is_alive": True,
                "record_type": "call",
            }
        },
    )

    speak_route = respx.post(f"{MOCK_BASE_URL}/calls/{call_control_id}/actions/speak").respond(
        status_code=200,
        json={"data": {"result": "ok"}},
    )

    hangup_route = respx.post(f"{MOCK_BASE_URL}/calls/{call_control_id}/actions/hangup").respond(
        status_code=200,
        json={"data": {"result": "ok"}},
    )

    # 2. Test via AsyncClient on FastAPI ASGI app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step A: Initiate Dial
        dial_resp = await client.post(
            "/calls/dial",
            json={"to_number": "+15559876543"},
        )
        assert dial_resp.status_code == 201
        assert dial_resp.json()["call_control_id"] == call_control_id
        assert active_calls[call_control_id]["status"] == "initiating"

        # Step B: Incoming Webhook -> call.initiated (Ringing)
        evt_initiated = build_telnyx_event("call.initiated", call_control_id)
        wh_resp1 = await client.post("/webhooks/telnyx", json=evt_initiated)
        assert wh_resp1.status_code == 200
        assert active_calls[call_control_id]["status"] == "ringing"

        # Step C: Incoming Webhook -> call.answered (Landline picked up)
        evt_answered = build_telnyx_event("call.answered", call_control_id)
        wh_resp2 = await client.post("/webhooks/telnyx", json=evt_answered)
        assert wh_resp2.status_code == 200
        assert active_calls[call_control_id]["status"] == "answered"
        # Verify our server instructed Telnyx to speak
        assert speak_route.called

        # Step D: Incoming Webhook -> call.speak.ended (Finished TTS)
        evt_speak_ended = build_telnyx_event("call.speak.ended", call_control_id)
        wh_resp3 = await client.post("/webhooks/telnyx", json=evt_speak_ended)
        assert wh_resp3.status_code == 200
        assert active_calls[call_control_id]["status"] == "message_completed"
        # Verify our server instructed Telnyx to hang up
        assert hangup_route.called

        # Step E: Incoming Webhook -> call.hangup (Terminated)
        evt_hangup = build_telnyx_event("call.hangup", call_control_id, hangup_reason="normal_clearing")
        wh_resp4 = await client.post("/webhooks/telnyx", json=evt_hangup)
        assert wh_resp4.status_code == 200
        assert active_calls[call_control_id]["status"] == "completed"
        assert active_calls[call_control_id]["hangup_reason"] == "normal_clearing"

        # Step F: Verify call state query endpoint
        status_resp = await client.get(f"/calls/{call_control_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "completed"
