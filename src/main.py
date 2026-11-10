import base64
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status

from src.auth import verify_api_key
from src.callbacks.router import webhook_router
from src.models import CallRequest, FrokenUrRequest, TodoCallRequest
from src.services.todo_service import todo_service
from src.telnyx_client import telnyx_client
from src.version import __version__

app = FastAPI(
    title="Claude Call - Fröken Ur & Telnyx",
    version=__version__,
)

# In-memory tracking for call state
active_calls: dict[str, dict[str, Any]] = {}


@app.get("/")
async def root():
    return {"message": "Claude Call Service"}


@app.get("/health")
async def health():
    """Health check endpoint for container probes and load balancers."""
    return {"status": "healthy", "version": app.version}


@app.get("/todos/{phone_number}", dependencies=[Depends(verify_api_key)])
async def get_user_todos(phone_number: str):
    """Retrieve current todo/shopping list items for a phone number."""
    return {"phone_number": phone_number, "items": todo_service.list_items(phone_number)}


@app.post("/calls/dial", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key)])
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


@app.post("/calls/froken-ur", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key)])
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


@app.post("/calls/todo", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_api_key)])
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
    """Handle incoming call control webhooks by delegating to WebhookRouter."""
    event_data = event.get("data", {})
    event_type = event_data.get("event_type", "")
    payload = event_data.get("payload", {})
    call_control_id = payload.get("call_control_id")

    if not call_control_id:
        return {"received": True, "warning": "missing call_control_id"}

    if call_control_id not in active_calls:
        client_state_raw = payload.get("client_state")
        call_type = webhook_router.resolve_call_type(client_state_raw)
        active_calls[call_control_id] = {
            "type": call_type,
            "status": "unknown",
            "to": payload.get("to", ""),
            "options_prompted": False,
            "pause_seconds": 3.0,
            "history": [],
        }

    call_state = active_calls[call_control_id]
    call_state["last_event"] = event_type

    # Dispatch to the application callback class (FrokenUrCallback, TodoListCallback, GenericCallback)
    await webhook_router.dispatch(
        event_type=event_type,
        call_control_id=call_control_id,
        call_state=call_state,
        payload=payload,
    )

    return {
        "received": True,
        "call_control_id": call_control_id,
        "status": call_state.get("status"),
        "type": call_state.get("type"),
    }


@app.get("/calls/{call_control_id}", dependencies=[Depends(verify_api_key)])
async def get_call_status(call_control_id: str):
    """Check current tracked state of a call."""
    if call_control_id not in active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    return active_calls[call_control_id]
