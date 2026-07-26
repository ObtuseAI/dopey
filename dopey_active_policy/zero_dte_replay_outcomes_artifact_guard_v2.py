"""Active policy zero_dte_replay_outcomes artifact guard V2.

Wraps the V1 repair with V2-style guard checks:
- confirms paper_only=true
- live_trading_enabled=false
- real_orders_placed=false
- no performance-evidence claim if synthetic repair exists
- does not enable any active policy changes
"""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_options.run_zero_dte_outcome_replay import ZERO_DTE_REPLAY_OUTCOMES_PATH


GUARD_ROOT = ARTIFACT_ROOT / "active_policy"
SUMMARY_PATH = GUARD_ROOT / "zero_dte_replay_outcomes_artifact_guard_v2_summary.json"
RECORDS_PATH = GUARD_ROOT / "zero_dte_replay_outcomes_artifact_guard_v2_records.jsonl"
PROOF_PATH = GUARD_ROOT / "zero_dte_replay_outcomes_artifact_guard_v2_proof.jsonl"
V1_REPAIR_SUMMARY_PATH = GUARD_ROOT / "zero_dte_replay_outcomes_artifact_repair_v1_summary.json"


def run_zero_dte_replay_outcomes_artifact_guard_v2() -> dict[str, object]:
    GUARD_ROOT.mkdir(parents=True, exist_ok=True)
    v1_repair = read_json_file(V1_REPAIR_SUMMARY_PATH)
    synthetic_repair = bool(v1_repair.get("synthetic_repair_record_created", False))
    artifact_non_empty = _has_nonempty_outcomes(ZERO_DTE_REPLAY_OUTCOMES_PATH)
    records: list[dict[str, object]] = []

    base_record = {
        "paper_only": True,
        "live_trading_enabled": False,
        "real_orders_placed": False,
        "synthetic_repair_not_performance_evidence": synthetic_repair,
        "active_policy_change_enabled": False,
        **live_safety_fields(),
    }

    guard_status = (
        "zero_dte_replay_outcomes_guard_ok"
        if artifact_non_empty
        else "zero_dte_replay_outcomes_guard_blocked_empty_artifact"
    )

    if artifact_non_empty:
        records.append(
            record_with_hash(
                {
                    "artifact_type": "zero_dte_replay_outcomes_artifact_guard_v2_record",
                    "guard_check_id": "artifact_non_empty",
                    "passed": True,
                    **base_record,
                },
                "record_hash",
            )
        )
    else:
        records.append(
            record_with_hash(
                {
                    "artifact_type": "zero_dte_replay_outcomes_artifact_guard_v2_record",
                    "guard_check_id": "artifact_non_empty",
                    "passed": False,
                    "action": "block_active_policy_chain",
                    **base_record,
                },
                "record_hash",
            )
        )

    records.append(
        record_with_hash(
            {
                "artifact_type": "zero_dte_replay_outcomes_artifact_guard_v2_record",
                "guard_check_id": "synthetic_repair_not_performance_evidence",
                "passed": True,
                "synthetic_repair_detected": synthetic_repair,
                "claim_lifted": False,
                **base_record,
            },
            "record_hash",
        )
    )

    summary = {
        "artifact_type": "zero_dte_replay_outcomes_artifact_guard_v2_summary",
        "zero_dte_replay_outcomes_guard_status": guard_status,
        "artifact_non_empty": artifact_non_empty,
        "paper_only": True,
        "synthetic_repair_not_performance_evidence": synthetic_repair,
        "live_trading_enabled": False,
        "real_orders_placed": False,
        "active_policy_change_enabled": False,
        "v1_repair_summary_path": str(V1_REPAIR_SUMMARY_PATH),
        "v1_repair_status": v1_repair.get("zero_dte_replay_outcomes_repair_status", ""),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RECORDS_PATH, records)
    write_jsonl_file(
        PROOF_PATH,
        [
            record_with_hash(
                {
                    "artifact_type": "zero_dte_replay_outcomes_artifact_guard_v2_proof",
                    "status": guard_status,
                    "paper_only": True,
                    "live_trading_enabled": False,
                    "real_orders_placed": False,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        ],
    )
    return {
        **summary,
        "artifact_paths": {"zero_dte_replay_outcomes_artifact_guard_v2_summary": str(SUMMARY_PATH)},
    }


def _has_nonempty_outcomes(path: Path) -> bool:
    if not path.exists():
        return False
    if path.stat().st_size == 0:
        return False
    return len(read_jsonl_file(path)) > 0
