# Stage 1: Build virtual environment using uv
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv from official binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency specifications
COPY pyproject.toml uv.lock ./

# Install production dependencies only (no dev packages)
RUN uv sync --frozen --no-dev

# Stage 2: Minimal runtime image
FROM python:3.13-slim AS runtime

WORKDIR /app

# Security: run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application source and migrations
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY pyproject.toml /app/pyproject.toml

# Set permissions
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check against /health endpoint
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

# Start FastAPI application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "src/log_config.json"]
