"""Cohesive per-symbol market profile, strategy research, and options laboratory."""

from __future__ import annotations

import csv
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Final

from dopey.protocols.identity import canonical_hash
from dopey.technical.history_adapter import load_validated_symbol_history
from dopey_dashboard.chart_state import build_chart_state
from dopey_equity_swing.market_structure import Bar, analyze_multi_timeframe_structure
from dopey_options.chain_snapshot_loader import load_latest_chain_snapshot
from dopey_options.risk_free_rate import FALLBACK_RATE, resolve_risk_free_rate

from .options_projector import project_option_values
from .research import evaluate_symbol_strategies


SYMBOL_LAB_VERSION: Final[str] = "dopey-symbol-intelligence-lab-v1"
ALLOWED_STRATEGY_MODES: Final[frozenset[str]] = frozenset(
    {
        "auto",
        "trend",
        "momentum",
        "breakout",
        "mean_reversion",
        "volatility",
        "bullish_scenario",
        "bearish_scenario",
    }
)
SYMBOL_LAB_ARTIFACT_ROOT: Final[Path] = (
    Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "symbol_lab"
)


def _annualized_realized_vol(rows: list[Bar], lookback: int) -> float:
    closes = [float(row["adjusted_close"]) for row in rows[-(lookback + 1) :]]
    returns = [math.log(later / earlier) for earlier, later in zip(closes, closes[1:]) if earlier > 0.0 and later > 0.0]
    if len(returns) < 2:
        return 0.0
    mean_value = sum(returns) / len(returns)
    variance = sum((value - mean_value) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(max(variance, 0.0)) * math.sqrt(252.0)


def _latest_csv(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    paths = sorted(directory.glob(pattern))
    return paths[-1] if paths else None


def _earnings_context(repository_root: Path, symbol: str, as_of_date: str) -> dict[str, object]:
    path = _latest_csv(
        repository_root / "dopey_data" / "real" / "raw" / "earnings_calendar",
        "*_earnings.csv",
    )
    if path is None:
        return {
            "status": "unavailable_no_earnings_snapshot",
            "earnings_date": None,
            "days_until_earnings": None,
            "inside_14_day_window": False,
        }
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle) if str(row.get("symbol", "")).upper() == symbol]
    if not rows:
        return {
            "status": "no_upcoming_earnings_record_for_symbol",
            "snapshot_path": str(path),
            "snapshot_date": path.name[:10],
            "earnings_date": None,
            "days_until_earnings": None,
            "inside_14_day_window": False,
        }
    earnings_date = str(rows[0]["earnings_date"])
    days_until = (date.fromisoformat(earnings_date) - date.fromisoformat(as_of_date)).days
    return {
        "status": "upcoming_earnings_observed",
        "snapshot_path": str(path),
        "snapshot_date": str(rows[0].get("snapshot_date", path.name[:10])),
        "earnings_date": earnings_date,
        "days_until_earnings": days_until,
        "inside_14_day_window": 0 <= days_until <= 14,
        "source": str(rows[0].get("source", "unknown")),
    }


def _fundamental_context(repository_root: Path, symbol: str) -> dict[str, object]:
    path = _latest_csv(
        repository_root / "dopey_data" / "real" / "raw" / "fundamentals",
        "*.csv",
    )
    if path is None:
        return {
            "status": "unavailable_no_fundamental_snapshot",
            "symbol": symbol,
            "directional_use": "missing_evidence_not_assumed_neutral",
        }
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle) if str(row.get("symbol", "")).upper() == symbol]
    if not rows:
        return {
            "status": "symbol_absent_from_latest_fundamental_snapshot",
            "symbol": symbol,
            "snapshot_path": str(path),
            "directional_use": "missing_evidence_not_assumed_neutral",
        }
    row = rows[0]
    fields = (
        "market_cap",
        "trailing_pe",
        "forward_pe",
        "price_to_sales",
        "price_to_book",
        "profit_margin",
        "revenue_growth",
        "free_cashflow",
        "total_debt",
        "total_cash",
    )
    return {
        "status": "real_fundamental_snapshot_available",
        "symbol": symbol,
        "snapshot_path": str(path),
        "as_of_date": str(row.get("date", path.name[:10])),
        "theme": str(row.get("theme", "unknown")),
        "metrics": {field: row.get(field) for field in fields},
        "directional_use": "context_only_not_a_prediction",
    }


