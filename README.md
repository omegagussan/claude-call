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
  - `D1TodoStorage` for Cloudflare D1 and Python SQLite connections, with raw SQL migrations in `src/migrations/`.
- **Interactive OpenAPI Documentation**: Hosted at `/docs` (Swagger UI) and `/redoc`, with automated CI generation to `dist/openapi.json`.
  All endpoints document a shared HTTP 500 error schema with a string `detail` field.

## API 0.3.0: structured phone numbers

This release changes `to_number` from a string to a validated object on all
three call endpoints (`/calls/dial`, `/calls/froken-ur`, and `/calls/todo`):

```json
{
  "to_number": {
    "country_code": "+46",
    "area_code": "8",
    "subscriber_number": "12345678"
  }
}
```

`area_code` is the riktnummer or mobile prefix in international form: Stockholm
`8` instead of `08`, or Swedish mobile prefix `70` instead of `070`. Preserve
significant zeros in countries such as Italy. For numbering plans without a
destination prefix, use an empty area code. Components must be strings.
Numbers are validated against international numbering metadata and sent to
Telnyx as E.164; validation does not establish ownership or reachability.

`from_number` is no longer accepted in requests (HTTP 422). Configure the caller
ID server-side using `TELNYX_FROM_NUMBER`. Old string destinations must be
migrated to the object format; endpoint paths remain unchanged.

`webhook_url` is also rejected in requests (HTTP 422). Configure the Voice API
application's webhook URL in Telnyx to
`https://<your-worker-hostname>/webhooks/telnyx`. Outbound calls use that
application configuration; callers cannot override the callback destination.

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
   Copy `.env.example` to `.env` and configure Telnyx if running live:
   ```env
   TELNYX_API_KEY=YOUR_TELNYX_KEY
   TELNYX_CONNECTION_ID=YOUR_CONNECTION_ID
   TELNYX_FROM_NUMBER=+15551234567

   TODO_TABLE_NAME=user_todos
   ```

For Cloudflare deployments, CI/CD syncs `TELNYX_API_KEY`, `TELNYX_CONNECTION_ID`,
and `TELNYX_FROM_NUMBER` from GitHub Actions repository secrets to Worker secrets
before deploying. Provision them once using GitHub CLI (each command prompts
for its value without putting it in shell history):

```bash
gh secret set TELNYX_API_KEY --repo omegagussan/claude-call
gh secret set TELNYX_CONNECTION_ID --repo omegagussan/claude-call
gh secret set TELNYX_FROM_NUMBER --repo omegagussan/claude-call
```

CI fails if any value is missing or secret synchronization fails. Values are
sent to Wrangler over stdin, not committed to git; other Worker secrets such
as `API_KEYS` are preserved. The Cloudflare deployment token needs Workers
Scripts Edit permission as well as D1 Edit for migrations.

These settings are read from each request's Worker bindings for both dialing
and webhook commands, not from the local `.env` file. Missing Worker
configuration returns HTTP 503 rather than using mock credentials.
Local Python runs continue to use `.env`. The Telnyx API key is separate from
the `API_KEYS` used to authenticate callers of this service.

---

## Running the Application

### Live application logs

Application logging initializes in the app entrypoint for both Cloudflare and
local Python, without depending on Docker or Uvicorn configuration. JSON logs
are written immediately to stdout and appear alongside Cloudflare invocation
logs:

```bash
npx wrangler tail claude-call --format pretty
```

Look for `webhook_received`, `webhook_processed`, `telnyx_completed`, and
`telnyx_rejected`. Provider failures include the actual Telnyx HTTP status and
numeric error codes; credentials, phone numbers, request/response bodies, and
speech content are not logged. No additional application access log is emitted.
Cloudflare's invocation `Ok` is not an HTTP status code.

### Start the FastAPI Server
```bash
make run
# or directly via uv:
uv run uvicorn src.main:app --reload
```
The server will start at `http://127.0.0.1:8000`.

### Database tests without Docker

Run `make test` for the full Python suite, or `make test-migrate` for SQLite
integration tests. These use Python's built-in `sqlite3` with temporary databases
to exercise the actual D1-compatible migrations, FIFO storage, persistence,
user isolation, and migration rollback. No database server or Docker is required.

To migrate a persistent local SQLite file:

```bash
make migrate
# Or choose a different database:
make migrate SQLITE_PATH=/tmp/claude-call.sqlite3
```

`make run` uses in-memory storage; the SQLite file is for local database checks.
Use `make dev-worker` for the actual D1 binding and Workers runtime, and apply
the migrations to its local D1 database using `npx wrangler d1 execute
claude_call_db --local --file=src/migrations/0001_create_todo_table.sql`.
SQLite tests verify SQL behavior, not Cloudflare's JavaScript binding API.

Todo storage and service methods are asynchronous: callers must `await` their
operations. D1 promises are awaited directly on the request event loop, and
webhooks use request-scoped storage without replacing the global local store.
The synchronous SQLite connection path is only for local SQL tests, not
production request handling.

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
# (applies pending remote D1 migrations, then runs `uv run pywrangler deploy`)
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

Every deployment through GitHub Actions or `make deploy-worker` applies pending
SQL files from `src/migrations/` before uploading the Worker. Wrangler tracks
applied files in `d1_migrations`; unchanged deployments do not rerun them.
A migration failure stops deployment. Production deployments are serialized.

To apply pending migrations separately:
```bash
make migrate-d1
```

The deployment API token needs D1 write permissions as well as Worker deployment
permissions. Add new numbered SQL files rather than editing applied migrations.
Keep schema changes compatible with the currently running Worker: migrations
run first and remain applied if the subsequent Worker upload fails.
