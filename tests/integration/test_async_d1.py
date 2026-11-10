import asyncio

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from src.main import active_calls, app
from src.services.todo_service import todo_service
from src.services.todo_storage import D1TodoStorage
from tests.mock_telnyx import build_telnyx_event
from tests.unit.test_todo_storage import MockD1Binding, MockD1PreparedStatement


class DelayedD1Statement(MockD1PreparedStatement):
    def bind(self, *args):
        return DelayedD1Statement(self.d1, self.query, args)

    async def all(self):
        await asyncio.sleep(0)
        return await super().all()

    async def first(self):
        await asyncio.sleep(0)
        return await super().first()

    async def run(self):
        await asyncio.sleep(0)
        return await super().run()


class DelayedD1Binding(MockD1Binding):
    def prepare(self, query):
        return DelayedD1Statement(self, query)


def app_with_db(db):
    async def bound_app(scope, receive, send):
        env = {
            "DB": db,
            "TELNYX_API_KEY": "test-provider-key",
            "TELNYX_CONNECTION_ID": "test-connection",
            "TELNYX_FROM_NUMBER": "+12025550199",
        }
        await app(dict(scope, env=env), receive, send)

    return bound_app


@pytest.mark.asyncio
async def test_todo_route_awaits_d1_and_keeps_request_bindings_isolated():
    first, second = DelayedD1Binding(), DelayedD1Binding()
    await D1TodoStorage(first).push("alice", "First database")
    await D1TodoStorage(second).push("alice", "Second database")
    default_storage = todo_service.storage
    async with (
        AsyncClient(transport=ASGITransport(app=app_with_db(first)), base_url="http://test") as client1,
        AsyncClient(transport=ASGITransport(app=app_with_db(second)), base_url="http://test") as client2,
    ):
        response1, response2 = await asyncio.gather(client1.get("/todos/alice"), client2.get("/todos/alice"))
    assert response1.json() == {"phone_number": "alice", "items": ["First database"]}
    assert response2.json() == {"phone_number": "alice", "items": ["Second database"]}
    assert todo_service.storage is default_storage


@pytest.mark.asyncio
@respx.mock
async def test_webhook_awaits_d1_push_list_and_pop_without_changing_global_storage():
    db = DelayedD1Binding()
    call_id = "async-d1-regression"
    default_storage = todo_service.storage
    respx.post(f"https://api.telnyx.com/v2/calls/{call_id}/actions/gather_using_speak").respond(
        200, json={"data": {"result": "ok"}}
    )
    active_calls[call_id] = {"type": "todo_list", "to": "alice"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app_with_db(db)), base_url="http://test") as client:
            for command, expected_items in [("PUSH Eggs", ["Eggs"]), ("LIST", ["Eggs"]), ("POP", [])]:
                event = build_telnyx_event("call.gather.ended", call_id, to="alice", speech=command)
                response = await client.post("/webhooks/telnyx", json=event)
                assert response.status_code == 200
                assert await D1TodoStorage(db).list_items("alice") == expected_items
        assert todo_service.storage is default_storage
    finally:
        active_calls.pop(call_id, None)
