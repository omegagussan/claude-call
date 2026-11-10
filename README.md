# claude-call

FastAPI service integrating **Telnyx Call Control / SIP** to place automated voice calls to landline and mobile phones.

## Features

- **Fröken Ur Service (`POST /calls/froken-ur`)**: Dials a recipient and periodically reads out the current time in Stockholm in Swedish (*"Vid ett pip är klockan..."*), calculating TTS duration and pausing before repeating the time progression until the user hangs up.
- **Voice Todo / Shopping List (`POST /calls/todo`)**: Interactive voice assistant allowing users to manage a personal list by phone number using voice commands:
  - `POP`: Retrieves and removes the oldest item from the list (FIFO).
  - `PUSH <item>`: Appends an item to the end of the list.
  - `LIST`: Speaks all current items on the list.
  - If the user is silent for the first 5 seconds, the options are announced automatically.
- **Pluggable Storage & Raw SQL Migrations**:
  - `InMemoryTodoStorage` for local development, tests, and dry-runs.
  - `PostgresTodoStorage` with an embedded raw SQL migrator (`src/migrations/`) that creates schemas, tables, indexes, and grants permissions dynamically from settings on startup.
- **Interactive OpenAPI Documentation**: Hosted at `/docs` (Swagger UI) and `/redoc`, with automated CI generation to `dist/openapi.json`.

---

## Prerequisites

- Python `>=3.15`
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)
- Node.js `>=22.12.0` (development version specified in `.nvmrc`) and `npm` (for Cloudflare Wrangler CLI)

---

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd claude-call
   ```

2. **Install all dependencies (including dev tools) with `uv`:**
   ```bash
   uv sync --all-groups
   ```

3. **(Optional) Install pre-commit hooks:**
   ```bash
   make pre-commit-install
   ```

4. **Configuration (`.env`):**
   Copy or create a `.env` file with your Telnyx and Postgres settings if running live:
   ```env
   TELNYX_API_KEY=YOUR_TELNYX_KEY
   TELNYX_CONNECTION_ID=YOUR_CONNECTION_ID
   TELNYX_FROM_NUMBER=+15551234567

   # Optional Postgres settings
   POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/claude_call
   TODO_TABLE_NAME=user_todos
   TODO_DB_SCHEMA=public
   ```

---

## Running the Application

### Start the FastAPI Server
```bash
make run
# or directly via uv:
uv run uvicorn src.main:app --reload
```
The server will start at `http://127.0.0.1:8000`.

### Interactive API Documentation
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## Generating `requirements.txt` from `pyproject.toml`

Dependencies are single-sourced in `pyproject.toml` and managed by `uv`.

To generate/export a flat `requirements.txt` (e.g. for Pyodide, Cloudflare Workers, or legacy pip environments without dev dependencies or hashes):

```bash
make requirements
# or directly via uv:
uv export --format requirements-txt --no-hashes --no-dev > requirements.txt
```

If you also need development packages included:
```bash
uv export --format requirements-txt --no-hashes > requirements.txt
```

---

## Cloudflare Worker Targets

When working with Cloudflare Workers (Pyodide Wasm runtime):

### 1. Installing Wrangler CLI
Ensure Node.js is installed (use the version in `.nvmrc`):
```bash
# If using nvm (Node Version Manager):
nvm install
nvm use

# Install the project's pinned Wrangler version:
npm ci

# Verify the local CLI:
npx --no-install wrangler --version
```

Wrangler is pinned in `package.json` and `package-lock.json`. Both CI jobs run
`npm ci`, so PyWrangler and direct `npx wrangler` commands use the same local CLI.

### 2. Worker Build & Development Commands
```bash
# 1. Build worker prerequisites (syncs dependencies and generates the OpenAPI schema)
make build-worker

# 2. Start local Cloudflare worker development server
make dev-worker
# (runs `npx wrangler dev`)

# 3. Deploy worker to Cloudflare
make deploy-worker
# (runs `npx wrangler deploy`)
```

Wrangler runs `make stage-worker` before bundling. This stages application sources
under `.wrangler/worker/src/`, preserving `src.*` imports without bundling the
repository's virtual environments or local configuration. The project metadata
is included so the deployed application reads its version from `pyproject.toml`.

### Cloudflare D1 Database Configuration

The application uses Cloudflare D1 (serverless SQLite). The database was created and linked via `wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "claude_call_db"
database_id = "7eb8c9df-c768-42c9-b7af-7f5aaa7a8821"
```

To create a new D1 database if needed:
```bash
npx wrangler d1 create claude_call_db
```

To apply database migrations to the remote Cloudflare D1 database:
```bash
npx wrangler d1 execute claude_call_db --remote --file=src/migrations/0001_create_todo_table.sql
npx wrangler d1 execute claude_call_db --remote --file=src/migrations/0002_apply_permissions.sql
```
