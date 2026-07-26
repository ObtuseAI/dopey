"""Generate public-data signal variants from the active public OHLCV lake."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    PUBLIC_SOURCE_TYPES,
    SIGNAL_ROOT,
    active_rows_by_symbol,
    pct_return,
    proof_record,
    realized_volatility,
    record_with_hash,
    rolling_mean,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
    write_summary_with_hash,
)

from .public_signal_family_registry_v3 import SIGNAL_FAMILIES_V3, public_signal_family_registry_v3


REGISTRY_PATH = SIGNAL_ROOT / "public_signal_family_registry_v3.jsonl"
CANDIDATES_PATH = SIGNAL_ROOT / "public_signal_mutation_candidates_v3.jsonl"
PARAMETER_GRID_PATH = SIGNAL_ROOT / "public_signal_parameter_grid_v3.jsonl"
RANKINGS_PATH = SIGNAL_ROOT / "public_signal_quality_rankings_v3.jsonl"
SUMMARY_PATH = SIGNAL_ROOT / "public_signal_mutation_factory_v3_summary.json"
PROOF_PATH = SIGNAL_ROOT / "public_signal_mutation_factory_v3_proof.jsonl"


DTE_BUCKETS = [7, 14, 21, 30, 45]
HOLD_WINDOWS = [1, 2, 3, 5, 10, 15, 20]
MONEYNESS_BUCKETS = ["ATM", "1pct_otm", "2pct_otm", "3pct_otm"]
EXIT_POLICIES = ["fast_scalp", "trend_follow", "invalidation_strict", "theta_protective", "volatility_expansion_hunter"]


def run_public_signal_mutation_factory_v3() -> dict[str, object]:
    return generate_public_signal_mutations_v3(5000)


def generate_public_signal_mutations_v3(candidate_cap: int) -> dict[str, object]:
    registry = public_signal_family_registry_v3()
    parameter_grid = build_parameter_grid_v3()
    rows_by_symbol = active_rows_by_symbol()
    spy_rows = rows_by_symbol.get("SPY", [])
    candidates: list[dict[str, object]] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        if len(rows) < 280:
            continue
        source_type = str(rows[-1].get("market_data_source_type", "public_live_fetch"))
        if source_type not in PUBLIC_SOURCE_TYPES and source_type != "":
            continue
        candidates.extend(symbol_signal_candidates(symbol, rows, spy_rows, parameter_grid, candidate_cap - len(candidates)))
        if len(candidates) >= candidate_cap:
            break
    ranked = rank_signal_candidates_v3(candidates)
    counts = Counter(str(candidate["trade_intent"]) for candidate in candidates)
    family_counts = Counter(str(candidate["setup_family"]) for candidate in candidates)
    summary = {
        "artifact_type": "public_signal_mutation_factory_v3_summary",
        "public_signal_mutation_factory_version": "dopey-public-signal-mutation-factory-v3",
        "public_signal_mutation_status": "public_signal_variants_generated" if candidates else "blocked_no_public_market_rows",
        "signal_variant_count": len(candidates),
        "family_count": len(registry),
        "parameter_grid_count": len(parameter_grid),
        "long_call_count": int(counts.get("long_call", 0)),
        "long_put_count": int(counts.get("long_put", 0)),
        "no_trade_count": int(counts.get("no_trade", 0)),
        "setup_family_counts": dict(sorted(family_counts.items())),
        "public_data_only": all(str(candidate.get("market_data_source_type", "")) in PUBLIC_SOURCE_TYPES for candidate in candidates),
        "fixture_signal_count": sum(1 for candidate in candidates if str(candidate.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(REGISTRY_PATH, registry)
    write_jsonl_file(PARAMETER_GRID_PATH, parameter_grid)
    write_jsonl_file(CANDIDATES_PATH, candidates)
    write_jsonl_file(RANKINGS_PATH, ranked)
    write_jsonl_file(PROOF_PATH, [proof_record("public-signal-mutation-factory-v3", str(summary["public_signal_mutation_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def build_parameter_grid_v3() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    grid_index = 1
    for family_index, family in enumerate(SIGNAL_FAMILIES_V3):
        family_name, direction, trade_intent = family
        for dte in DTE_BUCKETS[:3]:
            for hold in HOLD_WINDOWS[2:5]:
                for moneyness in MONEYNESS_BUCKETS[:3]:
                    for exit_policy in EXIT_POLICIES[:3]:
                        record = {
                            "artifact_type": "public_signal_parameter_grid_v3",
                            "grid_id": f"grid-v3-{grid_index:05d}",
                            "setup_family": family_name,
                            "direction": direction,
                            "trade_intent": trade_intent,
                            "ma_fast_window": 10 + (family_index % 4) * 5,
                            "ma_slow_window": 30 + (family_index % 5) * 10,
                            "rsi_window": 10 + (family_index % 4) * 2,
                            "macd_fast": 8 + (family_index % 4),
                            "macd_slow": 20 + (family_index % 5) * 2,
                            "macd_signal": 7 + (family_index % 3),
                            "atr_window": 10 + (family_index % 4) * 2,
                            "breakout_lookback": 20 + (family_index % 4) * 10,
                            "support_resistance_lookback": 30 + (family_index % 5) * 10,
                            "relative_strength_lookback": 20 + (family_index % 5) * 5,
                            "volatility_threshold": round(0.12 + (family_index % 6) * 0.04, 4),
                            "gap_threshold": round(0.006 + (family_index % 5) * 0.004, 4),
                            "volume_threshold": round(1.05 + (family_index % 5) * 0.15, 4),
                            "stop_distance": round(0.012 + (family_index % 5) * 0.006, 4),
                            "target_distance": round(0.025 + (family_index % 6) * 0.01, 4),
                            "hold_window": hold,
                            "dte_bucket": dte,
                            "moneyness_bucket": moneyness,
                            "exit_policy": exit_policy,
                            "confidence_threshold": round(0.48 + (family_index % 6) * 0.04, 4),
                            "no_trade_threshold": round(0.32 + (family_index % 5) * 0.03, 4),
                        }
                        records.append(record_with_hash(record, "record_hash"))
                        grid_index += 1
    return records


def symbol_signal_candidates(
    symbol: str,
    rows: list[dict[str, str]],
    spy_rows: list[dict[str, str]],
    parameter_grid: list[dict[str, object]],
    remaining_capacity: int,
) -> list[dict[str, object]]:
    if remaining_capacity <= 0:
        return []
    closes = [safe_float(row["close"]) for row in rows]
    volumes = [safe_float(row.get("volume", "0")) for row in rows]
    source_type = str(rows[-1].get("market_data_source_type", "public_live_fetch")) or "public_live_fetch"
    sampled_indexes = sample_signal_indexes(len(rows), 44)
    candidates: list[dict[str, object]] = []
    for sample_position, row_index in enumerate(sampled_indexes):
        if len(candidates) >= remaining_capacity:
            break
        features = feature_snapshot(symbol, rows, closes, volumes, row_index, spy_rows)
        selected_grids = select_grids_for_snapshot(parameter_grid, features, sample_position)
        for grid in selected_grids:
            if len(candidates) >= remaining_capacity:
                break
            signal = build_signal_candidate(symbol, rows[row_index], features, grid, source_type, len(candidates) + 1)
            candidates.append(record_with_hash(signal, "record_hash"))
    return candidates


def sample_signal_indexes(row_count: int, target_count: int) -> list[int]:
    start = 260
    end = max(start, row_count - 25)
    span = max(end - start, 1)
    step = max(5, span // target_count)
    indexes = list(range(start, end, step))
    return indexes[-target_count:]


def feature_snapshot(
    symbol: str,
    rows: list[dict[str, str]],
    closes: list[float],
    volumes: list[float],
    row_index: int,
    spy_rows: list[dict[str, str]],
) -> dict[str, object]:
    close = closes[row_index]
    open_value = safe_float(rows[row_index]["open"])
    high = safe_float(rows[row_index]["high"])
    low = safe_float(rows[row_index]["low"])
    ma_10 = rolling_mean(closes[max(0, row_index - 10):row_index])
    ma_20 = rolling_mean(closes[max(0, row_index - 20):row_index])
    ma_50 = rolling_mean(closes[max(0, row_index - 50):row_index])
    ma_100 = rolling_mean(closes[max(0, row_index - 100):row_index])
    recent_high = max(closes[max(0, row_index - 20):row_index] or [close])
    recent_low = min(closes[max(0, row_index - 20):row_index] or [close])
    returns_20 = pct_return(closes[max(0, row_index - 20)], close)
    spy_return = spy_window_return(spy_rows, str(rows[row_index]["date"]), 20)
    vol_20 = realized_volatility(closes[max(0, row_index - 20):row_index + 1])
    vol_60 = realized_volatility(closes[max(0, row_index - 60):row_index + 1])
    volume_ratio = volumes[row_index] / max(rolling_mean(volumes[max(0, row_index - 20):row_index]), 1.0)
    rsi_proxy = 50.0 + max(min(returns_20 * 220.0, 45.0), -45.0)
    gap = pct_return(closes[row_index - 1], open_value) if row_index > 0 else 0.0
    trend = "uptrend" if ma_20 >= ma_50 >= ma_100 else ("downtrend" if ma_20 <= ma_50 <= ma_100 else "sideways")
    regime = "high_volatility" if vol_20 >= vol_60 * 1.15 else ("low_volatility" if vol_20 <= vol_60 * 0.85 else "normal_volatility")
    return {
        "symbol": symbol,
        "date": rows[row_index]["date"],
        "close": close,
        "open": open_value,
        "high": high,
        "low": low,
        "ma_10": ma_10,
        "ma_20": ma_20,
        "ma_50": ma_50,
        "ma_100": ma_100,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "returns_20": returns_20,
        "spy_relative_strength": returns_20 - spy_return,
        "realized_vol_20": vol_20,
        "realized_vol_60": vol_60,
        "volume_ratio": volume_ratio,
        "rsi_proxy": rsi_proxy,
        "gap": gap,
        "trend_regime": trend,
        "volatility_regime": regime,
        "sector": sector_for_symbol(symbol),
    }


def spy_window_return(spy_rows: list[dict[str, str]], target_date: str, lookback: int) -> float:
    if not spy_rows:
        return 0.0
    index = 0
    for position, row in enumerate(spy_rows):
        if str(row.get("date", "")) <= target_date:
            index = position
        else:
            break
    if index <= lookback:
        return 0.0
    return pct_return(safe_float(spy_rows[index - lookback]["close"]), safe_float(spy_rows[index]["close"]))


def select_grids_for_snapshot(parameter_grid: list[dict[str, object]], features: dict[str, object], sample_position: int) -> list[dict[str, object]]:
    bullish = safe_float(features["returns_20"]) >= 0.0 or safe_float(features["spy_relative_strength"]) > 0.015
    high_vol = str(features["volatility_regime"]) == "high_volatility"
    selected: list[dict[str, object]] = []
    offset = (sample_position * 17) % max(len(parameter_grid), 1)
    rotated_grid = parameter_grid[offset:] + parameter_grid[:offset]
    used_families: set[str] = set()
    for grid in rotated_grid:
        family = str(grid["setup_family"])
        if family in used_families:
            continue
        intent = str(grid["trade_intent"])
        if intent == "no_trade":
            if sample_position % 11 == 0:
                selected.append(grid)
                used_families.add(family)
            continue
        if bullish and intent == "long_call" and family_filter_passes(family, features, high_vol):
            selected.append(grid)
            used_families.add(family)
        if not bullish and intent == "long_put" and family_filter_passes(family, features, high_vol):
            selected.append(grid)
            used_families.add(family)
        if len(selected) >= 3:
            break
    if not selected:
        selected = [grid for grid in parameter_grid if str(grid["setup_family"]) == "no_trade_capital_preservation"][:1]
    return selected


def family_filter_passes(family: str, features: dict[str, object], high_vol: bool) -> bool:
    close = safe_float(features["close"])
    recent_high = safe_float(features["recent_high"])
    recent_low = safe_float(features["recent_low"])
    rsi = safe_float(features["rsi_proxy"])
    volume_ratio = safe_float(features["volume_ratio"])
    gap = abs(safe_float(features["gap"]))
    if "squeeze" in family or "compression" in family:
        return not high_vol
    if "breakout" in family or "resistance" in family:
        return close >= recent_high * 0.985 or volume_ratio >= 1.15
    if "support" in family or "reversal" in family or "fade" in family:
        return close <= recent_low * 1.025 or rsi >= 68.0 or rsi <= 32.0
    if "gap" in family:
        return gap >= 0.006
    if "volume" in family:
        return volume_ratio >= 1.05
    return True


def build_signal_candidate(
    symbol: str,
    row: dict[str, str],
    features: dict[str, object],
    grid: dict[str, object],
    source_type: str,
    local_index: int,
) -> dict[str, object]:
    close = safe_float(features["close"])
    intent = str(grid["trade_intent"])
    direction = str(grid["direction"])
    stop_distance = safe_float(grid["stop_distance"])
    target_distance = safe_float(grid["target_distance"])
    if intent == "long_put":
        invalidation = close * (1.0 + stop_distance)
        target = close * (1.0 - target_distance)
    elif intent == "long_call":
        invalidation = close * (1.0 - stop_distance)
        target = close * (1.0 + target_distance)
    else:
        invalidation = close
        target = close
    confidence = confidence_score(features, grid, intent)
    risk_score = risk_score_for_signal(features, grid, intent)
    setup_family = str(grid["setup_family"])
    strategy_id = f"{setup_family}|{grid['exit_policy']}|dte{grid['dte_bucket']}|{grid['moneyness_bucket']}"
    signal_id_seed = f"{symbol}-{row['date']}-{setup_family}-{grid['grid_id']}-{local_index}"
    return {
        "artifact_type": "public_signal_mutation_candidate_v3",
        "signal_id": f"public-signal-v3-{stable_signal_id(signal_id_seed)}",
        "symbol": symbol,
        "timestamp": row["date"],
        "direction": direction,
        "trade_intent": intent,
        "setup_family": setup_family,
        "strategy_id": strategy_id,
        "entry_trigger": round(close, 4),
        "entry_price": round(close, 4),
        "invalidation_level": round(invalidation, 4),
        "target_price": round(target, 4),
        "target_move": round(abs(target - close), 4),
        "stop_distance": stop_distance,
        "target_distance": target_distance,
        "hold_window": int(grid["hold_window"]),
        "dte_bucket": int(grid["dte_bucket"]),
        "moneyness_bucket": str(grid["moneyness_bucket"]),
        "exit_policy": str(grid["exit_policy"]),
        "confidence_score": confidence,
        "risk_score": risk_score,
        "realized_vol_proxy": round(safe_float(features["realized_vol_20"]), 6),
        "spy_relative_strength": round(safe_float(features["spy_relative_strength"]), 6),
        "trend_regime": str(features["trend_regime"]),
        "volatility_regime": str(features["volatility_regime"]),
        "sector": str(features["sector"]),
        "market_data_source_type": source_type if source_type in PUBLIC_SOURCE_TYPES else "public_live_fetch",
        "data_source_label": source_type if source_type in PUBLIC_SOURCE_TYPES else "public_live_fetch",
        "zero_dte_research_lane": setup_family == "zero_dte_special_high_momentum_research_lane",
        "paper_only": True,
        "live_blocked": True,
    }


def confidence_score(features: dict[str, object], grid: dict[str, object], intent: str) -> float:
    if intent == "no_trade":
        return 0.25
    trend_bonus = 0.10 if str(features["trend_regime"]) in {"uptrend", "downtrend"} else 0.0
    rs_bonus = min(abs(safe_float(features["spy_relative_strength"])) * 4.0, 0.18)
    volume_bonus = min(max(safe_float(features.get("volume_ratio", 1.0)) - 1.0, 0.0) * 0.12, 0.10)
    base = safe_float(grid["confidence_threshold"])
    return round(min(base + trend_bonus + rs_bonus + volume_bonus, 0.93), 6)


def risk_score_for_signal(features: dict[str, object], grid: dict[str, object], intent: str) -> float:
    if intent == "no_trade":
        return 0.05
    vol = safe_float(features["realized_vol_20"])
    dte_penalty = 0.08 if int(grid["dte_bucket"]) <= 7 else 0.0
    hold_penalty = min(int(grid["hold_window"]) / 60.0, 0.20)
    return round(min(0.20 + vol * 0.35 + dte_penalty + hold_penalty, 0.95), 6)


def stable_signal_id(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def rank_signal_candidates_v3(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for candidate in candidates:
        score = safe_float(candidate["confidence_score"]) * 1.7 - safe_float(candidate["risk_score"]) + abs(safe_float(candidate["spy_relative_strength"])) * 2.0
        record = {
            "artifact_type": "public_signal_quality_ranking_v3",
            "signal_id": candidate["signal_id"],
            "symbol": candidate["symbol"],
            "setup_family": candidate["setup_family"],
            "strategy_id": candidate["strategy_id"],
            "quality_score": round(score, 6),
            "market_data_source_type": candidate["market_data_source_type"],
        }
        ranked.append(record_with_hash(record, "record_hash"))
    return sorted(ranked, key=lambda item: safe_float(item["quality_score"]), reverse=True)


def artifact_paths() -> dict[str, str]:
    return {
        "public_signal_family_registry_v3": str(REGISTRY_PATH),
        "public_signal_mutation_candidates_v3": str(CANDIDATES_PATH),
        "public_signal_parameter_grid_v3": str(PARAMETER_GRID_PATH),
        "public_signal_quality_rankings_v3": str(RANKINGS_PATH),
        "public_signal_mutation_factory_v3_summary": str(SUMMARY_PATH),
        "public_signal_mutation_factory_v3_proof": str(PROOF_PATH),
    }
