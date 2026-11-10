"""Stage application sources with their package layout intact for Wrangler."""

import shutil
from pathlib import Path


def stage_worker(project_root: Path) -> Path:
    destination = project_root / ".wrangler" / "worker"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        project_root / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(project_root / "pyproject.toml", destination / "pyproject.toml")
    return destination


if __name__ == "__main__":
    stage_worker(Path(__file__).resolve().parent.parent)
