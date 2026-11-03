import asyncio
from typing import Any

from src.callbacks.base import CallCallback
from src.services.time_service import format_froken_ur_speech
from src.telnyx_client import telnyx_client


class FrokenUrCallback(CallCallback):
    """Callback handler for Fröken Ur calls."""

    async def on_answered(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        await super().on_answered(call_control_id, call_state, payload)
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

    async def on_speak_ended(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        await super().on_speak_ended(call_control_id, call_state, payload)
        if call_state.get("status") == "completed":
            return

        call_state["status"] = "looping"
        pause = call_state.get("pause_seconds", 3.0)

        async def _delayed_next_announcement(cid: str, wait_secs: float) -> None:
            if wait_secs > 0:
                await asyncio.sleep(wait_secs)
            if call_state.get("status") != "completed":
                speech_text, est_duration = format_froken_ur_speech()
                call_state["time_announcements_count"] = call_state.get("time_announcements_count", 0) + 1
                call_state["last_estimated_duration"] = est_duration
                call_state.setdefault("history", []).append({"text": speech_text, "estimated_duration": est_duration})
                await telnyx_client.speak(
                    call_control_id=cid,
                    payload_text=speech_text,
                    language="sv-SE",
                    voice="female",
                )

        if pause == 0:
            await _delayed_next_announcement(call_control_id, 0.0)
        else:
            asyncio.create_task(_delayed_next_announcement(call_control_id, pause))
