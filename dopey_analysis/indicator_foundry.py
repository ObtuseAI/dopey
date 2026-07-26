"""Indicator foundry: classic technical battery + meta-discovery of new indicators.

Two layers, both leak-free over the validated real history spine:

1. BATTERY - a core battery of classic indicators implemented deterministically:
   RSI, EMA-cross spread, MACD histogram, Bollinger %B, ATR-normalized momentum,
   stochastic %K, Williams %R, rate-of-change, OBV slope, volume z-score,
   close-location value, and realized-vol ratio. Latest values are published as a
   per-symbol dashboard artifact.

2. FOUNDRY (the meta layer) - composes standardized primitives into candidate
   composite indicators via an enumerated grammar (differences, products,
   divergences across lookbacks), then evaluates every candidate's information
   coefficient (rank correlation with forward 5-day returns) on train
   (2015-2021) and validation (2022-2026) eras separately. Promotion demands
   same-sign IC above a bar that RISES with the number of candidates tested
   (multiple-testing discipline). Survivors are published as research inputs -
   explicitly NOT edge claims; they earn signal-family status only through the
   full honest lane. Paper-only, live-blocked.
"""
from __future__ import annotations

import json
import math
from array import array
from pathlib import Path
from typing import Any, Callable

from dopey_data.history_validator import validate_default_history_dataset
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
FOUNDRY_DIR = REPO_ROOT / "artifacts" / "dopey" / "indicator_foundry"
DASHBOARD_PATH = FOUNDRY_DIR / "classic_indicator_dashboard.jsonl"
CANDIDATE_TABLE_PATH = FOUNDRY_DIR / "candidate_ic_table.jsonl"
PROMOTED_PATH = FOUNDRY_DIR / "promoted_indicators.jsonl"
FOUNDRY_SUMMARY_PATH = FOUNDRY_DIR / "indicator_foundry_summary.json"
FOUNDRY_REPORT_PATH = REPORTS_DIR / "DOPEY_INDICATOR_FOUNDRY_REPORT.md"

TRAIN_END = "2021-12-31"
FORWARD_HORIZON = 5
EVAL_START = "2015-01-01"
EVAL_STRIDE = 3
BASE_IC_BAR = 0.03
CONTEXT_ONLY = {"VIX"}
NULL_SHIFTS = 20  # circular-shift empirical null (preserves autocorrelation, unlike a shuffle)
NULL_QUANTILE = 0.95
MIN_QUOTE_OBS = 120  # quote-derived lane stays "accruing" until this many joinable obs exist


# ---------- classic primitives (each: (closes, highs, lows, volumes, i) -> float) ----------

def _ema(values: list[float], span: int, index: int) -> float:
    alpha = 2.0 / (span + 1.0)
    start = max(index - 4 * span, 0)
    ema = values[start]
    for position in range(start + 1, index + 1):
        ema = alpha * values[position] + (1 - alpha) * ema
    return ema


def rsi(closes: list[float], index: int, period: int = 14) -> float:
    if index < period:
        return 50.0
    gains = losses = 0.0
    for position in range(index - period + 1, index + 1):
        change = closes[position] - closes[position - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    if losses == 0.0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def ema_cross_spread(closes: list[float], index: int, fast: int = 20, slow: int = 50) -> float:
    slow_value = _ema(closes, slow, index)
    return (_ema(closes, fast, index) - slow_value) / slow_value if slow_value else 0.0


def macd_histogram(closes: list[float], index: int) -> float:
    macd_line = _ema(closes, 12, index) - _ema(closes, 26, index)
    # signal approximated as EMA9 of macd over trailing window
    trail = [(_ema(closes, 12, position) - _ema(closes, 26, position)) for position in range(max(index - 20, 0), index + 1)]
    return macd_line - _ema(trail, 9, len(trail) - 1)


def bollinger_pct_b(closes: list[float], index: int, period: int = 20) -> float:
    window = closes[max(index - period + 1, 0) : index + 1]
    mean = sum(window) / len(window)
    deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / len(window)) or 1e-9
    return (closes[index] - (mean - 2 * deviation)) / (4 * deviation)


