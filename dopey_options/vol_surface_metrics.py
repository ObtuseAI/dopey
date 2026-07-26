"""Volatility-surface metrics from multi-expiry chain snapshots.

Treats the snapshot as a (strike x expiry) IV surface per symbol and extracts
the shape features institutions actually watch:

- skew slope: d(IV)/d(log-moneyness) on the put side (crash-fear gradient)
- risk-reversal proxy: OTM put IV minus OTM call IV (~10% OTM band)
- term slope: far-expiry ATM IV minus near-expiry ATM IV (event pricing)
- surface tears: day-over-day changes in skew or term beyond thresholds while
  spot moves the OTHER way - the asymmetric-accumulation signature (requires
  at least two archived snapshot days; honestly reports insufficient history
  until the archive grows).

Quote-derived, deterministic, not edge evidence. Paper-only, live-blocked.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .chain_snapshot_loader import CHAIN_RAW_DIR, load_latest_chain_snapshot, _parse_file

REPO_ROOT = Path(__file__).resolve().parent.parent
SURFACE_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics"
SURFACE_METRICS_PATH = SURFACE_ARTIFACT_DIR / "vol_surface_metrics.jsonl"
SURFACE_TEARS_PATH = SURFACE_ARTIFACT_DIR / "vol_surface_tears.jsonl"
SURFACE_SUMMARY_PATH = SURFACE_ARTIFACT_DIR / "vol_surface_summary.json"

OTM_BAND = 0.10
SKEW_TEAR_THRESHOLD = 0.030
TERM_TEAR_THRESHOLD = 0.030


def run_vol_surface_metrics() -> dict[str, Any]:
    snapshot = load_latest_chain_snapshot()
    if snapshot["chain_snapshot_status"] != "real_chain_snapshot_validated":
        summary = {
            "artifact_type": "vol_surface_summary",
            "surface_status": snapshot["chain_snapshot_status"],
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(SURFACE_SUMMARY_PATH, summary)
        return summary
    metrics = compute_surface_metrics(snapshot["rows"], snapshot["snapshot_date"])
    previous = _previous_snapshot_metrics(snapshot["snapshot_date"])
    tears = detect_surface_tears(metrics, previous) if previous else []
    summary = {
        "artifact_type": "vol_surface_summary",
        "surface_status": "vol_surface_metrics_computed",
        "snapshot_date": snapshot["snapshot_date"],
        "symbols_covered": len(metrics),
        "expiries_per_symbol_median": _median([record["expiry_count"] for record in metrics]) if metrics else 0,
        "tear_detection": "active" if previous else "insufficient_archive_history_needs_two_days",
        "tear_count": len(tears),
        "quote_derived": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    SURFACE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(SURFACE_METRICS_PATH, metrics)
    _write_jsonl(SURFACE_TEARS_PATH, tears)
    _write_json(SURFACE_SUMMARY_PATH, summary)
    return summary


def compute_surface_metrics(rows: list[dict[str, Any]], snapshot_date: str) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    metrics: list[dict[str, Any]] = []
    for symbol, symbol_rows in sorted(by_symbol.items()):
        spot = float(symbol_rows[0]["underlying_spot"])
        expiries = sorted({str(row["expiry"]) for row in symbol_rows})
        near, far = expiries[0], expiries[-1]
        near_rows = [row for row in symbol_rows if row["expiry"] == near]
        far_rows = [row for row in symbol_rows if row["expiry"] == far]
        skew = _put_skew_slope(near_rows, spot)
        risk_reversal = _risk_reversal(near_rows, spot)
        near_atm = _atm_iv(near_rows, spot)
        far_atm = _atm_iv(far_rows, spot)
        metrics.append(
            {
                "artifact_type": "vol_surface_metrics",
                "symbol": symbol,
                "snapshot_date": snapshot_date,
                "underlying_spot": spot,
                "expiry_count": len(expiries),
                "near_expiry": near,
                "far_expiry": far,
                "near_atm_iv": near_atm,
                "far_atm_iv": far_atm,
                "term_slope": round(far_atm - near_atm, 6) if near_atm and far_atm else 0.0,
                "put_skew_slope": skew,
                "risk_reversal_10pct": risk_reversal,
                "quote_derived": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return metrics


def detect_surface_tears(
    current: list[dict[str, Any]],
    previous: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    tears: list[dict[str, Any]] = []
    for record in current:
        prior = previous.get(record["symbol"])
        if not prior:
            continue
        skew_change = record["put_skew_slope"] - prior["put_skew_slope"]
        term_change = record["term_slope"] - prior["term_slope"]
        spot_change = (record["underlying_spot"] / prior["underlying_spot"]) - 1.0 if prior["underlying_spot"] else 0.0
        # put-skew steepening while spot RISES = divergent downside hedging demand
        divergent_skew = skew_change <= -SKEW_TEAR_THRESHOLD and spot_change > 0.0
        divergent_term = abs(term_change) >= TERM_TEAR_THRESHOLD
        if divergent_skew or divergent_term:
            tears.append(
                {
                    "artifact_type": "vol_surface_tear",
                    "symbol": record["symbol"],
                    "snapshot_date": record["snapshot_date"],
                    "previous_date": prior["snapshot_date"],
                    "tear_type": "divergent_put_skew_steepening" if divergent_skew else "term_structure_shift",
                    "skew_change": round(skew_change, 6),
                    "term_change": round(term_change, 6),
                    "spot_change_pct": round(spot_change, 6),
                    "quote_derived": True,
                    "not_edge_evidence": True,
                    "paper_only": True,
                    "live_blocked": True,
                }
            )
    return tears


def _previous_snapshot_metrics(current_date: str) -> dict[str, dict[str, Any]]:
    if not CHAIN_RAW_DIR.exists():
        return {}
    days = sorted(p.name for p in CHAIN_RAW_DIR.iterdir() if p.is_dir() and p.name < current_date)
    if not days:
        return {}
    previous_dir = CHAIN_RAW_DIR / days[-1]
    rows: list[dict[str, Any]] = []
    for path in sorted(previous_dir.glob("*.csv")):
        file_rows, _ = _parse_file(path.read_text(encoding="utf-8"), path.name)
        rows.extend(file_rows)
    if not rows:
        return {}
    return {record["symbol"]: record for record in compute_surface_metrics(rows, days[-1])}


def _atm_iv(rows: list[dict[str, Any]], spot: float) -> float:
    if not rows:
        return 0.0
    nearest = sorted(rows, key=lambda row: abs(float(row["strike"]) - spot))[:4]
    return round(sum(float(row["implied_vol"]) for row in nearest) / len(nearest), 6)


def _put_skew_slope(rows: list[dict[str, Any]], spot: float) -> float:
    puts = [
        (math.log(float(row["strike"]) / spot), float(row["implied_vol"]))
        for row in rows
        if row["option_type"] == "put" and 0.80 * spot <= float(row["strike"]) <= 1.0 * spot
    ]
    if len(puts) < 3:
        return 0.0
    xs = [item[0] for item in puts]
    ys = [item[1] for item in puts]
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 0:
        return 0.0
    return round(sum((x - x_mean) * (y - y_mean) for x, y in puts) / denominator, 6)


def _risk_reversal(rows: list[dict[str, Any]], spot: float) -> float:
    otm_puts = [row for row in rows if row["option_type"] == "put" and float(row["strike"]) <= spot * (1 - OTM_BAND / 2)]
    otm_calls = [row for row in rows if row["option_type"] == "call" and float(row["strike"]) >= spot * (1 + OTM_BAND / 2)]
    if not otm_puts or not otm_calls:
        return 0.0
    put_iv = min(otm_puts, key=lambda row: abs(float(row["strike"]) - spot * (1 - OTM_BAND)))["implied_vol"]
    call_iv = min(otm_calls, key=lambda row: abs(float(row["strike"]) - spot * (1 + OTM_BAND)))["implied_vol"]
    return round(float(put_iv) - float(call_iv), 6)


def _median(values: list[Any]) -> Any:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
