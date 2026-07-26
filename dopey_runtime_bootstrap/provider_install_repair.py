"""Repair public-data provider package installation into the repo venv."""
from __future__ import annotations

import subprocess
import time
import venv
from pathlib import Path

from dopey_wealth_engine.common import ARTIFACT_ROOT, REPO_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .active_python_resolver import REPO_VENV_PYTHON, launcher_python_used, preferred_repo_python, python_inventory
from .venv_package_import_audit import PROVIDER_PACKAGES, audit_imports_for_python, audit_provider_imports


ARTIFACT_DIR = ARTIFACT_ROOT / "provider_install"
SUMMARY_PATH = ARTIFACT_DIR / "provider_install_repair_summary.json"
PYTHON_INVENTORY_PATH = ARTIFACT_DIR / "provider_python_inventory.jsonl"
PACKAGE_INVENTORY_PATH = ARTIFACT_DIR / "provider_package_inventory.jsonl"
INSTALL_RECORDS_PATH = ARTIFACT_DIR / "provider_install_records.jsonl"
IMPORT_VERIFICATION_PATH = ARTIFACT_DIR / "provider_import_verification.jsonl"
PROOF_PATH = ARTIFACT_DIR / "provider_install_repair_proof.jsonl"


def run_provider_install_repair(package_timeout_seconds: int, openbb_timeout_seconds: int, attempt_openbb: bool) -> dict:
    ensure_repo_venv()
    python_records = python_inventory(5)
    before_records = audit_provider_imports(5)
    install_records: list[dict] = []
    install_records.append(_run_install(["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], package_timeout_seconds, "upgrade_core_packaging"))
    install_records.append(_run_install(["-m", "pip", "install", "yfinance", "pandas-datareader", "requests-cache", "yahooquery"], package_timeout_seconds, "install_public_provider_packages"))
    if attempt_openbb:
        install_records.append(_run_install(["-m", "pip", "install", "openbb"], openbb_timeout_seconds, "install_openbb_optional"))
    verification = audit_imports_for_python(preferred_repo_python(), PROVIDER_PACKAGES, 8)
    launcher = launcher_python_used()
    status_by_package = {str(record["package"]): str(record["import_status"]) for record in verification}
    install_attempts = len(install_records)
    install_success_count = sum(1 for record in install_records if record["status"] == "pass")
    install_timeout_count = sum(1 for record in install_records if record["status"] == "inconclusive_timeout")
    install_failure_count = sum(1 for record in install_records if record["status"] == "fail")
    active_python_status = "repo_venv_available"
    if launcher["explicit_repo_venv_command_required"]:
        active_python_status = "plain_python_outside_repo_venv_explicit_venv_required"
    summary = {
        "artifact_type": "provider_install_repair_summary",
        "provider_install_repair_version": "dopey-provider-install-repair-v2",
        "active_python_status": active_python_status,
        "repo_venv_exists": REPO_VENV_PYTHON.exists(),
        "repo_venv_python": str(REPO_VENV_PYTHON),
        "python_used_by_launcher": launcher,
        "yfinance_import_status": status_by_package.get("yfinance", "missing"),
        "pandas_datareader_import_status": status_by_package.get("pandas_datareader", "missing"),
        "yahooquery_import_status": status_by_package.get("yahooquery", "missing"),
        "openbb_import_status": status_by_package.get("openbb", "missing"),
        "install_attempt_count": install_attempts,
        "install_success_count": install_success_count,
        "install_timeout_count": install_timeout_count,
        "install_failure_count": install_failure_count,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(PYTHON_INVENTORY_PATH, python_records, False)
    write_jsonl(PACKAGE_INVENTORY_PATH, before_records, False)
    write_jsonl(INSTALL_RECORDS_PATH, install_records, False)
    write_jsonl(IMPORT_VERIFICATION_PATH, verification, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("provider-install-repair", "complete", summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def ensure_repo_venv() -> Path:
    if REPO_VENV_PYTHON.exists():
        return REPO_VENV_PYTHON
    builder = venv.EnvBuilder(with_pip=True, clear=False, symlinks=False)
    builder.create(str(REPO_ROOT / ".venv"))
    return REPO_VENV_PYTHON


def _run_install(arguments: list[str], timeout_seconds: int, install_id: str) -> dict:
    start = time.monotonic()
    command = [str(preferred_repo_python()), *arguments]
    try:
        completed = subprocess.run(command, cwd=str(REPO_ROOT), text=True, capture_output=True, timeout=timeout_seconds)
        status = "pass" if completed.returncode == 0 else "fail"
        exit_code: int | None = completed.returncode
        stdout_tail = completed.stdout[-1200:]
        stderr_tail = completed.stderr[-1200:]
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        status = "inconclusive_timeout"
        exit_code = None
        stdout_tail = _decode_timeout_stream(exc.stdout)[-1200:]
        stderr_tail = _decode_timeout_stream(exc.stderr)[-1200:]
        timed_out = True
    record = {
        "artifact_type": "provider_install_record",
        "install_id": install_id,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - start, 6),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "timeout_recorded_as_pass": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _decode_timeout_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def artifact_paths() -> dict[str, str]:
    return {
        "provider_install_repair_summary": str(SUMMARY_PATH),
        "provider_python_inventory": str(PYTHON_INVENTORY_PATH),
        "provider_package_inventory": str(PACKAGE_INVENTORY_PATH),
        "provider_install_records": str(INSTALL_RECORDS_PATH),
        "provider_import_verification": str(IMPORT_VERIFICATION_PATH),
        "provider_install_repair_proof": str(PROOF_PATH),
    }
