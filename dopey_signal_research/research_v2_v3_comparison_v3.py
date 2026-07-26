"""V2 vs V3 research comparison."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import load_v2_tournament_summary
from dopey_autonomy.public_champion_common import record_with_hash, safe_float


def compare_v2_v3(v3_row: dict[str, object]) -> dict[str, object]:
    v2 = load_v2_tournament_summary()
    v2_pf = safe_float(v2.get("top_profit_factor", 0.0))
    v2_holdout = safe_float(v2.get("top_split_pass_rate", 0.0))
    v3_pf = safe_float(v3_row.get("profit_factor", 0.0))
    v3_split = safe_float(v3_row.get("split_pass_rate", 0.0))
    v3_holdout = bool(v3_row.get("holdout_survival", False))
    improved_axes: list[str] = []
    if v3_pf > v2_pf:
        improved_axes.append("profit_factor")
    if v3_split > v2_holdout:
        improved_axes.append("split_pass_rate")
    if v3_holdout and v2_holdout == 0.0:
        improved_axes.append("holdout_survival")
    if safe_float(v3_row.get("expectancy", 0.0)) > 0.0:
        improved_axes.append("expectancy")
    if safe_float(v3_row.get("max_drawdown", 0.0)) > safe_float(v2.get("top_max_drawdown", -999.0)):
        improved_axes.append("drawdown")
    return record_with_hash(
        {
            "artifact_type": "research_v2_v3_comparison_v3",
            "family_id": v3_row.get("family_id", ""),
            "v2_top_profit_factor": v2_pf,
            "v3_profit_factor": v3_pf,
            "v2_top_split_pass_rate": v2_holdout,
            "v3_split_pass_rate": v3_split,
            "improved_vs_v2": bool(improved_axes),
            "improved_axes": improved_axes,
            **live_safety_fields(),
        },
        "record_hash",
    )
