"""Local dependency bootstrap for the DOPEY wealth engine."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
import venv
from pathlib import Path

from dopey_wealth_engine.common import ARTIFACT_ROOT, REPO_ROOT, proof_record, stable_hash, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "runtime_bootstrap"
SUMMARY_PATH = ARTIFACT_DIR / "local_dependency_bootstrap_summary.json"
STEPS_PATH = ARTIFACT_DIR / "local_dependency_bootstrap_steps.jsonl"
INSTALL_RECORDS_PATH = ARTIFACT_DIR / "local_dependency_bootstrap_install_records.jsonl"
PROOF_PATH = ARTIFACT_DIR / "local_dependency_bootstrap_proof.jsonl"
PACKAGE_CANDIDATES = [
    "openbb", "yfinance", "pandas", "numpy", "scipy", "matplotlib", "plotly",
    "pandas-ta", "mplfinance", "requests", "beautifulsoup4", "lxml", "pyarrow", "fastparquet",
]
IMPORT_NAMES = {
    "pandas-ta": "pandas_ta",
    "beautifulsoup4": "bs4",
}


def detect_python_environment(repo_root: Path) -> dict:
    venv_path = repo_root / ".venv"
    active_venv = sys.prefix != sys.base_prefix
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "active_venv": active_venv,
        "repo_venv_path": str(venv_path),
        "repo_venv_exists": venv_path.exists(),
    }


def ensure_repo_venv(repo_root: Path, steps: list[dict]) -> Path:
    venv_path = repo_root / ".venv"
    if venv_path.exists():
        steps.append({"step_id": "venv-detect", "status": "exists", "path": str(venv_path)})
        return venv_path
    start = time.monotonic()
    venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(venv_path)
    steps.append({
        "step_id": "venv-create",
        "status": "created",
        "path": str(venv_path),
        "duration_seconds": round(time.monotonic() - start, 6),
    })
    return venv_path


def venv_python(venv_path: Path) -> Path:
    candidate = venv_path / "Scripts" / "python.exe"
    if candidate.exists():
        return candidate
    return venv_path / "bin" / "python"


def import_available(package_name: str) -> bool:
    import_name = IMPORT_NAMES.get(package_name, package_name.replace("-", "_"))
    return importlib.util.find_spec(import_name) is not None


def install_package(python_path: Path, package_name: str, timeout_seconds: int) -> dict:
    command = [str(python_path), "-m", "pip", "install", "--disable-pip-version-check", package_name]
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        status = "installed" if completed.returncode == 0 else "install_failed"
        return {
            "package": package_name,
            "status": status,
            "exit_code": completed.returncode,
            "duration_seconds": round(time.monotonic() - start, 6),
            "timed_out": False,
            "stdout_tail": completed.stdout[-1200:],
            "stderr_tail": completed.stderr[-1200:],
            "global_install_attempted": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        return {
            "package": package_name,
            "status": "install_timeout_fallback_allowed",
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - start, 6),
            "timed_out": True,
            "stdout_tail": stdout[-1200:],
            "stderr_tail": stderr[-1200:],
            "global_install_attempted": False,
        }


def run_local_dependency_bootstrap(timeout_seconds: int) -> dict:
    steps: list[dict] = []
    install_records: list[dict] = []
    environment = detect_python_environment(REPO_ROOT)
    steps.append({"step_id": "python-detect", "status": "ok", "environment": environment})
    venv_path = ensure_repo_venv(REPO_ROOT, steps)
    python_path = venv_python(venv_path)
    steps.append({"step_id": "install-target", "status": "repo_venv", "python_path": str(python_path)})

    installed_count = 0
    fallback_count = 0
    already_available_count = 0
    for package_name in PACKAGE_CANDIDATES:
        if import_available(package_name):
            record = {
                "package": package_name,
                "status": "already_available_in_active_python",
                "duration_seconds": 0.0,
                "timed_out": False,
                "global_install_attempted": False,
            }
            already_available_count += 1
        elif timeout_seconds <= 0:
            record = {
                "package": package_name,
                "status": "install_skipped_zero_timeout_fallback_allowed",
                "duration_seconds": 0.0,
                "timed_out": False,
                "global_install_attempted": False,
            }
            fallback_count += 1
        else:
            per_package_timeout = min(max(timeout_seconds * 2, 5), 15) if package_name == "openbb" else timeout_seconds
            record = install_package(python_path, package_name, per_package_timeout)
            if record["status"] == "installed":
                installed_count += 1
            else:
                fallback_count += 1
        install_records.append(record)

    bootstrap_status = "completed_with_installs" if installed_count else "completed_with_fallbacks"
    summary = {
        "artifact_type": "local_dependency_bootstrap_summary",
        "bootstrap_version": "dopey-local-dependency-bootstrap-v1",
        "bootstrap_status": bootstrap_status,
        "python_environment": environment,
        "install_target_python": str(python_path),
        "package_candidates": PACKAGE_CANDIDATES,
        "installed_count": installed_count,
        "already_available_count": already_available_count,
        "fallback_package_count": fallback_count,
        "install_failures_do_not_block_internal_engines": True,
        "openbb_absence_terminal": False,
        "yfinance_absence_terminal": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
        "global_install_attempted": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(STEPS_PATH, steps, False)
    write_jsonl(INSTALL_RECORDS_PATH, install_records, False)
    write_jsonl(PROOF_PATH, [proof_record("local-dependency-bootstrap", summary["bootstrap_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "local_dependency_bootstrap_summary": str(SUMMARY_PATH),
        "local_dependency_bootstrap_steps": str(STEPS_PATH),
        "local_dependency_bootstrap_install_records": str(INSTALL_RECORDS_PATH),
        "local_dependency_bootstrap_proof": str(PROOF_PATH),
    }
