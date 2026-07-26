"""Trade-active repair policy for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7.

Converts no-trade-dominant V6 watchlist candidates into executable long-call /
long-put candidate rules without future leakage.  Every rule is required to:
- use only pre-entry features or prior historical statistics
- avoid future path leakage
- avoid realized future P&L labels at candidate time
- avoid holdout-outcome leakage
- never lower MIN_BREAKTHROUGH_PF
- never enable live trading
- block no-trade-only breakthroughs
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    record_with_hash,
    safe_float,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v7_common import (
    FUTURE_LEAKAGE_GUARD_V7_PATH,
    MIN_BREAKTHROUGH_PF,
    MIN_BREAKTHROUGH_SAMPLE,
    MIN_BREAKTHROUGH_SECTORS,
    MIN_BREAKTHROUGH_SPLIT_PASS,
    MIN_BREAKTHROUGH_SYMBOLS,
    RESEARCH_V7_VERSION,
    TRADE_ACTIVE_REPAIR_POLICY_V7_PATH,
    TRADE_ACTIVE_REPAIR_POLICY_V7_PROOF_PATH,
    TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH,
    TRADE_ACTIVE_REPAIR_RULES_V7_PATH,
    V7_HOLD_WINDOWS,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    load_v6_gate_summary,
    load_v6_rejection_records,
    load_v6_tournament_leaderboard,
    load_v6_trade_active_blocker_matrix,
    load_v6_watchlist_records,
    utc_now_iso,
    write_stage_proof,
)
from dopey_signal_research.future_leakage_guard_v7 import run_v7_leakage_guard_audit


__all__ = ["run_trade_active_repair_policy_v7"]


_REPAIR_RULES: list[dict[str, object]] = [
    {
        "rule_id": "v7-trade-active-direction-001",
        "rule_type": "no_trade_to_trade_active_conversion",
        "blocker_axis": "no_trade_dominant_watchlist",
        "description": (
            "Convert a no-trade-dominant watchlist candidate into an executable long-call or long-put "
            "candidate using only pre-entry directional bias: prior close-to-open momentum, pre-entry "
            "volume regime, and implied-volatility skew observed before the candidate bar. "
            "No future path data, no realized P&L labels, no holdout outcomes."
        ),
        "allowed_features": [
            "prior_close_to_open_return",
            "pre_entry_volume_regime",
            "pre_entry_iv_skew",
            "historical_directional_bias",
            "atr_prior",
            "rsi_prior",
        ],
        "forbidden_features": [
            "future_ohlcv",
            "future_path",
            "realized_pnl",
            "actual_outcome",
            "holdout_outcome",
            "post_exit_pnl",
            "tomorrow_close",
        ],
        "conversion_logic": "no_trade -> long_call if bullish_bias else long_put if bearish_bias else no_trade",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-block-no-trade-only-002",
        "rule_type": "no_trade_only_blocker",
        "blocker_axis": "no_trade_only_breakthrough",
        "description": (
            "Block any candidate whose only supporting evidence is no-trade simulation. "
            "A V7 breakthrough must include at least one trade-active leg (long_call or long_put) "
            "with a trade-active profit factor above the hard floor. No-trade-only records are "
            "explicitly excluded from breakthrough promotion."
        ),
        "allowed_features": [
            "trade_active_direction_flag",
            "trade_active_sample_count",
            "trade_active_profit_factor",
        ],
        "forbidden_features": [
            "no_trade_only_pnl",
            "future_path",
            "realized_pnl",
            "holdout_outcome",
        ],
        "conversion_logic": "block_breakthrough if trade_active_sample == 0 or trade_active_pf <= min_breakthrough_pf",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-pf-floor-003",
        "rule_type": "profit_factor_floor",
        "blocker_axis": "profit_factor_below_threshold",
        "description": (
            "Require trade-active profit factor to exceed the hard V7 floor of 1.10. "
            "Compute trade-active PF only from long-call and long-put simulated trades; exclude no-trade "
            "records from the numerator and denominator. Never lower MIN_BREAKTHROUGH_PF."
        ),
        "allowed_features": [
            "trade_active_gross_profit",
            "trade_active_gross_loss",
            "trade_active_win_count",
            "trade_active_loss_count",
        ],
        "forbidden_features": [
            "no_trade_pnl",
            "future_path",
            "realized_pnl",
            "holdout_outcome",
        ],
        "conversion_logic": "pass if trade_active_pf > min_breakthrough_pf else repair_or_reject",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-hold-window-004",
        "rule_type": "hold_window_selection",
        "blocker_axis": "hold_window_mismatch",
        "description": (
            "Select hold_window from (1, 2, 3, 5, 7) bars using pre-entry DTE, liquidity, and "
            "historical volatility term structure observed before entry. Shorter windows for high-volatility "
            "regimes; longer windows for trending low-volatility regimes. No future path data."
        ),
        "allowed_features": [
            "entry_dte",
            "historical_liquidity_prior",
            "historical_volatility_term_structure",
            "pre_entry_regime_label",
        ],
        "forbidden_features": [
            "future_ohlcv",
            "future_path",
            "realized_pnl",
            "holdout_outcome",
        ],
        "conversion_logic": "map(pre_entry_dte, liquidity, vol_term) -> hold_window in {1,2,3,5,7}",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-coverage-005",
        "rule_type": "coverage_preservation",
        "blocker_axis": "symbol_or_sector_coverage_below_min",
        "description": (
            "Preserve V7 gate coverage minima when converting no-trade candidates to trade-active ones. "
            "Any pruning that would reduce symbol or sector count below gate minima is labeled experimental "
            "and must be accompanied by a coverage audit using only historically available universe data."
        ),
        "allowed_features": [
            "historical_liquid_universe",
            "sector_map",
            "coverage_audit_prior",
        ],
        "forbidden_features": [
            "future_return_rank",
            "future_sector_performance",
            "realized_pnl",
        ],
        "conversion_logic": "require symbol_count >= min_symbols and sector_count >= min_sectors",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-sample-006",
        "rule_type": "trade_active_sample_floor",
        "blocker_axis": "trade_active_sample_inadequate",
        "description": (
            "Require the trade-active subset to contain at least the V7 trade-active sample minimum. "
            "If the converted long-call / long-put sample is below the floor, reject or queue another mutation. "
            "Use only counts from simulated trade-active legs; no future data."
        ),
        "allowed_features": [
            "trade_active_long_call_count",
            "trade_active_long_put_count",
            "trade_active_total_count",
        ],
        "forbidden_features": [
            "future_path",
            "realized_pnl",
            "holdout_outcome",
        ],
        "conversion_logic": "pass if trade_active_total_count >= min_trade_active_sample else reject",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-drawdown-007",
        "rule_type": "drawdown_control",
        "blocker_axis": "drawdown_exceeds_max",
        "description": (
            "Tighten pre-entry stop levels for trade-active legs using historical ATR and prior swing "
            "statistics computed before entry. Cap per-trade risk so that the cohort max drawdown stays "
            "within the absolute limit. No future path data."
        ),
        "allowed_features": [
            "historical_volatility",
            "atr_prior",
            "prior_swing_low",
            "prior_swing_high",
            "position_size",
        ],
        "forbidden_features": [
            "future_ohlcv",
            "future_path",
            "realized_pnl",
            "holdout_outcome",
            "post_exit_pnl",
        ],
        "conversion_logic": "set stop_at entry_spot +/- k * atr_prior; cap position_size",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-expectancy-008",
        "rule_type": "expectancy_filter",
        "blocker_axis": "expectancy_below_threshold",
        "description": (
            "Filter low-expectancy trade-active contexts using pre-entry edge estimates from prior "
            "historical bins. Compute expectancy only over long-call and long-put trades; no-trade records "
            "are excluded. No use of realized trade outcomes at candidate time."
        ),
        "allowed_features": [
            "historical_expectancy_by_context",
            "pre_entry_edge",
            "risk_reward_prior",
        ],
        "forbidden_features": [
            "realized_pnl",
            "actual_outcome",
            "future_path",
            "holdout_outcome",
        ],
        "conversion_logic": "pass if trade_active_expectancy > min_expectancy else reject",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-split-009",
        "rule_type": "split_pass_repair",
        "blocker_axis": "split_pass_rate_below_threshold",
        "description": (
            "Require trade-active split-pass rate to exceed the hard floor. Evaluate each time-based split "
            "using only trade-active trades; no-trade records do not count toward split pass. No split-outcome "
            "leakage into candidate generation."
        ),
        "allowed_features": [
            "calendar_features",
            "prior_split_sample_count",
            "regime_label_prior_to_split",
            "trade_active_split_pass_rate",
        ],
        "forbidden_features": [
            "split_outcome_label",
            "future_ohlcv",
            "realized_pnl",
            "holdout_outcome",
        ],
        "conversion_logic": "pass if trade_active_split_pass_rate >= min_breakthrough_split_pass else repair",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-model-pricing-010",
        "rule_type": "model_pricing_mandate",
        "blocker_axis": "quote_pricing_or_non_model_priced",
        "description": (
            "Mandate model-priced option entries and exits for all V7 trade-active simulations. "
            "Prohibit quote-priced or mark-to-market fills that could introduce look-ahead bias. "
            "Pricing inputs are restricted to pre-entry observable spot, strike, DTE, and implied vol proxies."
        ),
        "allowed_features": [
            "model_price",
            "entry_spot",
            "strike",
            "entry_dte",
            "iv_annual_prior",
        ],
        "forbidden_features": [
            "quote_price",
            "future_ask",
            "future_bid",
            "future_settlement",
            "realized_pnl",
        ],
        "conversion_logic": "require model_priced == True and quote_priced == False",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "v7-trade-active-experimental-prune-011",
        "rule_type": "coverage_pruning_experimental",
        "blocker_axis": "coverage_pruning_experimental",
        "description": (
            "Experimental: prune symbols or sectors from the trade-active conversion only when accompanied "
            "by a coverage audit that proves gate minima remain satisfied and the trade-active PF floor is "
            "still met. Allowed only under the experimental label."
        ),
        "allowed_features": [
            "coverage_audit_prior",
            "trade_active_pf_after_prune",
        ],
        "forbidden_features": [
            "future_path",
            "realized_pnl",
            "holdout_outcome",
        ],
        "conversion_logic": "experimental_prune if coverage_audit_pass and trade_active_pf > min_breakthrough_pf",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": True,
        "no_threshold_lowering": True,
        "experimental": True,
    },
]


def _rule_record(rule: dict[str, object]) -> dict[str, object]:
    rec = {
        "artifact_type": "trade_active_repair_rule_v7",
        **dict(rule),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_min_breakthrough_sample": MIN_BREAKTHROUGH_SAMPLE,
        "v7_min_breakthrough_symbols": MIN_BREAKTHROUGH_SYMBOLS,
        "v7_min_breakthrough_sectors": MIN_BREAKTHROUGH_SECTORS,
        "v7_min_breakthrough_split_pass": MIN_BREAKTHROUGH_SPLIT_PASS,
        "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "v7_hold_windows": list(V7_HOLD_WINDOWS),
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "rule_hash")


def _extract_watchlist_context(watchlist: list[dict[str, object]]) -> dict[str, object]:
    """Summarize the V6 watchlist records for policy context."""
    if not watchlist:
        return {"watchlist_count": 0, "top_watchlist_cohort": "", "top_watchlist_pf": 0.0}
    top = max(watchlist, key=lambda r: safe_float(r.get("profit_factor", 0.0)))
    families = Counter(str(r.get("stable_family_id", "")) for r in watchlist if str(r.get("stable_family_id", "")))
    return {
        "watchlist_count": len(watchlist),
        "top_watchlist_cohort": str(top.get("cohort_id", "")),
        "top_watchlist_subfamily": str(top.get("stable_subfamily_id", "")),
        "top_watchlist_pf": safe_float(top.get("profit_factor", 0.0)),
        "top_watchlist_sample": int(top.get("sample_count", 0) or 0),
        "watchlist_family_distribution": dict(families),
    }


def _extract_rejection_context(rejections: list[dict[str, object]]) -> dict[str, object]:
    """Summarize the V6 gate rejection records for policy context."""
    if not rejections:
        return {"rejection_count": 0, "top_rejection_reasons": {}}
    reasons: Counter = Counter()
    for r in rejections:
        for reason in r.get("reasons", []) or []:
            reasons[str(reason)] += 1
    return {
        "rejection_count": len(rejections),
        "top_rejection_reasons": dict(reasons.most_common(10)),
    }


def _extract_blocker_context(matrix: list[dict[str, object]]) -> dict[str, object]:
    """Summarize the V6 trade-active blocker matrix for policy context."""
    if not matrix:
        return {"blocker_count": 0, "top_blocker_types": {}}
    types = Counter(str(r.get("blocker_type", "")) for r in matrix if str(r.get("blocker_type", "")))
    return {
        "blocker_count": len(matrix),
        "top_blocker_types": dict(types.most_common(10)),
    }


def _extract_leaderboard_context(leaderboard: list[dict[str, object]]) -> dict[str, object]:
    """Summarize V6 tournament leaderboard trade-active / no-trade exposure."""
    if not leaderboard:
        return {"leaderboard_count": 0, "no_trade_dominant_count": 0}
    no_trade_dominant = 0
    for r in leaderboard:
        cohort_id = str(r.get("cohort_id", ""))
        if "no_trade" in cohort_id.lower():
            no_trade_dominant += 1
    return {
        "leaderboard_count": len(leaderboard),
        "no_trade_dominant_count": no_trade_dominant,
        "trade_active_dominant_count": len(leaderboard) - no_trade_dominant,
    }


def run_trade_active_repair_policy_v7() -> dict[str, object]:
    """Generate the V7 trade-active repair policy and write all artifacts."""
    rules = [dict(rule) for rule in _REPAIR_RULES]
    rule_records = [_rule_record(rule) for rule in rules]

    watchlist = load_v6_watchlist_records()
    rejections = load_v6_rejection_records()
    blocker_matrix = load_v6_trade_active_blocker_matrix()
    leaderboard = load_v6_tournament_leaderboard()
    gate_summary = load_v6_gate_summary()

    guard_summary = run_v7_leakage_guard_audit(rules)
    from dopey_signal_research.future_leakage_guard_v7 import audit_v7_no_leakage

    guard_records = audit_v7_no_leakage(rules)
    write_jsonl_file(FUTURE_LEAKAGE_GUARD_V7_PATH, guard_records)

    watchlist_context = _extract_watchlist_context(watchlist)
    rejection_context = _extract_rejection_context(rejections)
    blocker_context = _extract_blocker_context(blocker_matrix)
    leaderboard_context = _extract_leaderboard_context(leaderboard)

    policy = {
        "artifact_type": "trade_active_repair_policy_v7",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "trade_active_repair_policy_status": "trade_active_repair_policy_defined_v7",
        "repair_rule_count": len(rules),
        "repair_rules": rules,
        "future_leakage_detected": guard_summary["future_leakage_detected"],
        "thresholds_lowered": False,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "min_breakthrough_sample": MIN_BREAKTHROUGH_SAMPLE,
        "min_breakthrough_symbols": MIN_BREAKTHROUGH_SYMBOLS,
        "min_breakthrough_sectors": MIN_BREAKTHROUGH_SECTORS,
        "min_breakthrough_split_pass": MIN_BREAKTHROUGH_SPLIT_PASS,
        "min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "hold_windows": list(V7_HOLD_WINDOWS),
        "no_trade_only_blocked": True,
        "live_trading_enabled": False,
        "v6_watchlist_context": watchlist_context,
        "v6_rejection_context": rejection_context,
        "v6_blocker_context": blocker_context,
        "v6_leaderboard_context": leaderboard_context,
        "v6_gate_summary": {
            "watchlist_count": int(gate_summary.get("watchlist_count", 0) or 0),
            "pf_above_threshold_count": int(gate_summary.get("pf_above_threshold_count", 0) or 0),
            "breakthrough_candidate_count": int(gate_summary.get("breakthrough_candidate_count", 0) or 0),
            "rejection_count": int(gate_summary.get("rejection_count", 0) or 0),
        },
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_json_file(TRADE_ACTIVE_REPAIR_POLICY_V7_PATH, policy)
    write_jsonl_file(TRADE_ACTIVE_REPAIR_RULES_V7_PATH, rule_records)

    summary = {
        "artifact_type": "trade_active_repair_policy_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "trade_active_repair_policy_status": "trade_active_repair_policy_defined_v7",
        "repair_rule_count": len(rules),
        "future_leakage_detected": guard_summary["future_leakage_detected"],
        "thresholds_lowered": False,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "no_trade_only_blocked": True,
        "live_trading_enabled": False,
        "watchlist_count": watchlist_context["watchlist_count"],
        "rejection_count": rejection_context["rejection_count"],
        "blocker_count": blocker_context["blocker_count"],
        "leaderboard_count": leaderboard_context["leaderboard_count"],
        "no_trade_dominant_count": leaderboard_context["no_trade_dominant_count"],
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(TRADE_ACTIVE_REPAIR_POLICY_V7_SUMMARY_PATH, summary)
    write_stage_proof(
        TRADE_ACTIVE_REPAIR_POLICY_V7_PROOF_PATH,
        "trade-active-repair-policy-v7",
        "trade_active_repair_policy_defined_v7",
        summary,
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_trade_active_repair_policy_v7(), indent=2, sort_keys=True, default=str))
