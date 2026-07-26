"""Remove stale test-only rows from intermediate public signal artifacts."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    HARDENING_VERSION,
    SIGNAL_CANDIDATES_PATH,
    decision_artifacts_simv2_counts,
    hardening_proof_record,
    live_safety_fields,
    simv2_rows_in_artifact,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    SIGNAL_ROOT,
    is_test_symbol,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
)


SUMMARY_PATH = HARDENING_ROOT / "public_signal_artifact_cleaner_summary.json"
REMOVED_PATH = HARDENING_ROOT / "public_signal_artifact_cleaner_removed_rows.jsonl"
QUALITY_FLAGS_PATH = HARDENING_ROOT / "public_signal_artifact_cleaner_quality_flags.jsonl"
PROOF_PATH = HARDENING_ROOT / "public_signal_artifact_cleaner_proof.jsonl"
BACKUP_ROOT = SIGNAL_ROOT / "backups"


def run_public_signal_artifact_cleaner_v1() -> dict[str, object]:
    if not SIGNAL_CANDIDATES_PATH.exists():
        summary = _empty_summary("signal_artifact_missing")
        return {**summary, "artifact_paths": artifact_paths()}

    records = read_jsonl_file(SIGNAL_CANDIDATES_PATH)
    kept: list[dict[str, object]] = []
    removed: list[dict[str, object]] = []
    for record in records:
        symbol = str(record.get("symbol", ""))
        if is_test_symbol(symbol):
            removed.append(record_with_hash({
                "artifact_type": "public_signal_artifact_cleaner_removed_row",
                "symbol": symbol,
                "signal_id": record.get("signal_id", ""),
                "strategy_id": record.get("strategy_id", ""),
                "reason": "test_symbol_prefix",
                **live_safety_fields(),
            }, "record_hash"))
        else:
            kept.append(record)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_ROOT / f"public_signal_mutation_candidates_v4_pre_clean_{timestamp}.jsonl"
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SIGNAL_CANDIDATES_PATH, backup_path)
    write_jsonl_file(SIGNAL_CANDIDATES_PATH, kept)

    decision_counts = decision_artifacts_simv2_counts()
    quality_flags = [
        record_with_hash({
            "artifact_type": "public_signal_artifact_cleaner_quality_flag",
            "flag_id": "simv2_rows_remaining_in_signal_candidates",
            "value": simv2_rows_in_artifact(SIGNAL_CANDIDATES_PATH),
            "passed": simv2_rows_in_artifact(SIGNAL_CANDIDATES_PATH) == 0,
            **live_safety_fields(),
        }, "record_hash"),
        record_with_hash({
            "artifact_type": "public_signal_artifact_cleaner_quality_flag",
            "flag_id": "decision_artifacts_clean",
            "value": decision_counts,
            "passed": all(value == 0 for value in decision_counts.values()),
            **live_safety_fields(),
        }, "record_hash"),
    ]
    summary = {
        "artifact_type": "public_signal_artifact_cleaner_summary",
        "public_signal_artifact_cleaner_version": "dopey-public-signal-artifact-cleaner-v1",
        "signal_artifact_cleaner_status": "signal_artifact_cleaned",
        "input_signal_count": len(records),
        "removed_test_signal_count": len(removed),
        "output_signal_count": len(kept),
        "simv2_rows_remaining": simv2_rows_in_artifact(SIGNAL_CANDIDATES_PATH),
        "backup_path": str(backup_path),
        "decision_artifact_simv2_counts": decision_counts,
        "decision_artifacts_clean": all(value == 0 for value in decision_counts.values()),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(REMOVED_PATH, removed)
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "public-signal-artifact-cleaner-v1", str(summary["signal_artifact_cleaner_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def _empty_summary(status: str) -> dict[str, object]:
    summary = {
        "artifact_type": "public_signal_artifact_cleaner_summary",
        "public_signal_artifact_cleaner_version": "dopey-public-signal-artifact-cleaner-v1",
        "signal_artifact_cleaner_status": status,
        "input_signal_count": 0,
        "removed_test_signal_count": 0,
        "output_signal_count": 0,
        "simv2_rows_remaining": 0,
        "decision_artifacts_clean": True,
        **live_safety_fields(),
    }
    return write_summary_with_hash(SUMMARY_PATH, summary)


def artifact_paths() -> dict[str, str]:
    return {
        "public_signal_artifact_cleaner_summary": str(SUMMARY_PATH),
        "public_signal_artifact_cleaner_removed_rows": str(REMOVED_PATH),
        "public_signal_artifact_cleaner_quality_flags": str(QUALITY_FLAGS_PATH),
        "public_signal_artifact_cleaner_proof": str(PROOF_PATH),
    }
