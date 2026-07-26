"""Write real signal validation gate artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .real_signal_validation_gate import (
    REAL_DIRECTIONAL_SETUP_RECORDS_PATH,
    REAL_SIGNAL_QUALITY_FLAGS_PATH,
    REAL_SIGNAL_RECORDS_PATH,
    REAL_SIGNAL_VALIDATION_INPUT_PATH,
    REAL_SIGNAL_VALIDATION_PROOF_PATH,
    REAL_SIGNAL_VALIDATION_SUMMARY_PATH,
    build_real_signal_validation_gate,
)


def run_real_signal_validation_gate() -> dict[str, Any]:
    result = build_real_signal_validation_gate()
    _write_json(REAL_SIGNAL_VALIDATION_INPUT_PATH, result["input"])
    _write_jsonl(REAL_SIGNAL_RECORDS_PATH, result["signals"])
    _write_jsonl(REAL_DIRECTIONAL_SETUP_RECORDS_PATH, result["directional"])
    _write_jsonl(REAL_SIGNAL_QUALITY_FLAGS_PATH, result["flags"])
    _write_json(REAL_SIGNAL_VALIDATION_SUMMARY_PATH, {**result["summary"], "artifact_paths": artifact_paths()})
    _write_jsonl(REAL_SIGNAL_VALIDATION_PROOF_PATH, result["proof"])
    return {**result["summary"], "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "real_signal_validation_input": str(REAL_SIGNAL_VALIDATION_INPUT_PATH),
        "real_signal_records": str(REAL_SIGNAL_RECORDS_PATH),
        "real_directional_setup_records": str(REAL_DIRECTIONAL_SETUP_RECORDS_PATH),
        "real_signal_quality_flags": str(REAL_SIGNAL_QUALITY_FLAGS_PATH),
        "real_signal_validation_summary": str(REAL_SIGNAL_VALIDATION_SUMMARY_PATH),
        "real_signal_validation_proof": str(REAL_SIGNAL_VALIDATION_PROOF_PATH),
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    result = run_real_signal_validation_gate()
    print(json.dumps({
        "real_signal_validation_status": result["real_signal_validation_status"],
        "real_signal_evidence": result["real_signal_evidence"],
        "real_history_used": result["real_history_used"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
