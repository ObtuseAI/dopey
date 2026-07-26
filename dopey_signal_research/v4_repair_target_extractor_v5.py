"""V4 repair target extractor for V5.

Reads the V4 result analysis JSON (produced by `v4_result_analyzer_v5.py`)
and emits dedicated repair target records grouped by category.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    RESEARCH_V5_VERSION,
    V4_ANALYSIS_V5_PATH,
    V4_REPAIR_TARGETS_V5_PATH,
    utc_now_iso,
)


__all__ = ["extract_v4_repair_targets_v5"]


REPAIR_CATEGORY_AXIS = {
    "pf_repair_above_110": "profit_factor",
    "holdout_repair": "holdout_survival",
    "split_repair": "split_pass_rate",
    "expectancy_repair": "expectancy",
    "drawdown_repair": "max_drawdown",
    "no_trade_filter_injection": "no_trade_filter_quality",
    "sector_pruning": "sector_concentration",
    "symbol_pruning": "symbol_concentration",
    "subfamily_split": "family_separation",
    "dte_retune": "dte_holding_window",
    "moneyness_retune": "moneyness",
    "exit_policy_retune": "stop_target_asymmetry",
    "risk_filter_retune": "risk_filter_quality",
    "relative_strength_retune": "relative_strength",
    "volatility_retune": "volatility",
    "volume_retune": "volume",
    "stop_target_retune": "stop_target_combination",
    "profitable_slice_reinforcement": "net_pnl",
    "loss_driver_suppression": "net_pnl",
    "hold_window_retune": "hold_window",
    "stress_specific_repair": "stress_survival",
    "recent_market_reinforcement": "recent_window_performance",
}


def extract_v4_repair_targets_v5(analysis_path: Path = V4_ANALYSIS_V5_PATH) -> list[dict[str, object]]:
    """Extract grouped V4 repair target records from the V4 result analysis JSON."""
    if not analysis_path.exists():
        return []
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    raw_targets = analysis.get("v4_repair_targets", []) or []
    out: list[dict[str, object]] = []
    for idx, t in enumerate(raw_targets):
        repair_type = str(t.get("repair_type", "unknown"))
        rec = {
            "artifact_type": "v4_repair_target_extracted_v5",
            "repair_target_id": f"repair-ext-v5-{idx:04d}",
            "repair_type": repair_type,
            "repair_category": REPAIR_CATEGORY_AXIS.get(repair_type, "unknown"),
            "source_type": t.get("source_type", ""),
            "stable_family_id": t.get("stable_family_id", ""),
            "stable_subfamily_id": t.get("stable_subfamily_id", ""),
            "intended_fix": t.get("intended_fix", ""),
            "expected_evaluation_axis": t.get("expected_evaluation_axis", ""),
            "v5_min_breakthrough_pf": 1.10,
            "thresholds_lowered": False,
            "live_trading_enabled": False,
            "bundle_version": RESEARCH_V5_VERSION,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        out.append(record_with_hash(rec, "record_hash"))
    return out


def run_v4_repair_target_extractor_v5() -> dict[str, object]:
    records = extract_v4_repair_targets_v5()
    write_jsonl_file(V4_REPAIR_TARGETS_V5_PATH, records)
    return {
        "v4_repair_target_count": len(records),
        "path": str(V4_REPAIR_TARGETS_V5_PATH),
    }


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run_v4_repair_target_extractor_v5(), indent=2, sort_keys=True, default=str))
