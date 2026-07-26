"""Audit provider-package imports across the active Python executables."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dopey_wealth_engine.common import REPO_ROOT, stable_hash

from .active_python_resolver import preferred_repo_python, python_inventory


PROVIDER_PACKAGES = ["yfinance", "openbb", "pandas", "numpy", "requests", "pandas_datareader", "yahooquery", "requests_cache"]


def audit_provider_imports(timeout_seconds: int) -> list[dict]:
    records: list[dict] = []
    for python_record in python_inventory(timeout_seconds):
        if not python_record.get("exists"):
            continue
        python_path = Path(str(python_record["python_path"]))
        records.extend(audit_imports_for_python(python_path, PROVIDER_PACKAGES, timeout_seconds))
    return records


def audit_imports_for_python(python_path: Path, packages: list[str], timeout_seconds: int) -> list[dict]:
    script = (
        "import importlib.util, json, sys; "
        f"pkgs={packages!r}; "
        "print(json.dumps({'executable': sys.executable, 'imports': {p: bool(importlib.util.find_spec(p)) for p in pkgs}}, sort_keys=True))"
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", script],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return [_package_record(str(python_path), package, "timeout", False, f"TimeoutExpired: {exc}") for package in packages]
    except OSError as exc:
        return [_package_record(str(python_path), package, "python_unusable", False, f"{type(exc).__name__}: {exc}") for package in packages]
    if completed.returncode != 0:
        return [_package_record(str(python_path), package, "audit_failed", False, completed.stderr[-500:]) for package in packages]
    try:
        parsed = json.loads(completed.stdout.strip())
        imports = parsed.get("imports", {})
    except json.JSONDecodeError as exc:
        return [_package_record(str(python_path), package, "audit_parse_failed", False, f"JSONDecodeError: {exc}") for package in packages]
    return [_package_record(str(python_path), package, "importable" if imports.get(package) else "missing", bool(imports.get(package)), "") for package in packages]


def repo_venv_import_status(timeout_seconds: int) -> dict[str, str]:
    records = audit_imports_for_python(preferred_repo_python(), PROVIDER_PACKAGES, timeout_seconds)
    return {str(record["package"]): str(record["import_status"]) for record in records}


def _package_record(python_path: str, package: str, status: str, importable: bool, error: str) -> dict:
    record = {
        "artifact_type": "provider_package_inventory",
        "python_path": python_path,
        "package": package,
        "import_status": status,
        "importable": importable,
        "error": error,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
    }
    record["record_hash"] = stable_hash(record)
    return record


def main() -> int:
    print(json.dumps({"provider_package_inventory": audit_provider_imports(5)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
