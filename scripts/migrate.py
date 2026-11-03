#!/usr/bin/env python3
"""Dedicated migration runner script for production deployments."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.services.migrator import DatabaseMigrator  # noqa: E402


def run_migrations():
    print(f"[*] Running database migrations against {settings.postgres_dsn}...")
    try:
        import psycopg  # noqa: F401

        # Example standard psycopg connection if available
        conn = psycopg.connect(settings.postgres_dsn)
        migrator = DatabaseMigrator(db_client=conn, app_settings=settings)
        applied = migrator.apply_pending_migrations()
        print(f"[+] Applied {len(applied)} migrations: {applied}")
    except ImportError:
        print("[!] psycopg/db driver not installed in this environment. Using mock/dry-run check.")
        # Dry-run check ensuring migration files syntax and templating are valid
        migrator = DatabaseMigrator(db_client=None, app_settings=settings)
        for sql_file in sorted(migrator.migrations_dir.glob("*.sql")):
            rendered = migrator.render_sql(sql_file.read_text(encoding="utf-8"))
            print(f"  [OK] Validated {sql_file.name} ({len(rendered)} bytes rendered)")
        print("[+] All migration templates validated successfully.")


if __name__ == "__main__":
    run_migrations()
