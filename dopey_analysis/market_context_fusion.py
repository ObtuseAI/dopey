"""Fuse quote-derived positioning, sector regime, and vol-psychology context.

One artifact per symbol answering: is this a favorable moment to own premium?

- gamma regime (real dealer positioning): short-gamma (negative GEX / spot
  below flip) amplifies moves -> favorable for long premium; long-gamma pins
  price -> theta bleeds. Deterministic MM-hedging mechanics, measured not
  guessed.
- sector regime: each symbol's sector ETF relative strength vs SPY (20d) -
  own calls in leading sectors, puts in lagging ones, else no-trade bias.
- vol psychology: VRP state (fear premium rich = long premium headwind) and
  put/call OI extremes (crowd positioning) + surface tears if archive depth
  allows.
- verdict: entry_bias in {favorable, neutral, unfavorable} per strategy side,
  consumed by the forward paper walk as an entry filter. Context, not signal;
  not edge evidence. Paper-only, live-blocked.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dopey_data.history_validator import validate_default_history_dataset
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTEXT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "market_context"
ENTRY_CONTEXT_PATH = CONTEXT_ARTIFACT_DIR / "entry_context_fusion.jsonl"
CONTEXT_SUMMARY_PATH = CONTEXT_ARTIFACT_DIR / "market_context_fusion_summary.json"
POSITIONING_METRICS_PATH = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics" / "real_chain_positioning_metrics.jsonl"
VRP_SERIES_PATH = REPO_ROOT / "artifacts" / "dopey" / "market_structure" / "variance_risk_premium_series.jsonl"
SURFACE_TEARS_PATH = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics" / "vol_surface_tears.jsonl"
NEWS_INTELLIGENCE_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "news_intelligence.json"
CROSS_ASSET_REGIME_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "cross_asset_regime.json"
NEWS_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "news_context_manifest.json"
CROSS_ASSET_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "cross_asset_context_manifest.json"

SECTOR_MAP: dict[str, str] = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "GOOGL": "XLK", "META": "XLK",
    "AMZN": "XLY", "TSLA": "XLY", "NFLX": "XLY",
    "JPM": "XLF", "BAC": "XLF",
    "SPY": "SPY", "QQQ": "XLK", "IWM": "SPY", "DIA": "SPY",
    "XLF": "XLF", "XLK": "XLK", "XLE": "XLE", "XLY": "XLY", "XLI": "XLI",
    "XLU": "XLU", "XLP": "XLP", "XLV": "XLV",
    # liquid-ETF cohort (2026-07-23): each maps to itself so its entry bias
    # uses its own 20d relative strength vs SPY; missing history stays neutral.
    "XLB": "XLB", "XLC": "XLC", "XLRE": "XLRE", "GLD": "GLD", "TLT": "TLT",
    "EEM": "EEM", "EFA": "EFA", "HYG": "HYG", "SMH": "SMH", "XBI": "XBI",
    "ARKK": "ARKK", "USO": "USO",
}
RELATIVE_STRENGTH_LOOKBACK = 20
SECTOR_LEAD_THRESHOLD = 0.01
PC_OI_EXTREME_HIGH = 2.0
PC_OI_EXTREME_LOW = 0.5
EARNINGS_CALENDAR_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "earnings_calendar"
# Covers the forward walk's realistic worst-case holding span (3 marking sessions
# plus weekend/stale-mark gaps) - the window a print must clear, NOT the option tenor.
EARNINGS_BLACKOUT_DAYS = 10
GEOPOLITICAL_EVENT_COUNT_FOR_ENERGY_SHORT_VETO = 3
ENERGY_SUPPLY_EVENT_COUNT_FOR_ENERGY_SHORT_VETO = 2


def _earnings_blackout_symbols(reference_date: str) -> tuple[set[str], bool]:
    """(symbols with earnings inside the blackout window, anchor_missing flag).
    The window is the IV-crush kill zone for long premium held through the print."""
    if not EARNINGS_CALENDAR_DIR.exists():
        return set(), False
    files = sorted(EARNINGS_CALENDAR_DIR.glob("*_earnings.csv"))
    if not files:
        return set(), False
    try:
        anchor = date.fromisoformat(reference_date)
    except ValueError:
        # fail VISIBLE: no blackout can be computed without an anchor date
        return set(), True
    blocked: set[str] = set()
    for record in csv.DictReader(files[-1].read_text(encoding="utf-8").splitlines()):
        try:
            earnings = date.fromisoformat(str(record.get("earnings_date", "")))
        except ValueError:
            continue
        if anchor <= earnings <= anchor + timedelta(days=EARNINGS_BLACKOUT_DAYS):
            blocked.add(str(record.get("symbol", "")))
    return blocked, False


def run_market_context_fusion() -> dict[str, Any]:
    positioning = _load_jsonl(POSITIONING_METRICS_PATH)
    if not positioning:
        summary = {
            "artifact_type": "market_context_fusion_summary",
            "context_status": "blocked_missing_positioning_metrics",
            "paper_only": True,
            "live_blocked": True,
        }
        _write_json(CONTEXT_SUMMARY_PATH, summary)
        return summary
    dataset = validate_default_history_dataset()
    sector_strength = (
        _sector_relative_strength(dataset["bars_loaded"]) if dataset["dataset_status"] == "valid_real_dataset" else {}
    )
    anchor_date = str(positioning[0].get("snapshot_date", ""))
    vrp_rich, vrp_state = _latest_vrp_state(anchor_date)
    tears_by_symbol = {record["symbol"] for record in _load_jsonl(SURFACE_TEARS_PATH)}
    earnings_blocked, earnings_anchor_missing = _earnings_blackout_symbols(anchor_date)
    external_context = _external_context_state(anchor_date)
    contexts: list[dict[str, Any]] = []
    for metric in positioning:
        symbol = str(metric["symbol"])
        gex = float(metric["total_gex_dollar_per_pct"])
        flip = metric.get("gamma_flip_strike")
        spot = float(metric["underlying_spot"])
        short_gamma = gex < 0.0 or (flip is not None and spot < float(flip))
        sector = SECTOR_MAP.get(symbol, "SPY")
        sector_rs = sector_strength.get(sector, 0.0)
        pc_oi_raw = metric.get("put_call_oi_ratio")
        pc_oi = float(pc_oi_raw) if pc_oi_raw is not None else None
        if pc_oi is None:
            crowd_state = "crowd_undefined_no_call_oi"
        else:
            crowd_state = (
                "crowd_heavy_puts" if pc_oi >= PC_OI_EXTREME_HIGH
                else ("crowd_heavy_calls" if pc_oi <= PC_OI_EXTREME_LOW else "balanced")
            )
        in_earnings_blackout = symbol in earnings_blocked
        call_bias = "unfavorable" if in_earnings_blackout else _bias(short_gamma, sector_rs >= SECTOR_LEAD_THRESHOLD, vrp_rich)
        put_bias = "unfavorable" if in_earnings_blackout else _bias(short_gamma, sector_rs <= -SECTOR_LEAD_THRESHOLD, vrp_rich)
        put_veto_reasons = _external_entry_veto_reasons(sector, "long_put", external_context)
        if put_veto_reasons:
            put_bias = "unfavorable"
        contexts.append(
            {
                "artifact_type": "entry_context_fusion",
                "symbol": symbol,
                "snapshot_date": metric["snapshot_date"],
                "gamma_regime": "short_gamma_amplifying" if short_gamma else "long_gamma_pinning",
                "total_gex_dollar_per_pct": gex,
                "gamma_flip_strike": flip,
                "sector_etf": sector,
                "sector_relative_strength_20d": round(sector_rs, 6),
                "sector_regime": "leading" if sector_rs >= SECTOR_LEAD_THRESHOLD else ("lagging" if sector_rs <= -SECTOR_LEAD_THRESHOLD else "inline"),
                "vrp_rich_market": vrp_rich,
                "put_call_oi_ratio": pc_oi,
                "crowd_state": crowd_state,
                "surface_tear_present": symbol in tears_by_symbol,
                "earnings_blackout": in_earnings_blackout,
                "external_context_status": external_context["status"],
                "geopolitical_conflict_event_count_7d": external_context["geopolitical_conflict_event_count_7d"],
                "energy_supply_event_count_7d": external_context["energy_supply_event_count_7d"],
                "energy_theme_context_score": external_context["energy_theme_context_score"],
                "long_call_veto_reasons": [],
                "long_put_veto_reasons": list(put_veto_reasons),
                "long_call_entry_bias": call_bias,
                "long_put_entry_bias": put_bias,
                "quote_derived": True,
                "not_edge_evidence": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    summary = {
        "artifact_type": "market_context_fusion_summary",
        "context_status": "market_context_fusion_computed",
        "symbols_covered": len(contexts),
        "short_gamma_count": sum(1 for record in contexts if record["gamma_regime"] == "short_gamma_amplifying"),
        "earnings_blackout_count": sum(1 for record in contexts if record["earnings_blackout"]),
        "earnings_anchor_missing": earnings_anchor_missing,
        "external_context_status": external_context["status"],
        "energy_short_veto_count": sum(1 for record in contexts if record["long_put_veto_reasons"]),
        "vrp_rich_market": vrp_rich,
        "vrp_state": vrp_state,
        "favorable_call_contexts": sum(1 for record in contexts if record["long_call_entry_bias"] == "favorable"),
        "favorable_put_contexts": sum(1 for record in contexts if record["long_put_entry_bias"] == "favorable"),
        "quote_derived": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    CONTEXT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(ENTRY_CONTEXT_PATH, contexts)
    _write_json(CONTEXT_SUMMARY_PATH, summary)
    return summary


def _bias(short_gamma: bool, sector_aligned: bool, vrp_rich: bool) -> str:
    if vrp_rich:
        return "unfavorable"
    if short_gamma and sector_aligned:
        return "favorable"
    if sector_aligned or short_gamma:
        return "neutral"
    return "unfavorable"


def _external_entry_veto_reasons(
    sector: str,
    strategy: str,
    external_context: dict[str, Any],
) -> tuple[str, ...]:
    if sector != "XLE" or strategy != "long_put":
        return ()
    reasons: list[str] = []
    if external_context["status"] != "complete":
        reasons.append("energy_short_external_context_unavailable")
    geopolitical_count = int(external_context["geopolitical_conflict_event_count_7d"])
    energy_supply_count = int(external_context["energy_supply_event_count_7d"])
    energy_score = float(external_context["energy_theme_context_score"])
    elevated_event_risk = (
        geopolitical_count >= GEOPOLITICAL_EVENT_COUNT_FOR_ENERGY_SHORT_VETO
        or energy_supply_count >= ENERGY_SUPPLY_EVENT_COUNT_FOR_ENERGY_SHORT_VETO
    )
    if elevated_event_risk and energy_score >= 0.0:
        reasons.append("geopolitical_or_supply_risk_opposes_energy_short")
    return tuple(reasons)


def _external_context_state(anchor_date: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "blocked_missing_external_context",
        "geopolitical_conflict_event_count_7d": 0,
        "energy_supply_event_count_7d": 0,
        "energy_theme_context_score": 0.0,
    }
    required_paths = (
        NEWS_INTELLIGENCE_PATH,
        CROSS_ASSET_REGIME_PATH,
        NEWS_MANIFEST_PATH,
        CROSS_ASSET_MANIFEST_PATH,
    )
    if not all(path.exists() for path in required_paths):
        return base
    news_manifest = _load_json(NEWS_MANIFEST_PATH)
    cross_manifest = _load_json(CROSS_ASSET_MANIFEST_PATH)
    news = _load_json(NEWS_INTELLIGENCE_PATH)
    cross_asset = _load_json(CROSS_ASSET_REGIME_PATH)
    try:
        news_date = datetime.fromisoformat(str(news["decision_time"]).replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except (KeyError, ValueError):
        return {**base, "status": "blocked_news_context_timestamp_invalid"}
    cross_date = str(cross_asset.get("latest_source_date_max", ""))
    if news_date != anchor_date or cross_date != anchor_date:
        return {**base, "status": "blocked_external_context_not_aligned_to_chain_snapshot"}
    category_counts = news.get("category_counts_7d", {})
    if not isinstance(category_counts, dict):
        raise TypeError(f"news category counts must be an object: path={NEWS_INTELLIGENCE_PATH}")
    theme_scores = cross_asset.get("theme_context_scores", {})
    if not isinstance(theme_scores, dict):
        raise TypeError(f"cross-asset theme scores must be an object: path={CROSS_ASSET_REGIME_PATH}")
    observed = {
        "status": "complete",
        "geopolitical_conflict_event_count_7d": int(category_counts.get("geopolitical_conflict", 0)),
        "energy_supply_event_count_7d": int(category_counts.get("energy_supply", 0)),
        "energy_theme_context_score": float(theme_scores.get("energy", 0.0)),
    }
    if str(news_manifest.get("pipeline_status", "")) != "complete":
        return {**observed, "status": "blocked_news_manifest_not_complete"}
    if str(cross_manifest.get("dataset_status", "")) != "complete":
        return {**observed, "status": "blocked_cross_asset_manifest_not_complete"}
    return observed


def _sector_relative_strength(bars: list[dict[str, Any]]) -> dict[str, float]:
    closes: dict[str, list[float]] = {}
    for bar in bars:
        closes.setdefault(str(bar["symbol"]), []).append(float(bar["adjusted_close"]))
    spy = closes.get("SPY", [])
    if len(spy) < RELATIVE_STRENGTH_LOOKBACK + 1:
        return {}
    spy_return = spy[-1] / spy[-(RELATIVE_STRENGTH_LOOKBACK + 1)] - 1.0
    strength: dict[str, float] = {"SPY": 0.0}
    for sector in (
        "XLF", "XLK", "XLE", "XLY", "XLI", "XLU", "XLP", "XLV",
        "XLB", "XLC", "XLRE", "GLD", "TLT", "EEM", "EFA", "HYG",
        "SMH", "XBI", "ARKK", "USO",
    ):
        series = closes.get(sector, [])
        if len(series) >= RELATIVE_STRENGTH_LOOKBACK + 1:
            sector_return = series[-1] / series[-(RELATIVE_STRENGTH_LOOKBACK + 1)] - 1.0
            strength[sector] = sector_return - spy_return
    return strength


def _latest_vrp_state(anchor_date: str) -> tuple[bool, str]:
    """(vrp_rich for bias purposes, visibility state). Missing or stale VRP data
    must be VISIBLE as such - a silent False reads as "premium not expensive"."""
    records = _load_jsonl(VRP_SERIES_PATH)
    if not records:
        return False, "missing_or_stale"
    latest = records[-1]
    latest_date = str(latest.get("date", ""))
    try:
        if anchor_date and latest_date and (date.fromisoformat(anchor_date) - date.fromisoformat(latest_date)).days > 7:
            return False, "missing_or_stale"
    except ValueError:
        return False, "missing_or_stale"
    return (True, "rich") if latest.get("vrp_rich") is True else (False, "not_rich")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"JSON artifact must be an object: path={path}")
    return parsed


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
