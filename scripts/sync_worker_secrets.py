import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRET_NAMES = ("API_KEYS", "TELNYX_API_KEY")


def sync_worker_secrets() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        raise ValueError("Missing .env file; run make setup-env and configure both API secrets.")
    values = dotenv_values(env_file, interpolate=False)
    missing = [key for key in SECRET_NAMES if not (values.get(key) or "").strip()]
    if missing:
        raise ValueError(f"Missing .env values: {', '.join(missing)}")

    env = os.environ.copy()
    for canonical, legacy in (
        ("CLOUDFLARE_API_TOKEN", "CLOUDFLAIR_DEPLOY_KEY"),
        ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLAIR_ACCOUNT_ID"),
    ):
        value = env.get(canonical) or values.get(canonical) or values.get(legacy)
        if value:
            env[canonical] = value
    try:
        result = subprocess.run(
            ["npx", "--no-install", "wrangler", "secret", "bulk"],
            input=json.dumps({key: values[key] for key in SECRET_NAMES}),
            text=True,
            capture_output=True,
            cwd=PROJECT_ROOT,
            env=env,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("npx is unavailable; activate the project's Node.js version and run npm ci.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Wrangler secret synchronization timed out; remote state is unknown.") from exc
    if result.returncode:
        raise RuntimeError(
            "Wrangler secret synchronization failed; check Cloudflare authentication and Workers Scripts Edit "
            "permission. Remote state may be partially updated. Output suppressed to protect credentials."
        )
    print("Synchronized API_KEYS and TELNYX_API_KEY to Cloudflare; other bindings are unchanged.")


def main() -> int:
    try:
        sync_worker_secrets()
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
