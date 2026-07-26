"""Before/after comparison for conditional champion retune."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import load_public_trades, trades_for_champion
from dopey_autonomy.public_champion_common import pnl_metrics
from dopey_autonomy.champion_repair_common import conditional_champion_names
from dopey_autonomy.public_champion_common import group_records, safe_float


def build_before_after_rows(
    retune_trades: list[dict[str, object]],
    original_trades: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for parent in conditional_champion_names():
        before = trades_for_champion({"cohort_level": "variant_id", "cohort_id": parent}, original_trades)
        after = [t for t in retune_trades if str(t.get("parent_champion_id", "")) == parent]
        before_metrics = pnl_metrics(before)
        after_metrics = pnl_metrics(after)
        rows.append({
            "parent_champion_id": parent,
            "before_net_pnl": before_metrics.get("net_pnl", 0.0),
            "after_net_pnl": after_metrics.get("net_pnl", 0.0),
            "before_profit_factor": before_metrics.get("profit_factor", 0.0),
            "after_profit_factor": after_metrics.get("profit_factor", 0.0),
            "before_sample_count": before_metrics.get("sample_count", 0),
            "after_sample_count": after_metrics.get("sample_count", 0),
            "improvement_score": round(safe_float(after_metrics.get("expectancy")) - safe_float(before_metrics.get("expectancy")), 6),
        })
    return rows
