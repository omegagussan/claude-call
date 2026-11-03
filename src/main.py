import asyncio
import base64
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from src.services.time_service import format_froken_ur_speech
from src.services.todo_service import todo_service
from src.services.todo_speech import OPTIONS_PROMPT, parse_todo_intent
from src.telnyx_client import telnyx_client
from src.version import __version__

app = FastAPI(
    title="Claude Call - Fröken Ur & Telnyx",
    version=__version__,
)

# In-memory tracking for call state
active_calls: dict[str, dict[str, Any]] = {}


class CallRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None


class FrokenUrRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None
    pause_seconds: float = 3.0


class TodoCallRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None


@app.get("/")
async def root():
    return {"message": "Claude Call Service"}


@app.get("/health")
async def health():
    """Health check endpoint for container probes and load balancers."""
    return {"status": "healthy", "version": app.version}


@app.get("/todos/{phone_number}")
async def get_user_todos(phone_number: str):
    """Retrieve current todo/shopping list items for a phone number."""
    return {"phone_number": phone_number, "items": todo_service.list_items(phone_number)}


@app.post("/calls/dial", status_code=status.HTTP_201_CREATED)
async def make_call(request: CallRequest):
    """Trigger a generic outbound call to a landline via Telnyx."""
    try:
        kwargs: dict[str, Any] = {"to_number": request.to_number}
        if request.from_number:
            kwargs["from_number"] = request.from_number
        if request.webhook_url:
            kwargs["webhook_url"] = request.webhook_url

        result = await telnyx_client.dial(**kwargs)
        data = result.get("data", {})
        call_control_id = data.get("call_control_id")

        if call_control_id:
            active_calls[call_control_id] = {
                "type": "generic",
                "status": "initiating",
                "to": request.to_number,
                "data": data,
            }

        return {
            "status": "success",
            "call_control_id": call_control_id,
            "call_leg_id": data.get("call_leg_id"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/calls/froken-ur", status_code=status.HTTP_201_CREATED)
async def start_froken_ur(request: FrokenUrRequest):
    """
    Start Fröken Ur call: dials the given number and repeatedly announces the
    time in Stockholm with pauses until the user hangs up.
    """
    try:
        client_state_str = base64.b64encode(b"froken_ur").decode("utf-8")
        kwargs: dict[str, Any] = {
            "to_number": request.to_number,
            "client_state": client_state_str,
        }
        if request.from_number:
            kwargs["from_number"] = request.from_number
        if request.webhook_url:
            kwargs["webhook_url"] = request.webhook_url

        result = await telnyx_client.dial(**kwargs)
        data = result.get("data", {})
        call_control_id = data.get("call_control_id")

        if call_control_id:
            active_calls[call_control_id] = {
                "type": "froken_ur",
                "status": "initiating",
                "to": request.to_number,
                "pause_seconds": request.pause_seconds,
                "time_announcements_count": 0,
                "last_estimated_duration": 0.0,
                "history": [],
            }

        return {
            "status": "success",
            "mode": "froken_ur",
            "call_control_id": call_control_id,
            "call_leg_id": data.get("call_leg_id"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/calls/todo", status_code=status.HTTP_201_CREATED)
async def start_todo_call(request: TodoCallRequest):
    """
    Start Todo List voice call: allows user to POP, PUSH or LIST items
    via speech interaction.
    """
    try:
        client_state_str = base64.b64encode(b"todo_list").decode("utf-8")
        kwargs: dict[str, Any] = {
            "to_number": request.to_number,
            "client_state": client_state_str,
        }
        if request.from_number:
            kwargs["from_number"] = request.from_number
        if request.webhook_url:
            kwargs["webhook_url"] = request.webhook_url

        result = await telnyx_client.dial(**kwargs)
        data = result.get("data", {})
        call_control_id = data.get("call_control_id")

        if call_control_id:
            active_calls[call_control_id] = {
                "type": "todo_list",
                "status": "initiating",
                "to": request.to_number,
                "options_prompted": False,
                "last_action": None,
                "history": [],
            }

        return {
            "status": "success",
            "mode": "todo_list",
            "call_control_id": call_control_id,
            "call_leg_id": data.get("call_leg_id"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/webhooks/telnyx")
async def telnyx_webhook(event: dict[str, Any]):
    """Handle incoming call control webhooks from Telnyx."""
    event_data = event.get("data", {})
    event_type = event_data.get("event_type")
    payload = event_data.get("payload", {})
    call_control_id = payload.get("call_control_id")

    if not call_control_id:
        return {"received": True, "warning": "missing call_control_id"}

    if call_control_id not in active_calls:
        client_state_raw = payload.get("client_state")
        call_type = "generic"
        if client_state_raw:
            try:
                decoded = base64.b64decode(client_state_raw).decode("utf-8")
                if "froken_ur" in decoded:
                    call_type = "froken_ur"
                elif "todo_list" in decoded:
                    call_type = "todo_list"
            except Exception:
                pass
        active_calls[call_control_id] = {
            "type": call_type,
            "status": "unknown",
            "to": payload.get("to", ""),
            "options_prompted": False,
            "history": [],
        }

    call_state = active_calls[call_control_id]
    call_state["last_event"] = event_type
    call_type = call_state.get("type", "generic")
    user_phone = call_state.get("to") or payload.get("to", "")

    if event_type == "call.initiated":
        call_state["status"] = "ringing"

    elif event_type == "call.answered":
        call_state["status"] = "answered"
        if call_type == "froken_ur":
            speech_text, est_duration = format_froken_ur_speech()
            call_state["time_announcements_count"] = call_state.get("time_announcements_count", 0) + 1
            call_state["last_estimated_duration"] = est_duration
            call_state.setdefault("history", []).append({"text": speech_text, "estimated_duration": est_duration})
            await telnyx_client.speak(
                call_control_id=call_control_id,
                payload_text=speech_text,
                language="sv-SE",
                voice="female",
            )
        elif call_type == "todo_list":
            # Start initial 5-second silence gather for user command (POP, PUSH, LIST)
            # If user stays quiet for 5s, call.gather.ended event arrives with timeout/silence
            call_state["status"] = "awaiting_command"
            await telnyx_client.gather_using_speak(
                call_control_id=call_control_id,
                payload_text="",  # Quiet listen for 5s initially
                timeout_millis=5000,
            )
        else:
            await telnyx_client.speak(
                call_control_id=call_control_id,
                payload_text="Hello, this is Claude Call connecting via Telnyx.",
                language="en-US",
                voice="female",
            )

    elif event_type == "call.gather.ended":
        if call_type == "todo_list":
            # Extract user speech from payload or digits
            speech_text = (
                payload.get("speech", {}).get("transcript", "")
                if isinstance(payload.get("speech"), dict)
                else payload.get("speech", "")
            )
            if not speech_text:
                speech_text = payload.get("digits", "")

            command, argument = parse_todo_intent(speech_text)
            call_state["last_detected_command"] = command
            call_state["last_detected_argument"] = argument

            if command == "SILENCE" or (not speech_text and payload.get("status") in ("timeout", "valid")):
                # User was quiet for 5 seconds -> announce options and listen again
                call_state["options_prompted"] = True
                call_state["status"] = "prompting_options"
                await telnyx_client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text=OPTIONS_PROMPT,
                    timeout_millis=10000,
                )

            elif command == "POP":
                popped = todo_service.pop(user_phone)
                call_state["last_action"] = "POP"
                if popped:
                    msg = f"Popped {popped} from your list."
                else:
                    msg = "Your list is empty. Nothing to pop."
                call_state.setdefault("history", []).append(msg)
                await telnyx_client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text=f"{msg} What would you like to do next?",
                    timeout_millis=10000,
                )

            elif command == "PUSH":
                call_state["last_action"] = "PUSH"
                if not argument:
                    # User only said PUSH; ask for the item
                    call_state["awaiting_push_item"] = True
                    await telnyx_client.gather_using_speak(
                        call_control_id=call_control_id,
                        payload_text="What item would you like to add?",
                        timeout_millis=10000,
                    )
                else:
                    todo_service.push(user_phone, argument)
                    call_state["awaiting_push_item"] = False
                    msg = f"Added {argument} to your list."
                    call_state.setdefault("history", []).append(msg)
                    await telnyx_client.gather_using_speak(
                        call_control_id=call_control_id,
                        payload_text=f"{msg} Next command?",
                        timeout_millis=10000,
                    )

            elif command == "LIST":
                call_state["last_action"] = "LIST"
                items = todo_service.list_items(user_phone)
                if not items:
                    msg = "Your list has no items."
                else:
                    items_str = ", ".join(items)
                    msg = f"Your list has {len(items)} items: {items_str}."
                call_state.setdefault("history", []).append(msg)
                await telnyx_client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text=f"{msg} Next command?",
                    timeout_millis=10000,
                )

            elif call_state.get("awaiting_push_item") and speech_text:
                # User was prompted for push item and replied
                todo_service.push(user_phone, speech_text.strip())
                call_state["awaiting_push_item"] = False
                msg = f"Added {speech_text.strip()} to your list."
                call_state.setdefault("history", []).append(msg)
                await telnyx_client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text=f"{msg} Next command?",
                    timeout_millis=10000,
                )

            else:
                # Unknown command
                await telnyx_client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text=f"I did not understand. {OPTIONS_PROMPT}",
                    timeout_millis=10000,
                )

    elif event_type == "call.speak.ended":
        if call_type == "froken_ur":
            if call_state.get("status") != "completed":
                call_state["status"] = "looping"
                pause = call_state.get("pause_seconds", 3.0)

                async def _delayed_next_announcement(cid: str, wait_secs: float) -> None:
                    if wait_secs > 0:
                        await asyncio.sleep(wait_secs)
                    st = active_calls.get(cid)
                    if st and st.get("status") != "completed":
                        speech_text, est_duration = format_froken_ur_speech()
                        st["time_announcements_count"] = st.get("time_announcements_count", 0) + 1
                        st["last_estimated_duration"] = est_duration
                        st.setdefault("history", []).append({"text": speech_text, "estimated_duration": est_duration})
                        await telnyx_client.speak(
                            call_control_id=cid,
                            payload_text=speech_text,
                            language="sv-SE",
                            voice="female",
                        )

                # If wait_secs is 0 (e.g. test environment), run synchronously; otherwise schedule non-blocking task
                if pause == 0:
                    await _delayed_next_announcement(call_control_id, 0.0)
                else:
                    asyncio.create_task(_delayed_next_announcement(call_control_id, pause))
        elif call_type == "generic":
            call_state["status"] = "message_completed"
            await telnyx_client.hangup(call_control_id=call_control_id)

    elif event_type == "call.hangup":
        call_state["status"] = "completed"
        call_state["hangup_reason"] = payload.get("hangup_reason")

    return {
        "received": True,
        "call_control_id": call_control_id,
        "status": call_state.get("status"),
        "type": call_type,
    }


@app.get("/calls/{call_control_id}")
async def get_call_status(call_control_id: str):
    """Check current tracked state of a call."""
    if call_control_id not in active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    return active_calls[call_control_id]
