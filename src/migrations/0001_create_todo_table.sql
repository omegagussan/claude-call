-- Migration 0001: Create schema, todo table, and index
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.{table} (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(32) NOT NULL,
    item TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_{table}_phone ON {schema}.{table}(phone_number, id);
