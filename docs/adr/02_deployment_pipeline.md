# ADR 02: Deployment Pipeline Strategy (GitHub Actions vs Cloudflare Git Builds)

## Status
Accepted

## Context
Cloudflare Workers offers native "Workers Builds" which connects directly to a GitHub repository and automatically deploys on every push to `main`. 

However, Cloudflare Workers Builds has a critical limitation:
- It triggers immediately on git push.
- It does **not** wait for or inspect external GitHub Actions test suites.
- If a commit introduces broken business logic, failing unit tests, or broken database queries, Cloudflare still builds and deploys it to production.

## Decision
We deploy exclusively through **GitHub Actions** (`.github/workflows/cicd.yaml`) using `uv run pywrangler deploy`. PyWrangler syncs Python dependencies and invokes the compatible Wrangler CLI:
1. Cloudflare Workers Builds Git integration is **disabled / disconnected** in the Cloudflare dashboard.
2. The deployment job runs only **after** the `validate` job succeeds (all linting, Ruff format checks, Mypy static typing, unit tests, and OpenAPI spec generation pass).
3. Cloudflare credentials (`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`) are stored in GitHub Actions Secrets.

## Consequences
- **Pros**:
  - **Quality Gate**: Broken code and failing tests never reach production.
  - **Single Pipeline**: All CI (lint, test, openapi build, release, deploy) is unified in one transparent GitHub Actions run.
  - **Clean Auditing**: Deployment logs, test logs, and release artifacts are visible in one place.
- **Cons**:
  - Requires maintaining `CLOUDFLARE_API_TOKEN` in GitHub Secrets.
