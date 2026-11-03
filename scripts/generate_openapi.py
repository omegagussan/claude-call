#!/usr/bin/env python3
"""Generate openapi.json from FastAPI application."""

import json
import sys
from pathlib import Path

# Ensure project root is in PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app  # noqa: E402

OUTPUT_DIR = Path("dist")


def generate():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()

    json_path = OUTPUT_DIR / "openapi.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[+] Successfully generated OpenAPI spec at {json_path}")


if __name__ == "__main__":
    generate()