def atr_momentum(closes: list[float], highs: list[float], lows: list[float], index: int, period: int = 14) -> float:
    if index < period + 1:
        return 0.0
    true_ranges = [
        max(highs[position] - lows[position], abs(highs[position] - closes[position - 1]), abs(lows[position] - closes[position - 1]))
        for position in range(index - period + 1, index + 1)
    ]
    atr = sum(true_ranges) / period or 1e-9
    return (closes[index] - closes[index - period]) / atr


def stochastic_k(closes: list[float], highs: list[float], lows: list[float], index: int, period: int = 14) -> float:
    low = min(lows[max(index - period + 1, 0) : index + 1])
    high = max(highs[max(index - period + 1, 0) : index + 1])
    return (closes[index] - low) / (high - low) * 100.0 if high > low else 50.0


def obv_slope(closes: list[float], volumes: list[float], index: int, period: int = 20) -> float:
    obv = 0.0
    series = []
    for position in range(max(index - period, 1), index + 1):
        obv += volumes[position] if closes[position] > closes[position - 1] else (-volumes[position] if closes[position] < closes[position - 1] else 0.0)
        series.append(obv)
    if len(series) < 2:
        return 0.0
    scale = (sum(volumes[max(index - period, 0) : index + 1]) / period) or 1e-9
    return (series[-1] - series[0]) / (len(series) * scale)


def volume_z(volumes: list[float], index: int, period: int = 20) -> float:
    window = volumes[max(index - period, 0) : index]
    if len(window) < 5:
        return 0.0
    mean = sum(window) / len(window)
    deviation = math.sqrt(sum((value - mean) ** 2 for value in window) / max(len(window) - 1, 1)) or 1e-9
    return (volumes[index] - mean) / deviation


def close_location_value(closes: list[float], highs: list[float], lows: list[float], index: int) -> float:
    high, low = highs[index], lows[index]
    return ((closes[index] - low) - (high - closes[index])) / (high - low) if high > low else 0.0


def realized_vol_ratio(closes: list[float], index: int, short: int = 5, long: int = 20) -> float:
    def vol(period: int) -> float:
        window = closes[max(index - period, 0) : index + 1]
        returns = [math.log(later / earlier) for earlier, later in zip(window, window[1:]) if earlier > 0 and later > 0]
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        return math.sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))

    long_vol = vol(long) or 1e-9
    return vol(short) / long_vol


def rate_of_change(closes: list[float], index: int, period: int = 10) -> float:
    if index < period or closes[index - period] == 0:
        return 0.0
    return closes[index] / closes[index - period] - 1.0


def williams_r(closes: list[float], highs: list[float], lows: list[float], index: int, period: int = 14) -> float:
    high = max(highs[max(index - period + 1, 0) : index + 1])
    low = min(lows[max(index - period + 1, 0) : index + 1])
    return (high - closes[index]) / (high - low) * -100.0 if high > low else -50.0


PRIMITIVES: dict[str, Callable[..., float]] = {
    "rsi14": lambda c, h, l, v, i: rsi(c, i, 14),
    "ema20_50_spread": lambda c, h, l, v, i: ema_cross_spread(c, i, 20, 50),
    "macd_hist": lambda c, h, l, v, i: macd_histogram(c, i),
    "boll_pct_b": lambda c, h, l, v, i: bollinger_pct_b(c, i, 20),
    "atr_momentum14": lambda c, h, l, v, i: atr_momentum(c, h, l, i, 14),
    "stoch_k14": lambda c, h, l, v, i: stochastic_k(c, h, l, i, 14),
    "obv_slope20": lambda c, h, l, v, i: obv_slope(c, v, i, 20),
    "volume_z20": lambda c, h, l, v, i: volume_z(v, i, 20),
    "clv": lambda c, h, l, v, i: close_location_value(c, h, l, i),
    "rv_ratio_5_20": lambda c, h, l, v, i: realized_vol_ratio(c, i, 5, 20),
    "roc10": lambda c, h, l, v, i: rate_of_change(c, i, 10),
    "williams_r14": lambda c, h, l, v, i: williams_r(c, h, l, i, 14),
}


