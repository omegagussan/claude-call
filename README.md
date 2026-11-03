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

## Makefile Commands Reference

| Command | Description |
| :--- | :--- |
| `make run` | Starts the FastAPI application with auto-reload. |
| `make test` | Runs all unit and integration tests using `pytest`. |
| `make test-unit` | Runs fast unit tests (`tests/unit/`). |
| `make test-integration` | Runs full multi-step lifecycle integration tests (`tests/integration/`). |
| `make test-v` | Runs pytest in verbose mode. |
| `make check` | Runs full CI checks: linter, format check, type check, and tests. |
| `make lint` | Checks code with Ruff. |
| `make lint-fix` | Automatically fixes linter issues with Ruff. |
| `make format` | Formats all code with Ruff. |
| `make format-check` | Verifies that all code is formatted according to Ruff. |
| `make typecheck` | Runs Mypy static type checking on `src` and `tests`. |
| `make openapi` | Generates the latest OpenAPI specification into `dist/openapi.json`. |
| `make pre-commit` | Manually executes all pre-commit hooks on all tracked files. |
| `make simulate` | Runs the CLI local dry-run call simulator. |

---

## Project Structure

```text
claude-call/
├── .github/workflows/
│   └── cicd.yaml                    # Automated linting, testing, and OpenAPI GitHub release
├── scripts/
│   └── generate_openapi.py          # Extracts OpenAPI 3.1 specification to dist/openapi.json
├── src/
│   ├── config.py                    # Pydantic settings for Telnyx & DB
│   ├── main.py                      # FastAPI routes & Telnyx webhook router
│   ├── migrations/                  # Raw SQL migrations (.sql)
│   ├── services/
│   │   ├── migrator.py              # Lightweight SQL migration runner
│   │   ├── time_service.py          # Stockholm time and speech duration estimation
│   │   ├── todo_service.py          # Todo business logic service
│   │   ├── todo_speech.py           # Speech intent parser (POP, PUSH, LIST)
│   │   └── todo_storage.py          # Storage interface, InMemory & Postgres implementations
│   ├── telnyx_client.py             # Async client for Telnyx REST Call Control API
│   └── version.py                   # Single-source version reader from pyproject.toml
├── tests/
│   ├── integration/                 # Multi-step webhook & call flow tests
│   ├── mock_telnyx.py               # Telnyx webhook event generator fixture
│   └── unit/                        # Unit tests for storage, time, and routes
├── Makefile                         # Shortcuts for testing, linting, and running
└── pyproject.toml                   # Project dependencies and tool configurations
```
