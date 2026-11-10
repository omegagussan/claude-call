import sqlite3
from contextlib import closing

import pytest
from httpx import ASGITransport, AsyncClient

from scripts.migrate import run_migrations
from src.main import app
from src.services.migrator import DatabaseMigrator
from src.services.todo_service import TodoService
from src.services.todo_storage import D1TodoStorage


@pytest.mark.asyncio
async def test_server_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["version"] == app.version


@pytest.mark.asyncio
async def test_migrations_and_storage_persist_with_sqlite(tmp_path):
    database = tmp_path / "todos.sqlite3"
    assert run_migrations(database) == ["0001_create_todo_table", "0002_apply_permissions"]
    assert run_migrations(database) == []

    with closing(sqlite3.connect(database)) as conn, conn:
        service = TodoService(storage=D1TodoStorage(conn))
        assert await service.list_items("alice") == []
        assert await service.pop("alice") is None
        assert await service.push("alice", "  Eggs  ") == ["Eggs"]
        assert await service.push("alice", "Milk") == ["Eggs", "Milk"]
        await service.push("bob", "Bread")
        await service.push("alice", " '); DROP TABLE user_todos; -- ")
        assert await service.pop("alice") == "Eggs"
        assert await service.list_items("bob") == ["Bread"]

    with closing(sqlite3.connect(database)) as conn, conn:
        storage = D1TodoStorage(conn)
        assert await storage.list_items("alice") == ["Milk", "'); DROP TABLE user_todos; --"]
        assert await storage.push("alice", "  ") == await storage.list_items("alice")
        await storage.clear("alice")
        assert await storage.pop("alice") is None
        assert await storage.list_items("bob") == ["Bread"]
        assert DatabaseMigrator(conn).apply_pending_migrations() == []


def test_failed_migration_rolls_back_schema_and_tracking(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    migration = migrations / "0001_broken.sql"
    migration.write_text("CREATE TABLE example (id INTEGER); INVALID SQL;")

    with closing(sqlite3.connect(":memory:")) as conn:
        migrator = DatabaseMigrator(conn, migrations_dir=migrations)
        with pytest.raises(sqlite3.OperationalError):
            migrator.apply_pending_migrations()
        assert migrator.get_applied_versions() == set()
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'example'").fetchall() == []
        migration.write_text("CREATE TABLE example (id INTEGER);")
        assert migrator.apply_pending_migrations() == ["0001_broken"]
