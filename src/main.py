import asyncio
import base64
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from telnyx_client import telnyx_client
from services.time_service import format_froken_ur_speech

app = FastAPI(title="Claude Call - Fröken Ur & Telnyx")

# In-memory tracking for call state
active_calls: Dict[str, Dict[str, Any]] = {}


class CallRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None


class FrokenUrRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None
    pause_seconds: float = 3.0


@app.get("/")
async def root():
    return {"message": "Claude Call Service"}


@app.post("/calls/dial", status_code=status.HTTP_201_CREATED)
async def make_call(request: CallRequest):
    """Trigger a generic outbound call to a landline via Telnyx."""
    try:
        kwargs: Dict[str, Any] = {"to_number": request.to_number}
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calls/froken-ur", status_code=status.HTTP_201_CREATED)
async def start_froken_ur(request: FrokenUrRequest):
    """
    Start Fröken Ur call: dials the given number and repeatedly announces the
    time in Stockholm with pauses until the user hangs up.
    """
    try:
        client_state_str = base64.b64encode(b"froken_ur").decode("utf-8")
        kwargs: Dict[str, Any] = {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/telnyx")
async def telnyx_webhook(event: Dict[str, Any]):
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
            except Exception:
                pass
        active_calls[call_control_id] = {
            "type": call_type,
            "pause_seconds": 3.0,
            "time_announcements_count": 0,
            "last_estimated_duration": 0.0,
            "history": [],
        }

    call_state = active_calls[call_control_id]
    call_state["last_event"] = event_type
    call_type = call_state.get("type", "generic")

    if event_type == "call.initiated":
        call_state["status"] = "ringing"

    elif event_type == "call.answered":
        call_state["status"] = "answered"
        if call_type == "froken_ur":
            speech_text, est_duration = format_froken_ur_speech()
            call_state["time_announcements_count"] += 1
            call_state["last_estimated_duration"] = est_duration
            call_state["history"].append({"text": speech_text, "estimated_duration": est_duration})
            await telnyx_client.speak(
                call_control_id=call_control_id,
                payload_text=speech_text,
                language="sv-SE",
                voice="female",
            )
        else:
            await telnyx_client.speak(
                call_control_id=call_control_id,
                payload_text="Hello, this is Claude Call connecting via Telnyx.",
                language="en-US",
                voice="female",
            )

    elif event_type == "call.speak.ended":
        if call_type == "froken_ur":
            if call_state.get("status") != "completed":
                call_state["status"] = "looping"
                pause = call_state.get("pause_seconds", 3.0)
                if pause > 0:
                    await asyncio.sleep(pause)

                if call_state.get("status") != "completed":
                    speech_text, est_duration = format_froken_ur_speech()
                    call_state["time_announcements_count"] += 1
                    call_state["last_estimated_duration"] = est_duration
                    call_state["history"].append({"text": speech_text, "estimated_duration": est_duration})
                    await telnyx_client.speak(
                        call_control_id=call_control_id,
                        payload_text=speech_text,
                        language="sv-SE",
                        voice="female",
                    )
        else:
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
