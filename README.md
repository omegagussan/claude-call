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
