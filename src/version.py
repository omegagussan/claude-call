import tomllib
from pathlib import Path


def get_project_version() -> str:
    """Read the version dynamically from pyproject.toml."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        return str(data.get("project", {}).get("version", "0.1.0"))
    except Exception:
        return "0.1.0"


__version__ = get_project_version()
