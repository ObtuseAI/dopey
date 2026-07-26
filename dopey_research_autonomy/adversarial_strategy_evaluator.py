"""Adversarial evaluation records for autonomous long-premium research."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import stable_hash


ADVERSARIAL_SCENARIOS = ["adverse_regime_split", "volatility_spike_split", "earnings_exclusion_split", "zero_dte_stress_lane", "walk_forward_split", "symbol_holdout", "date_holdout", "sector_holdout", "multiple_testing_penalty", "capacity_liquidity_proxy"]


def build_adversarial_evaluations(has_data: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, scenario in enumerate(ADVERSARIAL_SCENARIOS):
        record = {
            "artifact_type": "adversarial_strategy_evaluations",
            "evaluation_id": f"adversarial-{index + 1:03d}",
            "scenario": scenario,
            "status": "blocked_no_accepted_real_data" if not has_data else "evaluated",
            "passed": False,
            "paper_only": True,
            "live_blocked": True,
            "better_than_frontier_claim": False,
        }
        record["evaluation_hash"] = stable_hash(record)
        records.append(record)
    return records

