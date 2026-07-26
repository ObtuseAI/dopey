"""Dedicated paper-only vNext settlement operation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dopey.constitution.execution_seal import assert_output_research_only
from dopey.protocols.identity import canonical_hash
from dopey.truth.agent_ablation import evaluate_agent_ablation_ledgers

from .accrual import run_forward_accrual_monitor
from .grading import SettlementPolicy
from .runtime import SettlementRunPaths, run_settlement_cycle


def _write_object_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(value), sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _settlement_policy() -> SettlementPolicy:
    return SettlementPolicy(
        neutral_return_band=0.01,
        contested_margin=0.0025,
        maximum_price_gap_days=5,
        probability_floor=1e-12,
    )


def _operation_status(accrual_monitor: Mapping[str, Any]) -> str:
    unresolved_count = sum(
        int(accrual_monitor.get(field, 0) or 0)
        for field in (
            "gradeable_unrecorded_count",
            "due_missing_verified_price_count",
            "quarantined_missing_point_in_time_proof_count",
        )
    )
    return "complete" if unresolved_count == 0 else "complete_with_operator_attention"


def run_operational_settlement(
    output_root: Path,
    as_of_date: str,
    observed_at: str,
) -> dict[str, Any]:
    prediction_ledger = output_root / "forward_predictions.jsonl"
    if not prediction_ledger.is_file():
        raise FileNotFoundError(
            "vNext settlement operation requires an existing prediction ledger: "
            f"path={prediction_ledger}"
        )
    paths = SettlementRunPaths(
        prediction_ledger=prediction_ledger,
        settlement_memory=output_root / "memory" / "settlements.jsonl",
        calibration_memory=output_root / "memory" / "calibration.jsonl",
        calibration_summary=output_root / "calibration_summary.json",
    )
    settlement = run_settlement_cycle(
        as_of_date,
        observed_at,
        paths,
        _settlement_policy(),
        10,
        30,
    )
    accrual_monitor = run_forward_accrual_monitor(
        prediction_ledger,
        paths.settlement_memory,
        as_of_date,
        output_root / "forward_accrual_monitor.json",
        _settlement_policy(),
    )
    ablation = evaluate_agent_ablation_ledgers(
        prediction_ledger,
        paths.settlement_memory,
        1000,
        20260714,
        0.05,
        30,
        3,
    )
    _write_object_atomic(output_root / "latest_agent_ablation.json", ablation)
    body: dict[str, Any] = {
        "artifact_type": "vnext_operational_settlement_result",
        "operation_version": "dopey-vnext-operational-settlement-v1",
        "operation_status": _operation_status(accrual_monitor),
        "as_of_date": as_of_date,
        "observed_at": observed_at,
        "prediction_count": int(settlement["prediction_count"]),
        "settled_count": int(settlement["settled_count"]),
        "newly_recorded_count": int(settlement["newly_recorded_count"]),
        "recorded_settlement_count": int(settlement["recorded_settlement_count"]),
        "pending_count": int(settlement["pending_count"]),
        "missing_price_count": int(settlement["missing_price_count"]),
        "quarantined_count": int(settlement["quarantined_count"]),
        "forward_evidence_status": str(accrual_monitor["monitor_status"]),
        "next_minimum_settlement_date": accrual_monitor["next_minimum_settlement_date"],
        "gradeable_unrecorded_count": int(accrual_monitor["gradeable_unrecorded_count"]),
        "agent_ablation_status": str(ablation["evaluation_status"]),
        "agent_ablation_eligible_settlement_count": int(ablation["eligible_settlement_count"]),
        "early_grading_performed": False,
        "synthetic_evidence_counted": False,
        "readiness_effect": "none_protected_external_gate",
        "automatic_promotion_count": 0,
        "promotion_allowed": False,
        "action_ready": False,
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order_authority": True,
    }
    result = {**body, "reproducibility_hash": canonical_hash(body)}
    assert_output_research_only(result)
    _write_object_atomic(output_root / "latest_settlement_operation.json", result)
    _write_object_atomic(output_root / "latest_settlement_summary.json", settlement)
    return result
