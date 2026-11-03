# AGENTS.md

Guidelines for agentic AI pairs and automated contributors working on `claude-call`.

## Core Philosophy & Stack
- **Python >=3.15** with package management via **`uv`**.
- **FastAPI** for webhooks and call control routes; **`httpx`** for async external requests.
- **Ruff** for formatting/linting and **Mypy** for static type checks.
- Zero extra migration dependencies: raw versioned SQL in `src/migrations/` managed by `DatabaseMigrator`.

## Project Structure
- `src/`: Application code (`main.py`, `config.py`, `telnyx_client.py`, `version.py`).
- `src/services/`: Business domain logic (`time_service.py`, `todo_service.py`, `todo_storage.py`, `migrator.py`).
- `src/migrations/`: Raw `.sql` migrations with `{schema}`, `{table}`, and `{app_role}` placeholders.
- `tests/unit/`: Fast unit tests for isolated functions and route error handling.
- `tests/integration/`: Multi-step call lifecycle & webhook tests mocking Telnyx with `respx`.
- `scripts/`: Tooling scripts (`generate_openapi.py`).

## Essential Commands
Always use the `Makefile` targets:
- `make check`: **Mandatory before committing.** Runs lint, format check, mypy typecheck, and pytest.
- `make test`: Runs all pytest suites.
- `make test-unit`: Runs `tests/unit/`.
- `make test-integration`: Runs `tests/integration/`.
- `make lint-fix`: Auto-fixes linter issues with Ruff.
- `make format`: Formats code with Ruff.
- `make openapi`: Generates `dist/openapi.json` from the FastAPI schema.
- `make run`: Starts FastAPI local dev server on port 8000 with auto-reload.

## Development Rules for Agents
1. **Never make real external API calls in tests**: Use `respx.mock` and `tests/mock_telnyx.py` to generate simulated Telnyx webhook payloads.
2. **Preserve Type Annotations**: Use modern Python types (`list[str]`, `dict[str, Any]`, `X | None`). Do not re-introduce deprecated `typing.List` / `typing.Dict`.
3. **Storage Interfaces**: If altering or adding storage features, implement them against `TodoStorage` interface in `src/services/todo_storage.py`. Default to `InMemoryTodoStorage` for tests.
4. **Version Single-Sourcing**: The version lives in `pyproject.toml` and is dynamically read by `src/version.py`. Do not hardcode versions in `main.py`.
