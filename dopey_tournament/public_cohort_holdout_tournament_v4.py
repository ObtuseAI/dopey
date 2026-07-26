"""Cohort holdout tournament V4 — symbol/sector/date holdouts at cohort level."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from dopey_autonomy.public_champion_common import (
    date_from_text,
    group_records,
    pnl_metrics,
    record_with_hash,
    safe_float,
    sector_for_symbol,
)

from dopey_strategy_cohorts.strategy_cohort_models import COHORT_LEVELS


def build_public_cohort_holdout_scores_v4(trades: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    date_values = [date_from_text(trade.get("entry_date")) for trade in trades]
    latest_date = max(date_values) if date_values else date_from_text("1970-01-01")
    holdout_scores: list[dict[str, object]] = []
    symbol_scores: list[dict[str, object]] = []
    for level in COHORT_LEVELS:
        groups = group_records(trades, level)
        for cohort_id, records in groups.items():
            executable = [r for r in records if str(r.get("trade_intent", "")) in {"long_call", "long_put"}]
            definitions = [
                {"split_id": f"{level}_older_history_holdout", "split_type": "older_history_holdout"},
                {"split_id": f"{level}_recent_12_months_holdout", "split_type": "recent_12_months_holdout", "latest_date": latest_date},
                {"split_id": f"{level}_symbol_holdout_top_half", "split_type": "symbol_holdout"},
                {"split_id": f"{level}_sector_holdout_top_half", "split_type": "sector_holdout"},
            ]
            for definition in definitions:
                selected = select_holdout_trades(executable, definition)
                holdout_scores.append(record_with_hash(
                    score_cohort_split(cohort_id, level, selected, str(definition["split_id"]), str(definition["split_type"])),
                    "record_hash",
                ))
            symbol_scores.extend(build_cohort_symbol_scores(cohort_id, level, executable))
    return holdout_scores, symbol_scores


def select_holdout_trades(records: list[dict[str, object]], definition: dict[str, object]) -> list[dict[str, object]]:
    split_type = str(definition["split_type"])
    if split_type == "older_history_holdout":
        return [r for r in records if date_from_text(r.get("entry_date")).year <= 2021]
    if split_type == "recent_12_months_holdout":
        latest_date = definition["latest_date"]
        threshold = latest_date - timedelta(days=365) if hasattr(latest_date, "__sub__") else date_from_text("1970-01-01")
        return [r for r in records if date_from_text(r.get("entry_date")) >= threshold]
    if split_type == "symbol_holdout":
        counts = Counter(str(r.get("symbol", "")) for r in records)
        symbols = {symbol for index, (symbol, _) in enumerate(counts.most_common()) if index % 2 == 0}
        return [r for r in records if str(r.get("symbol", "")) in symbols]
    if split_type == "sector_holdout":
        counts = Counter(sector_for_symbol(str(r.get("symbol", ""))) for r in records)
        sectors = {sector for index, (sector, _) in enumerate(counts.most_common()) if index % 2 == 0}
        return [r for r in records if sector_for_symbol(str(r.get("symbol", ""))) in sectors]
    return []


def score_cohort_split(cohort_id: str, level: str, records: list[dict[str, object]], split_id: str, split_type: str) -> dict[str, object]:
    metrics = pnl_metrics(records)
    passed = bool(
        metrics["sample_count"] >= 3
        and safe_float(metrics["net_pnl"]) > 0.0
        and safe_float(metrics["expectancy"]) > 0.0
        and safe_float(metrics["profit_factor"]) >= 1.02
    )
    return {
        "artifact_type": "public_cohort_holdout_score_v4",
        "cohort_level": level,
        "cohort_id": cohort_id,
        "split_id": split_id,
        "split_type": split_type,
        **metrics,
        "split_passed": passed,
        "public_data_only": all(str(r.get("market_data_source_type", "")).startswith("public") for r in records),
        "fixture_trade_count": sum(1 for r in records if str(r.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }


def build_cohort_symbol_scores(cohort_id: str, level: str, records: list[dict[str, object]]) -> list[dict[str, object]]:
    scores: list[dict[str, object]] = []
    for symbol, symbol_records in group_records(records, "symbol").items():
        score = score_cohort_split(cohort_id, level, symbol_records, f"{level}_symbol_holdout_{symbol}", "symbol_holdout")
        score["symbol"] = symbol
        scores.append(record_with_hash(score, "record_hash"))
    return scores
