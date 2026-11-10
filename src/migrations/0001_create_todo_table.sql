-- Migration 0001: Create todo table and index in SQLite / Cloudflare D1
CREATE TABLE IF NOT EXISTS user_todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    item TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_user_todos_phone ON user_todos(phone_number, id);
