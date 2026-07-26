"""OPERATOR TOOL - cross-provider OHLCV spot check (verification only).

The governed spine is single-provider (yahoo_finance). The staging gate
rejects IMPOSSIBLE rows (non-positive, OHLC-inconsistent) but cannot catch
plausible-but-wrong ones - the class behind the 2026-07-16/17 provider-glitch
incident. Two independent lanes:

1. INDEX ANCHOR (always on, keyless): FRED's official SP500 series vs the
   SPY spine, compared as DAILY RETURNS (levels differ by construction).
   Catches market-level spine corruption immediately, no credentials.
2. PER-SYMBOL LANE (optional): a deterministic weekly rotation of spine
   symbols vs Alpha Vantage's official API. Activates only when the operator
   exports ALPHAVANTAGE_API_KEY (free tier suffices - 20 symbols/week);
   unconfigured is a NORMAL soft state, not a failure. (Stooq was the
   original secondary but now sits behind a JavaScript bot-wall.)

Data governance: secondary rows are fetched, compared, and DISCARDED - never
persisted, never joined into research artifacts, never redistributed. The
spine remains the single source of truth; a material divergence is an alert
to investigate (either provider could be the wrong one).

Usage:  .venv\\Scripts\\python operator_tools\\operator_cross_provider_check.py
Cadence: invoked by the Monday preflight (weekly); safe to run ad hoc.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_core.market_calendar import is_trading_day  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402

HISTORY_DIR = REPO / "dopey_data" / "history" / "raw"
REPORT_PATH = REPO / "artifacts" / "dopey" / "observability" / "cross_provider_check.json"

SAMPLE_SYMBOLS = 20
COMPARE_TRADING_DAYS = 10
CLOSE_MINOR_REL_DIFF = 0.005   # <=0.5% treated as provider noise (rounding, venue)
CLOSE_MATERIAL_REL_DIFF = 0.02  # >2% is a material divergence worth investigating
VOLUME_REL_DIFF = 0.25          # consolidated-tape differences are common; informational
# SPY tracks SP500 within a few bps daily; ex-dividend days can add ~10-20bp.
ANCHOR_MINOR_RETURN_DIFF = 0.003
ANCHOR_MATERIAL_RETURN_DIFF = 0.008
FETCH_TIMEOUT_SECONDS = 30
USER_AGENT = {"User-Agent": "dopey-operator-research/1.0 (personal research)"}
ALPHAVANTAGE_KEY_ENV = "ALPHAVANTAGE_API_KEY"
CHECK_VERSION = "dopey-cross-provider-check-v2"


class SecondaryUnconfiguredError(RuntimeError):
    """Per-symbol secondary lane has no API key configured (a soft state)."""


def weekly_rotation(symbols: list[str], today: date, count: int) -> list[str]:
    """Deterministic weekly sample that rotates through the whole universe."""
    ordered = sorted(symbols)
    if not ordered:
        return []
    iso = today.isocalendar()
    offset = (iso[0] * 53 + iso[1]) * count % len(ordered)
    doubled = ordered + ordered
    return doubled[offset: offset + min(count, len(ordered))]


def _spine_recent_rows(symbol: str, day_floor: str) -> dict[str, tuple[float, float]]:
    path = HISTORY_DIR / f"{symbol}.csv"
    rows: dict[str, tuple[float, float]] = {}
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            day = str(row.get("date", ""))
            if day < day_floor:
                continue
            try:
                rows[day] = (float(row["close"]), float(row["volume"]))
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def fetch_secondary_rows(symbol: str, start: date, end: date) -> dict[str, tuple[float, float]]:
    """Fetch recent daily rows from Alpha Vantage; parsed, returned, never persisted."""
    api_key = os.environ.get(ALPHAVANTAGE_KEY_ENV, "").strip()
    if not api_key:
        raise SecondaryUnconfiguredError(
            f"{ALPHAVANTAGE_KEY_ENV} not set; per-symbol lane inactive"
        )
    cleaned = symbol.strip().upper().replace("_", "-")
    response = requests.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_DAILY",
            "symbol": cleaned,
            "outputsize": "compact",
            "apikey": api_key,
        },
        headers=USER_AGENT,
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict):
        note = payload.get("Note") or payload.get("Information") or payload.get("Error Message")
        raise RuntimeError(f"alphavantage returned no series: {str(note)[:120]}")
    rows: dict[str, tuple[float, float]] = {}
    start_iso, end_iso = start.isoformat(), end.isoformat()
    for day, fields in series.items():
        if not (start_iso <= str(day) <= end_iso) or not isinstance(fields, dict):
            continue
        try:
            close = float(fields.get("4. close", ""))
            volume = float(fields.get("5. volume", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if close > 0.0:
            rows[str(day)] = (close, volume)
    return rows


def fetch_fred_sp500_closes() -> dict[str, float]:
    """FRED's official SP500 daily closes (keyless); returned, never persisted."""
    response = requests.get(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
        headers=USER_AGENT,
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    closes: dict[str, float] = {}
    for line in response.text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) != 2 or parts[1] in (".", ""):
            continue
        try:
            closes[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return closes


def _daily_returns(closes_by_day: dict[str, float]) -> dict[str, float]:
    ordered = sorted(closes_by_day)
    returns: dict[str, float] = {}
    for previous, current in zip(ordered, ordered[1:]):
        prior = closes_by_day[previous]
        if prior > 0.0:
            returns[current] = closes_by_day[current] / prior - 1.0
    return returns


def sp500_anchor_check(day_floor: str) -> dict[str, object]:
    """Compare SPY spine daily returns vs FRED SP500 daily returns."""
    spine_rows = _spine_recent_rows("SPY", day_floor)
    spine_returns = _daily_returns({day: close for day, (close, _volume) in spine_rows.items()})
    try:
        fred_closes = fetch_fred_sp500_closes()
    except Exception as error:  # noqa: BLE001 - anchor outage must not kill the report
        return {"anchor_status": f"fred_fetch_failed:{type(error).__name__}", "issues": []}
    fred_returns = _daily_returns(
        {day: close for day, close in fred_closes.items() if day >= day_floor}
    )
    shared = sorted(set(spine_returns) & set(fred_returns))
    if not shared:
        return {"anchor_status": "no_shared_return_days", "issues": []}
    issues: list[dict[str, object]] = []
    worst = 0.0
    for day in shared:
        diff = abs(spine_returns[day] - fred_returns[day])
        worst = max(worst, diff)
        if diff > ANCHOR_MINOR_RETURN_DIFF:
            issues.append(
                {
                    "date": day,
                    "spy_spine_return": round(spine_returns[day], 6),
                    "fred_sp500_return": round(fred_returns[day], 6),
                    "abs_return_diff": round(diff, 6),
                    "severity": "material" if diff > ANCHOR_MATERIAL_RETURN_DIFF else "minor",
                }
            )
    return {
        "anchor_status": "compared",
        "shared_return_days": len(shared),
        "worst_abs_return_diff": round(worst, 6),
        "issues": issues,
    }


def compare_symbol(
    symbol: str,
    spine_rows: dict[str, tuple[float, float]],
    secondary_rows: dict[str, tuple[float, float]],
) -> dict[str, object]:
    shared = sorted(set(spine_rows) & set(secondary_rows))
    issues: list[dict[str, object]] = []
    worst_close_diff = 0.0
    for day in shared:
        spine_close, spine_volume = spine_rows[day]
        second_close, second_volume = secondary_rows[day]
        if spine_close <= 0.0 or second_close <= 0.0:
            continue
        close_diff = abs(spine_close - second_close) / spine_close
        worst_close_diff = max(worst_close_diff, close_diff)
        if close_diff > CLOSE_MINOR_REL_DIFF:
            issues.append(
                {
                    "date": day,
                    "field": "close",
                    "spine": round(spine_close, 6),
                    "secondary": round(second_close, 6),
                    "relative_diff": round(close_diff, 6),
                    "severity": "material" if close_diff > CLOSE_MATERIAL_REL_DIFF else "minor",
                }
            )
        if spine_volume > 0.0 and second_volume > 0.0:
            volume_diff = abs(spine_volume - second_volume) / spine_volume
            if volume_diff > VOLUME_REL_DIFF:
                issues.append(
                    {
                        "date": day,
                        "field": "volume",
                        "spine": spine_volume,
                        "secondary": second_volume,
                        "relative_diff": round(volume_diff, 4),
                        "severity": "informational",
                    }
                )
    return {
        "symbol": symbol,
        "shared_days_compared": len(shared),
        "worst_close_relative_diff": round(worst_close_diff, 6),
        "issues": issues,
    }


def run_cross_provider_check(today: date | None = None) -> dict[str, object]:
    today = today or datetime.now(timezone.utc).date()
    day_floor_date = today
    trading_days = 0
    while trading_days < COMPARE_TRADING_DAYS:
        day_floor_date = day_floor_date - timedelta(days=1)
        if is_trading_day(day_floor_date):
            trading_days += 1
    day_floor = day_floor_date.isoformat()
    anchor = sp500_anchor_check(day_floor)
    anchor_material = sum(
        1 for issue in anchor.get("issues", []) if issue.get("severity") == "material"
    )
    symbols = [path.stem for path in sorted(HISTORY_DIR.glob("*.csv"))]
    sampled = weekly_rotation(symbols, today, SAMPLE_SYMBOLS)
    per_symbol: list[dict[str, object]] = []
    fetch_failures: list[dict[str, str]] = []
    secondary_configured = True
    material_count = 0
    minor_count = 0
    for symbol in sampled:
        spine_rows = _spine_recent_rows(symbol, day_floor)
        if not spine_rows:
            fetch_failures.append({"symbol": symbol, "reason": "no_recent_spine_rows"})
            continue
        try:
            secondary = fetch_secondary_rows(symbol, day_floor_date, today)
        except SecondaryUnconfiguredError:
            secondary_configured = False
            break  # a soft state for the whole lane, not a per-symbol failure
        except Exception as error:  # noqa: BLE001 - a provider outage must not kill the report
            fetch_failures.append({"symbol": symbol, "reason": f"secondary_fetch_failed:{error}"})
            continue
        if not secondary:
            fetch_failures.append({"symbol": symbol, "reason": "secondary_returned_no_rows"})
            continue
        comparison = compare_symbol(symbol, spine_rows, secondary)
        per_symbol.append(comparison)
        for issue in comparison["issues"]:
            if issue["severity"] == "material":
                material_count += 1
            elif issue["severity"] == "minor":
                minor_count += 1
    compared = len(per_symbol)
    anchor_compared = anchor.get("anchor_status") == "compared"
    if material_count or anchor_material:
        verdict = "material_divergence_detected"
    elif compared:
        verdict = "cross_provider_consistent"
    elif anchor_compared and not secondary_configured:
        verdict = "anchor_consistent_per_symbol_lane_unconfigured"
    elif anchor_compared:
        verdict = "anchor_consistent_per_symbol_lane_unavailable"
    else:
        verdict = "inconclusive_no_comparisons"
    report = {
        "artifact_type": "cross_provider_check",
        "check_version": CHECK_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "index_anchor": {"provider": "fred_sp500_keyless", **anchor},
        "secondary_provider": "alphavantage_time_series_daily",
        "secondary_configured": secondary_configured,
        "secondary_activation": f"export {ALPHAVANTAGE_KEY_ENV} (free tier) to activate the per-symbol lane",
        "secondary_rows_discarded_not_persisted": True,
        "spine_remains_single_source_of_truth": True,
        "sampled_symbol_count": len(sampled),
        "compared_symbol_count": compared,
        "compare_window_start": day_floor,
        "material_close_divergences": material_count,
        "minor_close_divergences": minor_count,
        "anchor_material_divergences": anchor_material,
        "fetch_failures": fetch_failures,
        "per_symbol": per_symbol,
        "note": "a material divergence means ONE of the providers is wrong - investigate before trusting either",
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(REPORT_PATH, report)
    return report


def main() -> int:
    report = run_cross_provider_check()
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "compared_symbols": report["compared_symbol_count"],
                "material": report["material_close_divergences"],
                "minor": report["minor_close_divergences"],
                "fetch_failures": len(report["fetch_failures"]),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if report["verdict"] != "material_divergence_detected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
