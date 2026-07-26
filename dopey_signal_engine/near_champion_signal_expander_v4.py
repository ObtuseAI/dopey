"""Near-champion signal expander V4.

Uses the prior rejected near champions as mutation seeds and expands them across
dates, symbols, sector peers, adjacent DTE/moneyness buckets, alternate exits,
and tighter/wider invalidations while preserving parent lineage.
"""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash, safe_float, sector_for_symbol
from dopey_autonomy.signal_deepening_common import NEAR_CHAMPION_SEEDS


DTE_ADJACENCY = {"dte7": [7, 10, 14], "dte14": [10, 14, 21], "dte21": [14, 21, 30], "dte30": [21, 30, 45], "dte45": [30, 45]}
MONEYNESS_ADJACENCY = {
    "ATM": ["ATM", "1pct_otm"],
    "1pct_otm": ["ATM", "1pct_otm", "2pct_otm"],
    "2pct_otm": ["1pct_otm", "2pct_otm", "3pct_otm"],
    "3pct_otm": ["2pct_otm", "3pct_otm"],
}
EXIT_ALTERNATES = ["fast_scalp", "trend_follow", "invalidation_strict", "theta_protective", "volatility_expansion_hunter"]
INVALIDATION_FACTORS = [0.85, 1.0, 1.15, 1.3]


def parse_seed(seed: str) -> dict[str, str]:
    parts = seed.split("|")
    setup_family = parts[0] if len(parts) > 0 else ""
    exit_policy = parts[1] if len(parts) > 1 else ""
    dte_token = parts[2] if len(parts) > 2 else "dte14"
    moneyness = parts[3] if len(parts) > 3 else "ATM"
    return {"setup_family": setup_family, "exit_policy": exit_policy, "dte_token": dte_token, "moneyness": moneyness}


def near_champion_expansion_plan_v4(seeds: list[str] | None = None) -> list[dict[str, object]]:
    seeds = seeds or NEAR_CHAMPION_SEEDS
    plans: list[dict[str, object]] = []
    for seed_index, seed in enumerate(seeds):
        parsed = parse_seed(seed)
        dte_key = parsed["dte_token"].replace("dte", "dte")
        dte_adjacent = DTE_ADJACENCY.get(dte_key, [14, 21, 30])
        moneyness_adjacent = MONEYNESS_ADJACENCY.get(parsed["moneyness"], ["ATM", "1pct_otm"])
        for dte in dte_adjacent:
            for moneyness in moneyness_adjacent:
                for exit_policy in EXIT_ALTERNATES:
                    for inv_factor in INVALIDATION_FACTORS:
                        plan = {
                            "artifact_type": "near_champion_expansion_plan_v4",
                            "seed_id": seed,
                            "parent_strategy_id": seed,
                            "seed_index": seed_index,
                            "setup_family": parsed["setup_family"],
                            "exit_policy": exit_policy,
                            "dte_bucket": dte,
                            "moneyness_bucket": moneyness,
                            "invalidation_factor": round(inv_factor, 4),
                            "expansion_axes": ["dates", "symbols", "sector_peers", "dte", "moneyness", "invalidation", "exits"],
                            "preserve_parent_lineage": True,
                            "fixture_allowed": False,
                            "live_trading_enabled": False,
                        }
                        plans.append(record_with_hash(plan, "record_hash"))
    return plans


def expand_near_champion_signal(signal: dict[str, object], plan: dict[str, object], local_index: int) -> dict[str, object]:
    expanded = dict(signal)
    base_close = safe_float(signal.get("entry_price", signal.get("close", 0.0)))
    base_stop = safe_float(signal.get("stop_distance", 0.02))
    inv_factor = safe_float(plan.get("invalidation_factor", 1.0))
    expanded["stop_distance"] = round(base_stop * inv_factor, 6)
    intent = str(signal.get("trade_intent", ""))
    if intent == "long_put":
        expanded["invalidation_level"] = round(base_close * (1.0 + base_stop * inv_factor), 4)
        expanded["target_price"] = round(base_close * (1.0 - safe_float(signal.get("target_distance", 0.03))), 4)
    elif intent == "long_call":
        expanded["invalidation_level"] = round(base_close * (1.0 - base_stop * inv_factor), 4)
        expanded["target_price"] = round(base_close * (1.0 + safe_float(signal.get("target_distance", 0.03))), 4)
    expanded["exit_policy"] = str(plan.get("exit_policy", signal.get("exit_policy", "")))
    expanded["dte_bucket"] = int(plan.get("dte_bucket", signal.get("dte_bucket", 14)))
    expanded["moneyness_bucket"] = str(plan.get("moneyness_bucket", signal.get("moneyness_bucket", "ATM")))
    expanded["strategy_id"] = f"{plan.get('setup_family', signal.get('setup_family', ''))}|{expanded['exit_policy']}|dte{expanded['dte_bucket']}|{expanded['moneyness_bucket']}"
    expanded["parent_lineage"] = str(plan.get("parent_strategy_id", ""))
    expanded["near_champion_seed"] = bool(plan.get("parent_strategy_id"))
    expanded["symbol"] = str(signal.get("symbol", ""))
    expanded["sector"] = str(signal.get("sector", sector_for_symbol(str(signal.get("symbol", "")))))
    return expanded
