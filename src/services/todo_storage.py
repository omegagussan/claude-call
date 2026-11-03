from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from src.config import Settings, settings
from src.services.migrator import DatabaseMigrator


class TodoStorage(ABC):
    """Abstract interface for Todo storage backends."""

    @abstractmethod
    def push(self, phone_number: str, item: str) -> list[str]:
        """Append an item to the end of the user's list and return current list."""
        raise NotImplementedError

    @abstractmethod
    def pop(self, phone_number: str) -> str | None:
        """Retrieve and remove the oldest item from the list (FIFO)."""
        raise NotImplementedError

    @abstractmethod
    def list_items(self, phone_number: str) -> list[str]:
        """List all items for a phone number in FIFO order."""
        raise NotImplementedError

    @abstractmethod
    def clear(self, phone_number: str) -> None:
        """Clear all items for a phone number."""
        raise NotImplementedError


class InMemoryTodoStorage(TodoStorage):
    """In-memory implementation used for local development, dry-runs, and tests."""

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = defaultdict(list)

    def push(self, phone_number: str, item: str) -> list[str]:
        clean_item = item.strip()
        if clean_item:
            self._store[phone_number].append(clean_item)
        return list(self._store[phone_number])

    def pop(self, phone_number: str) -> str | None:
        items = self._store.get(phone_number)
        if items and len(items) > 0:
            return items.pop(0)
        return None

    def list_items(self, phone_number: str) -> list[str]:
        return list(self._store.get(phone_number, []))

    def clear(self, phone_number: str) -> None:
        self._store[phone_number] = []


class PostgresTodoStorage(TodoStorage):
    """
    Production storage implementation backed by PostgreSQL.
    Features dynamic table/schema configuration and auto-migration on start.
    """

    def __init__(
        self,
        db_client: Any = None,
        app_settings: Settings = settings,
        auto_migrate: bool | None = None,
    ) -> None:
        self.db = db_client
        self.settings = app_settings
        self.table_ref = f"{self.settings.todo_db_schema}.{self.settings.todo_table_name}"
        self.migrator = DatabaseMigrator(db_client=self.db, app_settings=self.settings) if self.db else None

        should_migrate = auto_migrate if auto_migrate is not None else self.settings.auto_apply_migrations
        if self.db and should_migrate and self.migrator:
            self.migrate()

    def migrate(self) -> list[str]:
        """Apply pending migrations."""
        if not self.migrator:
            return []
        return self.migrator.apply_pending_migrations()

    def push(self, phone_number: str, item: str) -> list[str]:
        clean_item = item.strip()
        if not clean_item:
            return self.list_items(phone_number)

        query = f"INSERT INTO {self.table_ref} (phone_number, item) VALUES (%s, %s);"
        self.db.execute(query, (phone_number, clean_item))
        return self.list_items(phone_number)

    def pop(self, phone_number: str) -> str | None:
        # Atomic FIFO pop using CTE: DELETE the oldest record and RETURNING the item
        query = f"""
            DELETE FROM {self.table_ref}
            WHERE id = (
                SELECT id FROM {self.table_ref}
                WHERE phone_number = %s
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING item;
        """
        row = self.db.fetchone(query, (phone_number,))
        if row:
            return str(row[0]) if isinstance(row, (tuple, list)) else str(row.get("item"))
        return None

    def list_items(self, phone_number: str) -> list[str]:
        query = f"SELECT item FROM {self.table_ref} WHERE phone_number = %s ORDER BY id ASC;"
        rows = self.db.fetchall(query, (phone_number,))
        items: list[str] = []
        if rows:
            for row in rows:
                val = row[0] if isinstance(row, (tuple, list)) else row.get("item")
                items.append(str(val))
        return items

    def clear(self, phone_number: str) -> None:
        query = f"DELETE FROM {self.table_ref} WHERE phone_number = %s;"
        self.db.execute(query, (phone_number,))