def _median_or_none(values: list[float]) -> float | None:
    return None if not values else round(median(values), 6)


def _chain_context(rows: list[dict[str, Any]], snapshot_status: str, snapshot_date: str) -> dict[str, object]:
    if not rows:
        return {
            "status": snapshot_status,
            "snapshot_date": snapshot_date,
            "contract_count": 0,
            "expiry_count": 0,
            "expiries": [],
            "quote_derived": False,
        }
    spot = float(rows[0]["underlying_spot"])
    expiries = sorted({str(row["expiry"]) for row in rows})
    spreads = [
        (float(row["ask"]) - float(row["bid"])) / float(row["mid"])
        for row in rows
        if float(row["mid"]) > 0.0
    ]
    near_atm = [row for row in rows if abs(float(row["strike"]) / spot - 1.0) <= 0.03]
    term_structure = []
    for expiry in expiries:
        expiry_rows = [row for row in near_atm if str(row["expiry"]) == expiry]
        if expiry_rows:
            term_structure.append(
                {
                    "expiry": expiry,
                    "dte_calendar": min(int(row["dte_calendar"]) for row in expiry_rows),
                    "median_near_atm_iv": _median_or_none([float(row["implied_vol"]) for row in expiry_rows]),
                }
            )
    call_oi = sum(int(row["open_interest"]) for row in rows if row["option_type"] == "call")
    put_oi = sum(int(row["open_interest"]) for row in rows if row["option_type"] == "put")
    call_iv = [float(row["implied_vol"]) for row in near_atm if row["option_type"] == "call"]
    put_iv = [float(row["implied_vol"]) for row in near_atm if row["option_type"] == "put"]
    median_call_iv = _median_or_none(call_iv)
    median_put_iv = _median_or_none(put_iv)
    return {
        "status": "validated_quote_derived_chain_context",
        "snapshot_date": snapshot_date,
        "underlying_spot": round(spot, 6),
        "contract_count": len(rows),
        "expiry_count": len(expiries),
        "expiries": expiries,
        "median_spread_pct": _median_or_none(spreads),
        "total_call_open_interest": call_oi,
        "total_put_open_interest": put_oi,
        "put_call_open_interest_ratio": round(put_oi / call_oi, 6) if call_oi > 0 else None,
        "median_near_atm_call_iv": median_call_iv,
        "median_near_atm_put_iv": median_put_iv,
        "near_atm_put_minus_call_iv": (
            None
            if median_put_iv is None or median_call_iv is None
            else round(median_put_iv - median_call_iv, 6)
        ),
        "term_structure": term_structure,
        "quote_derived": True,
        "future_quote_not_known": True,
    }


def _structure_price(record: object) -> float | None:
    if not isinstance(record, dict):
        return None
    value = record.get("zone_mid")
    return None if value is None else float(value)


def _selected_direction(
    strategy_mode: str,
    strategy_research: dict[str, object],
    structure: dict[str, Any],
) -> tuple[str, str, str | None]:
    if strategy_mode == "bullish_scenario":
        return "bullish", "operator_selected_scenario_direction", None
    if strategy_mode == "bearish_scenario":
        return "bearish", "operator_selected_scenario_direction", None
    results = list(strategy_research["strategy_results"])
    allowed_family = None if strategy_mode == "auto" else strategy_mode
    active = [
        record
        for record in results
        if record.get("current_signal_active") is True
        and (allowed_family is None or record.get("family") == allowed_family)
    ]
    if active:
        best = active[0]
        return str(best["direction"]), "current_historical_recipe_signal", str(best["strategy_id"])
    structure_direction = str(structure.get("multi_timeframe_direction", "neutral"))
    if structure_direction in {"bullish", "bearish"}:
        return structure_direction, "multi_timeframe_structure_fallback_no_recipe_signal", None
    return "neutral", "no_directional_evidence_abstention", None


def _default_scenario_price(direction: str, current_price: float, support: float | None, resistance: float | None, atr: float) -> float:
    if direction == "bullish":
        return max(current_price + 1.5 * atr, resistance or current_price)
    if direction == "bearish":
        return min(current_price - 1.5 * atr, support or current_price)
    return current_price


