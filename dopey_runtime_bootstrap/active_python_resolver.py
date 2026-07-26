"""Resolve the active Python paths that matter for public provider installs."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from dopey_wealth_engine.common import REPO_ROOT, stable_hash


REPO_VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def python_inventory(timeout_seconds: int) -> list[dict]:
    records: list[dict] = []
    records.append(_python_record("current_sys_executable", Path(sys.executable), True))
    records.append(_python_record("repo_venv", REPO_VENV_PYTHON, REPO_VENV_PYTHON.exists()))
    path_python = shutil.which("python")
    if path_python:
        records.append(_python_record("path_python", Path(path_python), Path(path_python).exists()))
    records.extend(_py_launcher_records(timeout_seconds))
    return records


def preferred_repo_python() -> Path:
    if REPO_VENV_PYTHON.exists():
        return REPO_VENV_PYTHON
    return Path(sys.executable)


def launcher_python_used() -> dict:
    path_python = shutil.which("python") or ""
    uses_repo_venv = bool(path_python) and Path(path_python).resolve() == preferred_repo_python().resolve()
    status = "repo_venv_python" if uses_repo_venv else "path_python_outside_repo_venv"
    record = {
        "artifact_type": "provider_python_launcher_resolution",
        "python_used_by_plain_python": path_python,
        "repo_venv_python": str(REPO_VENV_PYTHON),
        "recommended_python": str(preferred_repo_python()),
        "status": status,
        "explicit_repo_venv_command_required": not uses_repo_venv,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _python_record(source: str, path: Path, exists: bool) -> dict:
    record = {
        "artifact_type": "provider_python_inventory",
        "source": source,
        "python_path": str(path),
        "exists": exists,
        "is_repo_venv": path == REPO_VENV_PYTHON,
        "is_current_sys_executable": path == Path(sys.executable),
    }
    record["record_hash"] = stable_hash(record)
    return record


def _py_launcher_records(timeout_seconds: int) -> list[dict]:
    py_path = shutil.which("py")
    if not py_path:
        return []
    try:
        completed = subprocess.run(
            [py_path, "-0p"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    records: list[dict] = []
    for line in completed.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split(None, 1)
        candidate = parts[-1].strip()
        if candidate.lower().endswith(".exe"):
            records.append(_python_record("py_launcher", Path(candidate), Path(candidate).exists()))
    return records


def main() -> int:
    print(json.dumps({"python_inventory": python_inventory(5), "launcher": launcher_python_used()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
