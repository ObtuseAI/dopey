"""Two-question evaluation of volatility compression - the honest split.

Popular "squeeze" content (and most backtests of it) conflates two claims
that have very different evidence:

Q1 RANGE:     does Bollinger-bandwidth compression predict the SIZE of the
              forward move (|forward return|)? Volatility clustering says it
              should; this is the defensible half.
Q2 DIRECTION: after a CONFIRMED squeeze break (the scanner's exact rule),
              does the break direction predict the SIGNED forward return
              beyond the symbol's unconditional drift? This is the half that
              usually evaporates out of sample.

Discipline:
- per-symbol rank-ICs aggregated across symbols (pooling raw |returns| across
  symbols would let cross-symbol volatility levels fake the correlation);
- train era <= TRAIN_END, validation after, same convention as the foundry;
- circular-shift empirical null for Q1 (preserves autocorrelation, unlike a
  shuffle) - the observed mean IC must clear the null's 95th percentile of
  |mean IC| in BOTH eras with the same sign;
- Q2 events use the SAME evolvable thresholds the live scanner detector uses
  (one parameter surface, no study-only tuning), compared against the
  symbol's own era drift, with explicit sample floors;
- deterministic, paper-only, research-only: this artifact can argue a setup
  DOWN or keep it accruing; it can never promote anything by itself.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from dopey_analysis.indicator_foundry import rank_ic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .playbook_scanner import SCANNER_EVOLVABLE_PARAMETERS, bollinger_band_state

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STUDY_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "strategy_engineering" / "compression_expansion_study.json"
)

EVAL_START = "2015-01-01"
TRAIN_END = "2021-12-31"
EVAL_STRIDE = 3
FORWARD_HORIZON = 5
NULL_SHIFTS = 20
NULL_QUANTILE = 0.95
MIN_SYMBOL_OBS = 60          # per era, before a symbol's IC counts
MIN_SYMBOLS_FOR_CLAIM = 10   # cross-symbol aggregation floor
MIN_DIRECTION_EVENTS = 30    # per era, before Q2 reports a rate at all

STUDY_VERSION = "dopey-compression-expansion-study-v1"


def _closes_volumes_dates(
    bars: Sequence[Mapping[str, Any]],
) -> tuple[list[float], list[float], list[str]]:
    closes = [float(bar["adjusted_close" if "adjusted_close" in bar else "close"]) for bar in bars]
    volumes = [float(bar.get("volume", 0.0)) for bar in bars]
    dates = [str(bar["date"]) for bar in bars]
    return closes, volumes, dates


def compression_depth_series(
    closes: Sequence[float], window: int, band_k: float, lookback: int
) -> list[float]:
    """Depth in [0,1] per index: 1 - percentile rank of bandwidth in its own
    trailing lookback (higher = more compressed). math.nan while warming up."""
    n = len(closes)
    bandwidths = [math.nan] * n
    for index in range(window - 1, n):
        bandwidths[index] = bollinger_band_state(closes, index, window, band_k)[0]
    depths = [math.nan] * n
    for index in range(window - 1 + lookback, n):
        trailing = bandwidths[index - lookback: index]
        current = bandwidths[index]
        if not math.isfinite(current):
            continue
        # midrank tie handling: strictly-below plus half of the ties, so a
        # window of identical bandwidths reads 0.5, not an artifact of <= vs <
        below = sum(1 for value in trailing if value < current)
        ties = sum(1 for value in trailing if value == current)
        depths[index] = 1.0 - (below + 0.5 * ties) / lookback
    return depths


def _volume_z(volumes: Sequence[float], index: int) -> float:
    window = volumes[max(0, index - 20): index]
    if len(window) < 10:
        return math.nan
    mean = sum(window) / len(window)
    std = (sum((value - mean) ** 2 for value in window) / max(len(window) - 1, 1)) ** 0.5
    # epsilon floor mirrors the scanner detector exactly: a spike over
    # dead-flat volume must register as confirmation, not divide to zero
    return (volumes[index] - mean) / (std or 1e-9)


def _band_arrays(
    closes: Sequence[float], window: int, band_k: float
) -> tuple[list[float], list[float], list[float]]:
    """(bandwidths, uppers, lowers) per index, computed once - O(n*window)."""
    n = len(closes)
    bandwidths = [math.nan] * n
    uppers = [math.nan] * n
    lowers = [math.nan] * n
    for index in range(window - 1, n):
        bandwidths[index], uppers[index], lowers[index] = bollinger_band_state(
            closes, index, window, band_k
        )
    return bandwidths, uppers, lowers


def _squeeze_break_at(
    bandwidths: Sequence[float],
    uppers: Sequence[float],
    lowers: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    index: int,
    params: Mapping[str, float],
) -> str | None:
    """The scanner's detect_bb_squeeze rule at a historical index, using
    precomputed band arrays. Cheap gates (band break, volume) run first; the
    trailing-percentile sort only happens for the rare surviving candidates."""
    window = int(params["BB_SQUEEZE_WINDOW"])
    lookback = int(params["BB_SQUEEZE_LOOKBACK"])
    if index < window + lookback + 1:
        return None
    prior_upper = uppers[index - 1]
    prior_lower = lowers[index - 1]
    close = closes[index]
    if not math.isfinite(prior_upper) or not math.isfinite(prior_lower):
        return None
    if close > prior_upper:
        direction = "long"
    elif close < prior_lower:
        direction = "short"
    else:
        return None
    volume_z = _volume_z(volumes, index)
    if not math.isfinite(volume_z) or volume_z < params["BB_SQUEEZE_VOLUME_Z_MIN"]:
        return None
    prior_bandwidth = bandwidths[index - 1]
    trailing = bandwidths[index - 1 - lookback: index - 1]
    if not math.isfinite(prior_bandwidth):
        return None
    ranked = sorted(value for value in trailing if math.isfinite(value))
    if not ranked:
        return None
    squeeze_bar = ranked[max(0, int(len(ranked) * params["BB_SQUEEZE_PCTL"]) - 1)]
    if prior_bandwidth > squeeze_bar:
        return None
    return direction


def squeeze_break_direction(
    closes: Sequence[float],
    volumes: Sequence[float],
    index: int,
    params: Mapping[str, float],
) -> str | None:
    """Replay the scanner's detect_bb_squeeze rule point-in-time at index."""
    window = int(params["BB_SQUEEZE_WINDOW"])
    band_k = float(params["BB_SQUEEZE_BAND_K"])
    bandwidths, uppers, lowers = _band_arrays(closes, window, band_k)
    return _squeeze_break_at(
        bandwidths, uppers, lowers, closes, volumes, index, params
    )


