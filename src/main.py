import base64
import logging
from typing import Any

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.auth import verify_api_key
from src.callbacks.router import webhook_router
from src.log_config import configure_logging
from src.models import (
    CallRequest,
    ConfirmVerificationRequest,
    DestinationVerificationRequired,
    ErrorResponse,
    FrokenUrRequest,
    NumberVerificationRequest,
    ProviderErrorResponse,
    StartVerificationRequest,
    TodoCallRequest,
    VerificationRequested,
    VerificationStatus,
)
from src.services.todo_service import TodoService, todo_service
from src.services.todo_storage import D1TodoStorage
from src.telnyx_client import TelnyxClientDep, destination_verification_required, provider_error_codes
from src.version import __version__
from src.webhook_auth import verify_telnyx_signature

configure_logging()
logger = logging.getLogger(__name__)

asgi_worker: Any = None
try:
    from workers import asgi as asgi_worker  # Cloudflare Workers Python runtime
except ImportError:
    pass

app = FastAPI(
    title="Claude Call - Fröken Ur & Telnyx",
    version=__version__,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Internal server error",
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ProviderErrorResponse,
            "description": "Telnyx rejected an upstream request",
        },
    },
)


@app.exception_handler(httpx.HTTPStatusError)
async def handle_provider_error(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    if destination_verification_required(exc):
        verification_error = DestinationVerificationRequired(
            detail="Verify (whitelist) this destination number before calling it.",
            provider="telnyx",
            provider_status=403,
            provider_error_codes=provider_error_codes(exc.response),
        )
        return JSONResponse(status_code=403, content=verification_error.model_dump())
    error = ProviderErrorResponse(
        detail="Telnyx rejected the request",
        provider="telnyx",
        provider_status=exc.response.status_code,
        provider_error_codes=provider_error_codes(exc.response),
    )
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content=error.model_dump())


@app.post("/numbers/verifications", dependencies=[Depends(verify_api_key)])
async def start_number_verification(
    request: StartVerificationRequest, client: TelnyxClientDep
) -> VerificationRequested:
    """Explicitly send a verification code via SMS or call; provider charges may apply."""
    await client.start_number_verification(request.phone_number.e164, request.verification_method)
    return VerificationRequested(phone_number=request.phone_number.e164)


def verification_status(phone_number: str, result: dict[str, Any] | None) -> VerificationStatus:
    if result is None:
        return VerificationStatus(phone_number=phone_number, verified=False)
    data = result.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("verified_at"), str) or not data["verified_at"]:
        logger.error("telnyx_invalid_verification_response")
        raise HTTPException(status_code=502, detail="Invalid Telnyx verification response")
    return VerificationStatus(phone_number=phone_number, verified=True, verified_at=data["verified_at"])


@app.post("/numbers/verifications/confirm", dependencies=[Depends(verify_api_key)])
async def confirm_number_verification(
    request: ConfirmVerificationRequest, client: TelnyxClientDep
) -> VerificationStatus:
    """Submit the code received by the number's owner."""
    result = await client.confirm_number_verification(request.phone_number.e164, request.verification_code)
    return verification_status(request.phone_number.e164, result)


@app.post("/numbers/verifications/status", dependencies=[Depends(verify_api_key)])
async def number_verification_status(request: NumberVerificationRequest, client: TelnyxClientDep) -> VerificationStatus:
    """Read verification status without sending a code or placing a call."""
    result = await client.number_verification_status(request.phone_number.e164)
    return verification_status(request.phone_number.e164, result)


# In-memory tracking for call state
active_calls: dict[str, dict[str, Any]] = {}


def get_d1_db(request: Request) -> Any | None:
    """Extract D1 database binding from ASGI scope['env'] if present."""
    scope_env = request.scope.get("env")
    if scope_env is not None:
        if isinstance(scope_env, dict):
            return scope_env.get("DB") or scope_env.get("claude_call_db")
        if hasattr(scope_env, "DB"):
            return scope_env.DB
        if hasattr(scope_env, "claude_call_db"):
            return scope_env.claude_call_db
    return None


@app.get("/")
async def root():
    return {"message": "Claude Call Service"}


@app.get("/health")
async def health():
    """Health check endpoint for container probes and load balancers."""
    return {"status": "healthy", "version": app.version}


@app.get("/todos/{phone_number}", dependencies=[Depends(verify_api_key)])
async def get_user_todos(request: Request, phone_number: str):
    """Retrieve current todo/shopping list items for a phone number."""
    db = get_d1_db(request)
    service = TodoService(D1TodoStorage(db)) if db is not None else todo_service
    return {"phone_number": phone_number, "items": await service.list_items(phone_number)}


