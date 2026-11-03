from pathlib import Path
from typing import Any

from src.config import Settings, settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class DatabaseMigrator:
    """
    Lightweight, self-contained SQL migration runner.
    Tracks applied migrations in `_schema_migrations` and applies pending .sql scripts
    with dynamic table/schema/role templating from Settings.
    """

    def __init__(
        self, db_client: Any, app_settings: Settings = settings, migrations_dir: Path = MIGRATIONS_DIR
    ) -> None:
        self.db = db_client
        self.settings = app_settings
        self.migrations_dir = migrations_dir

    def _ensure_migration_table(self) -> None:
        create_tracking_table = f"""
        CREATE TABLE IF NOT EXISTS {self.settings.todo_db_schema}._schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
        self.db.execute(create_tracking_table)

    def get_applied_versions(self) -> set[str]:
        self._ensure_migration_table()
        query = f"SELECT version FROM {self.settings.todo_db_schema}._schema_migrations;"
        rows = self.db.fetchall(query)
        if not rows:
            return set()
        return {r[0] if isinstance(r, (tuple, list)) else r.get("version") for r in rows}

    def render_sql(self, sql_content: str) -> str:
        """Substitute dynamic configuration variables into the migration SQL."""
        return sql_content.format(
            schema=self.settings.todo_db_schema,
            table=self.settings.todo_table_name,
            app_role=self.settings.db_app_role,
        )

    def apply_pending_migrations(self) -> list[str]:
        """Find and apply all unrun .sql migration files in lexicographical order."""
        applied = self.get_applied_versions()
        sql_files = sorted(self.migrations_dir.glob("*.sql"))
        executed: list[str] = []

        for file_path in sql_files:
            version_name = file_path.name
            if version_name in applied:
                continue

            raw_sql = file_path.read_text(encoding="utf-8")
            rendered_sql = self.render_sql(raw_sql)

            # Execute migration DDL
            self.db.execute(rendered_sql)

            # Record version as applied
            record_query = f"INSERT INTO {self.settings.todo_db_schema}._schema_migrations (version) VALUES (%s);"
            self.db.execute(record_query, (version_name,))
            executed.append(version_name)

        return executed