def _strategy_results_for_family(strategy_research: dict[str, object], family: str, direction: str) -> list[dict[str, object]]:
    return [
        record
        for record in strategy_research["strategy_results"]
        if record.get("family") == family and record.get("direction") == direction
    ]


def _meta_plans(
    strategy_research: dict[str, object],
    structure: dict[str, Any],
    earnings: dict[str, object],
    selected_direction: str,
) -> list[dict[str, object]]:
    current = float(structure["current_price"])
    atr = float(structure["daily_atr"])
    support = _structure_price(structure.get("nearest_support"))
    resistance = _structure_price(structure.get("nearest_resistance"))
    plan_specs = (
        ("trend_continuation", "trend", selected_direction),
        ("range_resolution", "breakout", selected_direction),
        ("statistical_reversion", "mean_reversion", "bearish" if selected_direction == "bullish" else "bullish"),
        ("volatility_release", "volatility", selected_direction),
    )
    plans: list[dict[str, object]] = []
    for plan_id, family, direction in plan_specs:
        if direction not in {"bullish", "bearish"}:
            direction = "neutral"
        candidates = _strategy_results_for_family(strategy_research, family, direction)
        best = candidates[0] if candidates else None
        active = best is not None and best.get("current_signal_active") is True
        target = (
            max(current + 1.5 * atr, resistance or current)
            if direction == "bullish"
            else min(current - 1.5 * atr, support or current)
            if direction == "bearish"
            else current
        )
        invalidation = (
            min(current - atr, support or current - atr)
            if direction == "bullish"
            else max(current + atr, resistance or current + atr)
            if direction == "bearish"
            else current
        )
        plans.append(
            {
                "plan_id": plan_id,
                "family": family,
                "direction": direction,
                "plan_status": "active_shadow_hypothesis" if active else "watch_for_trigger",
                "strategy_id": None if best is None else best["strategy_id"],
                "historical_evidence_status": "untested_for_direction" if best is None else best["evidence_status"],
                "historical_sample_count": 0 if best is None else best["sample_count"],
                "trigger": (
                    "current_recipe_conditions_are_active"
                    if active
                    else "wait_for_all_past_only_recipe_conditions_to_align"
                ),
                "invalidation_price": round(invalidation, 6),
                "scenario_target_price": round(max(target, 0.01), 6),
                "options_expression_bias": "long_call_or_defined_risk_call_debit_research" if direction == "bullish" else "long_put_or_defined_risk_put_debit_research" if direction == "bearish" else "no_directional_option_expression",
                "confidence_cap": 0.55 if active and best is not None and best["evidence_status"] == "historically_supported_not_forward_proven" else 0.35,
                "forward_proof_required": True,
                "not_trade_recommendation": True,
            }
        )
    if earnings.get("inside_14_day_window") is True:
        plans.insert(
            0,
            {
                "plan_id": "earnings_event_abstention",
                "family": "event_risk",
                "direction": "neutral",
                "plan_status": "abstain_or_require_separate_event_model",
                "strategy_id": None,
                "historical_evidence_status": "event_distribution_not_estimated_in_symbol_lab_v1",
                "historical_sample_count": 0,
                "trigger": f"earnings_inside_14_day_window:{earnings.get('earnings_date')}",
                "invalidation_price": None,
                "scenario_target_price": None,
                "options_expression_bias": "none_until_event_volatility_and_gap_distribution_are_validated",
                "confidence_cap": 0.20,
                "forward_proof_required": True,
                "not_trade_recommendation": True,
            },
        )
    return plans


