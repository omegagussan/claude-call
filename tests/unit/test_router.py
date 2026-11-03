import pytest

from src.callbacks.base import GenericCallback
from src.callbacks.froken_ur import FrokenUrCallback
from src.callbacks.router import WebhookRouter
from src.callbacks.todo_list import TodoListCallback


def test_webhook_router_resolution():
    router = WebhookRouter()

    # Handlers mapped
    assert isinstance(router.get_handler("generic"), GenericCallback)
    assert isinstance(router.get_handler("froken_ur"), FrokenUrCallback)
    assert isinstance(router.get_handler("todo_list"), TodoListCallback)
    assert isinstance(router.get_handler("unknown_type"), GenericCallback)

    # Resolve from client_state
    import base64

    b64_froken = base64.b64encode(b"froken_ur").decode()
    b64_todo = base64.b64encode(b"todo_list").decode()

    assert router.resolve_call_type(b64_froken) == "froken_ur"
    assert router.resolve_call_type(b64_todo) == "todo_list"
    assert router.resolve_call_type(None) == "generic"
    assert router.resolve_call_type("invalid_base64") == "generic"


@pytest.mark.asyncio
async def test_router_dispatch_lifecycle():
    router = WebhookRouter()
    state = {"type": "generic"}

    # Dispatch initiated
    await router.dispatch("call.initiated", "cid_1", state, {})
    assert state["status"] == "ringing"

    # Dispatch hangup
    await router.dispatch("call.hangup", "cid_1", state, {"hangup_reason": "normal_clearing"})
    assert state["status"] == "completed"
    assert state["hangup_reason"] == "normal_clearing"
