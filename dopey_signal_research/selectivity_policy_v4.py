"""V4 selectivity policy (no-trade filter rules).

Defines pre-entry rules that improve PF by removing bad trades before
simulation. Each rule operates on pre-entry features or historical prior
statistics only — no future information or realized outcome labels.
"""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash


# Rule ids and their pre-entry feature requirements.
# "feature" => rule reads pre-entry features
# "historical_prior" => rule reads sample-supported prior statistics
RULE_TYPES = ("feature", "historical_prior")


# Pre-entry feature rules.
FEATURE_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "no_trade_overextended_entry",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "feature_path": ["reversal", "overextension"],
        "operator": ">",
        "threshold": 0.06,
        "intent": "no_trade",
        "description": "Block entries where prior move is over 6% above structure",
    },
    {
        "rule_id": "no_trade_thin_volume",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "feature_path": ["risk_filter", "avoid_thin_volume"],
        "operator": ">=",
        "threshold": 1.0,
        "intent": "no_trade",
        "description": "Block entries on thin/unreliable volume regimes",
    },
    {
        "rule_id": "no_trade_poor_regime_alignment",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "feature_path": ["risk_filter", "avoid_poor_regime_alignment"],
        "operator": ">=",
        "threshold": 1.0,
        "intent": "no_trade",
        "description": "Block entries when market/sector regime conflicts with setup",
    },
    {
        "rule_id": "no_trade_volume_climax",
        "rule_type": "feature",
        "applies_to": "volume_subfamilies",
        "feature_path": ["volume", "volume_climax"],
        "operator": ">=",
        "threshold": 1.0,
        "intent": "no_trade",
        "description": "Block volume-subfamily entries on exhaustion/climax spikes",
    },
    {
        "rule_id": "no_trade_volatility_shock_regime",
        "rule_type": "feature",
        "applies_to": "all_subfamilies",
        "feature_path": ["regime", "volatility_regime"],
        "operator": ">=",
        "threshold": 1.0,
        "intent": "no_trade",
        "description": "Block entries when volatility_shock regime AND risk_on_proxy absent",
    },
    {
        "rule_id": "no_trade_weak_relative_strength",
        "rule_type": "feature",
        "applies_to": "continuation_subfamilies",
        "feature_path": ["relative_strength", "vs_spy"],
        "operator": "<",
        "threshold": -0.01,
        "intent": "no_trade",
        "description": "Block continuation entries when symbol underperforms SPY",
    },
)


# Historical prior rules — require sample-supported prior statistics.
HISTORICAL_PRIOR_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "no_trade_negative_pf_symbol",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "symbol",
        "min_trade_count": 30,
        "profit_factor_threshold": 0.90,
        "intent": "no_trade",
        "description": "Block symbols with sample-supported negative profit factor",
    },
    {
        "rule_id": "no_trade_negative_pf_sector",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "sector",
        "min_trade_count": 30,
        "profit_factor_threshold": 0.90,
        "intent": "no_trade",
        "description": "Block sectors with sample-supported negative profit factor",
    },
    {
        "rule_id": "no_trade_negative_regime",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "regime",
        "min_trade_count": 25,
        "profit_factor_threshold": 0.90,
        "intent": "no_trade",
        "description": "Block regimes with sample-supported negative profit factor",
    },
    {
        "rule_id": "no_trade_holdout_partition_failure",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "holdout_partition",
        "min_trade_count": 20,
        "holdout_pass_rate_threshold": 0.50,
        "intent": "no_trade",
        "description": "Block entries in holdout partitions that systematically fail",
    },
    {
        "rule_id": "no_trade_split_partition_failure",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "split_partition",
        "min_trade_count": 20,
        "split_pass_rate_threshold": 0.50,
        "intent": "no_trade",
        "description": "Block entries in split partitions that systematically fail",
    },
    {
        "rule_id": "no_trade_stop_target_asymmetry_weak",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "stop_target_bucket",
        "min_trade_count": 25,
        "asymmetry_threshold": 0.6,
        "intent": "no_trade",
        "description": "Block entries when stop/target asymmetry is weak (<= 0.6)",
    },
    {
        "rule_id": "no_trade_market_sector_conflict",
        "rule_type": "historical_prior",
        "applies_to": "all_subfamilies",
        "scope": "market_sector_conflict",
        "min_trade_count": 20,
        "conflict_share_threshold": 0.50,
        "intent": "no_trade",
        "description": "Block entries when market/sector conflict share is high",
    },
)


def all_rules() -> tuple[dict[str, object], ...]:
    return FEATURE_RULES + HISTORICAL_PRIOR_RULES


def rule_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for rule in all_rules():
        records.append(
            record_with_hash(
                {
                    "artifact_type": "no_trade_filter_rule_v4",
                    "rule_id": rule["rule_id"],
                    "rule_type": rule["rule_type"],
                    "applies_to": rule["applies_to"],
                    "scope": rule.get("scope", ""),
                    "intent": rule.get("intent", "no_trade"),
                    "description": rule.get("description", ""),
                    "public_data_only": True,
                    "uses_future_information": False,
                    "uses_realized_outcome_label": False,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )
    return records


def selectivity_policy() -> dict[str, object]:
    return {
        "artifact_type": "selectivity_policy_v4",
        "selectivity_policy_v4_version": "dopey-selectivity-policy-v4",
        "feature_rule_count": len(FEATURE_RULES),
        "historical_prior_rule_count": len(HISTORICAL_PRIOR_RULES),
        "total_rule_count": len(FEATURE_RULES) + len(HISTORICAL_PRIOR_RULES),
        "future_information_used": False,
        "outcome_label_used": False,
        "minimum_symbol_floor": 8,
        "minimum_sector_floor": 8,
        "experimental_label_required_for_below_floor": True,
        "applies_to_subfamilies": ("continuation", "volume"),
        "public_data_only": True,
        **live_safety_fields(),
    }
