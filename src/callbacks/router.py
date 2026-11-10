import base64
from typing import Any

from src.callbacks.base import CallCallback, GenericCallback
from src.callbacks.froken_ur import FrokenUrCallback
from src.callbacks.todo_list import TodoListCallback
from src.services.todo_service import TodoService


class WebhookRouter:
    """
    Routes incoming Telnyx webhooks to the corresponding application callback class
    based on call type or client_state.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, CallCallback] = {
            "generic": GenericCallback(),
            "froken_ur": FrokenUrCallback(),
            "todo_list": TodoListCallback(),
        }

    def register(self, call_type: str, handler: CallCallback) -> None:
        """Register a custom callback handler."""
        self._handlers[call_type] = handler

    def resolve_call_type(self, client_state_b64: str | None) -> str:
        """Infer call type from base64 encoded client_state."""
        if not client_state_b64:
            return "generic"
        try:
            decoded = base64.b64decode(client_state_b64).decode("utf-8")
            if "froken_ur" in decoded:
                return "froken_ur"
            elif "todo_list" in decoded:
                return "todo_list"
        except Exception:
            pass
        return "generic"

    def get_handler(self, call_type: str) -> CallCallback:
        """Retrieve handler for call type, defaulting to GenericCallback."""
        return self._handlers.get(call_type, self._handlers["generic"])

    async def dispatch(
        self,
        event_type: str,
        call_control_id: str,
        call_state: dict[str, Any],
        payload: dict[str, Any],
        service: TodoService | None = None,
    ) -> None:
        """Dispatch event to handler method based on event_type."""
        call_type = call_state.get("type", "generic")
        handler = self.get_handler(call_type)
        if isinstance(handler, TodoListCallback) and service is not None:
            handler = TodoListCallback(service)

        if event_type == "call.initiated":
            await handler.on_initiated(call_control_id, call_state, payload)
        elif event_type == "call.answered":
            await handler.on_answered(call_control_id, call_state, payload)
        elif event_type == "call.gather.ended":
            await handler.on_gather_ended(call_control_id, call_state, payload)
        elif event_type == "call.speak.ended":
            await handler.on_speak_ended(call_control_id, call_state, payload)
        elif event_type == "call.hangup":
            await handler.on_hangup(call_control_id, call_state, payload)


webhook_router = WebhookRouter()
