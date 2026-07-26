"""Held-out fitness for the scanner-parameter surface (the 3rd evolvable surface).

SCANNER_EVOLVABLE_PARAMETERS is declared the third recursive-improvement
surface but, until this module, had no fitness function - so it could be
tuned only by hand and never plugged into the external evolver. This closes
that gap the honest way.

The question a scanner-threshold change must answer: do the scanner's
DIRECTIONAL detections have out-of-sample edge? We replay the self-contained
directional detectors point-in-time over the HELD-OUT era (strictly after
TRAIN_END, the same split as the foundry and screener), settle each detection
by its forward return in the detection's own direction, and score the mean
EXCESS over the symbol's point-in-time drift - so a detector that merely rides
a name's trend earns nothing. The score is deflated by the number of distinct
detectors that fired (a breadth penalty) and reported on a 0..1 scale where
0.5 is "no edge".

Discipline:
- HELD-OUT only. In-sample scoring is the V1-V7 curve-fit disease.
- Point-in-time: each detection sees only bars[:index+1]; the drift baseline
  for a detection never includes its own forward window.
- Self-contained directional detectors only: cross-sectional/lane detectors
  need context we cannot faithfully reconstruct historically, so scoring them
  here would be dishonest - they are settled forward, not fitted.
- Measure-only: this returns a number; it never edits a threshold. The
  external evolver recommends and an operator applies through gated commit.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any, Mapping, Sequence

from .playbook_scanner import (
    SCANNER_EVOLVABLE_PARAMETERS,
    detect_band_snapback,
    detect_bb_squeeze,
    detect_box_breakout,
    detect_capitulation,
    detect_channel_breakout,
    detect_gap_continuation,
    detect_quality_pullback,
    detect_short_term_reversal,
    detect_ts_momentum,
    detect_vcp,
    detect_52w_high_proximity,
)

TRAIN_END = "2021-12-31"
EVAL_START = "2015-01-01"
FORWARD_HORIZON = 5
EVAL_STRIDE = 5
WARMUP_BARS = 260  # a year-plus so 52w/ts-momentum detectors are live
MIN_EVENTS = 50          # below this the measurement is invalid
MIN_DISTINCT_DETECTORS = 3
SCANNER_FITNESS_VERSION = "dopey-scanner-holdout-fitness-v5"
DRIFT_BASELINE_POLICY_VERSION = "point-in-time-matured-forward-windows-v2"
EVENT_DEDUPLICATION_POLICY_VERSION = "symbol-date-mean-cofire-v1"
SOURCE_HASH_POLICY_VERSION = "selected-symbol-bars-sha256-v1"
SOURCE_HASH_FIELDS = ("date", "open", "high", "low", "close", "volume")

# Self-contained directional detectors, each governed by evolvable thresholds.
# (Direction "either" detectors like vol_coil are excluded - an ungraded
# direction cannot be scored for directional edge.)
SELF_CONTAINED_DIRECTIONAL = {
    "ts_momentum": detect_ts_momentum,
    "channel_breakout": detect_channel_breakout,
    "gap_continuation": detect_gap_continuation,
    "week52_high": detect_52w_high_proximity,
    "box_breakout": detect_box_breakout,
    "vcp": detect_vcp,
    "short_term_reversal": detect_short_term_reversal,
    "quality_pullback": detect_quality_pullback,
    "band_snapback": detect_band_snapback,
    "capitulation": detect_capitulation,
    "bb_squeeze": detect_bb_squeeze,
}


def _era(day: str) -> str:
    return "train" if day <= TRAIN_END else "validation"


def _select_symbols(
    available_symbols: Sequence[str],
    symbol_cap: int,
) -> list[str]:
    """Choose a deterministic hash-spread cross-section, never A-to-M."""

    if symbol_cap <= 0:
        raise ValueError(f"scanner symbol cap must be positive: symbol_cap={symbol_cap}")
    return sorted(
        available_symbols,
        key=lambda symbol: (
            hashlib.sha256(symbol.encode("utf-8")).hexdigest(),
            symbol,
        ),
    )[:symbol_cap]


def _matured_drift_observation(
    closes: Sequence[float],
    dates: Sequence[str],
    current_index: int,
) -> float | None:
    """Return the newest baseline observation knowable at current_index.

    A five-day return originating after ``current_index - FORWARD_HORIZON``
    has not matured yet and cannot enter a point-in-time drift baseline.
    """
    origin_index = current_index - FORWARD_HORIZON
    if origin_index < 0 or current_index >= len(closes):
        return None
    origin_day = dates[origin_index]
    maturity_day = dates[current_index]
    if origin_day < EVAL_START or _era(origin_day) != "validation":
        return None
    if origin_day <= TRAIN_END < maturity_day:
        return None
    entry = float(closes[origin_index])
    if entry <= 0.0:
        return None
    return float(closes[current_index]) / entry - 1.0


def _source_universe_hash(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    symbols: Sequence[str],
) -> str:
    digest = hashlib.sha256()
    for symbol in symbols:
        digest.update(symbol.encode("utf-8"))
        digest.update(b"\x00")
        for bar in bars_by_symbol[symbol]:
            source_row = {
                field: bar.get(field)
                for field in SOURCE_HASH_FIELDS
            }
            digest.update(
                json.dumps(
                    source_row,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            digest.update(b"\n")
    return digest.hexdigest()


def evaluate_scanner_holdout(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    symbol_cap: int = 40,
    stride: int = EVAL_STRIDE,
) -> dict[str, Any]:
    """Settle self-contained directional detections on the held-out era.

    Deterministic: symbols sorted, a fixed cap, a fixed stride. Returns the
    aggregate held-out edge plus per-detector breakdown - never a threshold.
    """
    symbols = _select_symbols(tuple(bars_by_symbol), symbol_cap)
    source_universe_hash = _source_universe_hash(
        bars_by_symbol,
        symbols,
    )
    excesses: list[float] = []
    signed: list[float] = []
    event_excesses: dict[tuple[str, str], list[float]] = {}
    event_signed_returns: dict[tuple[str, str], list[float]] = {}
    per_detector: dict[str, dict[str, float]] = {}
    detector_errors: Counter[str] = Counter()
    matured_drift_observations = 0
    for symbol in symbols:
        bars = list(bars_by_symbol[symbol])
        closes = [float(bar["close"]) for bar in bars]
        dates = [str(bar["date"]) for bar in bars]
        n = len(bars)
        if n < WARMUP_BARS + FORWARD_HORIZON + 10:
            continue
        # point-in-time held-out drift accumulator (never includes the future
        # window of the detection it baselines)
        drift_total = 0.0
        drift_count = 0
        for index in range(WARMUP_BARS, n - FORWARD_HORIZON):
            day = dates[index]
            matured_drift = _matured_drift_observation(
                closes,
                dates,
                index,
            )
            if matured_drift is not None:
                drift_total += matured_drift
                drift_count += 1
                matured_drift_observations += 1
            if day < EVAL_START:
                continue
            # era hygiene: forward window may not straddle the split
            if day <= TRAIN_END < dates[index + FORWARD_HORIZON]:
                continue
            entry = closes[index]
            if entry <= 0.0:
                continue
            forward = closes[index + FORWARD_HORIZON] / entry - 1.0
            if _era(day) == "validation" and index % stride == 0:
                bar_slice = bars[: index + 1]
                drift = drift_total / drift_count if drift_count else 0.0
                for name, detector in SELF_CONTAINED_DIRECTIONAL.items():
                    try:
                        detection = detector(bar_slice, {})
                    except Exception as error:  # noqa: BLE001 - surfaced below
                        detector_errors[
                            f"{name}:{type(error).__name__}"
                        ] += 1
                        continue
                    if not detection:
                        continue
                    direction = detection.get("direction")
                    if direction not in ("long", "short"):
                        continue
                    signed_return = forward if direction == "long" else -forward
                    signed_drift = drift if direction == "long" else -drift
                    excess = signed_return - signed_drift
                    signed.append(signed_return)
                    excesses.append(excess)
                    event_key = (symbol, day)
                    event_excesses.setdefault(event_key, []).append(excess)
                    event_signed_returns.setdefault(event_key, []).append(
                        signed_return
                    )
                    bucket = per_detector.setdefault(name, {"events": 0.0, "excess": 0.0})
                    bucket["events"] += 1
                    bucket["excess"] += excess
    event_deduped_excesses = [
        sum(values) / len(values)
        for _, values in sorted(event_excesses.items())
    ]
    event_deduped_signed = [
        sum(values) / len(values)
        for _, values in sorted(event_signed_returns.items())
    ]
    raw_detector_events = len(excesses)
    events = len(event_deduped_excesses)
    distinct_detectors = len(per_detector)
    detector_exception_count = sum(detector_errors.values())
    sufficient = (
        events >= MIN_EVENTS
        and distinct_detectors >= MIN_DISTINCT_DETECTORS
        and detector_exception_count == 0
    )
    mean_excess = (
        sum(event_deduped_excesses) / events
        if events
        else 0.0
    )
    raw_detector_weighted_mean_excess = (
        sum(excesses) / raw_detector_events
        if raw_detector_events
        else 0.0
    )
    # breadth deflation: reward edge that survives despite testing many
    # detectors, penalize edge that only appears because many were tried
    deflated_excess = (
        mean_excess / (1.0 + math.log10(max(distinct_detectors, 1)))
        if events
        else 0.0
    )
    return {
        "scanner_fitness_version": SCANNER_FITNESS_VERSION,
        "holdout_events": events,
        "holdout_event_unit": "unique_symbol_date",
        "raw_detector_events": raw_detector_events,
        "cofired_detector_event_duplicates": (
            raw_detector_events - events
        ),
        "event_deduplication_policy_version": (
            EVENT_DEDUPLICATION_POLICY_VERSION
        ),
        "distinct_detectors_fired": distinct_detectors,
        "symbols_evaluated": len(symbols),
        "selected_symbols": symbols,
        "symbol_selection_policy": "deterministic_sha256_spread_v1",
        "mean_excess_over_drift": round(mean_excess, 6),
        "event_deduped_mean_excess_over_drift": round(
            mean_excess,
            6,
        ),
        "raw_detector_weighted_mean_excess_over_drift": round(
            raw_detector_weighted_mean_excess,
            6,
        ),
        "deflated_mean_excess": round(deflated_excess, 6),
        "hit_rate": (
            round(
                sum(1 for value in event_deduped_signed if value > 0)
                / events,
                4,
            )
            if events
            else 0.0
        ),
        "raw_detector_weighted_hit_rate": (
            round(
                sum(1 for value in signed if value > 0)
                / raw_detector_events,
                4,
            )
            if raw_detector_events
            else 0.0
        ),
        "per_detector": {
            name: {
                "events": int(bucket["events"]),
                "mean_excess": round(bucket["excess"] / bucket["events"], 6),
            }
            for name, bucket in sorted(per_detector.items())
        },
        "sample_sufficient": sufficient,
        "eval_start": EVAL_START,
        "train_end": TRAIN_END,
        "forward_horizon_days": FORWARD_HORIZON,
        "drift_baseline_policy": (
            "point_in_time_only_fully_matured_forward_windows"
        ),
        "drift_baseline_policy_version": DRIFT_BASELINE_POLICY_VERSION,
        "matured_drift_observation_count": matured_drift_observations,
        "source_universe_hash": source_universe_hash,
        "source_hash_policy_version": SOURCE_HASH_POLICY_VERSION,
        "source_hash_fields": list(SOURCE_HASH_FIELDS),
        "detector_exception_count": detector_exception_count,
        "detector_exception_counts": dict(sorted(detector_errors.items())),
        "detector_exception_budget_status": (
            "within_budget"
            if detector_exception_count == 0
            else "breached_measurement_invalid"
        ),
        "evaluable_parameters": sorted(SCANNER_EVOLVABLE_PARAMETERS),
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
