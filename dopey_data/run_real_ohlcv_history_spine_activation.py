"""Write real OHLCV history-spine activation gate artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .real_ohlcv_history_spine_activation import (
    REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH,
    REAL_OHLCV_HISTORY_ACTIVATION_PROOF_PATH,
    REAL_OHLCV_HISTORY_ACTIVATION_QUALITY_FLAGS_PATH,
    REAL_OHLCV_HISTORY_DATE_COVERAGE_PATH,
    REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH,
    REAL_OHLCV_HISTORY_SYMBOL_COVERAGE_PATH,
    build_real_ohlcv_history_spine_activation,
)


REAL_OHLCV_HISTORY_SPINE_UPGRADE_COMPAT_PATH = REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH.parent / "real_ohlcv_history_spine_upgrade.json"
REAL_OHLCV_HISTORY_QUALITY_FLAGS_COMPAT_PATH = REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH.parent / "real_ohlcv_history_quality_flags.jsonl"
REAL_OHLCV_HISTORY_SPINE_PROOF_COMPAT_PATH = REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH.parent / "real_ohlcv_history_spine_proof.jsonl"


def run_real_ohlcv_history_spine_activation() -> dict[str, Any]:
    result = build_real_ohlcv_history_spine_activation()
    _write_json(REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH, result["activation"])
    _write_json(REAL_OHLCV_HISTORY_SPINE_UPGRADE_COMPAT_PATH, _compat_upgrade_record(result["activation"]))
    _write_jsonl(REAL_OHLCV_HISTORY_SYMBOL_COVERAGE_PATH, result["symbol_coverage"])
    _write_jsonl(REAL_OHLCV_HISTORY_DATE_COVERAGE_PATH, result["date_coverage"])
    _write_jsonl(REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH, result["blockers"])
    _write_jsonl(REAL_OHLCV_HISTORY_ACTIVATION_QUALITY_FLAGS_PATH, result["quality_flags"])
    _write_jsonl(REAL_OHLCV_HISTORY_QUALITY_FLAGS_COMPAT_PATH, result["quality_flags"])
    _write_jsonl(REAL_OHLCV_HISTORY_ACTIVATION_PROOF_PATH, result["proof"])
    _write_jsonl(REAL_OHLCV_HISTORY_SPINE_PROOF_COMPAT_PATH, result["proof"])
    return {**result["activation"], "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "real_ohlcv_history_spine_activation": str(REAL_OHLCV_HISTORY_SPINE_ACTIVATION_PATH),
        "real_ohlcv_history_spine_upgrade": str(REAL_OHLCV_HISTORY_SPINE_UPGRADE_COMPAT_PATH),
        "real_ohlcv_history_symbol_coverage": str(REAL_OHLCV_HISTORY_SYMBOL_COVERAGE_PATH),
        "real_ohlcv_history_date_coverage": str(REAL_OHLCV_HISTORY_DATE_COVERAGE_PATH),
        "real_ohlcv_history_activation_blockers": str(REAL_OHLCV_HISTORY_ACTIVATION_BLOCKERS_PATH),
        "real_ohlcv_history_activation_quality_flags": str(REAL_OHLCV_HISTORY_ACTIVATION_QUALITY_FLAGS_PATH),
        "real_ohlcv_history_quality_flags": str(REAL_OHLCV_HISTORY_QUALITY_FLAGS_COMPAT_PATH),
        "real_ohlcv_history_activation_proof": str(REAL_OHLCV_HISTORY_ACTIVATION_PROOF_PATH),
        "real_ohlcv_history_spine_proof": str(REAL_OHLCV_HISTORY_SPINE_PROOF_COMPAT_PATH),
    }


def _compat_upgrade_record(activation: dict[str, Any]) -> dict[str, Any]:
    return {
        **activation,
        "artifact_type": "real_ohlcv_history_spine_upgrade",
        "upgrade_version": "dopey-real-ohlcv-history-spine-upgrade-compat-v1",
        "history_spine_status": "valid_real_history_spine" if activation["valid_real_dataset"] else "missing_real_dataset",
        "history_spine_upgrade_status": activation["history_spine_activation_status"],
        "upgrade_hash": activation["activation_hash"],
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_real_ohlcv_history_spine_activation()
    print(json.dumps({
        "history_spine_activation_status": result["history_spine_activation_status"],
        "valid_real_dataset": result["valid_real_dataset"],
        "real_history_used": result["real_history_used"],
        "real_ohlcv_rows_activated": result["real_ohlcv_rows_activated"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
