from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any


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
    Production-ready storage implementation that talks to a PostgreSQL database connection/session.
    Can be injected with any DB connection or cursor-compatible engine (e.g. asyncpg/psycopg/SQLAlchemy).

    Schema expected:
        CREATE TABLE IF NOT EXISTS user_todos (
            id SERIAL PRIMARY KEY,
            phone_number VARCHAR(32) NOT NULL,
            item TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_user_todos_phone ON user_todos(phone_number, id);
    """

    def __init__(self, db_client: Any = None) -> None:
        self.db = db_client

    def push(self, phone_number: str, item: str) -> list[str]:
        clean_item = item.strip()
        if not clean_item:
            return self.list_items(phone_number)

        # Uses database client if provided
        query = "INSERT INTO user_todos (phone_number, item) VALUES (%s, %s);"
        self.db.execute(query, (phone_number, clean_item))
        return self.list_items(phone_number)

    def pop(self, phone_number: str) -> str | None:
        # Atomic FIFO pop using CTE: DELETE the oldest record and RETURNING the item
        query = """
            DELETE FROM user_todos
            WHERE id = (
                SELECT id FROM user_todos
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
        query = "SELECT item FROM user_todos WHERE phone_number = %s ORDER BY id ASC;"
        rows = self.db.fetchall(query, (phone_number,))
        items: list[str] = []
        if rows:
            for row in rows:
                val = row[0] if isinstance(row, (tuple, list)) else row.get("item")
                items.append(str(val))
        return items

    def clear(self, phone_number: str) -> None:
        query = "DELETE FROM user_todos WHERE phone_number = %s;"
        self.db.execute(query, (phone_number,))
