import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from src.main import active_calls, app
from src.services.todo_service import todo_service
from src.services.todo_storage import InMemoryTodoStorage
from tests.mock_telnyx import build_telnyx_event

MOCK_BASE_URL = "https://api.telnyx.com/v2"


@pytest.fixture(autouse=True)
def cleanup():
    active_calls.clear()
    todo_service.set_storage(InMemoryTodoStorage())


@pytest.mark.asyncio
@respx.mock
async def test_todo_call_silence_then_push_list_pop():
    call_control_id = "v3:todo-call-999"
    user_phone = "+46709876543"

    # Mock dial
    respx.post(f"{MOCK_BASE_URL}/calls").respond(
        status_code=200,
        json={"data": {"call_control_id": call_control_id, "record_type": "call"}},
    )

    # Mock gather_using_speak
    gather_route = respx.post(f"{MOCK_BASE_URL}/calls/{call_control_id}/actions/gather_using_speak").respond(
        status_code=200,
        json={"data": {"result": "ok"}},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Initiate Todo Call
        dial_resp = await client.post(
            "/calls/todo",
            json={"to_number": {"country_code": "+46", "area_code": "70", "subscriber_number": user_phone[5:]}},
        )
        assert dial_resp.status_code == 200
        assert dial_resp.json()["mode"] == "todo_list"

        # Step 2: Call Answered -> initiates initial 5-second silence gather
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.answered", call_control_id, to=user_phone),
        )
        assert gather_route.call_count == 1
        assert active_calls[call_control_id]["status"] == "awaiting_command"

        # Step 3: User is quiet for 5s -> timeout webhook arrives
        # Expectation: server reads out options (POP, PUSH, LIST)
        evt_silence = build_telnyx_event(
            "call.gather.ended",
            call_control_id,
            to=user_phone,
            status="timeout",
            speech="",
        )
        await client.post("/webhooks/telnyx", json=evt_silence)
        assert gather_route.call_count == 2
        assert active_calls[call_control_id]["options_prompted"] is True

        # Step 4: User declares intent: "PUSH oat milk"
        evt_push = build_telnyx_event(
            "call.gather.ended",
            call_control_id,
            to=user_phone,
            speech={"transcript": "PUSH oat milk"},
        )
        await client.post("/webhooks/telnyx", json=evt_push)
        assert gather_route.call_count == 3
        # Verify stored in todo_service for this phone number
        assert await todo_service.list_items(user_phone) == ["oat milk"]

        # Push another item: "PUSH dark roast coffee"
        evt_push2 = build_telnyx_event(
            "call.gather.ended",
            call_control_id,
            to=user_phone,
            speech={"transcript": "PUSH dark roast coffee"},
        )
        await client.post("/webhooks/telnyx", json=evt_push2)
        assert await todo_service.list_items(user_phone) == ["oat milk", "dark roast coffee"]

        # Step 5: User declares intent: "LIST"
        evt_list = build_telnyx_event(
            "call.gather.ended",
            call_control_id,
            to=user_phone,
            speech={"transcript": "LIST"},
        )
        await client.post("/webhooks/telnyx", json=evt_list)
        assert active_calls[call_control_id]["last_action"] == "LIST"

        # Step 6: User declares intent: "POP" (retrieves and removes oldest item)
        evt_pop = build_telnyx_event(
            "call.gather.ended",
            call_control_id,
            to=user_phone,
            speech={"transcript": "POP"},
        )
        await client.post("/webhooks/telnyx", json=evt_pop)
        assert active_calls[call_control_id]["last_action"] == "POP"
        # Oldest item ("oat milk") removed, "dark roast coffee" remains
        assert await todo_service.list_items(user_phone) == ["dark roast coffee"]

        # Step 7: Check HTTP API for todos
        todos_resp = await client.get(f"/todos/{user_phone}")
        assert todos_resp.status_code == 200
        assert todos_resp.json()["items"] == ["dark roast coffee"]

        # Step 8: User hangs up
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.hangup", call_control_id, to=user_phone),
        )
        call_status = (await client.get(f"/calls/{call_control_id}")).json()
        assert call_status["status"] == "completed"


@pytest.mark.asyncio
@respx.mock
async def test_user_hangs_up_and_calls_again_to_retrieve_persisted_list():
    """
    Test persistence across distinct calls:
    Call 1: User pushes items to their list and hangs up.
    Call 2: User calls again from the same phone number, says LIST, and verifies their items are still there.
    """
    user_phone = "+46709876543"
    call_1_id = "v3:call-session-1"
    call_2_id = "v3:call-session-2"

    # Mock Telnyx dial for both calls
    respx.post(f"{MOCK_BASE_URL}/calls").side_effect = [
        httpx.Response(200, json={"data": {"call_control_id": call_1_id, "record_type": "call"}}),
        httpx.Response(200, json={"data": {"call_control_id": call_2_id, "record_type": "call"}}),
    ]

    # Mock gather actions for call 1 and call 2
    respx.post(f"{MOCK_BASE_URL}/calls/{call_1_id}/actions/gather_using_speak").respond(
        status_code=200, json={"data": {"result": "ok"}}
    )
    respx.post(f"{MOCK_BASE_URL}/calls/{call_2_id}/actions/gather_using_speak").respond(
        status_code=200, json={"data": {"result": "ok"}}
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # === FIRST CALL ===
        # 1. Dial call 1
        dial_resp1 = await client.post(
            "/calls/todo",
            json={"to_number": {"country_code": "+46", "area_code": "70", "subscriber_number": user_phone[5:]}},
        )
        assert dial_resp1.status_code == 200
        assert dial_resp1.json()["call_control_id"] == call_1_id

        # 2. Answer call 1
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.answered", call_1_id, to=user_phone),
        )

        # 3. User says "PUSH Apples"
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event(
                "call.gather.ended", call_1_id, to=user_phone, speech={"transcript": "PUSH Apples"}
            ),
        )

        # 4. User says "PUSH Butter"
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event(
                "call.gather.ended", call_1_id, to=user_phone, speech={"transcript": "PUSH Butter"}
            ),
        )

        # 5. User hangs up call 1
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.hangup", call_1_id, to=user_phone),
        )
        assert active_calls[call_1_id]["status"] == "completed"

        # === SECOND CALL (New call_control_id, same phone number) ===
        # 6. Dial call 2
        dial_resp2 = await client.post(
            "/calls/todo",
            json={"to_number": {"country_code": "+46", "area_code": "70", "subscriber_number": user_phone[5:]}},
        )
        assert dial_resp2.status_code == 200
        assert dial_resp2.json()["call_control_id"] == call_2_id

        # 7. Answer call 2
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.answered", call_2_id, to=user_phone),
        )

        # 8. User asks for list: "LIST"
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.gather.ended", call_2_id, to=user_phone, speech={"transcript": "LIST"}),
        )

        # Verify that Call 2 retrieved the items saved in Call 1
        call_2_history = active_calls[call_2_id]["history"]
        assert any("Apples, Butter" in entry for entry in call_2_history)

        # 9. User hangs up call 2
        await client.post(
            "/webhooks/telnyx",
            json=build_telnyx_event("call.hangup", call_2_id, to=user_phone),
        )
        assert active_calls[call_2_id]["status"] == "completed"

        # 10. Check list state is still preserved
        assert await todo_service.list_items(user_phone) == ["Apples", "Butter"]
