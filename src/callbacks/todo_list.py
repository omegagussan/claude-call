from typing import Any

from src.callbacks.base import CallCallback
from src.services.todo_service import TodoService, todo_service
from src.services.todo_speech import OPTIONS_PROMPT, parse_todo_intent


class TodoListCallback(CallCallback):
    """Callback handler for Voice Todo / Shopping List calls."""

    def __init__(self, service: TodoService = todo_service) -> None:
        super().__init__()
        self.service = service

    async def on_answered(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        await super().on_answered(call_control_id, call_state, payload)
        # Start initial 5-second silence gather for user command (POP, PUSH, LIST)
        call_state["status"] = "awaiting_command"
        await self.client.gather_using_speak(
            call_control_id=call_control_id,
            payload_text="",  # Quiet listen for 5s initially
            timeout_millis=5000,
        )

    async def on_gather_ended(self, call_control_id: str, call_state: dict[str, Any], payload: dict[str, Any]) -> None:
        await super().on_gather_ended(call_control_id, call_state, payload)
        user_phone = call_state.get("to") or payload.get("to", "")

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
            await self.client.gather_using_speak(
                call_control_id=call_control_id,
                payload_text=OPTIONS_PROMPT,
                timeout_millis=10000,
            )

        elif command == "POP":
            popped = await self.service.pop(user_phone)
            call_state["last_action"] = "POP"
            if popped:
                msg = f"Popped {popped} from your list."
            else:
                msg = "Your list is empty. Nothing to pop."
            call_state.setdefault("history", []).append(msg)
            await self.client.gather_using_speak(
                call_control_id=call_control_id,
                payload_text=f"{msg} What would you like to do next?",
                timeout_millis=10000,
            )

        elif command == "PUSH":
            call_state["last_action"] = "PUSH"
            if not argument:
                call_state["awaiting_push_item"] = True
                await self.client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text="What item would you like to add?",
                    timeout_millis=10000,
                )
            else:
                await self.service.push(user_phone, argument)
                call_state["awaiting_push_item"] = False
                msg = f"Added {argument} to your list."
                call_state.setdefault("history", []).append(msg)
                await self.client.gather_using_speak(
                    call_control_id=call_control_id,
                    payload_text=f"{msg} Next command?",
                    timeout_millis=10000,
                )

        elif command == "LIST":
            call_state["last_action"] = "LIST"
            items = await self.service.list_items(user_phone)
            if not items:
                msg = "Your list has no items."
            else:
                items_str = ", ".join(items)
                msg = f"Your list has {len(items)} items: {items_str}."
            call_state.setdefault("history", []).append(msg)
            await self.client.gather_using_speak(
                call_control_id=call_control_id,
                payload_text=f"{msg} Next command?",
                timeout_millis=10000,
            )

        elif call_state.get("awaiting_push_item") and speech_text:
            await self.service.push(user_phone, speech_text.strip())
            call_state["awaiting_push_item"] = False
            msg = f"Added {speech_text.strip()} to your list."
            call_state.setdefault("history", []).append(msg)
            await self.client.gather_using_speak(
                call_control_id=call_control_id,
                payload_text=f"{msg} Next command?",
                timeout_millis=10000,
            )

        else:
            await self.client.gather_using_speak(
                call_control_id=call_control_id,
                payload_text=f"I did not understand. {OPTIONS_PROMPT}",
                timeout_millis=10000,
            )
