"""Detect OpenBB runtime availability without installing or creating credentials."""
from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json


ARTIFACT_DIR = ARTIFACT_ROOT / "openbb_autonomy"
RUNTIME_STATUS_PATH = ARTIFACT_DIR / "openbb_runtime_status.json"


def detect_openbb_runtime() -> dict[str, Any]:
    spec = importlib.util.find_spec("openbb")
    import_available = spec is not None
    import_error = ""
    version = ""
    status = "not_installed_adapter_ready"
    if import_available:
        try:
            version = importlib.metadata.version("openbb")
        except importlib.metadata.PackageNotFoundError as exc:
            import_error = f"{type(exc).__name__}: {exc}"
            status = "installed_version_unknown_adapter_ready"
        else:
            status = "installed_read_only_adapter_ready"
    record = {
        "artifact_type": "openbb_runtime_status",
        "runtime_detector_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "openbb_import_available": import_available,
        "openbb_version": version,
        "openbb_runtime_status": status,
        "openbb_import_error": import_error,
        "global_install_attempted": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "network_fetch_performed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["summary_hash"] = stable_hash(record)
    write_json(RUNTIME_STATUS_PATH, record)
    return {**record, "artifact_paths": {"openbb_runtime_status": str(RUNTIME_STATUS_PATH)}}


def runtime_status_path() -> str:
    return str(RUNTIME_STATUS_PATH)
