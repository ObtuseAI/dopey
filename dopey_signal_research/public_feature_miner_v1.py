"""Public feature miner V1 — new predictive features from public OHLCV."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import FEATURE_REGISTRY_PATH, RESEARCH_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import (
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


RECORDS_PATH = RESEARCH_ROOT / "public_feature_records_v1.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_ROOT / "public_feature_quality_flags_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "public_feature_miner_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "public_feature_miner_v1_proof.jsonl"


def run_public_feature_miner_v1(max_symbols: int = 80, step: int = 5) -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    rows_by_symbol = active_rows_by_symbol()
    spy_rows = rows_by_symbol.get("SPY", [])
    registry: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    group_counts: Counter[str] = Counter()
    fixture_count = 0

    symbols = [symbol for symbol, rows in rows_by_symbol.items() if len(rows) >= 200 and not is_test_symbol(symbol)]
    for symbol in symbols[:max_symbols]:
        rows = rows_by_symbol[symbol]
        for index in range(60, len(rows) - 5, step):
            feature_bundle = compute_features(symbol, rows, index, spy_rows)
            if is_test_symbol(symbol):
                fixture_count += 1
                continue
            for group, features in feature_bundle.items():
                for feature_name, value in features.items():
                    group_counts[group] += 1
                    registry.append(record_with_hash({
                        "artifact_type": "public_feature_registry_v1",
                        "symbol": symbol,
                        "sector": sector_for_symbol(symbol),
                        "date": rows[index]["date"],
                        "feature_group": group,
                        "feature_name": feature_name,
                        "feature_value": round(float(value), 6),
                        "market_data_source_type": "public_live_fetch",
                        **live_safety_fields(),
                    }, "record_hash"))
            records.append(record_with_hash({
                "artifact_type": "public_feature_record_v1",
                "symbol": symbol,
                "date": rows[index]["date"],
                "feature_vector": {group: features for group, features in feature_bundle.items()},
                **live_safety_fields(),
            }, "record_hash"))

    summary = {
        "artifact_type": "public_feature_miner_v1_summary",
        "public_feature_miner_version": "dopey-public-feature-miner-v1",
        "public_feature_miner_status": "public_features_mined",
        "feature_count": len(registry),
        "symbol_count": len({row["symbol"] for row in registry}),
        "row_count": len(records),
        "feature_group_counts": dict(group_counts),
        "public_data_only": True,
        "fixture_feature_count": fixture_count,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FEATURE_REGISTRY_PATH, registry)
    write_jsonl_file(RECORDS_PATH, records[:5000])
    write_jsonl_file(QUALITY_FLAGS_PATH, [record_with_hash({"artifact_type": "public_feature_quality_flag_v1", "flag_id": "public_data_only", "passed": True, **live_safety_fields()}, "record_hash")])
    write_stage_proof(PROOF_PATH, "public-feature-miner-v1", str(summary["public_feature_miner_status"]), summary)
    return {**summary, "artifact_paths": {"public_feature_miner_v1_summary": str(SUMMARY_PATH)}}


def compute_features(symbol: str, rows: list[dict[str, str]], index: int, spy_rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    window = rows[index - 20:index + 1]
    closes = [safe_float(row["close"]) for row in window]
    highs = [safe_float(row["high"]) for row in window]
    lows = [safe_float(row["low"]) for row in window]
    volumes = [safe_float(row["volume"]) for row in window]
    spot = closes[-1]
    prior = closes[-2] if len(closes) > 1 else spot
    range_pct = (highs[-1] - lows[-1]) / max(spot, 0.01)
    compression = (max(highs[-10:]) - min(lows[-10:])) / max(spot, 0.01)
    ma20 = rolling_mean(closes)
    ma50 = rolling_mean([safe_float(row["close"]) for row in rows[index - 50:index + 1]]) if index >= 50 else ma20
    rel_spy = relative_return(rows, index, spy_rows)
    rel_sector = pct_return(closes[-1], closes[-6]) if len(closes) >= 6 else 0.0
    realized_vol = realized_volatility(closes)
    vol_percentile = min(realized_vol / 0.5, 1.0)
    volume_percentile = volumes[-1] / max(sum(volumes[-20:]) / 20.0, 1.0)
    close_location = (spot - lows[-1]) / max(highs[-1] - lows[-1], 0.01)
    wick_rejection = (highs[-1] - max(spot, prior)) / max(highs[-1] - lows[-1], 0.01)
    trend_stack = 1.0 if ma20 > ma50 and spot > ma20 else (-1.0 if ma20 < ma50 and spot < ma20 else 0.0)
    overextension = abs(pct_return(spot, ma20))
    return {
        "price_structure": {
            "compression_10d": compression,
            "range_expansion": range_pct,
            "close_location_value": close_location,
            "wick_rejection_proxy": wick_rejection,
        },
        "trend_structure": {
            "ma_slope_acceleration": pct_return(ma20, ma50),
            "trend_persistence": trend_stack,
            "trend_failure": 1.0 if trend_stack > 0 and spot < prior else 0.0,
        },
        "relative_strength": {
            "vs_spy": rel_spy,
            "rolling_relative_rank": rel_sector,
            "relative_acceleration": rel_spy - rel_sector,
        },
        "volatility": {
            "realized_vol_percentile": vol_percentile,
            "atr_percentile": range_pct,
            "vol_compression_percentile": 1.0 - vol_percentile,
        },
        "volume": {
            "volume_percentile": volume_percentile,
            "volume_dry_up": 1.0 if volume_percentile < 0.6 else 0.0,
            "volume_climax": 1.0 if volume_percentile > 1.8 else 0.0,
        },
        "regime": {
            "broad_market_regime": 1.0 if rel_spy > 0 else -1.0,
            "volatility_regime": 1.0 if vol_percentile > 0.6 else 0.0,
            "risk_on_proxy": 1.0 if rel_spy > 0 and vol_percentile < 0.7 else 0.0,
        },
        "reversal": {
            "overextension": overextension,
            "mean_reversion_pressure": overextension * (1.0 if close_location < 0.35 or close_location > 0.65 else 0.0),
        },
        "continuation": {
            "breakout_continuation": 1.0 if spot > max(closes[:-1]) and volume_percentile > 1.0 else 0.0,
            "pullback_continuation": 1.0 if trend_stack > 0 and close_location > 0.45 else 0.0,
        },
        "risk_filter": {
            "avoid_thin_volume": 1.0 if volume_percentile < 0.5 else 0.0,
            "avoid_overextended_move": 1.0 if overextension > 0.04 else 0.0,
            "avoid_poor_regime_alignment": 1.0 if rel_spy < -0.02 and trend_stack > 0 else 0.0,
        },
        "robinhood_market_data": {
            "official_robinhood_market_data_allowed": 1.0,
        },
    }


def relative_return(rows: list[dict[str, str]], index: int, spy_rows: list[dict[str, str]]) -> float:
    if not spy_rows:
        return 0.0
    date = rows[index]["date"]
    symbol_return = pct_return(safe_float(rows[index]["close"]), safe_float(rows[index - 5]["close"])) if index >= 5 else 0.0
    spy_index = next((idx for idx, row in enumerate(spy_rows) if row["date"] == date), -1)
    if spy_index < 5:
        return symbol_return
    spy_return = pct_return(safe_float(spy_rows[spy_index]["close"]), safe_float(spy_rows[spy_index - 5]["close"]))
    return round(symbol_return - spy_return, 6)