def _era(date: str) -> str:
    return "train" if date <= TRAIN_END else "validation"


def evaluate_range_question(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    params: Mapping[str, float],
) -> dict[str, Any]:
    """Q1: per-symbol rank-IC of compression depth vs |forward return|."""
    window = int(params["BB_SQUEEZE_WINDOW"])
    lookback = int(params["BB_SQUEEZE_LOOKBACK"])
    band_k = float(params["BB_SQUEEZE_BAND_K"])
    per_symbol: dict[str, dict[str, list[float]]] = {}
    for symbol, bars in sorted(bars_by_symbol.items()):
        closes, _volumes, dates = _closes_volumes_dates(bars)
        n = len(closes)
        if n < window + lookback + FORWARD_HORIZON + 10:
            continue
        depths = compression_depth_series(closes, window, band_k, lookback)
        series: dict[str, list[float]] = {
            "train_x": [], "train_y": [], "validation_x": [], "validation_y": [],
        }
        for index in range(window + lookback, n - FORWARD_HORIZON):
            if dates[index] < EVAL_START or index % EVAL_STRIDE != 0:
                continue
            # era hygiene: forward windows may not straddle the boundary
            if dates[index] <= TRAIN_END < dates[index + FORWARD_HORIZON]:
                continue
            depth = depths[index]
            entry = closes[index]
            if not math.isfinite(depth) or entry <= 0.0:
                continue
            forward_abs = abs(closes[index + FORWARD_HORIZON] / entry - 1.0)
            era = _era(dates[index])
            series[f"{era}_x"].append(depth)
            series[f"{era}_y"].append(forward_abs)
        per_symbol[symbol] = series

    def era_summary(era: str) -> dict[str, Any]:
        ics: list[float] = []
        per_symbol_obs: dict[str, int] = {}
        for symbol, series in per_symbol.items():
            xs, ys = series[f"{era}_x"], series[f"{era}_y"]
            if len(xs) < MIN_SYMBOL_OBS:
                continue
            per_symbol_obs[symbol] = len(xs)
            ics.append(rank_ic(xs, ys))
        if len(ics) < MIN_SYMBOLS_FOR_CLAIM:
            return {
                "era_status": "insufficient_symbols",
                "symbols_evaluated": len(ics),
            }
        mean_ic = sum(ics) / len(ics)
        # circular-shift null: shift each symbol's forward series by the same
        # fractional offsets; the null statistic is the mean cross-symbol IC.
        null_means: list[float] = []
        for shift_index in range(NULL_SHIFTS):
            shifted_ics: list[float] = []
            for symbol, series in per_symbol.items():
                xs, ys = series[f"{era}_x"], series[f"{era}_y"]
                if len(xs) < MIN_SYMBOL_OBS:
                    continue
                offset = (shift_index + 1) * len(ys) // (NULL_SHIFTS + 1)
                if offset < FORWARD_HORIZON:
                    continue
                shifted = list(ys[offset:]) + list(ys[:offset])
                shifted_ics.append(rank_ic(xs, shifted))
            if shifted_ics:
                null_means.append(abs(sum(shifted_ics) / len(shifted_ics)))
        null_means.sort()
        null_bar = (
            null_means[min(int(NULL_QUANTILE * len(null_means)), len(null_means) - 1)]
            if null_means
            else math.inf
        )
        return {
            "era_status": "evaluated",
            "symbols_evaluated": len(ics),
            "total_observations": sum(per_symbol_obs.values()),
            "mean_rank_ic": round(mean_ic, 5),
            "positive_ic_share": round(sum(1 for value in ics if value > 0) / len(ics), 4),
            "empirical_null_bar_abs_mean_ic": round(null_bar, 5),
            "cleared_null": abs(mean_ic) >= null_bar,
        }

    train = era_summary("train")
    validation = era_summary("validation")
    both_evaluated = (
        train.get("era_status") == "evaluated" and validation.get("era_status") == "evaluated"
    )
    survives = bool(
        both_evaluated
        and train.get("cleared_null")
        and validation.get("cleared_null")
        and float(train.get("mean_rank_ic", 0.0)) * float(validation.get("mean_rank_ic", 0.0)) > 0
    )
    return {
        "question": "does_compression_predict_forward_range",
        "hypothesized_sign": "positive",
        "train": train,
        "validation": validation,
        "survives_both_eras_same_sign_above_null": survives,
    }


