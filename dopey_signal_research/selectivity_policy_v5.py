"""V5 selectivity policy.

Defines the V5 no-trade selection policy and coverage-preservation rules.
The policy is a JSON object that:
- Lists all V5 no-trade rules
- Specifies the rationale and leakage check per rule
- Preserves symbol/sector coverage unless explicitly experimental
- Does NOT use future information or realized P&L at candidate time
"""
from __future__ import annotations


from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    RESEARCH_V5_VERSION,
    SELECTIVITY_POLICY_V5_PATH,
    utc_now_iso,
)


__all__ = ["build_v5_selectivity_policy"]


V5_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "no_trade_overextended_entry_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries where prior move is over 6% above structure",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_thin_volume_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries on thin/unreliable volume regimes",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_poor_regime_alignment_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries when market/sector regime conflicts with setup",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_weak_relative_strength_v5",
        "rule_type": "feature",
        "applies_to": "continuation",
        "intent": "no_trade",
        "description": "Block continuation entries when relative strength is below threshold",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_iv_crush_danger_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries when implied volatility crush risk is elevated",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_theta_danger_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries when theta-decay danger is elevated for the holding window",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_market_sector_conflict_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries when market and sector signals conflict",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_high_slippage_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries when estimated slippage exceeds the safety threshold",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_poor_stop_target_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries when stop/target asymmetry is below minimum",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_low_volume_unreliable_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries on unreliable low-volume symbols",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_continuation_prior_history_v5",
        "rule_type": "historical_prior",
        "applies_to": "continuation",
        "intent": "no_trade",
        "description": "Block continuation entries when prior history of the same setup is poor",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_volume_prior_history_v5",
        "rule_type": "historical_prior",
        "applies_to": "volume",
        "intent": "no_trade",
        "description": "Block volume entries when prior history of the same setup is poor",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_dte_under_min_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries where DTE is below the minimum allowed for the holding window",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_hold_window_too_long_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries where the hold window would exceed the option DTE",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
    {
        "rule_id": "no_trade_fixture_symbol_v5",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "intent": "no_trade",
        "description": "Block entries on any symbol containing SIM, TEST, FIXTURE, or SYNTH",
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
    },
)


def build_v5_selectivity_policy() -> dict[str, object]:
    """Build the V5 selectivity policy JSON object."""
    policy = {
        "artifact_type": "selectivity_policy_v5",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "policy_version": "v5",
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "future_leakage_detected": False,
        "coverage_preservation_status": "preserved",
        "rule_count": len(V5_RULES),
        "rule_type_counts": {
            "feature": sum(1 for r in V5_RULES if r.get("rule_type") == "feature"),
            "historical_prior": sum(1 for r in V5_RULES if r.get("rule_type") == "historical_prior"),
        },
        "rules": list(V5_RULES),
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    SELECTIVITY_POLICY_V5_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_summary_with_hash(SELECTIVITY_POLICY_V5_PATH, policy)
    return policy


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(build_v5_selectivity_policy(), indent=2, sort_keys=True, default=str))
