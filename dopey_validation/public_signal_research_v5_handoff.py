"""Shared-handoff re-sync for V5 after validation completes.

Copies all V5 handoff artifacts to both shared targets, writes
SESSION_COPY_MANIFEST.json in each available target, and writes the local
session copy manifest.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from dopey_autonomy.run_public_signal_research_breakthrough_v5 import (
    HANDOFF_FOLDER,
    _build_handoff_file_list,
)
from dopey_autonomy.signal_research_v5_common import RESEARCH_V5_ROOT, utc_now_iso
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["sync_v5_shared_handoff"]


LOCAL_MANIFEST_PATH = RESEARCH_V5_ROOT / "public_signal_research_breakthrough_v5_session_copy_manifest.json"


def sync_v5_shared_handoff() -> dict[str, object]:
    files = _build_handoff_file_list()
    targets = [
        Path("C:/Users/CH/Desktop/Shared Folder"),
        Path("//FRANKENSTEIN/Shared Folder"),
    ]
    target_results: list[dict[str, object]] = []
    overall_status: list[str] = []
    overall_copied = 0
    overall_target = ""

    for base in targets:
        result: dict[str, object] = {"target_root": str(base), "copied_count": 0, "error": ""}
        if not base.exists():
            result["error"] = f"target_not_available: {base}"
            target_results.append(result)
            overall_status.append("target_failed")
            continue
        dest = base / HANDOFF_FOLDER
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        file_records: list[dict[str, object]] = []
        for path in files:
            if not path.exists():
                continue
            try:
                shutil.copy2(path, dest / path.name)
                copied += 1
                data = path.read_bytes()
                file_records.append(
                    {
                        "file_name": path.name,
                        "file_size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            except OSError as exc:
                file_records.append(
                    {"file_name": path.name, "file_size": 0, "sha256": "", "error": str(exc)}
                )
        manifest = {
            "target_root": str(dest),
            "copied_count": copied,
            "missing_count": len(files) - copied,
            "file_names": [fr["file_name"] for fr in file_records],
            "file_sizes": {fr["file_name"]: fr["file_size"] for fr in file_records},
            "hashes": {fr["file_name"]: fr["sha256"] for fr in file_records},
            "live_trading_enabled": False,
            "credentials_present": False,
            "broker_connection_enabled": False,
            "real_order_enabled": False,
            "timestamp": utc_now_iso(),
        }
        manifest_path = dest / "SESSION_COPY_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        result["copied_count"] = copied
        result["manifest_path"] = str(manifest_path)
        target_results.append(result)
        overall_status.append("copied")
        overall_copied = copied
        overall_target = str(dest)

    if all(s == "target_failed" for s in overall_status):
        shared_copy_status = "no_target_available"
    elif any(s == "target_failed" for s in overall_status):
        shared_copy_status = "partial_copy"
    else:
        shared_copy_status = "copied"

    local_manifest = {
        "target_root": overall_target,
        "copied_count": overall_copied,
        "target_results": target_results,
        "live_trading_enabled": False,
        "credentials_present": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "timestamp": utc_now_iso(),
    }
    LOCAL_MANIFEST_PATH.write_text(json.dumps(local_manifest, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "shared_copy_status": shared_copy_status,
        "target_root": overall_target,
        "copied_count": overall_copied,
        "target_results": target_results,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(sync_v5_shared_handoff(), indent=2, sort_keys=True, default=str))
