-- Migration 0002: In SQLite / D1, table permissions are managed via Cloudflare API token / bindings.
-- This migration ensures schema metadata table exists.
CREATE TABLE IF NOT EXISTS _schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);
