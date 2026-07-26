"""Targeted signal retune generator for conditional champions."""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    RETUNE_CANDIDATES_PATH,
    conditional_champion_names,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    PUBLIC_SOURCE_TYPES,
    SIGNAL_ROOT,
    active_rows_by_symbol,
    is_test_symbol,
    pct_return,
    realized_volatility,
    record_with_hash,
    rolling_mean,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
)
from dopey_strategy_cohorts.strategy_id_canonicalizer import attach_cohort_ids

from .conditional_champion_sample_expander_v1 import sample_expansion_targets


WATCHDOG_CAP = 15_000
MINIMUM_CAP = 5_000
DTE_BUCKETS = [10, 14, 21, 30, 45]
MONEYNESS_BUCKETS = ["ATM", "1pct_otm", "2pct_otm", "3pct_otm"]
EXIT_POLICIES = ["trend_follow", "theta_protective", "invalidation_strict", "volatility_expansion_hunter", "fast_scalp"]
STOP_TARGETS = ["tighter_stop", "normal_stop", "wider_stop", "partial_target", "delayed_target", "time_stop"]
FILTERS = ["high_volume", "low_volatility", "high_volatility", "trend_confirmed", "sector_confirmed", "spy_rs_confirmed", "avoid_concentration"]

EXPANSION_PATH = SIGNAL_ROOT / "conditional_champion_sample_expansion_records_v1.jsonl"
RANKINGS_PATH = SIGNAL_ROOT / "conditional_champion_retune_quality_rankings_v1.jsonl"
SUMMARY_PATH = SIGNAL_ROOT / "conditional_champion_signal_retune_v1_summary.json"
PROOF_PATH = SIGNAL_ROOT / "conditional_champion_signal_retune_v1_proof.jsonl"
PLANS_PATH = REPAIR_ROOT / "conditional_champion_repair_plans_v1.jsonl"


