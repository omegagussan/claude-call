# claude-call

FastAPI service integrating **Telnyx Call Control / SIP** to place automated voice calls to landline and mobile phones.

## Features

- **Fröken Ur Service (`POST /calls/froken-ur`)**: Dials a recipient and periodically reads out the current time in Stockholm in Swedish (*"Vid ett pip är klockan..."*), calculating TTS duration and pausing before repeating the time progression until the user hangs up.
  Each `call.speak.ended` webhook schedules the next announcement as a FastAPI
  background task. Cloudflare's ASGI adapter keeps that task alive with
  `wait_until` after sending the webhook response; no user speech is required.
  This is bounded post-response work (Cloudflare allows up to 30 seconds), not
  an indefinitely running call loop. Keep pauses short (default: 3 seconds)
  to leave time for the Telnyx request. Call state is still in memory, so
  cross-instance state and durable scheduling are not guaranteed.
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

## API 0.4.0: destination verification

Trial accounts can require individual destination verification even when the
country is allowed by the outbound profile. All endpoints below require this
service's API key and use the same structured `phone_number` object as
`to_number` in call requests:

1. `POST /numbers/verifications` with `phone_number` and
   `verification_method: "sms"` or `"call"` explicitly sends an ownership code.
   Provider charges may apply. Only request codes for numbers you control or
   have permission to verify.
2. `POST /numbers/verifications/confirm` with `phone_number` and
   `verification_code` (a digit string) submits the received code.
3. `POST /numbers/verifications/status` with `phone_number` reads the current
   `verified` status and `verified_at` without sending any code.

Verification is account-wide in Telnyx, not tied to an individual API key of
this service. No verification messages or calls are sent automatically.
Calls remain allowed without a verification precheck on unrestricted accounts.
If Telnyx returns the specific unverified-destination restriction, all three
call endpoints return HTTP 403 with `code: "destination_verification_required"`,
an instruction to verify/whitelist the number, and the provider status/codes.
Other authorization errors (including other uses of Telnyx code 10010) remain
HTTP 502. Incorrect verification codes also return the structured provider
error, without echoing the submitted code. No automatic retries are performed.

### Structured phone numbers (introduced in 0.3.0)

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

`wrangler.toml` owns the non-secret Worker variables `TELNYX_CONNECTION_ID`,
`TELNYX_FROM_NUMBER`, and `API_KEY_AUTH_ENABLED`. Only `TELNYX_API_KEY` and
`API_KEYS` need encrypted Worker secrets. Normal deployments preserve these
secrets instead of overwriting them with potentially stale GitHub values.

To provision or rotate runtime secrets, update `API_KEYS` and `TELNYX_API_KEY`
in your ignored local `.env`, then run:

```bash
make sync-worker-secrets
```

This explicitly replaces only those two Worker secrets and can activate a new
Worker version immediately. Both values are validated before upload and passed
to Wrangler through stdin, never arguments or temporary files. CLI output is
suppressed to protect credentials; failures return a nonzero exit status.
Authenticate with `npx wrangler login`, or provide Cloudflare API credentials
in the process environment or `.env` (the existing `CLOUDFLAIR_*` aliases are
supported). Install Node.js and run `npm ci` first.

CI/CD never reads or syncs runtime API secrets. After provisioning Cloudflare,
remove `API_KEYS` and `TELNYX_API_KEY` from GitHub Actions repository secrets.
CI still requires Cloudflare deployment credentials with Workers Scripts Edit
and D1 Edit permissions. Manual workflow runs remain available for code
deployment without secret rotation.

These settings are read from each request's Worker bindings for both dialing
and webhook commands, not from the local `.env` file. Missing Worker
configuration returns HTTP 503 rather than using mock credentials.
Local Python runs continue to use `.env`. The Telnyx API key is separate from
the `API_KEYS` used to authenticate callers of this service.

---

## Running the Application

### Telnyx callback authentication

`POST /webhooks/telnyx` requires Telnyx's `telnyx-signature-ed25519` and
`telnyx-timestamp` headers, not Basic auth or this service's API key.
Configure `TELNYX_PUBLIC_KEY` with your Telnyx account's base64 Ed25519 public
key (not your API key). For local Python use `.env`; on Cloudflare use the
Worker binding, configured as a non-secret `TELNYX_PUBLIC_KEY` entry in
`wrangler.toml`'s `[vars]` section. The public verification key is not a secret.

Verification covers the exact raw body prefixed with `timestamp|`.
Timestamps more than five minutes old or ahead are rejected with HTTP 401.
Missing or invalid server key configuration fails closed with HTTP 503.
Provision the public key before deploying this change or callbacks will fail.
The timestamp window limits replay age; it does not deduplicate retries within
that window. Test lifecycle fixtures bypass verification; signature tests use
real Ed25519 signing keys and the actual callback route.

### Live application logs

Application logging initializes in the app entrypoint for both Cloudflare and
local Python, without depending on Docker or Uvicorn configuration. JSON logs
are written immediately to stdout and appear alongside Cloudflare invocation
logs:

```bash
make tail-worker
```

Look for `webhook_received`, `webhook_processed`, `telnyx_completed`, and
`telnyx_rejected`. Provider failures include the actual Telnyx HTTP status and
numeric error codes; credentials, phone numbers, request/response bodies, and
speech content are not logged. No additional application access log is emitted.
Cloudflare's invocation `Ok` is not an HTTP status code.

Telnyx HTTP rejections return HTTP **502** from this API, with `detail`,
`provider: "telnyx"`, `provider_status` (for example 403), and
`provider_error_codes`. The same status and codes appear in `telnyx_rejected`
logs. Raw provider messages are deliberately excluded because they can echo
private request data. API authentication failures still use HTTP 401/403.
Start `make tail-worker` **before** reproducing an error: tail streams new
events, not historical ones. For past events use Cloudflare's persisted Logs.

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
