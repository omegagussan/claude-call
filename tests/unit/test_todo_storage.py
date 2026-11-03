from typing import Any

from src.config import Settings
from src.services.migrator import DatabaseMigrator
from src.services.todo_service import TodoService
from src.services.todo_storage import InMemoryTodoStorage, PostgresTodoStorage


class MockPostgresClient:
    """Simulates a Postgres DB client with tables and migration tracking."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._next_id = 1
        self.applied_migrations: set[str] = set()
        self.executed_queries: list[str] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        self.executed_queries.append(query)
        if "INSERT INTO" in query and "_schema_migrations" in query:
            self.applied_migrations.add(params[0])
        elif "INSERT INTO" in query:
            phone, item = params
            self.rows.append({"id": self._next_id, "phone_number": phone, "item": item})
            self._next_id += 1
        elif "DELETE FROM" in query and "WHERE phone_number = %s;" in query:
            phone = params[0]
            self.rows = [r for r in self.rows if r["phone_number"] != phone]

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        if "DELETE FROM" in query and "RETURNING item" in query:
            phone = params[0]
            matching = [r for r in self.rows if r["phone_number"] == phone]
            if not matching:
                return None
            oldest = matching[0]
            self.rows.remove(oldest)
            return (oldest["item"],)
        return None

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        if "_schema_migrations" in query:
            return [(v,) for v in self.applied_migrations]
        elif "SELECT item FROM" in query:
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


def test_database_migrator_applies_sql_files_with_settings():
    mock_db = MockPostgresClient()
    custom_settings = Settings(
        todo_table_name="custom_shopping_list",
        todo_db_schema="custom_schema",
        db_app_role="custom_role",
    )
    migrator = DatabaseMigrator(db_client=mock_db, app_settings=custom_settings)

    # First run applies pending migrations
    applied = migrator.apply_pending_migrations()
    assert len(applied) >= 2
    assert "0001_create_todo_table.sql" in applied
    assert "0002_apply_permissions.sql" in applied

    # Verify custom schema and table name was rendered into SQL
    create_queries = [
        q for q in mock_db.executed_queries if "CREATE TABLE IF NOT EXISTS custom_schema.custom_shopping_list" in q
    ]
    assert len(create_queries) == 1

    # Second run is idempotent (no migrations unrun)
    applied_again = migrator.apply_pending_migrations()
    assert applied_again == []


def test_postgres_storage_auto_migrates_on_startup():
    mock_db = MockPostgresClient()
    custom_settings = Settings(
        todo_table_name="company_tasks",
        todo_db_schema="public",
        auto_apply_migrations=True,
    )
    # Storage initializes and applies migrations automatically
    pg_storage = PostgresTodoStorage(db_client=mock_db, app_settings=custom_settings)
    assert "0001_create_todo_table.sql" in mock_db.applied_migrations

    phone = "+46700000002"
    pg_storage.push(phone, "Batteries")
    pg_storage.push(phone, "Light bulb")
    assert pg_storage.list_items(phone) == ["Batteries", "Light bulb"]

    popped = pg_storage.pop(phone)
    assert popped == "Batteries"
    assert pg_storage.list_items(phone) == ["Light bulb"]


def test_todo_service_with_migrated_postgres():
    mock_db = MockPostgresClient()
    pg_storage = PostgresTodoStorage(db_client=mock_db)
    service = TodoService(storage=pg_storage)

    phone = "+46700000003"
    service.push(phone, "Item 1")
    service.push(phone, "Item 2")
    assert service.list_items(phone) == ["Item 1", "Item 2"]
    assert service.pop(phone) == "Item 1"
    assert service.list_items(phone) == ["Item 2"]