def evaluate_direction_question(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    params: Mapping[str, float],
) -> dict[str, Any]:
    """Q2: signed forward return in the break direction vs the era drift."""
    events: dict[str, list[tuple[float, float]]] = {"train": [], "validation": []}
    drift_sums: dict[str, dict[str, tuple[float, int]]] = {"train": {}, "validation": {}}
    window = int(params["BB_SQUEEZE_WINDOW"])
    lookback = int(params["BB_SQUEEZE_LOOKBACK"])
    band_k = float(params["BB_SQUEEZE_BAND_K"])
    for symbol, bars in sorted(bars_by_symbol.items()):
        closes, volumes, dates = _closes_volumes_dates(bars)
        n = len(closes)
        if n < window + lookback + FORWARD_HORIZON + 10:
            continue
        bandwidths, uppers, lowers = _band_arrays(closes, window, band_k)
        for index in range(window + lookback + 1, n - FORWARD_HORIZON):
            date = dates[index]
            if date < EVAL_START:
                continue
            if date <= TRAIN_END < dates[index + FORWARD_HORIZON]:
                continue
            entry = closes[index]
            if entry <= 0.0:
                continue
            era = _era(date)
            forward = closes[index + FORWARD_HORIZON] / entry - 1.0
            # Event first, THEN accumulate this index into the drift baseline:
            # an event's baseline must be strictly point-in-time and never
            # include its own forward window.
            direction = _squeeze_break_at(
                bandwidths, uppers, lowers, closes, volumes, index, params
            )
            if direction is not None:
                signed = forward if direction == "long" else -forward
                drift_total, drift_count = drift_sums[era].get(symbol, (0.0, 0))
                drift = drift_total / drift_count if drift_count else 0.0
                signed_drift = drift if direction == "long" else -drift
                events[era].append((signed, signed_drift))
            if index % EVAL_STRIDE == 0:
                total, count = drift_sums[era].get(symbol, (0.0, 0))
                drift_sums[era][symbol] = (total + forward, count + 1)

    def era_summary(era: str) -> dict[str, Any]:
        rows = events[era]
        if len(rows) < MIN_DIRECTION_EVENTS:
            return {"era_status": "insufficient_events_accruing", "events": len(rows)}
        signed = [row[0] for row in rows]
        excess = [row[0] - row[1] for row in rows]
        return {
            "era_status": "evaluated",
            "events": len(rows),
            "hit_rate": round(sum(1 for value in signed if value > 0) / len(signed), 4),
            "mean_signed_return": round(sum(signed) / len(signed), 5),
            "mean_excess_over_drift": round(sum(excess) / len(excess), 5),
        }

    train = era_summary("train")
    validation = era_summary("validation")
    return {
        "question": "does_break_direction_predict_signed_return_beyond_drift",
        "baseline": "same_symbol_point_in_time_unconditional_drift_at_the_same_horizon",
        "train": train,
        "validation": validation,
        "directional_claim_supported": bool(
            train.get("era_status") == "evaluated"
            and validation.get("era_status") == "evaluated"
            and float(train.get("mean_excess_over_drift", 0.0)) > 0
            and float(validation.get("mean_excess_over_drift", 0.0)) > 0
        ),
    }


