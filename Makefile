.PHONY: test test-unit test-integration test-v typecheck lint format check run simulate pre-commit-install openapi generate-openapi migrate migrate-d1 test-migrate setup-env sync-worker stage-worker build-worker dev-worker deploy-worker tail-worker

SQLITE_PATH ?= .local/claude-call.sqlite3

setup-env:
	@if [ ! -f .env ]; then cp .env.example .env && echo "[+] Created .env from .env.example"; fi

sync-worker:
	@rm -f requirements.txt
	uv run pywrangler sync

stage-worker: sync-worker
	uv run python scripts/stage_worker.py

build-worker: sync-worker openapi
	@echo "[+] Worker dependencies and OpenAPI assets built successfully."

dev-worker: setup-env sync-worker
	uv run pywrangler dev

tail-worker:
	npx --no-install wrangler tail claude-call --format pretty

deploy-worker: build-worker
	$(MAKE) migrate-d1
	uv run pywrangler deploy

migrate-d1:
	npx --no-install wrangler d1 migrations apply claude_call_db --remote

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

test-v:
	uv run pytest -v

typecheck:
	uv run mypy src tests

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

format:
	uv run ruff format .

check: lint format-check typecheck test

format-check:
	uv run ruff format --check .

pre-commit-install:
	uv run pre-commit install

pre-commit:
	uv run pre-commit run --all-files

run:
	uv run uvicorn src.main:app --reload

simulate:
	uv run python tests/integration/test_telnyx_client_simulation.py

openapi generate-openapi:
	uv run python scripts/generate_openapi.py

migrate:
	uv run python scripts/migrate.py "$(SQLITE_PATH)"

test-migrate:
	uv run pytest tests/integration/test_sqlite_storage.py
