"""Calibrate the model IV proxy against real chain quotes.

The real-history backtester prices options with IV = trailing realized vol x
IV_RISK_PREMIUM_MULTIPLIER. This module measures that proxy against reality:
for each symbol's validated chain snapshot it compares (a) chain ATM implied
vol vs trailing realized vol from the governed history spine, and (b) the
model premium vs the market mid for near-ATM contracts. Output is an error
distribution and a data-driven recommended multiplier - evidence for tuning
the simulator toward reality, never for tuning signals toward profit.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from dopey_data.history_validator import validate_default_history_dataset
from dopey_research_pipeline.artifact_io import (
    write_json_atomic,
    write_jsonl_atomic,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .chain_snapshot_loader import load_latest_chain_snapshot
from .greeks_engine import implied_vol_bisection
from .model_iv_calibration_contract import (
    MODEL_IV_CALIBRATION_COMPLETE_STATUS,
    MODEL_IV_CALIBRATION_VERSION,
)
from .option_pricing_models import option_pricing_input, price_european_option
from .risk_free_rate import resolve_risk_free_rate

REPO_ROOT = Path(__file__).resolve().parent.parent
CALIBRATION_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics"
CALIBRATION_SUMMARY_PATH = CALIBRATION_ARTIFACT_DIR / "model_iv_calibration_summary.json"
CALIBRATION_ROWS_PATH = CALIBRATION_ARTIFACT_DIR / "model_iv_calibration_rows.jsonl"

RV_LOOKBACK = 20
ATM_BAND_PCT = 0.05
MIN_CONTRACTS_PER_SYMBOL = 6  # thinner chains fall back to the global multiplier

RISK_FREE_RATE, RISK_FREE_SOURCE = resolve_risk_free_rate()


def _current_multiplier() -> float:
    """Measure the SAME multiplier the backtester actually uses (fixed-point:
    calibration grades the calibrated model, converging on the market)."""
    from dopey_backtest.real_history_honest_backtester import resolve_iv_multiplier

    return resolve_iv_multiplier()[0]


CURRENT_MULTIPLIER = _current_multiplier()


def run_model_iv_calibration() -> dict[str, Any]:
    snapshot = load_latest_chain_snapshot()
    if snapshot["chain_snapshot_status"] != "real_chain_snapshot_validated":
        summary = {
            "artifact_type": "model_iv_calibration_summary",
            "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
            "calibration_status": snapshot["chain_snapshot_status"],
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(CALIBRATION_SUMMARY_PATH, summary)
        return summary
    dataset = validate_default_history_dataset()
    if dataset["dataset_status"] != "valid_real_dataset":
        summary = {
            "artifact_type": "model_iv_calibration_summary",
            "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
            "calibration_status": "blocked_missing_valid_real_history",
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(CALIBRATION_SUMMARY_PATH, summary)
        return summary
    realized_by_symbol = _trailing_realized_vol(dataset["bars_loaded"])
    calibration_rows: list[dict[str, Any]] = []
    iv_ratios: list[float] = []
    premium_errors_pct: list[float] = []
    ratios_by_symbol: dict[str, list[float]] = {}
    bisection_used = 0
    for row in snapshot["rows"]:
        symbol = str(row["symbol"])
        realized = realized_by_symbol.get(symbol)
        spot = float(row["underlying_spot"])
        strike = float(row["strike"])
        if realized is None or realized <= 0.0:
            continue
        if abs(strike - spot) / spot > ATM_BAND_PCT:
            continue
        chain_iv = float(row["implied_vol"])
        market_mid = float(row["mid"])
        if market_mid <= 0.0:
            continue
        # Prefer the house inversion of the actual market mid over the vendor's
        # reported IV field: same pricer both directions, arbitrage-band guarded.
        bisected = implied_vol_bisection(
            market_mid, spot, strike,
            max(float(row["dte_calendar"]) / 365.0, 1e-6),
            RISK_FREE_RATE, str(row["option_type"]),
        )
        effective_iv = bisected if bisected is not None else chain_iv
        if bisected is not None:
            bisection_used += 1
        model_iv = realized * CURRENT_MULTIPLIER
        model_premium = _model_price(row, model_iv)
        chain_iv_premium = _model_price(row, chain_iv)
        ratio = effective_iv / realized
        iv_ratios.append(ratio)
        ratios_by_symbol.setdefault(symbol, []).append(ratio)
        premium_errors_pct.append((model_premium - market_mid) / market_mid)
        calibration_rows.append(
            {
                "artifact_type": "model_iv_calibration_row",
                "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
                "symbol": symbol,
                "snapshot_date": row["snapshot_date"],
                "option_type": row["option_type"],
                "strike": strike,
                "underlying_spot": spot,
                "dte_calendar": row["dte_calendar"],
                "market_mid": market_mid,
                "chain_iv": round(chain_iv, 6),
                "mid_bisection_iv": round(bisected, 6) if bisected is not None else None,
                "iv_source": "mid_bisection" if bisected is not None else "vendor_chain_iv",
                "realized_vol_20d": round(realized, 6),
                "model_iv_current_proxy": round(model_iv, 6),
                "model_premium_current_proxy": model_premium,
                "premium_at_chain_iv": chain_iv_premium,
                "premium_error_pct_vs_mid": round((model_premium - market_mid) / market_mid, 6),
                "quote_derived": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    if not iv_ratios:
        summary = {
            "artifact_type": "model_iv_calibration_summary",
            "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
            "calibration_status": "blocked_no_atm_overlap",
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(CALIBRATION_SUMMARY_PATH, summary)
        return summary
    iv_ratios.sort()
    premium_errors_pct.sort()
    # Per-symbol calibration: each liquid symbol earns its own multiplier (its
    # chain's median IV/RV), clamped to the same band as the global; thin
    # chains (< MIN_CONTRACTS_PER_SYMBOL) stay on the global fallback.
    from dopey_backtest.real_history_honest_backtester import IV_MULTIPLIER_CLAMP

    per_symbol_multipliers = {
        symbol: {
            "multiplier": round(min(max(_median(sorted(ratios)), IV_MULTIPLIER_CLAMP[0]), IV_MULTIPLIER_CLAMP[1]), 4),
            "contracts": len(ratios),
        }
        for symbol, ratios in sorted(ratios_by_symbol.items())
        if len(ratios) >= MIN_CONTRACTS_PER_SYMBOL
    }
    summary = {
        "artifact_type": "model_iv_calibration_summary",
        "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
        "calibration_status": MODEL_IV_CALIBRATION_COMPLETE_STATUS,
        "snapshot_date": snapshot["snapshot_date"],
        "atm_contracts_compared": len(calibration_rows),
        "iv_from_mid_bisection_count": bisection_used,
        "symbols_covered": sorted({row["symbol"] for row in calibration_rows}),
        "current_multiplier": CURRENT_MULTIPLIER,
        "recommended_multiplier_median_iv_over_rv": round(_median(iv_ratios), 4),
        "per_symbol_multipliers": per_symbol_multipliers,
        "iv_over_rv_p25": round(iv_ratios[len(iv_ratios) // 4], 4),
        "iv_over_rv_p75": round(iv_ratios[(3 * len(iv_ratios)) // 4], 4),
        "model_premium_error_pct_median": round(_median(premium_errors_pct), 4),
        "model_premium_error_pct_p25": round(premium_errors_pct[len(premium_errors_pct) // 4], 4),
        "model_premium_error_pct_p75": round(premium_errors_pct[(3 * len(premium_errors_pct)) // 4], 4),
        "interpretation": (
            "median premium error < 0 means the model proxy UNDERPRICES options vs market "
            "(historical backtest premiums too cheap -> net P&L flattered); recalibrate the "
            "simulator multiplier toward the recommended value in the next lane revision"
        ),
        "quote_derived": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    CALIBRATION_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(CALIBRATION_ROWS_PATH, calibration_rows)
    _write_json(CALIBRATION_SUMMARY_PATH, summary)
    return summary


def _model_price(row: dict[str, Any], implied_vol: float) -> float:
    pricing = price_european_option(
        option_pricing_input(
            symbol=str(row["symbol"]),
            option_type=str(row["option_type"]),
            strike=float(row["strike"]),
            expiry=str(row["expiry"]),
            valuation_date=str(row["snapshot_date"]),
            underlying_price=float(row["underlying_spot"]),
            time_to_expiry_years=max(float(row["dte_calendar"]) / 365.0, 1e-6),
            implied_vol=implied_vol,
            risk_free_rate=RISK_FREE_RATE,
            dividend_yield=0.0,
            pricing_source_tier="model_priced",
        )
    )
    return round(float(pricing.model_price), 6)


def _trailing_realized_vol(bars: list[dict[str, Any]]) -> dict[str, float]:
    closes_by_symbol: dict[str, list[float]] = {}
    for bar in bars:
        closes_by_symbol.setdefault(str(bar["symbol"]), []).append(float(bar["adjusted_close"]))
    result: dict[str, float] = {}
    for symbol, closes in closes_by_symbol.items():
        window = closes[-(RV_LOOKBACK + 1):]
        returns = [math.log(later / earlier) for earlier, later in zip(window, window[1:]) if earlier > 0 and later > 0]
        if len(returns) < 2:
            continue
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        result[symbol] = math.sqrt(max(variance, 0.0)) * math.sqrt(252.0)
    return result


def _median(values: list[float]) -> float:
    middle = len(values) // 2
    return values[middle] if len(values) % 2 == 1 else (values[middle - 1] + values[middle]) / 2.0


def _write_json(path: Path, record: dict[str, Any]) -> None:
    write_json_atomic(path, record)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    write_jsonl_atomic(path, records)
