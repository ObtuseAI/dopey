"""Holdout scoring helpers for the public walk-forward tournament V3."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from dopey_autonomy.public_champion_common import date_from_text, group_records, pnl_metrics, record_with_hash, safe_float, sector_for_symbol


def build_public_holdout_scores_v3(trades: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    strategy_groups = group_records(trades, "strategy_id")
    date_values = [date_from_text(trade.get("entry_date")) for trade in trades]
    latest_date = max(date_values) if date_values else date_from_text("1970-01-01")
    definitions = [
        {"split_id": "older_history_holdout", "split_type": "older_history_holdout"},
        {"split_id": "recent_12_months_holdout", "split_type": "recent_12_months_holdout", "latest_date": latest_date},
        {"split_id": "symbol_holdout_top_half", "split_type": "symbol_holdout"},
        {"split_id": "sector_holdout_top_half", "split_type": "sector_holdout"},
    ]
    holdout_scores: list[dict[str, object]] = []
    symbol_scores: list[dict[str, object]] = []
    for strategy_id, records in strategy_groups.items():
        trade_records = executable_trades(records)
        for definition in definitions:
            selected = select_holdout_trades(trade_records, definition)
            score = score_split(strategy_id, selected, str(definition["split_id"]), str(definition["split_type"]))
            holdout_scores.append(record_with_hash(score, "record_hash"))
        symbol_scores.extend(build_symbol_holdout_scores(strategy_id, trade_records))
    return holdout_scores, symbol_scores


def executable_trades(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [record for record in records if str(record.get("trade_intent", "")) in {"long_call", "long_put"}]


def select_holdout_trades(records: list[dict[str, object]], definition: dict[str, object]) -> list[dict[str, object]]:
    split_type = str(definition["split_type"])
    if split_type == "older_history_holdout":
        return [record for record in records if date_from_text(record.get("entry_date")).year <= 2021]
    if split_type == "recent_12_months_holdout":
        latest_date = definition["latest_date"]
        threshold = latest_date - timedelta(days=365) if hasattr(latest_date, "__sub__") else date_from_text("1970-01-01")
        return [record for record in records if date_from_text(record.get("entry_date")) >= threshold]
    if split_type == "symbol_holdout":
        counts = Counter(str(record.get("symbol", "")) for record in records)
        symbols = {symbol for index, (symbol, _) in enumerate(counts.most_common()) if index % 2 == 0}
        return [record for record in records if str(record.get("symbol", "")) in symbols]
    if split_type == "sector_holdout":
        counts = Counter(sector_for_symbol(str(record.get("symbol", ""))) for record in records)
        sectors = {sector for index, (sector, _) in enumerate(counts.most_common()) if index % 2 == 0}
        return [record for record in records if sector_for_symbol(str(record.get("symbol", ""))) in sectors]
    return []


def build_symbol_holdout_scores(strategy_id: str, records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = group_records(records, "symbol")
    scores: list[dict[str, object]] = []
    for symbol, symbol_records in grouped.items():
        score = score_split(strategy_id, symbol_records, f"symbol_holdout_{symbol}", "symbol_holdout")
        score["symbol"] = symbol
        scores.append(record_with_hash(score, "record_hash"))
    return scores


def score_split(strategy_id: str, records: list[dict[str, object]], split_id: str, split_type: str) -> dict[str, object]:
    metrics = pnl_metrics(records)
    passed = bool(metrics["sample_count"] >= 3 and safe_float(metrics["net_pnl"]) > 0.0 and safe_float(metrics["expectancy"]) > 0.0 and safe_float(metrics["profit_factor"]) >= 1.02)
    return {
        "artifact_type": "public_holdout_score_v3",
        "strategy_id": strategy_id,
        "split_id": split_id,
        "split_type": split_type,
        **metrics,
        "split_passed": passed,
        "public_data_only": all(str(record.get("market_data_source_type", "")).startswith("public") for record in records),
        "fixture_trade_count": sum(1 for record in records if str(record.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }

