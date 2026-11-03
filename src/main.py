from typing import Any, Dict
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from telnyx_client import telnyx_client

app = FastAPI(title="Claude Call - Telnyx Integration")

# In-memory tracking for call state during local runs/tests
active_calls: Dict[str, Dict[str, Any]] = {}


class CallRequest(BaseModel):
    to_number: str
    from_number: str | None = None
    webhook_url: str | None = None


@app.get("/")
async def root():
    return {"message": "Claude Call Service"}


@app.post("/calls/dial", status_code=status.HTTP_201_CREATED)
async def make_call(request: CallRequest):
    """Trigger an outbound call to a landline via Telnyx."""
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
        active_calls[call_control_id] = {}

    active_calls[call_control_id]["last_event"] = event_type

    if event_type == "call.initiated":
        active_calls[call_control_id]["status"] = "ringing"

    elif event_type == "call.answered":
        active_calls[call_control_id]["status"] = "answered"
        # Example action: when the landline answers, speak a greeting
        await telnyx_client.speak(
            call_control_id=call_control_id,
            payload_text="Hello, this is Claude Call connecting via Telnyx.",
        )

    elif event_type == "call.speak.ended":
        active_calls[call_control_id]["status"] = "message_completed"
        # Hang up after speaking
        await telnyx_client.hangup(call_control_id=call_control_id)

    elif event_type == "call.hangup":
        active_calls[call_control_id]["status"] = "completed"
        active_calls[call_control_id]["hangup_reason"] = payload.get("hangup_reason")

    return {"received": True, "call_control_id": call_control_id, "status": active_calls[call_control_id]["status"]}


@app.get("/calls/{call_control_id}")
async def get_call_status(call_control_id: str):
    """Check current tracked state of a call."""
    if call_control_id not in active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    return active_calls[call_control_id]
