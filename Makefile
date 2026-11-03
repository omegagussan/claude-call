.PHONY: test test-unit test-integration test-v typecheck lint format check run simulate pre-commit-install openapi generate-openapi

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
	uv run python scripts/migrate.py

docker-build:
	docker build -t claude-call:latest .

docker-run:
	docker run -p 8000:8000 --rm claude-call:latest