def run_conditional_champion_signal_retune_v1(candidate_cap: int = WATCHDOG_CAP) -> dict[str, object]:
    from dopey_autonomy.public_champion_common import read_jsonl_file

    cap = max(min(candidate_cap, WATCHDOG_CAP), MINIMUM_CAP)
    parents = conditional_champion_names()
    plans = read_jsonl_file(PLANS_PATH)
    rows_by_symbol = active_rows_by_symbol()
    symbols = [symbol for symbol, rows in rows_by_symbol.items() if len(rows) >= 200 and not is_test_symbol(symbol)]
    expansion_targets = sample_expansion_targets(parents, rows_by_symbol)

    candidates: list[dict[str, object]] = []
    expansions: list[dict[str, object]] = []
    plan_by_parent = {str(p.get("champion_name", "")): p for p in plans}

    for parent_id in parents:
        setup_family = parent_id.split("|")[0] if "|" in parent_id else "bollinger_expansion"
        preferred_symbols = expansion_targets.get(parent_id, symbols[:40])
        for symbol in preferred_symbols:
            if len(candidates) >= cap:
                break
            rows = rows_by_symbol.get(symbol, [])
            if len(rows) < 200:
                continue
            for index in range(120, len(rows) - 20, 3):
                if len(candidates) >= cap:
                    break
                row = rows[index]
                features = feature_snapshot(symbol, rows, index)
                if not passes_filters(features):
                    continue
                for dte in DTE_BUCKETS:
                    for moneyness in MONEYNESS_BUCKETS:
                        for exit_policy in EXIT_POLICIES:
                            for stop_target in STOP_TARGETS[:3]:
                                plan = plan_by_parent.get(parent_id, {})
                                candidate = build_retune_candidate(
                                    symbol, row, features, setup_family, parent_id, plan,
                                    dte, moneyness, exit_policy, stop_target, len(candidates),
                                )
                                candidates.append(candidate)
                                if len(candidates) >= cap:
                                    break
                            if len(candidates) >= cap:
                                break
                        if len(candidates) >= cap:
                            break
                    if len(candidates) >= cap:
                        break
                expansions.append(record_with_hash({
                    "artifact_type": "conditional_champion_sample_expansion_record_v1",
                    "parent_champion_id": parent_id,
                    "symbol": symbol,
                    "date": row.get("date", ""),
                    **live_safety_fields(),
                }, "record_hash"))

    ranked = rank_candidates(candidates)
    summary = {
        "artifact_type": "conditional_champion_signal_retune_v1_summary",
        "conditional_champion_signal_retune_version": "dopey-public-champion-signal-retune-v1",
        "conditional_champion_signal_retune_status": "conditional_retune_candidates_written",
        "retune_candidate_count": len(candidates),
        "parent_champion_count": len(parents),
        "repair_plan_count": len(plans),
        "sample_expansion_count": len(expansions),
        "public_data_only": all(str(c.get("market_data_source_type", "")) in PUBLIC_SOURCE_TYPES for c in candidates),
        "fixture_signal_count": 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RETUNE_CANDIDATES_PATH, candidates)
    write_jsonl_file(EXPANSION_PATH, expansions[:5000])
    write_jsonl_file(RANKINGS_PATH, ranked[:500])
    write_stage_proof(PROOF_PATH, "conditional-champion-signal-retune-v1", str(summary["conditional_champion_signal_retune_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def feature_snapshot(symbol: str, rows: list[dict[str, str]], index: int) -> dict[str, object]:
    window = rows[max(0, index - 20): index + 1]
    closes = [safe_float(row["close"]) for row in window]
    volumes = [safe_float(row.get("volume", 0)) for row in window]
    close = closes[-1]
    ma20 = rolling_mean(closes)
    vol = realized_volatility(closes)
    return {
        "symbol": symbol,
        "date": window[-1]["date"],
        "close": close,
        "ma20": ma20,
        "volume_ratio": volumes[-1] / max(rolling_mean(volumes), 1.0),
        "realized_vol_20": vol,
        "trend_regime": "uptrend" if close > ma20 else "downtrend",
        "volatility_regime": "high_volatility" if vol > 0.35 else "low_volatility",
        "sector": sector_for_symbol(symbol),
    }


def passes_filters(features: dict[str, object]) -> bool:
    return safe_float(features.get("volume_ratio")) >= 0.8


def build_retune_candidate(
    symbol: str,
    row: dict[str, str],
    features: dict[str, object],
    setup_family: str,
    parent_id: str,
    plan: dict[str, object],
    dte: int,
    moneyness: str,
    exit_policy: str,
    stop_target: str,
    seq: int,
) -> dict[str, object]:
    close = safe_float(row["close"])
    stop_distance = {"tighter_stop": 0.010, "normal_stop": 0.015, "wider_stop": 0.025}.get(stop_target, 0.015)
    target_distance = {"partial_target": 0.018, "delayed_target": 0.030, "time_stop": 0.022}.get(stop_target, 0.025)
    direction = "bullish" if features["trend_regime"] == "uptrend" else "bearish"
    trade_intent = "long_call" if direction == "bullish" else "long_put"
    strategy_id = f"{setup_family}|{exit_policy}|dte{dte}|{moneyness}"
    signal_id = hashlib.sha256(f"{parent_id}-{symbol}-{row['date']}-{seq}".encode()).hexdigest()[:16]
    candidate = {
        "artifact_type": "conditional_champion_retune_candidate_v1",
        "signal_id": f"retune-v1-{signal_id}",
        "symbol": symbol,
        "timestamp": row["date"],
        "date": row["date"],
        "direction": direction,
        "trade_intent": trade_intent,
        "setup_family": setup_family,
        "strategy_id": strategy_id,
        "entry_price": close,
        "invalidation_level": close * (1.0 - stop_distance) if direction == "bullish" else close * (1.0 + stop_distance),
        "target_price": close * (1.0 + target_distance) if direction == "bullish" else close * (1.0 - target_distance),
        "hold_window": min(max(dte // 3, 2), 15),
        "dte_bucket": dte,
        "moneyness_bucket": moneyness,
        "exit_policy": exit_policy,
        "stop_target_profile": stop_target,
        "parent_champion_id": parent_id,
        "repair_plan_id": plan.get("repair_plan_id", f"repair-{parent_id}"),
        "repair_type": plan.get("repair_type", "sample_expansion"),
        "market_data_source_type": row.get("market_data_source_type", "public_cache"),
        "data_source_label": row.get("market_data_source_type", "public_cache"),
        "regime": features["volatility_regime"],
        "trend_regime": features["trend_regime"],
        "sector": features["sector"],
        "public_data_only": True,
        "fixture_signal": False,
        "paper_only": True,
        "live_blocked": True,
        **live_safety_fields(),
    }
    return record_with_hash(attach_cohort_ids(candidate), "record_hash")


def rank_candidates(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked = []
    for candidate in candidates:
        score = safe_float(candidate.get("dte_bucket")) * 0.01 + (1.0 if candidate.get("exit_policy") == "theta_protective" else 0.5)
        ranked.append(record_with_hash({
            "artifact_type": "conditional_champion_retune_quality_ranking_v1",
            "signal_id": candidate.get("signal_id", ""),
            "parent_champion_id": candidate.get("parent_champion_id", ""),
            "quality_score": round(score, 6),
            **live_safety_fields(),
        }, "record_hash"))
    return sorted(ranked, key=lambda item: safe_float(item.get("quality_score")), reverse=True)


def artifact_paths() -> dict[str, str]:
    return {
        "conditional_champion_retune_candidates_v1": str(RETUNE_CANDIDATES_PATH),
        "conditional_champion_signal_retune_v1_summary": str(SUMMARY_PATH),
    }
