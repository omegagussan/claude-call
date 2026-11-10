from pathlib import Path
from typing import Any

from src.config import Settings, settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class DatabaseMigrator:
    """
    Lightweight, self-contained SQL migration runner for SQLite / D1 and local dev.
    Tracks applied migrations in `_schema_migrations` and applies pending .sql scripts.
    """

    def __init__(
        self, db_client: Any, app_settings: Settings = settings, migrations_dir: Path = MIGRATIONS_DIR
    ) -> None:
        self.db = db_client
        self.settings = app_settings
        self.migrations_dir = migrations_dir

    def _ensure_migration_table(self) -> None:
        create_tracking_table = """
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        );
        """
        self.db.execute(create_tracking_table)

    def get_applied_versions(self) -> set[str]:
        self._ensure_migration_table()
        query = "SELECT version FROM _schema_migrations;"
        rows = self.db.fetchall(query)
        if not rows:
            return set()
        return {r[0] if isinstance(r, (tuple, list)) else r.get("version") for r in rows}

    def render_sql(self, sql_content: str) -> str:
        """Substitute dynamic configuration variables into the migration SQL."""
        return sql_content.format(
            table=self.settings.todo_table_name,
        )

    def apply_pending_migrations(self) -> list[str]:
        """Find and apply all unrun .sql migration files in lexicographical order."""
        applied = self.get_applied_versions()
        all_migrations = sorted(self.migrations_dir.glob("*.sql"))

        applied_now: list[str] = []
        for file in all_migrations:
            version = file.stem
            if version not in applied:
                sql_raw = file.read_text(encoding="utf-8")
                sql = self.render_sql(sql_raw)

                # Execute individual statements separated by semicolon
                statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
                for statement in statements:
                    self.db.execute(statement)

                record_query = "INSERT INTO _schema_migrations (version) VALUES (?);"
                self.db.execute(record_query, (version,))
                applied_now.append(version)

        return applied_now
