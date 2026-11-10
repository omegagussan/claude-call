#!/usr/bin/env python3
"""
Production/dev entrypoint that wires the JSON log config into uvicorn.run().
Use this instead of the raw `uvicorn` CLI so log_config is applied correctly.

  Dev:   uv run python scripts/run.py --reload
  Local: uv run python scripts/run.py
"""

import sys

import uvicorn

from src.log_config import log_config

if __name__ == "__main__":
    reload = "--reload" in sys.argv
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=log_config,
        reload=reload,
    )