@app.post(
    "/calls/dial",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
    responses={
        403: {
            "model": DestinationVerificationRequired | ErrorResponse,
            "description": "Destination verification required or API key forbidden",
        }
    },
)
async def make_call(request: CallRequest, client: TelnyxClientDep):
    """Trigger a generic outbound call to a landline via Telnyx."""
    try:
        kwargs: dict[str, Any] = {"to_number": request.to_number.e164}

        result = await client.dial(**kwargs)
        data = result.get("data", {})
        call_control_id = data.get("call_control_id")

        if call_control_id:
            active_calls[call_control_id] = {
                "type": "generic",
                "status": "initiating",
                "to": request.to_number.e164,
                "data": data,
            }

        return {
            "status": "success",
            "call_control_id": call_control_id,
            "call_leg_id": data.get("call_leg_id"),
        }
    except httpx.HTTPStatusError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/calls/froken-ur",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
    responses={
        403: {
            "model": DestinationVerificationRequired | ErrorResponse,
            "description": "Destination verification required or API key forbidden",
        }
    },
)
async def start_froken_ur(request: FrokenUrRequest, client: TelnyxClientDep):
    """
    Start Fröken Ur call: dials the given number and repeatedly announces the
    time in Stockholm with pauses until the user hangs up.
    """
    try:
        client_state_str = base64.b64encode(b"froken_ur").decode("utf-8")
        kwargs: dict[str, Any] = {
            "to_number": request.to_number.e164,
            "client_state": client_state_str,
        }
        result = await client.dial(**kwargs)
        data = result.get("data", {})
        call_control_id = data.get("call_control_id")

        if call_control_id:
            active_calls[call_control_id] = {
                "type": "froken_ur",
                "status": "initiating",
                "to": request.to_number.e164,
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
    except httpx.HTTPStatusError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/calls/todo",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_api_key)],
    responses={
        403: {
            "model": DestinationVerificationRequired | ErrorResponse,
            "description": "Destination verification required or API key forbidden",
        }
    },
)
async def start_todo_call(request: TodoCallRequest, client: TelnyxClientDep):
    """
    Start Todo List voice call: allows user to POP, PUSH or LIST items
    via speech interaction.
    """
    try:
        client_state_str = base64.b64encode(b"todo_list").decode("utf-8")
        kwargs: dict[str, Any] = {
            "to_number": request.to_number.e164,
            "client_state": client_state_str,
        }
        result = await client.dial(**kwargs)
        data = result.get("data", {})
        call_control_id = data.get("call_control_id")

        if call_control_id:
            active_calls[call_control_id] = {
                "type": "todo_list",
                "status": "initiating",
                "to": request.to_number.e164,
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
    except httpx.HTTPStatusError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/webhooks/telnyx",
    dependencies=[Depends(verify_telnyx_signature)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid Telnyx signature or stale timestamp"},
        503: {"model": ErrorResponse, "description": "Webhook verification is not configured"},
    },
)
async def telnyx_webhook(
    http_request: Request, event: dict[str, Any], client: TelnyxClientDep, background_tasks: BackgroundTasks
):
    """Handle incoming call control webhooks by delegating to WebhookRouter."""
    event_data = event.get("data", {})
    event_type = event_data.get("event_type", "")
    payload = event_data.get("payload", {})
    call_control_id = payload.get("call_control_id")

    if not call_control_id:
        logger.warning("webhook_missing_call_id", extra={"event_type": event_type})
        return {"received": True, "warning": "missing call_control_id"}

    logger.info("webhook_received", extra={"event_type": event_type, "call_control_id": call_control_id})
    db = get_d1_db(http_request)
    service = TodoService(D1TodoStorage(db)) if db is not None else todo_service

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

    async def dispatch_event() -> None:
        try:
            await webhook_router.dispatch(
                event_type=event_type,
                call_control_id=call_control_id,
                call_state=call_state,
                payload=payload,
                service=service,
                client=client,
            )
        except Exception as exc:
            logger.error(
                "webhook_failed",
                extra={
                    "event_type": event_type,
                    "call_control_id": call_control_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        logger.info(
            "webhook_processed",
            extra={
                "event_type": event_type,
                "call_control_id": call_control_id,
                "call_status": call_state.get("status"),
            },
        )

    if call_state.get("type") == "froken_ur" and event_type == "call.speak.ended":
        background_tasks.add_task(dispatch_event)
        logger.info("announcement_scheduled", extra={"call_control_id": call_control_id})
    else:
        await dispatch_event()

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


# Expose to Cloudflare Worker runtime when running under Pyodide / Python Workers
Default = asgi_worker.entrypoint(app) if asgi_worker is not None else app