# ---------- the meta layer ----------

def generate_candidates() -> list[dict[str, Any]]:
    """Enumerate composite indicator candidates from standardized primitives."""
    names = sorted(PRIMITIVES)
    candidates: list[dict[str, Any]] = []
    for first_index, first in enumerate(names):
        for second in names[first_index + 1 :]:
            candidates.append({"candidate_id": f"diff({first},{second})", "op": "diff", "inputs": [first, second]})
            candidates.append({"candidate_id": f"prod({first},{second})", "op": "prod", "inputs": [first, second]})
    for name in names:
        candidates.append({"candidate_id": f"lagdiv({name},5)", "op": "lagdiv", "inputs": [name], "lag": 5})
    return candidates


def _standardize(series: list[float], fit_flags: list[bool] | None = None) -> list[float]:
    """Z-score a series. When fit_flags is given, the mean/std are FIT ON THE
    FLAGGED (train-era) VALUES ONLY and applied everywhere: full-sample fitting
    would leak validation-era distribution parameters into train-era composite
    orderings (diff/prod outputs depend on the fitted scales)."""
    if fit_flags is None:
        fit_flags = [True] * len(series)
    finite = [value for value, flagged in zip(series, fit_flags) if flagged and math.isfinite(value)]
    if len(finite) < 10:
        return [0.0] * len(series)
    mean = sum(finite) / len(finite)
    deviation = math.sqrt(sum((value - mean) ** 2 for value in finite) / max(len(finite) - 1, 1)) or 1e-9
    return [(value - mean) / deviation if math.isfinite(value) else 0.0 for value in series]


def candidate_series(candidate: dict[str, Any], primitive_series: dict[str, list[float]]) -> list[float]:
    if candidate["op"] == "diff":
        first, second = (primitive_series[name] for name in candidate["inputs"])
        return [a - b for a, b in zip(first, second)]
    if candidate["op"] == "prod":
        first, second = (primitive_series[name] for name in candidate["inputs"])
        return [a * b for a, b in zip(first, second)]
    lag = int(candidate.get("lag", 5))
    base = primitive_series[candidate["inputs"][0]]
    return [base[index] - base[index - lag] if index >= lag else 0.0 for index in range(len(base))]


def rank_ic(values: list[float], forwards: list[float]) -> float:
    """Spearman rank correlation between indicator values and forward returns."""
    pairs = [(value, forward) for value, forward in zip(values, forwards) if math.isfinite(value) and math.isfinite(forward)]
    if len(pairs) < 30:
        return 0.0
    def ranks(sequence: list[float]) -> list[float]:
        # average ranks for ties (proper Spearman; arbitrary tie ranks add noise)
        order = sorted(range(len(sequence)), key=lambda position: sequence[position])
        result = [0.0] * len(sequence)
        index = 0
        while index < len(order):
            tie_end = index
            while tie_end + 1 < len(order) and sequence[order[tie_end + 1]] == sequence[order[index]]:
                tie_end += 1
            average = (index + tie_end) / 2.0
            for position in order[index : tie_end + 1]:
                result[position] = average
            index = tie_end + 1
        return result
    x_ranks = ranks([pair[0] for pair in pairs])
    y_ranks = ranks([pair[1] for pair in pairs])
    x_mean = sum(x_ranks) / len(x_ranks)
    y_mean = sum(y_ranks) / len(y_ranks)
    covariance = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_ranks, y_ranks))
    x_var = math.sqrt(sum((x - x_mean) ** 2 for x in x_ranks))
    y_var = math.sqrt(sum((y - y_mean) ** 2 for y in y_ranks))
    return covariance / (x_var * y_var) if x_var > 0 and y_var > 0 else 0.0


