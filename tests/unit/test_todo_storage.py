from typing import Any

from src.services.todo_service import TodoService
from src.services.todo_storage import D1TodoStorage, InMemoryTodoStorage


class MockD1PreparedStatement:
    def __init__(self, d1: "MockD1Binding", query: str, params: tuple[Any, ...] = ()):
        self.d1 = d1
        self.query = query
        self.params = params

    def bind(self, *args: Any) -> "MockD1PreparedStatement":
        return MockD1PreparedStatement(self.d1, self.query, args)

    def run(self) -> dict[str, Any]:
        if "INSERT INTO" in self.query:
            phone, item = self.params
            self.d1.rows.append({"id": self.d1._next_id, "phone_number": phone, "item": item})
            self.d1._next_id += 1
        elif "DELETE FROM" in self.query and "WHERE id = ?" in self.query:
            row_id = self.params[0]
            self.d1.rows = [r for r in self.d1.rows if r["id"] != row_id]
        elif "DELETE FROM" in self.query and "WHERE phone_number = ?" in self.query:
            phone = self.params[0]
            self.d1.rows = [r for r in self.d1.rows if r["phone_number"] != phone]
        return {"success": True}

    def first(self) -> dict[str, Any] | None:
        if "SELECT id, item FROM" in self.query:
            phone = self.params[0]
            matching = [r for r in self.d1.rows if r["phone_number"] == phone]
            if matching:
                return matching[0]
        return None

    def all(self) -> Any:
        class D1Result:
            def __init__(self, results: list[dict[str, Any]]):
                self.results = results

            def to_py(self):
                return self.results

        if "SELECT item FROM" in self.query:
            phone = self.params[0]
            matching = [{"item": r["item"]} for r in self.d1.rows if r["phone_number"] == phone]
            return D1Result(matching)
        return D1Result([])


class MockD1Binding:
    """Mock Cloudflare D1 environment binding with prepare().bind().first()/all()/run()."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._next_id = 1

    def prepare(self, query: str) -> MockD1PreparedStatement:
        return MockD1PreparedStatement(self, query)


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


def test_d1_storage_with_cloudflare_binding():
    mock_d1 = MockD1Binding()
    d1_storage = D1TodoStorage(d1_client=mock_d1)

    phone = "+46700000002"
    d1_storage.push(phone, "Batteries")
    d1_storage.push(phone, "Light bulb")
    assert d1_storage.list_items(phone) == ["Batteries", "Light bulb"]

    popped = d1_storage.pop(phone)
    assert popped == "Batteries"
    assert d1_storage.list_items(phone) == ["Light bulb"]


def test_todo_service_with_d1_storage():
    mock_d1 = MockD1Binding()
    d1_storage = D1TodoStorage(d1_client=mock_d1)
    service = TodoService(storage=d1_storage)

    phone = "+46700000003"
    service.push(phone, "Item 1")
    service.push(phone, "Item 2")
    assert service.list_items(phone) == ["Item 1", "Item 2"]
    assert service.pop(phone) == "Item 1"
    assert service.list_items(phone) == ["Item 2"]
