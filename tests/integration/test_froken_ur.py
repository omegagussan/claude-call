import asyncio

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
async def test_froken_ur_call_flow_loop_and_hangup():
    call_control_id = "v3:froken-ur-call-123"

    # Mock Telnyx REST endpoints
    dial_route = respx.post(f"{MOCK_BASE_URL}/calls").respond(
        status_code=200,
        json={
            "data": {
                "call_control_id": call_control_id,
                "call_leg_id": "leg_froken",
                "call_session_id": "sess_froken",
                "is_alive": True,
                "record_type": "call",
            }
        },
    )

    speak_route = respx.post(f"{MOCK_BASE_URL}/calls/{call_control_id}/actions/speak").respond(
        status_code=200,
        json={"data": {"result": "ok"}},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Initiate Fröken Ur call (set pause_seconds=0 for fast test execution)
        dial_resp = await client.post(
            "/calls/froken-ur",
            json={
                "to_number": {"country_code": "+46", "area_code": "8", "subscriber_number": "12345678"},
                "pause_seconds": 0.0,
            },
        )
        assert dial_resp.status_code == 201
        data = dial_resp.json()
        assert data["mode"] == "froken_ur"
        assert data["call_control_id"] == call_control_id
        assert dial_route.called

        # 2. Webhook: Call initiated (ringing)
        evt_init = build_telnyx_event("call.initiated", call_control_id)
        r_init = await client.post("/webhooks/telnyx", json=evt_init)
        assert r_init.status_code == 200
        assert active_calls[call_control_id]["status"] == "ringing"

        # 3. Webhook: Call answered (user picks up landline)
        # Should trigger first time announcement with estimated duration
        evt_ans = build_telnyx_event("call.answered", call_control_id)
        r_ans = await client.post("/webhooks/telnyx", json=evt_ans)
        assert r_ans.status_code == 200
        assert active_calls[call_control_id]["time_announcements_count"] == 1
        assert active_calls[call_control_id]["last_estimated_duration"] > 0
        assert speak_route.call_count == 1

        # 4. Webhook: First speak ended
        # Progresses to a second announcement
        evt_speak_1 = build_telnyx_event("call.speak.ended", call_control_id)
        r_spk1 = await client.post("/webhooks/telnyx", json=evt_speak_1)
        assert r_spk1.status_code == 200
        assert active_calls[call_control_id]["time_announcements_count"] == 2
        assert speak_route.call_count == 2

        # 5. Webhook: Second speak ended
        # Progresses to a third time announcement
        evt_speak_2 = build_telnyx_event("call.speak.ended", call_control_id)
        r_spk2 = await client.post("/webhooks/telnyx", json=evt_speak_2)
        assert r_spk2.status_code == 200
        assert active_calls[call_control_id]["time_announcements_count"] == 3
        assert speak_route.call_count == 3

        # Verify announcements contain expected phrase and calculated duration
        for item in active_calls[call_control_id]["history"]:
            assert "Vid ett pip är klockan" in item["text"]
            assert item["estimated_duration"] > 0

        # 6. Webhook: User hangs up
        evt_hangup = build_telnyx_event("call.hangup", call_control_id, hangup_reason="call_rejected")
        r_hup = await client.post("/webhooks/telnyx", json=evt_hangup)
        assert r_hup.status_code == 200
        assert active_calls[call_control_id]["status"] == "completed"

        # Check call status endpoint
        status_resp = await client.get(f"/calls/{call_control_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["type"] == "froken_ur"
        assert status_data["status"] == "completed"
        assert status_data["time_announcements_count"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_froken_ur_repeats_at_least_twice_during_call():
    """Integration test verifying that Fröken Ur repeats the time announcement at least 2 times before user hangup."""
    call_control_id = "v3:froken-ur-repeat-test"

    # Mock Telnyx API
    respx.post(f"{MOCK_BASE_URL}/calls").respond(
        status_code=200,
        json={"data": {"call_control_id": call_control_id, "record_type": "call"}},
    )
    speak_route = respx.post(f"{MOCK_BASE_URL}/calls/{call_control_id}/actions/speak").respond(
        status_code=200,
        json={"data": {"result": "ok"}},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Dial Fröken Ur
        dial_resp = await client.post(
            "/calls/froken-ur",
            json={
                "to_number": {"country_code": "+46", "area_code": "8", "subscriber_number": "11223344"},
                "pause_seconds": 0.0,
            },
        )
        assert dial_resp.status_code == 201

        # Step 2: Answer the call -> 1st announcement
        await client.post("/webhooks/telnyx", json=build_telnyx_event("call.answered", call_control_id))
        assert speak_route.call_count == 1

        # Step 3: First announcement ends -> triggers 2nd announcement (repeat >= 2)
        await client.post("/webhooks/telnyx", json=build_telnyx_event("call.speak.ended", call_control_id))
        assert speak_route.call_count >= 2

        # Step 4: Verify count and progression
        status_resp = await client.get(f"/calls/{call_control_id}")
        assert status_resp.status_code == 200
        call_state = status_resp.json()
        assert call_state["time_announcements_count"] >= 2
        assert len(call_state["history"]) >= 2

        # Step 5: User hangs up
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.hangup", call_control_id, hangup_reason="normal_clearing"),
        )
        final_status = (await client.get(f"/calls/{call_control_id}")).json()
        assert final_status["status"] == "completed"
        assert final_status["time_announcements_count"] >= 2


@pytest.mark.asyncio
@respx.mock
async def test_concurrent_health_checks_during_active_froken_ur_call():
    """
    Simulates a single worker event loop processing an active Fröken Ur call (with a real pause)
    and verifies that concurrent /health probes respond instantly (<50ms) without waiting
    for the call's pause or speak steps to complete.
    """
    call_control_id = "v3:concurrent-froken-health"
    user_phone = "+46812345678"

    respx.post(f"{MOCK_BASE_URL}/calls").respond(
        status_code=200,
        json={"data": {"call_control_id": call_control_id, "record_type": "call"}},
    )
    respx.post(f"{MOCK_BASE_URL}/calls/{call_control_id}/actions/speak").respond(
        status_code=200,
        json={"data": {"result": "ok"}},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start Fröken Ur with a 1.0s pause between repetitions
        dial_resp = await client.post(
            "/calls/froken-ur",
            json={
                "to_number": {"country_code": "+46", "area_code": "8", "subscriber_number": "12345678"},
                "pause_seconds": 1.0,
            },
        )
        assert dial_resp.status_code == 201

        # User answers the call (1st speech trigger)
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.answered", call_control_id, to=user_phone),
        )

        # First speak finishes -> triggers 1.0s background pause task
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.speak.ended", call_control_id, to=user_phone),
        )

        # Call state should be in 'looping' state while the 1.0s pause ticks
        assert active_calls[call_control_id]["status"] == "looping"

        # Concurrently fire multiple /health requests on the same single event loop
        # They must execute immediately and return 200 without waiting for the 1.0s pause
        health_responses = await asyncio.gather(
            client.get("/health"),
            client.get("/health"),
            client.get("/health"),
            client.get("/health"),
            client.get("/health"),
        )

        for resp in health_responses:
            assert resp.status_code == 200
            assert resp.json() == {"status": "healthy", "version": app.version}

        # Wait for the 1.0s pause to complete and trigger the second speech
        await asyncio.sleep(1.1)
        assert active_calls[call_control_id]["time_announcements_count"] >= 2
