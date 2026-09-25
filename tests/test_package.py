"""Package-level guarantees from the ADRs."""

from importlib import resources
from pathlib import Path
import tomllib

import health_tree

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _project() -> dict[str, object]:
    project: dict[str, object] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))[
        "project"
    ]
    return project


def test_version_matches_pyproject() -> None:
    """The package version matches pyproject.toml (ADR 0015)."""
    assert health_tree.__version__ == _project()["version"]


def test_has_no_runtime_dependencies() -> None:
    """The library installs nothing else (ADR 0002)."""
    assert _project()["dependencies"] == []


def test_ships_type_information() -> None:
    """The package is marked as typed (PEP 561)."""
    assert resources.files(health_tree).joinpath("py.typed").is_file()
