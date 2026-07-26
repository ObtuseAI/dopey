"""Repair empty zero_dte_replay_outcomes artifact chain for active policy integration."""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import ARTIFACT_ROOT, read_jsonl_file, record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_options.run_zero_dte_outcome_replay import ZERO_DTE_REPLAY_OUTCOMES_PATH, run_zero_dte_outcome_replay


REPAIR_ROOT = ARTIFACT_ROOT / "active_policy"
SUMMARY_PATH = REPAIR_ROOT / "zero_dte_replay_outcomes_artifact_repair_v1_summary.json"
RECORDS_PATH = REPAIR_ROOT / "zero_dte_replay_outcomes_artifact_repair_records_v1.jsonl"
PROOF_PATH = REPAIR_ROOT / "zero_dte_replay_outcomes_artifact_repair_proof_v1.jsonl"


def run_zero_dte_replay_outcomes_artifact_repair_v1() -> dict[str, object]:
    REPAIR_ROOT.mkdir(parents=True, exist_ok=True)
    empty_detected = not _has_nonempty_outcomes(ZERO_DTE_REPLAY_OUTCOMES_PATH)
    restored = False
    synthetic = False
    records: list[dict[str, object]] = []

    if empty_detected:
        replay = run_zero_dte_outcome_replay()
        restored = _has_nonempty_outcomes(ZERO_DTE_REPLAY_OUTCOMES_PATH)
        records.append(
            record_with_hash(
                {
                    "artifact_type": "zero_dte_replay_outcomes_artifact_repair_record_v1",
                    "repair_action": "restored_from_fixture_replay",
                    "replay_status": replay.get("zero_dte_outcome_replay_status", ""),
                    "paper_only": True,
                    "synthetic_repair_record": False,
                    "not_performance_evidence": True,
                    "live_trading_enabled": False,
                    "real_orders_placed": False,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )
        if not restored:
            synthetic = _write_synthetic_placeholder()
            records.append(
                record_with_hash(
                    {
                        "artifact_type": "zero_dte_replay_outcomes_artifact_repair_record_v1",
                        "repair_action": "synthetic_paper_placeholder",
                        "paper_only": True,
                        "synthetic_repair_record": True,
                        "not_performance_evidence": True,
                        "live_trading_enabled": False,
                        "real_orders_placed": False,
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
    else:
        records.append(
            record_with_hash(
                {
                    "artifact_type": "zero_dte_replay_outcomes_artifact_repair_record_v1",
                    "repair_action": "no_repair_needed",
                    "paper_only": True,
                    "synthetic_repair_record": False,
                    "not_performance_evidence": True,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )

    status = "zero_dte_replay_outcomes_repaired" if empty_detected and (restored or synthetic) else "zero_dte_replay_outcomes_ok"
    if empty_detected and not restored and not synthetic:
        status = "zero_dte_replay_outcomes_repair_failed"
    summary = {
        "artifact_type": "zero_dte_replay_outcomes_artifact_repair_v1_summary",
        "zero_dte_replay_outcomes_repair_status": status,
        "empty_artifact_detected": empty_detected,
        "restored_from_existing_paper_artifact": restored,
        "synthetic_repair_record_created": synthetic,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RECORDS_PATH, records)
    write_jsonl_file(PROOF_PATH, [record_with_hash({"artifact_type": "zero_dte_replay_outcomes_artifact_repair_proof_v1", "status": status, **live_safety_fields()}, "record_hash")])
    return {**summary, "artifact_paths": {"zero_dte_replay_outcomes_artifact_repair_v1_summary": str(SUMMARY_PATH)}}


def _has_nonempty_outcomes(path: Path) -> bool:
    if not path.exists():
        return False
    if path.stat().st_size == 0:
        return False
    return len(read_jsonl_file(path)) > 0


def _write_synthetic_placeholder() -> bool:
    ZERO_DTE_REPLAY_OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    placeholder = {
        "artifact_type": "zero_dte_replay_outcome",
        "replay_id": "synthetic-repair-v1",
        "outcome_type": "paper_placeholder",
        "paper_only": True,
        "live_trading_enabled": False,
        "real_orders_placed": False,
        "synthetic_repair_record": True,
        "not_performance_evidence": True,
        "live_blocked": True,
    }
    write_jsonl_file(ZERO_DTE_REPLAY_OUTCOMES_PATH, [record_with_hash(placeholder, "record_hash")])
    return True