def empirical_null_bar(
    candidate_values: dict[str, list[float]], forwards: list[float], shifts: int = NULL_SHIFTS
) -> float:
    """Familywise empirical null via deterministic circular shifts of the forward
    returns. A shift destroys any feature-return relationship while preserving both
    marginals AND autocorrelation (which a shuffle would destroy, making the null
    too easy). The bar is the NULL_QUANTILE of max|IC| across all candidates per
    shift - the White's-reality-check statistic for this candidate family."""
    n = len(forwards)
    if n < 60 or not candidate_values:
        return 0.0
    max_ics: list[float] = []
    for shift_index in range(shifts):
        offset = (shift_index + 1) * n // (shifts + 1)
        if offset < FORWARD_HORIZON * 2:
            continue
        shifted = forwards[offset:] + forwards[:offset]
        max_ics.append(max(abs(rank_ic(values, shifted)) for values in candidate_values.values()))
    if not max_ics:
        return 0.0
    max_ics.sort()
    position = min(int(NULL_QUANTILE * len(max_ics)), len(max_ics) - 1)
    return max_ics[position]


QUOTE_ATM_BAND = 0.02
QUOTE_TARGET_DTE = 30


def quote_features_for_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Per-symbol quote-derived primitives from one validated snapshot's rows:
    put/call OI ratio, ATM IV at the ~30-DTE tenor, and put-minus-call IV skew."""
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_symbol.setdefault(str(row["symbol"]), []).append(row)
    features: dict[str, dict[str, float]] = {}
    for symbol, symbol_rows in by_symbol.items():
        dtes = sorted({int(row["dte_calendar"]) for row in symbol_rows}, key=lambda dte: abs(dte - QUOTE_TARGET_DTE))
        tenor_rows = [row for row in symbol_rows if int(row["dte_calendar"]) == dtes[0]] if dtes else []
        call_oi = sum(int(row["open_interest"]) for row in symbol_rows if row["option_type"] == "call")
        put_oi = sum(int(row["open_interest"]) for row in symbol_rows if row["option_type"] == "put")
        spot = float(symbol_rows[0]["underlying_spot"])
        atm = [row for row in tenor_rows if spot > 0 and abs(float(row["strike"]) - spot) / spot <= QUOTE_ATM_BAND]
        call_ivs = [float(row["implied_vol"]) for row in tenor_rows if row["option_type"] == "call"]
        put_ivs = [float(row["implied_vol"]) for row in tenor_rows if row["option_type"] == "put"]
        record: dict[str, float] = {}
        if call_oi > 0:
            record["pc_oi"] = put_oi / call_oi
        if atm:
            record["atm_iv"] = sum(float(row["implied_vol"]) for row in atm) / len(atm)
        if call_ivs and put_ivs:
            record["iv_skew_put_minus_call"] = sum(put_ivs) / len(put_ivs) - sum(call_ivs) / len(call_ivs)
        if record:
            features[symbol] = record
    return features


def evaluate_quote_derived_lane(compact_by_symbol: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The foundry's growth frontier: quote-derived primitives (positioning, IV,
    skew) joined to forward returns as the chain archive accrues. Reports honest
    insufficient_sample until MIN_QUOTE_OBS joinable observations exist; after
    that, the same rank-IC discipline applies. Never fabricates history.

    Takes the compact per-symbol spine view ({"dates": [...], "adjusted_closes":
    [...]}) rather than raw row dicts - the join needs nothing else, and the raw
    rows are deliberately freed before this runs (memory discipline)."""
    from dopey_options.chain_snapshot_loader import list_chain_snapshot_dates, load_chain_snapshot

    date_index: dict[str, dict[str, int]] = {}
    for symbol, series in compact_by_symbol.items():
        date_index[symbol] = {date: position for position, date in enumerate(series["dates"])}
    values_by_feature: dict[str, list[float]] = {}
    forwards: list[float] = []
    snapshot_days = 0
    for snapshot_date in list_chain_snapshot_dates():
        snapshot = load_chain_snapshot(snapshot_date)
        if snapshot["chain_snapshot_status"] != "real_chain_snapshot_validated":
            continue
        snapshot_days += 1
        for symbol, feature_record in quote_features_for_rows(snapshot["rows"]).items():
            closes = compact_by_symbol.get(symbol, {}).get("adjusted_closes", [])
            position = date_index.get(symbol, {}).get(snapshot_date)
            if position is None or position + FORWARD_HORIZON >= len(closes):
                continue  # spine hasn't grown past this snapshot yet - not joinable
            entry = float(closes[position])
            future = float(closes[position + FORWARD_HORIZON])
            if entry <= 0:
                continue
            forwards.append(future / entry - 1.0)
            for name in ("pc_oi", "atm_iv", "iv_skew_put_minus_call"):
                values_by_feature.setdefault(name, []).append(float(feature_record.get(name, math.nan)))
    joinable = len(forwards)
    lane: dict[str, Any] = {
        "snapshot_days_in_archive": snapshot_days,
        "joinable_observations": joinable,
        "min_observations_required": MIN_QUOTE_OBS,
        "quote_primitives": sorted(values_by_feature),
        "not_edge_evidence": True,
    }
    if joinable < MIN_QUOTE_OBS:
        lane["quote_lane_status"] = "insufficient_sample_accruing"
        return lane
    bar = BASE_IC_BAR * (1.0 + math.log10(max(len(values_by_feature), 10)) / 2.0)
    lane["quote_lane_status"] = "quote_lane_evaluated"
    lane["ic_bar"] = round(bar, 5)
    lane["feature_ics"] = {
        name: round(rank_ic(values, forwards), 5) for name, values in sorted(values_by_feature.items())
    }
    lane["cleared_bar"] = sorted(name for name, ic_value in lane["feature_ics"].items() if abs(ic_value) >= bar)
    return lane


