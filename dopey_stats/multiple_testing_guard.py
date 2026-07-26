"""Multiple-testing guard for fixture/model-only statistics."""
from __future__ import annotations

from typing import Any

from .statistical_truth_models import MultipleTestingAdjustment


def build_multiple_testing_adjustment(trade_records: list[dict[str, Any]]) -> dict[str, Any]:
    strategy_families = {str(record.get("candidate_strategy", "")) for record in trade_records if record.get("candidate_strategy")}
    signal_families = {str(record.get("signal_family", "")) for record in trade_records if record.get("signal_family")}
    adjusted = {family: None for family in sorted(signal_families)}
    adjustment = MultipleTestingAdjustment(
        artifact_type="multiple_testing_adjustment",
        statistical_truth_version="",
        strategy_family_count=len(strategy_families),
        tested_signal_family_count=len(signal_families),
        p_values_blocked=True,
        bonferroni_adjustment_applied=True,
        benjamini_hochberg_adjustment_applied=True,
        adjusted_p_values=adjusted,
        significance_claim_allowed=False,
        real_alpha_claim_allowed=False,
        promotion_allowed=False,
        diagnostic_only=True,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        adjustment_hash="",
    )
    return adjustment.to_dict()
