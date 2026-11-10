# ADR 01: Hosting Platform and Database

## Status
Accepted

## Context
We need a simple, cheap, and fast way to host the `claude-call` FastAPI service and store user todo items. Traditional servers or containers require managing servers, connection pools, and paying for idle CPU time.

## Decision
1. **Hosting**: Use **Cloudflare Workers** with the Python (Pyodide Wasm) runtime.
   - Serverless: Fast cold starts and runs close to users.
   - Low cost: Scales to zero when no calls are happening.
   - Wrapped using Cloudflare's ASGI entry point (`workers.asgi`).

2. **Database**: Use **Cloudflare D1** (serverless SQLite).
   - Built directly into Cloudflare Workers (injected via `request.scope["env"].DB`).
   - Replaces PostgreSQL to remove TCP socket and external database server requirements.
   - Simple SQL queries with parameter binding (`?`).

## Consequences
- **Pros**:
  - No servers to manage or patch.
  - Very cheap / generous free tier.
  - Fast response times for Telnyx webhooks.
- **Cons / Limits**:
  - No C-extensions: dependencies must be pure Python.
  - SQLite dialect instead of PostgreSQL (no PostgreSQL-specific functions or schemas).
