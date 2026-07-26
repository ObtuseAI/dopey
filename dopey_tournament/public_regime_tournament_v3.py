"""Regime scoring helpers for public tournament V3."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import date_from_text, group_records, pnl_metrics, record_with_hash, safe_float


REGIME_SPLITS = [
    ("bull_regime", "bull_regime"),
    ("bear_regime", "bear_regime"),
    ("sideways_regime", "sideways_regime"),
    ("high_volatility", "high_volatility"),
    ("low_volatility", "low_volatility"),
    ("2020_like_shock_proxy", "date_proxy"),
    ("2022_like_bear_proxy", "date_proxy"),
    ("2023_2024_trend_proxy", "date_proxy"),
    ("2025_2026_recent_proxy", "date_proxy"),
]


def build_public_regime_scores_v3(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    scores: list[dict[str, object]] = []
    for strategy_id, records in group_records(executable_trades(trades), "strategy_id").items():
        for split_id, split_type in REGIME_SPLITS:
            selected = select_regime_records(records, split_id)
            score = score_regime(strategy_id, selected, split_id, split_type)
            scores.append(record_with_hash(score, "record_hash"))
    return scores


def executable_trades(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [record for record in records if str(record.get("trade_intent", "")) in {"long_call", "long_put"}]


def select_regime_records(records: list[dict[str, object]], split_id: str) -> list[dict[str, object]]:
    if split_id == "bull_regime":
        return [record for record in records if str(record.get("trend_regime", "")) == "uptrend"]
    if split_id == "bear_regime":
        return [record for record in records if str(record.get("trend_regime", "")) == "downtrend"]
    if split_id == "sideways_regime":
        return [record for record in records if str(record.get("trend_regime", "")) == "sideways"]
    if split_id == "high_volatility":
        return [record for record in records if str(record.get("regime", "")) == "high_volatility"]
    if split_id == "low_volatility":
        return [record for record in records if str(record.get("regime", "")) == "low_volatility"]
    if split_id == "2020_like_shock_proxy":
        return [record for record in records if date_from_text(record.get("entry_date")).year == 2020]
    if split_id == "2022_like_bear_proxy":
        return [record for record in records if date_from_text(record.get("entry_date")).year == 2022]
    if split_id == "2023_2024_trend_proxy":
        return [record for record in records if date_from_text(record.get("entry_date")).year in {2023, 2024}]
    if split_id == "2025_2026_recent_proxy":
        return [record for record in records if date_from_text(record.get("entry_date")).year in {2025, 2026}]
    return []


def score_regime(strategy_id: str, records: list[dict[str, object]], split_id: str, split_type: str) -> dict[str, object]:
    metrics = pnl_metrics(records)
    passed = bool(metrics["sample_count"] >= 3 and safe_float(metrics["net_pnl"]) > 0.0 and safe_float(metrics["profit_factor"]) >= 1.02)
    return {
        "artifact_type": "public_regime_score_v3",
        "strategy_id": strategy_id,
        "split_id": split_id,
        "split_type": split_type,
        **metrics,
        "split_passed": passed,
        "public_data_only": all(str(record.get("market_data_source_type", "")).startswith("public") for record in records),
        "fixture_trade_count": sum(1 for record in records if str(record.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }

