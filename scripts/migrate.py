#!/usr/bin/env python3
"""Apply D1-compatible migrations to a local SQLite database."""

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.services.migrator import DatabaseMigrator  # noqa: E402


def run_migrations(database_path: Path) -> list[str]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[*] Running SQLite migrations against {database_path}...")
    with closing(sqlite3.connect(database_path)) as conn:
        migrator = DatabaseMigrator(db_client=conn, app_settings=settings)
        applied = migrator.apply_pending_migrations()
    print(f"[+] Applied {len(applied)} migrations: {applied}")
    return applied


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Local SQLite database file")
    args = parser.parse_args()
    run_migrations(args.database)
