from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from src.config import Settings, settings
from src.services.migrator import DatabaseMigrator


class TodoStorage(ABC):
    """Abstract interface for Todo storage backends."""

    @abstractmethod
    async def push(self, phone_number: str, item: str) -> list[str]:
        """Append an item to the end of the user's list and return current list."""
        raise NotImplementedError

    @abstractmethod
    async def pop(self, phone_number: str) -> str | None:
        """Retrieve and remove the oldest item from the list (FIFO)."""
        raise NotImplementedError

    @abstractmethod
    async def list_items(self, phone_number: str) -> list[str]:
        """List all items for a phone number in FIFO order."""
        raise NotImplementedError

    @abstractmethod
    async def clear(self, phone_number: str) -> None:
        """Clear all items for a phone number."""
        raise NotImplementedError


class InMemoryTodoStorage(TodoStorage):
    """In-memory implementation used for local development, dry-runs, and tests."""

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = defaultdict(list)

    async def push(self, phone_number: str, item: str) -> list[str]:
        clean_item = item.strip()
        if clean_item:
            self._store[phone_number].append(clean_item)
        return list(self._store[phone_number])

    async def pop(self, phone_number: str) -> str | None:
        items = self._store.get(phone_number)
        if items and len(items) > 0:
            return items.pop(0)
        return None

    async def list_items(self, phone_number: str) -> list[str]:
        return list(self._store.get(phone_number, []))

    async def clear(self, phone_number: str) -> None:
        self._store[phone_number] = []


class D1TodoStorage(TodoStorage):
    """
    Storage implementation backed by Cloudflare D1 (SQLite).
    Supports D1 JavaScript proxy objects and synchronous sqlite3 connections.
    """

    def __init__(
        self,
        d1_client: Any = None,
        app_settings: Settings = settings,
        auto_migrate: bool = False,
    ) -> None:
        self.d1 = d1_client
        self.settings = app_settings
        self.table_name = self.settings.todo_table_name
        self.migrator = DatabaseMigrator(db_client=self.d1, app_settings=self.settings) if self.d1 else None

        if self.d1 and auto_migrate and self.migrator:
            self.migrate()

    def migrate(self) -> list[str]:
        """Apply pending migrations."""
        if not self.migrator:
            return []
        return self.migrator.apply_pending_migrations()

    async def push(self, phone_number: str, item: str) -> list[str]:
        clean_item = item.strip()
        if not clean_item:
            return await self.list_items(phone_number)

        query = f"INSERT INTO {self.table_name} (phone_number, item) VALUES (?, ?);"
        if hasattr(self.d1, "prepare"):
            stmt = self.d1.prepare(query).bind(phone_number, clean_item)
            await stmt.run()
        else:
            self.d1.execute(query, (phone_number, clean_item))

        return await self.list_items(phone_number)

    async def pop(self, phone_number: str) -> str | None:
        # SQLite / D1 FIFO pop: find oldest id, delete it, return the item
        if hasattr(self.d1, "prepare"):
            sel_query = f"SELECT id, item FROM {self.table_name} WHERE phone_number = ? ORDER BY id ASC LIMIT 1;"
            stmt = self.d1.prepare(sel_query).bind(phone_number)
            row = await stmt.first()

            if row:
                row_dict = row.to_py() if hasattr(row, "to_py") else dict(row)
                row_id = row_dict.get("id")
                item = row_dict.get("item")
                if row_id is not None:
                    del_query = f"DELETE FROM {self.table_name} WHERE id = ?;"
                    await self.d1.prepare(del_query).bind(row_id).run()
                return str(item) if item is not None else None
            return None

        # Python DB-API compatible cursor / connection
        query = f"""
            DELETE FROM {self.table_name}
            WHERE id = (
                SELECT id FROM {self.table_name}
                WHERE phone_number = ?
                ORDER BY id ASC
                LIMIT 1
            )
            RETURNING item;
        """
        row = self.d1.execute(query, (phone_number,)).fetchone()
        if row:
            val = row[0] if isinstance(row, (tuple, list)) else row.get("item")
            return str(val) if val is not None else None
        return None

    async def list_items(self, phone_number: str) -> list[str]:
        query = f"SELECT item FROM {self.table_name} WHERE phone_number = ? ORDER BY id ASC;"
        if hasattr(self.d1, "prepare"):
            stmt = self.d1.prepare(query).bind(phone_number)
            rows_res = await stmt.all()

            if hasattr(rows_res, "to_py"):
                rows_res = rows_res.to_py()
            res_results = rows_res["results"] if isinstance(rows_res, dict) else rows_res.results
            if hasattr(res_results, "to_py"):
                res_results = res_results.to_py()
            items: list[str] = []
            if res_results:
                for r in res_results:
                    item_val = r.get("item") if isinstance(r, dict) else r
                    if item_val is not None:
                        items.append(str(item_val))
            return items

        rows = self.d1.execute(query, (phone_number,)).fetchall()
        items_list: list[str] = []
        if rows:
            for row in rows:
                val = row[0] if isinstance(row, (tuple, list)) else row.get("item")
                if val is not None:
                    items_list.append(str(val))
        return items_list

    async def clear(self, phone_number: str) -> None:
        query = f"DELETE FROM {self.table_name} WHERE phone_number = ?;"
        if hasattr(self.d1, "prepare"):
            await self.d1.prepare(query).bind(phone_number).run()
        else:
            self.d1.execute(query, (phone_number,))
