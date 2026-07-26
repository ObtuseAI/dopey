"""Run a module through the repo venv Python when it exists."""
from __future__ import annotations

import subprocess
import sys

from dopey_wealth_engine.common import REPO_ROOT

from .active_python_resolver import preferred_repo_python


def run_module_with_repo_venv(module_name: str, arguments: list[str]) -> int:
    command = [str(preferred_repo_python()), "-m", module_name, *arguments]
    completed = subprocess.run(command, cwd=str(REPO_ROOT))
    return int(completed.returncode)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m dopey_runtime_bootstrap.repo_venv_launcher <module> [args...]")
        return 2
    return run_module_with_repo_venv(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
