from typing import Any

from src.telnyx_client import TelnyxClient, telnyx_client


class CallCallback:
    """Abstract base class for Call Control webhook handlers."""

    def __init__(self, client: TelnyxClient = telnyx_client) -> None:
        self.client = client

    async def on_initiated(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        """Handle call.initiated (ringing)."""
        call_state["status"] = "ringing"

    async def on_answered(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        """Handle call.answered (recipient picked up)."""
        call_state["status"] = "answered"

    async def on_gather_ended(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        """Handle call.gather.ended (speech or DTMF collected)."""
        pass

    async def on_speak_ended(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        """Handle call.speak.ended (TTS audio finished playing)."""
        pass

    async def on_hangup(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        """Handle call.hangup (call terminated)."""
        call_state["status"] = "completed"
        call_state["hangup_reason"] = payload.get("hangup_reason")


class GenericCallback(CallCallback):
    """Default handler for generic outbound calls."""

    async def on_answered(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        await super().on_answered(call_control_id, call_state, payload)
        await self.client.speak(
            call_control_id=call_control_id,
            payload_text="Hello, this is Claude Call connecting via Telnyx.",
            language="en-US",
            voice="female",
        )

    async def on_speak_ended(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        await super().on_speak_ended(call_control_id, call_state, payload)
        call_state["status"] = "message_completed"
        await self.client.hangup(call_control_id=call_control_id)
