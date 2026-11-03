from typing import Any

from src.services.todo_service import TodoService
from src.services.todo_storage import InMemoryTodoStorage, PostgresTodoStorage


class MockPostgresClient:
    """Simulates a Postgres DB client (rows table with auto-increment IDs)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._next_id = 1

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        if "INSERT INTO user_todos" in query:
            phone, item = params
            self.rows.append({"id": self._next_id, "phone_number": phone, "item": item})
            self._next_id += 1
        elif "DELETE FROM user_todos WHERE phone_number = %s;" in query:
            phone = params[0]
            self.rows = [r for r in self.rows if r["phone_number"] != phone]

    def fetchone(self, query: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        if "DELETE FROM user_todos" in query and "RETURNING item" in query:
            phone = params[0]
            matching = [r for r in self.rows if r["phone_number"] == phone]
            if not matching:
                return None
            oldest = matching[0]
            self.rows.remove(oldest)
            return (oldest["item"],)
        return None

    def fetchall(self, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        if "SELECT item FROM user_todos" in query:
            phone = params[0]
            matching = [r for r in self.rows if r["phone_number"] == phone]
            return [(r["item"],) for r in matching]
        return []


def test_in_memory_storage_interface():
    storage = InMemoryTodoStorage()
    phone = "+46700000001"

    assert storage.list_items(phone) == []
    assert storage.pop(phone) is None

    storage.push(phone, "Eggs")
    storage.push(phone, "Flour")
    assert storage.list_items(phone) == ["Eggs", "Flour"]

    assert storage.pop(phone) == "Eggs"
    assert storage.list_items(phone) == ["Flour"]
    assert storage.pop(phone) == "Flour"
    assert storage.pop(phone) is None


def test_postgres_storage_interface():
    mock_db = MockPostgresClient()
    pg_storage = PostgresTodoStorage(db_client=mock_db)
    phone = "+46700000002"

    # Push items
    pg_storage.push(phone, "Batteries")
    pg_storage.push(phone, "Light bulb")
    assert pg_storage.list_items(phone) == ["Batteries", "Light bulb"]

    # Pop oldest item
    popped = pg_storage.pop(phone)
    assert popped == "Batteries"
    assert pg_storage.list_items(phone) == ["Light bulb"]

    # Pop last item
    assert pg_storage.pop(phone) == "Light bulb"
    assert pg_storage.pop(phone) is None


def test_todo_service_pluggable_storage():
    mock_db = MockPostgresClient()
    pg_storage = PostgresTodoStorage(db_client=mock_db)
    service = TodoService(storage=pg_storage)

    phone = "+46700000003"
    service.push(phone, "Item 1")
    service.push(phone, "Item 2")
    assert service.list_items(phone) == ["Item 1", "Item 2"]
    assert service.pop(phone) == "Item 1"
    assert service.list_items(phone) == ["Item 2"]
