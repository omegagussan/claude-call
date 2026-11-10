import asyncio
import inspect
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


class D1TodoStorage(TodoStorage):
    """
    Storage implementation backed by Cloudflare D1 (SQLite).
    Supports D1 JavaScript proxy objects, aiosqlite, and sqlite3 db connections.
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

    def _execute(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        """Execute query across D1 JS binding or Python sqlite cursor."""
        if hasattr(self.d1, "prepare"):
            # Cloudflare D1 JS binding
            stmt = self.d1.prepare(query)
            if params:
                stmt = stmt.bind(*params)
            res = stmt.run()
            if inspect.isawaitable(res):
                return self._run_coro_if_needed(res)
            return res

        # Standard sqlite3-like connection
        return self.d1.execute(query, params)

    def _run_coro_if_needed(self, awaitable: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        return loop.run_until_complete(awaitable)

    def push(self, phone_number: str, item: str) -> list[str]:
        clean_item = item.strip()
        if not clean_item:
            return self.list_items(phone_number)

        query = f"INSERT INTO {self.table_name} (phone_number, item) VALUES (?, ?);"
        if hasattr(self.d1, "prepare"):
            stmt = self.d1.prepare(query).bind(phone_number, clean_item)
            res = stmt.run()
            if inspect.isawaitable(res):
                self._run_coro_if_needed(res)
        else:
            self.d1.execute(query, (phone_number, clean_item))

        return self.list_items(phone_number)

    def pop(self, phone_number: str) -> str | None:
        # SQLite / D1 FIFO pop: find oldest id, delete it, return the item
        if hasattr(self.d1, "prepare"):
            sel_query = f"SELECT id, item FROM {self.table_name} WHERE phone_number = ? ORDER BY id ASC LIMIT 1;"
            stmt = self.d1.prepare(sel_query).bind(phone_number)
            first_res = stmt.first()
            if inspect.isawaitable(first_res):
                row = self._run_coro_if_needed(first_res)
            else:
                row = first_res

            if row:
                row_dict = row.to_py() if hasattr(row, "to_py") else dict(row)
                row_id = row_dict.get("id")
                item = row_dict.get("item")
                if row_id is not None:
                    del_query = f"DELETE FROM {self.table_name} WHERE id = ?;"
                    del_res = self.d1.prepare(del_query).bind(row_id).run()
                    if inspect.isawaitable(del_res):
                        self._run_coro_if_needed(del_res)
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
        row = self.d1.fetchone(query, (phone_number,))
        if row:
            val = row[0] if isinstance(row, (tuple, list)) else row.get("item")
            return str(val) if val is not None else None
        return None

    def list_items(self, phone_number: str) -> list[str]:
        query = f"SELECT item FROM {self.table_name} WHERE phone_number = ? ORDER BY id ASC;"
        if hasattr(self.d1, "prepare"):
            stmt = self.d1.prepare(query).bind(phone_number)
            all_res = stmt.all()
            if inspect.isawaitable(all_res):
                rows_res = self._run_coro_if_needed(all_res)
            else:
                rows_res = all_res

            res_results = rows_res.results if hasattr(rows_res, "results") else rows_res
            if hasattr(res_results, "to_py"):
                res_results = res_results.to_py()
            items: list[str] = []
            if res_results:
                for r in res_results:
                    item_val = r.get("item") if isinstance(r, dict) else r
                    if item_val is not None:
                        items.append(str(item_val))
            return items

        rows = self.d1.fetchall(query, (phone_number,))
        items_list: list[str] = []
        if rows:
            for row in rows:
                val = row[0] if isinstance(row, (tuple, list)) else row.get("item")
                if val is not None:
                    items_list.append(str(val))
        return items_list

    def clear(self, phone_number: str) -> None:
        query = f"DELETE FROM {self.table_name} WHERE phone_number = ?;"
        if hasattr(self.d1, "prepare"):
            res = self.d1.prepare(query).bind(phone_number).run()
            if inspect.isawaitable(res):
                self._run_coro_if_needed(res)
        else:
            self.d1.execute(query, (phone_number,))


# Alias for backward-compatibility if referenced elsewhere
PostgresTodoStorage = D1TodoStorage
