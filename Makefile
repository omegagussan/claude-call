.PHONY: test test-unit test-integration test-v run simulate

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

test-v:
	uv run pytest -v

run:
	uv run uvicorn src.main:app --reload

simulate:
	uv run python tests/integration/test_telnyx_client_simulation.py
