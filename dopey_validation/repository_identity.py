"""Repository and interpreter identity checks that work in Git worktrees."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path


EXPECTED_PROJECT_NAME = "dopey"


def is_dopey_repository(repo_root: Path) -> bool:
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return False
    configuration = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = configuration.get("project")
    if not isinstance(project, dict):
        return False
    return project.get("name") == EXPECTED_PROJECT_NAME


def is_virtual_environment_active() -> bool:
    executable = Path(sys.executable)
    return executable.is_file() and Path(sys.prefix).resolve() != Path(sys.base_prefix).resolve()


def active_python_executable() -> Path:
    return Path(sys.executable).resolve()