def run_compression_expansion_study(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    if bars_by_symbol is None:
        from .swing_target_discovery import load_ohlcv_history

        bars_by_symbol = load_ohlcv_history(
            REPO_ROOT / "dopey_data" / "history" / "raw"
        )
    params = dict(SCANNER_EVOLVABLE_PARAMETERS)
    range_question = evaluate_range_question(bars_by_symbol, params)
    direction_question = evaluate_direction_question(bars_by_symbol, params)
    summary = {
        "artifact_type": "compression_expansion_study",
        "study_version": STUDY_VERSION,
        "setup_id": "bb_squeeze_breakout",
        "parameters": {
            key: params[key]
            for key in sorted(params)
            if key.startswith("BB_SQUEEZE")
        },
        "parameter_surface_note": "identical evolvable thresholds as the live scanner detector; no study-only tuning",
        "eval_start": EVAL_START,
        "train_end": TRAIN_END,
        "forward_horizon_days": FORWARD_HORIZON,
        "eval_stride_days": EVAL_STRIDE,
        "symbols_available": len(bars_by_symbol),
        "range_question": range_question,
        "direction_question": direction_question,
        "honest_reading": (
            "volatility clustering makes Q1 plausibly positive; Q2 is expected to fail - "
            "if it does, squeeze detections remain range/context research, and any "
            "directional trust must be EARNED through forward settlement, never assumed"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    STUDY_PATH.parent.mkdir(parents=True, exist_ok=True)
    STUDY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
