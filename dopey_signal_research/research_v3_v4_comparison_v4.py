"""V3 vs V4 research comparison.

Compares the top research family / subfamily metrics from V3 to the
corresponding V4 row. Returns whether V4 improved on V3 on at least one of:
profit factor, split pass rate, holdout survival, expectancy, drawdown.
"""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash, safe_float
from dopey_autonomy.signal_research_v4_common import load_v3_tournament_summary


def compare_v3_v4(v4_row: dict[str, object]) -> dict[str, object]:
    v3 = load_v3_tournament_summary()
    v3_pf = safe_float(v3.get("top_profit_factor", 0.0))
    v3_split = safe_float(v3.get("top_split_pass_rate", 0.0))
    v3_pnl = safe_float(v3.get("top_net_pnl", 0.0))
    v3_dd = safe_float(v3.get("top_max_drawdown", -999.0))
    v4_pf = safe_float(v4_row.get("profit_factor", 0.0))
    v4_split = safe_float(v4_row.get("split_pass_rate", 0.0))
    v4_pnl = safe_float(v4_row.get("net_pnl", 0.0))
    v4_dd = safe_float(v4_row.get("max_drawdown", -999.0))
    improved_axes: list[str] = []
    if v4_pf > v3_pf:
        improved_axes.append("profit_factor")
    if v4_split > v3_split:
        improved_axes.append("split_pass_rate")
    if bool(v4_row.get("holdout_survival", False)):
        improved_axes.append("holdout_survival")
    if safe_float(v4_row.get("expectancy", 0.0)) > 0.0:
        improved_axes.append("expectancy")
    if v4_dd > v3_dd:
        improved_axes.append("drawdown")
    if v4_pnl > v3_pnl:
        improved_axes.append("net_pnl")
    return record_with_hash(
        {
            "artifact_type": "research_v3_v4_comparison_v4",
            "stable_subfamily_id": v4_row.get("stable_subfamily_id", ""),
            "family_id": v4_row.get("family_id", ""),
            "v3_top_profit_factor": v3_pf,
            "v4_profit_factor": v4_pf,
            "v3_top_split_pass_rate": v3_split,
            "v4_split_pass_rate": v4_split,
            "v3_top_net_pnl": v3_pnl,
            "v4_net_pnl": v4_pnl,
            "improved_vs_v3": bool(improved_axes),
            "improved_axes": improved_axes,
            **live_safety_fields(),
        },
        "record_hash",
    )