def _build_symbol_lab_state_with_chain(
    repository_root: Path,
    symbol: str,
    strategy_mode: str,
    scenario_stock_price: float | None,
    days_forward: int,
    iv_shift: float,
    chain_snapshot: dict[str, Any],
) -> dict[str, object]:
    root = repository_root.resolve()
    normalized_symbol = symbol.strip().upper()
    normalized_mode = strategy_mode.strip().lower()
    if normalized_mode not in ALLOWED_STRATEGY_MODES:
        raise ValueError(
            f"unsupported symbol-lab strategy_mode: value={strategy_mode!r}, allowed={sorted(ALLOWED_STRATEGY_MODES)}"
        )
    rows, history_proof = load_validated_symbol_history(
        normalized_symbol,
        root / "dopey_data" / "history" / "history_dataset_manifest.json",
    )
    structure = analyze_multi_timeframe_structure(normalized_symbol, rows)
    chart = build_chart_state(root, normalized_symbol, "daily")
    strategy_research = evaluate_symbol_strategies(rows)
    selected_direction, direction_source, selected_strategy_id = _selected_direction(
        normalized_mode,
        strategy_research,
        structure,
    )
    earnings = _earnings_context(root, normalized_symbol, str(structure["as_of_date"]))
    fundamentals = _fundamental_context(root, normalized_symbol)
    all_chain_rows = chain_snapshot.get("rows")
    if not isinstance(all_chain_rows, list):
        raise TypeError("validated options-chain snapshot rows must be a list")
    chain_rows = [row for row in all_chain_rows if str(row.get("symbol", "")).upper() == normalized_symbol]
    chain_context = _chain_context(
        chain_rows,
        str(chain_snapshot["chain_snapshot_status"]),
        str(chain_snapshot["snapshot_date"]),
    )
    current_price = float(structure["current_price"])
    support = _structure_price(structure.get("nearest_support"))
    resistance = _structure_price(structure.get("nearest_resistance"))
    scenario_price = (
        _default_scenario_price(
            selected_direction,
            current_price,
            support,
            resistance,
            float(structure["daily_atr"]),
        )
        if scenario_stock_price is None
        else float(scenario_stock_price)
    )
    realized_volatility = _annualized_realized_vol(rows, 20)
    risk_free_rate, risk_free_source = resolve_risk_free_rate(FALLBACK_RATE)
    target_dte = max(21, min(120, days_forward * 3))
    options = project_option_values(
        chain_rows,
        scenario_price,
        days_forward,
        iv_shift,
        selected_direction,
        target_dte,
        risk_free_rate,
        risk_free_source,
        0.0,
        support,
        resistance,
        realized_volatility,
    )
    plans = _meta_plans(strategy_research, structure, earnings, selected_direction)
    body: dict[str, object] = {
        "artifact_type": "dopey_symbol_intelligence_lab",
        "schema_version": SYMBOL_LAB_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": normalized_symbol,
        "as_of_date": str(structure["as_of_date"]),
        "request": {
            "strategy_mode": normalized_mode,
            "scenario_stock_price_requested": scenario_stock_price,
            "scenario_stock_price_effective": round(scenario_price, 6),
            "days_forward": days_forward,
            "iv_shift_decimal": round(iv_shift, 6),
        },
        "selected_research_direction": selected_direction,
        "direction_source": direction_source,
        "selected_strategy_id": selected_strategy_id,
        "market_profile": {
            "current_price": round(current_price, 6),
            "daily_atr": round(float(structure["daily_atr"]), 6),
            "daily_atr_pct": round(float(structure["daily_atr_pct"]), 6),
            "realized_volatility_20d_annualized": round(realized_volatility, 6),
            "multi_timeframe_direction": structure["multi_timeframe_direction"],
            "multi_timeframe_agreement_score": structure["multi_timeframe_agreement_score"],
            "nearest_support": structure.get("nearest_support"),
            "nearest_resistance": structure.get("nearest_resistance"),
            "confluence_zones": structure.get("confluence_zones", [])[:12],
            "timeframes": structure["timeframes"],
            "earnings": earnings,
            "fundamentals": fundamentals,
            "options_chain": chain_context,
        },
        "technical_intelligence": {
            "indicator_count": chart["indicator_count"],
            "indicator_snapshot": chart["indicator_snapshot"],
            "geometric_patterns": chart["geometric_patterns"],
            "candlestick_patterns": chart["candlestick_patterns"],
            "divergences": chart["divergences"],
            "volume_profile": chart["volume_profile"],
            "regime_statistics": chart["regime_statistics"],
        },
        "strategy_research": strategy_research,
        "meta_plans": plans,
        "options_value_lab": options,
        "source_proof": {
            "history": history_proof,
            "chain_snapshot_status": chain_snapshot["chain_snapshot_status"],
            "chain_snapshot_date": chain_snapshot["snapshot_date"],
            "chain_quote_derived": chain_snapshot["quote_derived"],
        },
        "knowledge_boundaries": [
            "historical_recipe_results_are_not_forward_proof",
            "future_option_values_are_model_projections_not_executable_quotes",
            "earnings_gap_distribution_requires_separate_event_validation",
            "dividend_yield_is_zero_until_a_governed_point_in_time_dividend_lane_is_available",
            "best_expression_means_highest_scenario_fit_not_expected_profit",
        ],
        "synthetic_data_used": False,
        "profitability_claim_allowed": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    hash_body = {key: value for key, value in body.items() if key != "generated_utc"}
    return {**body, "content_hash": canonical_hash(hash_body)}


def build_symbol_lab_state(
    repository_root: Path,
    symbol: str,
    strategy_mode: str,
    scenario_stock_price: float | None,
    days_forward: int,
    iv_shift: float,
) -> dict[str, object]:
    """Build a source-bound symbol dossier and interactive option scenario projection."""

    chain_snapshot = load_latest_chain_snapshot()
    return _build_symbol_lab_state_with_chain(
        repository_root,
        symbol,
        strategy_mode,
        scenario_stock_price,
        days_forward,
        iv_shift,
        chain_snapshot,
    )


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _manifest_symbols(repository_root: Path) -> list[str]:
    manifest_path = repository_root / "dopey_data" / "history" / "history_dataset_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_files = payload.get("data_files")
    if not isinstance(data_files, list):
        raise TypeError(f"history manifest data_files must be a list: path={manifest_path}")
    symbols = {
        str(symbol).upper()
        for record in data_files
        if isinstance(record, dict)
        for symbol in record.get("symbols", [])
    }
    return sorted(symbols)


def run_symbol_lab_batch(repository_root: Path, symbols: list[str]) -> dict[str, object]:
    """Materialize reproducible full dossiers for a governed symbol set."""

    root = repository_root.resolve()
    selected_symbols = sorted(set(symbol.upper() for symbol in symbols)) if symbols else _manifest_symbols(root)
    chain_snapshot = load_latest_chain_snapshot()
    results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for symbol in selected_symbols:
        try:
            result = _build_symbol_lab_state_with_chain(
                root,
                symbol,
                "auto",
                None,
                14,
                0.0,
                chain_snapshot,
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as error:
            failures.append({"symbol": symbol, "error_type": type(error).__name__, "message": str(error)})
            continue
        _write_json_atomic(SYMBOL_LAB_ARTIFACT_ROOT / "symbols" / f"{symbol}.json", result)
        options = result["options_value_lab"]
        strategy = result["strategy_research"]
        if not isinstance(options, dict) or not isinstance(strategy, dict):
            raise TypeError(f"symbol lab result contains invalid section types: symbol={symbol}")
        results.append(
            {
                "symbol": symbol,
                "content_hash": result["content_hash"],
                "selected_research_direction": result["selected_research_direction"],
                "active_strategy_ids": strategy["current_active_strategy_ids"],
                "option_projector_status": options["projector_status"],
                "best_expression_id": (
                    None
                    if not isinstance(options.get("best_expression"), dict)
                    else options["best_expression"].get("expression_id")
                ),
            }
        )
    batch_status = "complete" if not failures else "partial_explicit_symbol_failures"
    body: dict[str, object] = {
        "artifact_type": "dopey_symbol_lab_batch",
        "schema_version": SYMBOL_LAB_VERSION,
        "batch_status": batch_status,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "requested_symbol_count": len(selected_symbols),
        "completed_symbol_count": len(results),
        "failed_symbol_count": len(failures),
        "results": results,
        "failures": failures,
        "historical_testing_is_not_forward_proof": True,
        "profitability_claim_allowed": False,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    hash_body = {key: value for key, value in body.items() if key != "generated_utc"}
    summary = {**body, "batch_hash": canonical_hash(hash_body)}
    _write_json_atomic(SYMBOL_LAB_ARTIFACT_ROOT / "latest_batch_summary.json", summary)
    return summary
