import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

DOCKERFILE_PATH = Path(__file__).resolve().parent.parent.parent / "Dockerfile"


@pytest.mark.asyncio
async def test_server_health_endpoint():
    """Verify that the /health endpoint responds properly for container probes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


def test_dockerfile_structure():
    """Verify that the Dockerfile exists, is slim multi-stage, and configures the healthcheck."""
    assert DOCKERFILE_PATH.exists()
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")

    # Assert multi-stage slim base
    assert "FROM python:3.13-slim AS builder" in content
    assert "FROM python:3.13-slim AS runtime" in content
    assert "uv sync --frozen --no-dev" in content

    # Assert healthcheck against /health
    assert "HEALTHCHECK" in content
    assert "/health" in content

    # Assert non-root user
    assert "USER appuser" in content


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker daemon is not available on this host")
def test_docker_build_and_start_container():
    """Integration test that builds the docker container and checks /health if docker is installed."""
    build_cmd = ["docker", "build", "-t", "claude-call-test:latest", "."]
    subprocess.run(build_cmd, check=True)