def evaluate_macro_derived_lane(compact_by_symbol: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Market-wide macro primitives (VIX term-structure slope, SKEW, VIX level)
    joined to SPY forward returns. A common-per-date feature can only ever test
    TIMING, so the join is SPY-only - pooling across symbols would fake sample
    size. Same rank-IC discipline and accrual gate as the quote lane."""
    from dopey_market_intake.macro_context_gate import load_macro_lanes

    loaded = load_macro_lanes()
    if loaded["macro_status"] != "macro_lanes_validated":
        return {"macro_lane_status": loaded["macro_status"], "joinable_observations": 0}
    by_date: dict[str, dict[str, float]] = {}
    for row in loaded["lanes"].get("vol_term_structure.csv", []):
        try:
            by_date.setdefault(row["date"], {})[row["symbol"]] = float(row["close"])
        except (KeyError, ValueError):
            continue
    spy = compact_by_symbol.get("SPY", {"dates": [], "adjusted_closes": []})
    spy_closes = spy["adjusted_closes"]
    spy_index = {date: position for position, date in enumerate(spy["dates"])}
    features: dict[str, list[float]] = {"vix_ts_slope_9d_3m": [], "skew_level": [], "vix_level": []}
    forwards: list[float] = []
    for day in sorted(by_date):
        record = by_date[day]
        position = spy_index.get(day)
        if position is None or position + FORWARD_HORIZON >= len(spy_closes) or position % EVAL_STRIDE != 0:
            continue
        short_end, long_end = record.get("VIX9D"), record.get("VIX3M")
        skew, vix = record.get("SKEW"), record.get("VIX")
        if not short_end or not long_end or skew is None or vix is None:
            continue
        entry = float(spy_closes[position])
        future = float(spy_closes[position + FORWARD_HORIZON])
        if entry <= 0:
            continue
        forwards.append(future / entry - 1.0)
        features["vix_ts_slope_9d_3m"].append((long_end - short_end) / short_end)
        features["skew_level"].append(skew)
        features["vix_level"].append(vix)
    joinable = len(forwards)
    lane: dict[str, Any] = {
        "joinable_observations": joinable,
        "min_observations_required": MIN_QUOTE_OBS,
        "macro_primitives": sorted(features),
        "join_policy": "spy_only_market_wide_features_test_timing_not_selection",
        "not_edge_evidence": True,
    }
    if joinable < MIN_QUOTE_OBS:
        lane["macro_lane_status"] = "insufficient_sample_accruing"
        return lane
    bar = BASE_IC_BAR * (1.0 + math.log10(max(len(features), 10)) / 2.0)
    lane["macro_lane_status"] = "macro_lane_evaluated"
    lane["ic_bar"] = round(bar, 5)
    lane["feature_ics"] = {name: round(rank_ic(values, forwards), 5) for name, values in sorted(features.items())}
    lane["cleared_bar"] = sorted(name for name, ic_value in lane["feature_ics"].items() if abs(ic_value) >= bar)
    return lane


def evaluate_attention_lane(compact_by_symbol: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Crowd-attention primitive (Wikimedia pageview z-score) joined per
    (date, symbol) to forward returns - the honest test of 'overhyped' as a
    put-side hypothesis. Same accrual gate and IC discipline as the other lanes."""
    from dopey_market_intake.macro_context_gate import ATTENTION_Z_WINDOW, load_macro_lanes

    loaded = load_macro_lanes()
    if loaded["macro_status"] != "macro_lanes_validated":
        return {"attention_lane_status": loaded["macro_status"], "joinable_observations": 0}
    series: dict[str, list[tuple[str, float]]] = {}
    for row in loaded["lanes"].get("wikipedia_pageviews.csv", []):
        try:
            series.setdefault(row["symbol"], []).append((row["date"], float(row["views"])))
        except (KeyError, ValueError):
            continue
    values: list[float] = []
    forwards: list[float] = []
    for symbol, points in sorted(series.items()):
        points.sort()
        spine = compact_by_symbol.get(symbol, {"dates": [], "adjusted_closes": []})
        closes = spine["adjusted_closes"]
        date_index = {date: position for position, date in enumerate(spine["dates"])}
        views = [value for _, value in points]
        for offset, (day, _) in enumerate(points):
            if offset < 20:
                continue
            window = views[max(offset - ATTENTION_Z_WINDOW, 0) : offset]
            mean = sum(window) / len(window)
            deviation = (sum((value - mean) ** 2 for value in window) / max(len(window) - 1, 1)) ** 0.5 or 1e-9
            position = date_index.get(day)
            if position is None or position + FORWARD_HORIZON >= len(closes):
                continue
            entry = float(closes[position])
            future = float(closes[position + FORWARD_HORIZON])
            if entry <= 0:
                continue
            values.append((views[offset] - mean) / deviation)
            forwards.append(future / entry - 1.0)
    lane: dict[str, Any] = {
        "joinable_observations": len(forwards),
        "min_observations_required": MIN_QUOTE_OBS,
        "primitive": "wikipedia_attention_z60",
        "hypothesis": "crowded_attention_predicts_negative_forward_returns_put_side",
        "not_edge_evidence": True,
    }
    if len(forwards) < MIN_QUOTE_OBS:
        lane["attention_lane_status"] = "insufficient_sample_accruing"
        return lane
    lane["attention_lane_status"] = "attention_lane_evaluated"
    ic_value = rank_ic(values, forwards)
    lane["attention_ic"] = round(ic_value, 5)
    lane["ic_bar"] = round(BASE_IC_BAR, 5)
    lane["cleared_bar"] = abs(ic_value) >= BASE_IC_BAR
    return lane


def run_indicator_foundry() -> dict[str, Any]:
    dataset = validate_default_history_dataset()
    if dataset["dataset_status"] != "valid_real_dataset":
        summary = {"artifact_type": "indicator_foundry_summary", "foundry_status": "blocked_missing_valid_real_history", "paper_only": True, "live_blocked": True}
        _write_json(FOUNDRY_SUMMARY_PATH, summary)
        return summary
    # Memory discipline: the full-universe spine as per-row dicts is the single
    # largest allocation in any supervisor stage (>1GB at 200 symbols). Group,
    # then release each symbol's row dicts as soon as its compact per-symbol
    # arrays exist - the derived lanes only ever need dates + adjusted closes.
    bars_loaded = dataset.pop("bars_loaded")
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for bar in bars_loaded:
        bars_by_symbol.setdefault(str(bar["symbol"]), []).append(bar)
    bars_loaded.clear()
    candidates = generate_candidates()
    train_values: dict[str, array] = {c["candidate_id"]: array("d") for c in candidates}
    train_forwards: array = array("d")
    valid_values: dict[str, array] = {c["candidate_id"]: array("d") for c in candidates}
    valid_forwards: array = array("d")
    dashboard: list[dict[str, Any]] = []
    compact_by_symbol: dict[str, dict[str, Any]] = {}
    for symbol, rows in sorted(bars_by_symbol.items()):
        if symbol in CONTEXT_ONLY:
            rows.clear()
            continue
        rows.sort(key=lambda row: str(row["date"]))
        closes = [float(row["adjusted_close"]) for row in rows]
        ratio = [float(row["adjusted_close"]) / float(row["close"]) if float(row["close"]) > 0 else 1.0 for row in rows]
        highs = [float(row["high"]) * r for row, r in zip(rows, ratio)]
        lows = [float(row["low"]) * r for row, r in zip(rows, ratio)]
        volumes = [float(row["volume"]) for row in rows]
        dates = [str(row["date"]) for row in rows]
        compact_by_symbol[symbol] = {"dates": dates, "adjusted_closes": closes}
        eval_indexes = [
            index for index in range(60, len(rows) - FORWARD_HORIZON)
            if dates[index] >= EVAL_START and index % EVAL_STRIDE == 0
            # era hygiene: drop observations whose forward window STRADDLES the
            # train/validation boundary (feature in train, return partly in validation)
            and not (dates[index] <= TRAIN_END < dates[index + FORWARD_HORIZON])
        ]
        is_train = [dates[index] <= TRAIN_END for index in eval_indexes]
        primitive_series = {
            name: _standardize([func(closes, highs, lows, volumes, index) for index in eval_indexes], is_train)
            for name, func in PRIMITIVES.items()
        }
        forwards = [closes[index + FORWARD_HORIZON] / closes[index] - 1.0 for index in eval_indexes]
        for candidate in candidates:
            series = candidate_series(candidate, primitive_series)
            for value, forward, in_train in zip(series, forwards, is_train):
                (train_values if in_train else valid_values)[candidate["candidate_id"]].append(value)
        for forward, in_train in zip(forwards, is_train):
            (train_forwards if in_train else valid_forwards).append(forward)
        latest = len(rows) - 1
        dashboard.append({
            "artifact_type": "classic_indicator_dashboard",
            "symbol": symbol,
            "date": dates[latest],
            **{name: round(func(closes, highs, lows, volumes, latest), 6) for name, func in PRIMITIVES.items()},
            "paper_only": True, "live_blocked": True,
        })
        rows.clear()  # release this symbol's row dicts; compact arrays carry on
    ic_bar = BASE_IC_BAR * (1.0 + math.log10(max(len(candidates), 10)) / 2.0)
    empirical_bar = empirical_null_bar(train_values, train_forwards)
    promotion_bar = max(ic_bar, empirical_bar)
    table: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    for candidate in candidates:
        train_ic = rank_ic(train_values[candidate["candidate_id"]], train_forwards)
        valid_ic = rank_ic(valid_values[candidate["candidate_id"]], valid_forwards)
        survives = abs(train_ic) >= promotion_bar and abs(valid_ic) >= promotion_bar and (train_ic * valid_ic) > 0
        record = {
            "artifact_type": "indicator_candidate_ic",
            "candidate_id": candidate["candidate_id"],
            "train_ic": round(train_ic, 5),
            "validation_ic": round(valid_ic, 5),
            "ic_bar": round(ic_bar, 5),
            "empirical_null_bar": round(empirical_bar, 5),
            "same_sign_both_eras": (train_ic * valid_ic) > 0,
            "promoted": survives,
            "not_edge_evidence": True,
            "paper_only": True, "live_blocked": True,
        }
        table.append(record)
        if survives:
            promoted.append(record)
    quote_lane = evaluate_quote_derived_lane(compact_by_symbol)
    macro_lane = evaluate_macro_derived_lane(compact_by_symbol)
    attention_lane = evaluate_attention_lane(compact_by_symbol)
    summary = {
        "artifact_type": "indicator_foundry_summary",
        "foundry_status": "indicator_foundry_complete",
        "classic_primitive_count": len(PRIMITIVES),
        "candidates_generated": len(candidates),
        "ic_bar_after_multiple_testing_scaling": round(ic_bar, 5),
        "empirical_null_bar_circular_shift": round(empirical_bar, 5),
        "null_shifts": NULL_SHIFTS,
        "train_observations": len(train_forwards),
        "validation_observations": len(valid_forwards),
        "promoted_count": len(promoted),
        "promoted_ids": [record["candidate_id"] for record in promoted],
        "promotion_rule": "abs(IC) >= max(analytic bar, circular-shift empirical null bar) in BOTH eras with same sign; survivors are research inputs, not edge claims",
        "era_hygiene": "train-era-only standardization; boundary-straddling forward windows excluded",
        "quote_derived_lane": quote_lane,
        "macro_derived_lane": macro_lane,
        "attention_derived_lane": attention_lane,
        "forward_horizon_days": FORWARD_HORIZON,
        "not_edge_evidence": True,
        "paper_only": True, "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    FOUNDRY_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(DASHBOARD_PATH, dashboard)
    _write_jsonl(CANDIDATE_TABLE_PATH, table)
    _write_jsonl(PROMOTED_PATH, promoted)
    _write_json(FOUNDRY_SUMMARY_PATH, summary)
    _write_report(summary, promoted)
    return summary


def _write_report(summary: dict[str, Any], promoted: list[dict[str, Any]]) -> None:
    lines = [
        "# DOPEY Indicator Foundry Report",
        "",
        "## Classic Battery",
        f"- {summary['classic_primitive_count']} primitives computed leak-free per symbol; latest values in the dashboard artifact.",
        "",
        "## Meta-Discovery",
        f"- candidates generated: `{summary['candidates_generated']}` (enumerated composition grammar)",
        f"- IC bar (scaled for multiple testing): `{summary['ic_bar_after_multiple_testing_scaling']}` | "
        f"empirical circular-shift null bar: `{summary['empirical_null_bar_circular_shift']}`",
        f"- era hygiene: `{summary['era_hygiene']}`",
        f"- observations: train `{summary['train_observations']}` / validation `{summary['validation_observations']}`",
        f"- PROMOTED: `{summary['promoted_count']}`",
        "",
        "## Quote-Derived Lane (grows with the chain archive)",
        f"- status: `{summary['quote_derived_lane'].get('quote_lane_status', '')}` | "
        f"joinable obs: `{summary['quote_derived_lane'].get('joinable_observations', 0)}`"
        f"/`{summary['quote_derived_lane'].get('min_observations_required', 0)}` | "
        f"archive days: `{summary['quote_derived_lane'].get('snapshot_days_in_archive', 0)}`",
        "",
        "## Macro-Derived Lane (VIX term structure / SKEW, SPY-only join)",
        f"- status: `{summary['macro_derived_lane'].get('macro_lane_status', '')}` | "
        f"joinable obs: `{summary['macro_derived_lane'].get('joinable_observations', 0)}`"
        f"/`{summary['macro_derived_lane'].get('min_observations_required', 0)}`",
        f"- feature ICs: `{summary['macro_derived_lane'].get('feature_ics', {})}` | "
        f"cleared bar: `{summary['macro_derived_lane'].get('cleared_bar', [])}`",
    ]
    for record in sorted(promoted, key=lambda item: -abs(item["validation_ic"])):
        lines.append(f"  - `{record['candidate_id']}`: train IC `{record['train_ic']}`, validation IC `{record['validation_ic']}`")
    lines += [
        "",
        "## Honest Limits",
        "- IC survival across eras is a research signal, not tradable edge; promoted indicators",
        "  must still pass the full honest lane (costs, baselines, truth layer) as signal families.",
        "- paper_only: true; live_blocked: true.",
    ]
    FOUNDRY_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")
