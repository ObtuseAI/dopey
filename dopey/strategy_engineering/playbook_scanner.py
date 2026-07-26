"""Autonomous playbook scanner: hunt EVERY computable setup archetype, daily.

Walks the whole OHLCV spine against the full strategy playbook — momentum,
mean-reversion, volatility, flow, macro, event families — so no human ever has
to hand-type a setup again. Each detector is small, interpretable, and
point-in-time (uses only bars up to the scan date).

Detections are research flags with the laboratory's standing honesty contract:
``paper_only`` / ``live_blocked`` / ``is_trade_signal=False``. Every setup
family EARNS trust separately through forward settlement; detections feed that
ledger, they do not bypass it. Setups whose data lanes are not wired into the
provided context are reported as typed gaps — never silently skipped, never
faked.

Recursive improvement: ``SCANNER_EVOLVABLE_PARAMETERS`` is the third evolvable
surface (after the exit trio and screen weights). The evolution harness may
hill-climb these thresholds ONLY against held-out-era fitness and only ever
recommends — the scanner cannot tune itself against its own detections.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .playbook import computable_setups, data_gapped_setups, playbook_summary
from .scanner_evolvable_config import evolvable_parameters
from .swing_target_discovery import load_ohlcv_history

Bars = Sequence[Mapping[str, float]]
PLAYBOOK_SCAN_VERSION = "dopey-playbook-scan-v2"
BIG_MOVER_SELECTION_POLICY_VERSION = "big-mover-independent-selection-v1"

# ---------------------------------------------------------------------------
# Evolvable thresholds (recursive-improvement surface; held-out scoring only).
# ---------------------------------------------------------------------------
# Assembled from top-level constants in scanner_evolvable_config so the external
# evolver can address each threshold by name (its AST perturber requires the
# `NAME = <number>` form, which a dict literal does not provide).
SCANNER_EVOLVABLE_PARAMETERS: dict[str, float] = evolvable_parameters()

_P = SCANNER_EVOLVABLE_PARAMETERS  # local alias

ATTENTION_FADE_MIN_Z = 2.0
ATTENTION_FADE_SMA_WINDOW = 50
ATTENTION_FADE_TREND_LOOKBACK = 63
ATTENTION_FADE_MIN_EXTENSION = 0.08
ATTENTION_FADE_MIN_RSI = 70.0


# ---------------------------------------------------------------------------
# Small point-in-time helpers (bars are date-ascending dicts with OHLCV).
# ---------------------------------------------------------------------------

def _closes(bars: Bars) -> list[float]:
    return [float(b["close"]) for b in bars]


def _ret(closes: Sequence[float], lookback: int, skip: int = 0) -> float:
    if len(closes) <= lookback + skip:
        return math.nan
    end = closes[-1 - skip]
    start = closes[-1 - skip - lookback]
    return end / start - 1.0 if start > 0.0 else math.nan


def _sma(values: Sequence[float], window: int) -> float:
    return sum(values[-window:]) / window if len(values) >= window else math.nan


def _stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return math.nan
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) <= period:
        return math.nan
    gains = losses = 0.0
    for prev, cur in zip(closes[-period - 1:-1], closes[-period:]):
        change = cur - prev
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    if losses == 0.0:
        return 100.0 if gains > 0.0 else 50.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def _true_ranges(bars: Bars) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        out.append(max(
            float(cur["high"]) - float(cur["low"]),
            abs(float(cur["high"]) - float(prev["close"])),
            abs(float(cur["low"]) - float(prev["close"])),
        ))
    return out


def _vol_percentile(closes: Sequence[float], window: int = 20, history: int = 252) -> float:
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0.0]
    if len(rets) < window * 2:
        return math.nan
    vols = [_stdev(rets[max(0, i - window):i]) for i in range(window, len(rets) + 1)]
    vols = [v for v in vols[-history:] if not math.isnan(v)]
    if not vols:
        return math.nan
    current = vols[-1]
    return sum(v <= current for v in vols) / len(vols)


def _close_location(bar: Mapping[str, float]) -> float:
    high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
    return (close - low) / (high - low) if high > low else 0.5


def _volume_ratio(bars: Bars, window: int = 20) -> float:
    vols = [float(b.get("volume", 0.0)) for b in bars]
    avg = _sma(vols[:-1], window)
    return vols[-1] / avg if avg and avg > 0.0 else math.nan


# ---------------------------------------------------------------------------
# Detectors — each returns None or {direction, strength, details}.
# ---------------------------------------------------------------------------

def detect_ts_momentum(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    r = _ret(closes, int(_P["TS_MOMENTUM_LOOKBACK"]), int(_P["TS_MOMENTUM_SKIP"]))
    if math.isnan(r) or abs(r) < 0.05:
        return None
    return {"direction": "long" if r > 0 else "short", "strength": min(abs(r), 1.0),
            "details": {"trailing_12_1_return": round(r, 4)}}


def detect_relative_momentum_rank(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    ranks = ctx.get("momentum_ranks")
    symbol = ctx.get("symbol", "")
    if not isinstance(ranks, Mapping) or symbol not in ranks:
        return None
    rank = float(ranks[symbol])  # 0..1 cross-sectional percentile
    if rank >= 0.9:
        return {"direction": "long", "strength": rank, "details": {"momentum_percentile": round(rank, 4)}}
    if rank <= 0.1:
        return {"direction": "short", "strength": 1.0 - rank, "details": {"momentum_percentile": round(rank, 4)}}
    return None


def detect_channel_breakout(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    window = int(_P["CHANNEL_BREAKOUT_WINDOW"])
    if len(bars) < window + 1:
        return None
    highs = [float(b["high"]) for b in bars[-window - 1:-1]]
    lows = [float(b["low"]) for b in bars[-window - 1:-1]]
    close = float(bars[-1]["close"])
    if close > max(highs):
        return {"direction": "long", "strength": min((close / max(highs) - 1.0) * 20.0, 1.0),
                "details": {"channel_high": max(highs), "window": window}}
    if close < min(lows):
        return {"direction": "short", "strength": min((min(lows) / close - 1.0) * 20.0, 1.0),
                "details": {"channel_low": min(lows), "window": window}}
    return None


def detect_gap_continuation(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    if len(bars) < 2:
        return None
    prev, cur = bars[-2], bars[-1]
    prev_close = float(prev["close"])
    gap = float(cur["open"]) / prev_close - 1.0 if prev_close > 0.0 else 0.0
    if abs(gap) < _P["GAP_MIN_PCT"]:
        return None
    loc = _close_location(cur)
    held = (gap > 0 and loc >= 0.6 and float(cur["close"]) > prev_close) or \
           (gap < 0 and loc <= 0.4 and float(cur["close"]) < prev_close)
    if not held:
        return None
    return {"direction": "long" if gap > 0 else "short",
            "strength": min(abs(gap) * 10.0, 1.0),
            "details": {"gap_pct": round(gap * 100.0, 3), "close_location": round(loc, 3)}}


def detect_52w_high_proximity(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    if len(bars) < 60:
        return None
    closes = _closes(bars)
    high_52w = max(float(b["high"]) for b in bars[-252:])
    close = closes[-1]
    proximity = 1.0 - close / high_52w if high_52w > 0.0 else 1.0
    momentum_6m = _ret(closes, min(126, len(closes) - 2))
    if proximity <= _P["W52_HIGH_PROXIMITY"] and momentum_6m > 0.0:
        return {"direction": "long", "strength": min(momentum_6m, 1.0),
                "details": {"pct_below_52w_high": round(proximity * 100.0, 3), "momentum_6m": round(momentum_6m, 4)}}
    return None


def detect_box_breakout(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    window = int(_P["BOX_WINDOW"])
    if len(bars) < window + 21:
        return None
    box = bars[-window - 1:-1]
    box_high = max(float(b["high"]) for b in box)
    box_low = min(float(b["low"]) for b in box)
    if box_low <= 0.0 or (box_high / box_low - 1.0) > _P["BOX_MAX_RANGE_PCT"]:
        return None
    close = float(bars[-1]["close"])
    vol_ratio = _volume_ratio(bars)
    if close > box_high and (math.isnan(vol_ratio) or vol_ratio >= 1.3):
        return {"direction": "long", "strength": min((close / box_high - 1.0) * 25.0 + 0.3, 1.0),
                "details": {"box_high": box_high, "box_range_pct": round((box_high / box_low - 1.0) * 100.0, 3),
                            "volume_ratio": None if math.isnan(vol_ratio) else round(vol_ratio, 2)}}
    return None


def detect_base_breakout(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    if len(bars) < 60:
        return None
    base = bars[-40:-1]
    base_high = max(float(b["high"]) for b in base)
    base_low = min(float(b["low"]) for b in base)
    depth = 1.0 - base_low / base_high if base_high > 0.0 else 1.0
    close = float(bars[-1]["close"])
    vol_ratio = _volume_ratio(bars)
    if depth <= 0.35 and close > base_high and not math.isnan(vol_ratio) and vol_ratio >= 1.5:
        return {"direction": "long", "strength": min(vol_ratio / 3.0, 1.0),
                "details": {"base_depth_pct": round(depth * 100.0, 2), "pivot": base_high,
                            "volume_ratio": round(vol_ratio, 2)}}
    return None


def detect_vcp(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    steps = int(_P["VCP_CONTRACTION_STEPS"])
    seg = 10
    if len(bars) < seg * steps + 5:
        return None
    ranges: list[float] = []
    for i in range(steps):
        chunk = bars[-(steps - i) * seg - 1: -(steps - i - 1) * seg - 1 or None]
        chigh = max(float(b["high"]) for b in chunk)
        clow = min(float(b["low"]) for b in chunk)
        ranges.append(chigh / clow - 1.0 if clow > 0.0 else math.inf)
    contracting = all(b < a for a, b in zip(ranges, ranges[1:]))
    if not contracting:
        return None
    pivot = max(float(b["high"]) for b in bars[-seg - 1:-1])
    close = float(bars[-1]["close"])
    if close > pivot:
        return {"direction": "long", "strength": min(0.4 + (ranges[0] - ranges[-1]), 1.0),
                "details": {"contraction_ranges_pct": [round(r * 100.0, 2) for r in ranges], "pivot": pivot}}
    return None


def detect_pyramid_context(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    trs = _true_ranges(bars[-15:])
    atr = sum(trs) / len(trs) if trs else math.nan
    r20 = _ret(closes, 20)
    if math.isnan(atr) or math.isnan(r20) or atr <= 0.0:
        return None
    move_in_atr = (closes[-1] - closes[-21]) / atr if len(closes) > 21 else 0.0
    if abs(move_in_atr) >= 4.0:
        return {"direction": "long" if move_in_atr > 0 else "short",
                "strength": min(abs(move_in_atr) / 10.0, 1.0),
                "details": {"move_in_atr_units": round(move_in_atr, 2), "context": "add-to-winner conditions present"}}
    return None


def detect_rs_leadership(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    bench = ctx.get("benchmark_closes")
    if not isinstance(bench, Sequence) or len(bench) < 40 or len(bars) < 40:
        return None
    closes = _closes(bars)
    n = min(len(closes), len(bench), 252)
    ratio = [closes[-n + i] / bench[-n + i] for i in range(n) if bench[-n + i] > 0.0]
    if len(ratio) < 40:
        return None
    rs_at_high = ratio[-1] >= max(ratio) * 0.999
    price_at_high = closes[-1] >= max(closes[-n:]) * 0.999
    if rs_at_high and not price_at_high:
        return {"direction": "long", "strength": 0.6,
                "details": {"rs_line_new_high": True, "price_new_high": False}}
    return None


def detect_golden_cross_state(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    if len(closes) < 200:
        return None
    sma50, sma200 = _sma(closes, 50), _sma(closes, 200)
    prev50, prev200 = _sma(closes[:-1], 50), _sma(closes[:-1], 200)
    if any(math.isnan(v) for v in (sma50, sma200, prev50, prev200)):
        return None
    crossed_up = prev50 <= prev200 and sma50 > sma200
    crossed_down = prev50 >= prev200 and sma50 < sma200
    if crossed_up or crossed_down:
        return {"direction": "long" if crossed_up else "short", "strength": 0.5,
                "details": {"event": "golden_cross" if crossed_up else "death_cross"}}
    return None


def detect_crash_guard_state(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    bench = ctx.get("benchmark_closes")
    closes = bench if isinstance(bench, Sequence) and len(bench) >= 60 else _closes(bars)
    if len(closes) < 60:
        return None
    drawdown = closes[-1] / max(closes) - 1.0
    vol_pct = _vol_percentile(list(closes))
    if drawdown <= -0.20 and not math.isnan(vol_pct) and vol_pct >= 0.80:
        return {"direction": "guard", "strength": 1.0,
                "details": {"drawdown_pct": round(drawdown * 100.0, 2), "vol_percentile": round(vol_pct, 3),
                            "action": "suppress momentum entries (crash-rebound state)"}}
    return None


def detect_short_term_reversal(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    r5 = _ret(closes, 5)
    if math.isnan(r5) or abs(r5) < _P["REVERSAL_WEEK_RETURN"]:
        return None
    return {"direction": "short" if r5 > 0 else "long",
            "strength": min(abs(r5) * 5.0, 1.0),
            "details": {"weekly_return_pct": round(r5 * 100.0, 3), "framing": "fade the weekly extreme"}}


def detect_quality_pullback(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    if len(closes) < 200:
        return None
    sma200 = _sma(closes, 200)
    rsi = _rsi(closes)
    if closes[-1] > sma200 and rsi <= _P["PULLBACK_RSI"]:
        return {"direction": "long", "strength": min((_P["PULLBACK_RSI"] - rsi) / _P["PULLBACK_RSI"] + 0.3, 1.0),
                "details": {"rsi_14": round(rsi, 1), "above_200d": True}}
    return None


def detect_band_snapback(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    if len(closes) < 25:
        return None
    sma20 = _sma(closes, 20)
    sd = _stdev(closes[-20:])
    if math.isnan(sma20) or math.isnan(sd) or sd <= 0.0:
        return None
    z = (closes[-1] - sma20) / sd
    trend = abs(_ret(closes, 20)) if not math.isnan(_ret(closes, 20)) else 0.0
    if abs(z) >= _P["SNAPBACK_SIGMA"] and trend < 0.10:  # only fade in non-trending tape
        return {"direction": "short" if z > 0 else "long", "strength": min(abs(z) / 4.0, 1.0),
                "details": {"band_z": round(z, 2), "trend_20d_abs": round(trend, 4)}}
    return None


def detect_long_horizon_reversal(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    r3y = _ret(closes, min(756, len(closes) - 2))
    if math.isnan(r3y):
        return None
    if r3y <= -0.60:
        return {"direction": "long", "strength": min(abs(r3y) / 2.0, 1.0),
                "details": {"trailing_3y_return_pct": round(r3y * 100.0, 1), "framing": "overreaction loser"}}
    if r3y >= 3.0:
        return {"direction": "short", "strength": min(r3y / 6.0, 1.0),
                "details": {"trailing_3y_return_pct": round(r3y * 100.0, 1), "framing": "overreaction winner"}}
    return None


def detect_big_mover_dual(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """Both framings for a big mover: continuation vs reversion — competing
    hypotheses are scored, then only the favored setup is recorded."""
    closes = _closes(bars)
    if len(closes) < 30:
        return None
    latest = closes[-1] / closes[-2] - 1.0 if closes[-2] > 0.0 else 0.0
    mover_floor = ctx.get("mover_return_floor", 0.04)
    if abs(latest) < float(mover_floor):
        return None
    sma20 = _sma(closes, 20)
    trend_aligned = (latest > 0 and closes[-1] > sma20) or (latest < 0 and closes[-1] < sma20)
    loc = _close_location(bars[-1])
    strong_close = loc >= 0.7 if latest > 0 else loc <= 0.3
    vol_ratio = _volume_ratio(bars)
    participation = not math.isnan(vol_ratio) and vol_ratio >= 1.5
    rsi = _rsi(closes)
    stretched = rsi >= 70.0 or rsi <= 30.0

    continuation = 0.34 * trend_aligned + 0.33 * strong_close + 0.33 * participation
    reversion = (0.5 * stretched + 0.5 * (not trend_aligned)) * min(abs(latest) * 10.0, 1.0)
    favored = "momentum_continuation" if continuation >= reversion else "mean_reversion"
    selected_setup_id = (
        "big_mover_momentum"
        if favored == "momentum_continuation"
        else "big_mover_fade"
    )
    return {
        "selected_setup_id": selected_setup_id,
        "direction": ("long" if latest > 0 else "short") if favored == "momentum_continuation"
                     else ("short" if latest > 0 else "long"),
        "strength": round(max(continuation, reversion), 4),
        "details": {
            "move_pct": round(latest * 100.0, 3),
            "competing_hypotheses": True,
            "hypotheses_recorded": 1,
            "continuation_score": round(continuation, 4),
            "reversion_score": round(reversion, 4),
            "favored_framing": favored,
            "selected_setup_id": selected_setup_id,
            "selection_policy_version": BIG_MOVER_SELECTION_POLICY_VERSION,
            "trend_aligned": trend_aligned, "strong_close": strong_close,
            "participation": participation, "rsi_14": round(rsi, 1),
            "settlement_decides": "the independently selected framing is settled",
        },
    }


def detect_capitulation(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    closes = _closes(bars)
    if len(closes) < 60:
        return None
    r10 = _ret(closes, 10)
    vol_pct = _vol_percentile(closes)
    bar = bars[-1]
    day_range = (float(bar["high"]) - float(bar["low"])) / float(bar["low"]) if float(bar["low"]) > 0 else 0.0
    washout = day_range >= 0.05 and _close_location(bar) >= 0.5
    if not math.isnan(r10) and r10 <= -0.15 and not math.isnan(vol_pct) and vol_pct >= _P["CAPITULATION_VOL_PCT"] and washout:
        return {"direction": "long", "strength": min(abs(r10) * 3.0, 1.0),
                "details": {"drop_10d_pct": round(r10 * 100.0, 2), "vol_percentile": round(vol_pct, 3),
                            "washout_day": True}}
    return None


def detect_low_vol_rank(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    ranks = ctx.get("vol_ranks")
    symbol = ctx.get("symbol", "")
    if not isinstance(ranks, Mapping) or symbol not in ranks:
        return None
    rank = float(ranks[symbol])  # 0 = lowest vol
    if rank <= _P["LOW_VOL_QUINTILE"]:
        return {"direction": "long", "strength": 1.0 - rank,
                "details": {"vol_rank_percentile": round(rank, 4)}}
    return None


def detect_vol_coil(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    if len(bars) < 30:
        return None
    ranges = [(float(b["high"]) - float(b["low"])) / float(b["low"]) for b in bars[-20:] if float(b["low"]) > 0.0]
    if len(ranges) < 8:
        return None
    latest7 = ranges[-7:]
    if min(latest7) == latest7[-1] and latest7[-1] <= sorted(ranges)[max(0, int(len(ranges) * _P["COIL_RANGE_PCT"]) - 1)]:
        return {"direction": "either", "strength": 0.5,
                "details": {"nr7": True, "latest_range_pct": round(latest7[-1] * 100.0, 3),
                            "resolution": "direction decided by the break, not predicted"}}
    return None


def bollinger_band_state(
    closes: Sequence[float], index_end: int, window: int, band_k: float
) -> tuple[float, float, float]:
    """(bandwidth, upper, lower) for the window ENDING at index_end inclusive.

    Population std over the window, bands at band_k sigma, bandwidth
    normalized by the mean so it is comparable across price levels. Pure and
    point-in-time: uses only closes[.. index_end].
    """
    segment = closes[index_end - window + 1: index_end + 1]
    mean = sum(segment) / window
    if mean <= 0.0:
        return math.inf, math.inf, -math.inf
    variance = sum((value - mean) ** 2 for value in segment) / window
    std = variance ** 0.5
    upper = mean + band_k * std
    lower = mean - band_k * std
    return (upper - lower) / mean, upper, lower


def detect_bb_squeeze(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    """Squeeze YESTERDAY (bandwidth in the bottom percentile of its own trailing
    window) + a CONFIRMED break of yesterday's band today on above-average
    volume. Yesterday's bands are the reference so the break day cannot widen
    the very bands it must clear. Emits a resolved direction - unlike the
    resting coil, every detection is settleable."""
    window = int(_P["BB_SQUEEZE_WINDOW"])
    lookback = int(_P["BB_SQUEEZE_LOOKBACK"])
    band_k = float(_P["BB_SQUEEZE_BAND_K"])
    if len(bars) < lookback + window + 2:
        return None
    closes = _closes(bars)
    n = len(closes)
    prior_widths = [
        bollinger_band_state(closes, index, window, band_k)[0]
        for index in range(n - 1 - lookback, n - 1)
    ]
    prior_bandwidth, prior_upper, prior_lower = bollinger_band_state(
        closes, n - 2, window, band_k
    )
    ranked = sorted(prior_widths)
    squeeze_bar = ranked[max(0, int(len(ranked) * _P["BB_SQUEEZE_PCTL"]) - 1)]
    if not math.isfinite(prior_bandwidth) or prior_bandwidth > squeeze_bar:
        return None
    volumes = [float(b.get("volume", 0.0)) for b in bars]
    volume_window = volumes[-21:-1]
    volume_mean = sum(volume_window) / len(volume_window)
    volume_std = (
        sum((value - volume_mean) ** 2 for value in volume_window)
        / max(len(volume_window) - 1, 1)
    ) ** 0.5 or 1e-9
    volume_z = (volumes[-1] - volume_mean) / volume_std
    if volume_z < _P["BB_SQUEEZE_VOLUME_Z_MIN"]:
        return None
    close = closes[-1]
    if close > prior_upper:
        direction = "long"
    elif close < prior_lower:
        direction = "short"
    else:
        return None  # still coiled: the resting state belongs to detect_vol_coil
    depth = (squeeze_bar - prior_bandwidth) / squeeze_bar if squeeze_bar > 0 else 0.0
    strength = min(1.0, 0.5 + 0.25 * depth + min(max(volume_z, 0.0), 2.0) / 8.0)
    return {
        "direction": direction,
        "strength": round(strength, 4),
        "details": {
            "prior_bandwidth": round(prior_bandwidth, 6),
            "squeeze_bar_bandwidth": round(squeeze_bar, 6),
            "break_reference": "prior_session_bands",
            "volume_z": round(volume_z, 3),
            "direction_note": "compression forecasts range, not direction; the directional claim is graded by forward settlement",
        },
    }


def detect_turn_of_month(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    date = str(bars[-1].get("date", ""))
    if len(date) != 10:
        return None
    day = int(date[8:10])
    in_window = day >= 28 or day <= 3
    if in_window:
        return {"direction": "long", "strength": 0.2,
                "details": {"calendar_day": day, "framing": "turn-of-month flow window (weak documented edge)"}}
    return None


def detect_tax_loss_window(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    date = str(bars[-1].get("date", ""))
    if len(date) != 10 or date[5:7] not in ("12", "01"):
        return None
    closes = _closes(bars)
    r1y = _ret(closes, min(252, len(closes) - 2))
    if not math.isnan(r1y) and r1y <= -0.30:
        return {"direction": "long", "strength": min(abs(r1y), 1.0),
                "details": {"trailing_1y_return_pct": round(r1y * 100.0, 1),
                            "window": "december_tax_loss" if date[5:7] == "12" else "january_rebound"}}
    return None


def detect_breadth_thrust(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
    series = ctx.get("universe_advance_ratios")  # date-ascending advance ratios
    if not isinstance(series, Sequence) or len(series) < 10:
        return None
    window = list(series[-10:])
    if min(window) < 0.40 and window[-1] > 0.615:
        return {"direction": "long", "strength": 0.8,
                "details": {"thrust_low": round(min(window), 3), "thrust_high": round(window[-1], 3)}}
    return None


# Lane-context detectors: fire only when the macro/flow lane state is provided.
# Lane-state fields that name the specific symbols a state implicates. A state
# carrying one of these fires ONLY for those symbols; a state carrying none is
# market-wide and fires exactly once, on the market proxy (benchmark) symbol —
# otherwise a single macro state floods one detection per scanned symbol.
_LANE_SYMBOL_LIST_FIELDS = (
    "crowded_symbols",
    "extreme_short_flow_symbols",
    "crowded_short_symbols",
    "notable_buying",
    "short_candidates",
    "negative_gex_symbols",
)


def _lane_detector(lane_key: str, description: str) -> Callable[[Bars, Mapping[str, Any]], dict[str, Any] | None]:
    def detect(bars: Bars, ctx: Mapping[str, Any]) -> dict[str, Any] | None:
        state = ctx.get(lane_key)
        if not isinstance(state, Mapping) or not state.get("detected"):
            return None
        symbol = str(ctx.get("symbol", "")).upper()
        implicated: list[str] | None = None
        for field in _LANE_SYMBOL_LIST_FIELDS:
            value = state.get(field)
            if isinstance(value, (list, tuple)):
                implicated = [str(s).upper() for s in value]
                break
        if implicated is not None:
            if symbol not in implicated:
                return None
        elif symbol != str(ctx.get("market_proxy_symbol", "")).upper():
            return None  # market-wide state: one detection, on the proxy only
        return {"direction": str(state.get("direction", "either")),
                "strength": float(state.get("strength", 0.5)),
                "details": {"lane": lane_key, "description": description, **{k: v for k, v in state.items() if k not in ("detected",)}}}
    return detect


detect_vol_regime_shift = _lane_detector("vix_term_structure_state", "VIX term-structure regime flip")
detect_gamma_squeeze_context = _lane_detector("gex_state", "negative dealer gamma squeeze context")
detect_squeeze_context = _lane_detector("short_interest_state", "short-interest squeeze context")
detect_congress_cluster = _lane_detector("congress_state", "clustered congressional purchases")
detect_cot_extreme = _lane_detector("cot_state", "CFTC positioning extreme")
detect_liquidity_state = _lane_detector("liquidity_state", "net-liquidity impulse state")
detect_cross_asset_state = _lane_detector("cross_asset_state", "cross-asset risk-on/off confirmation")
detect_rot_short_context = _lane_detector("fundamental_rot_state", "valuation-excess + fundamental-rot short context")
detect_sector_rotation = _lane_detector("sector_rotation_state", "business-cycle sector rotation state")


def detect_attention_fade(
    bars: Bars, ctx: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Require independent price and regime confirmation before a bearish fade."""
    state = ctx.get("attention_state")
    if not isinstance(state, Mapping) or not state.get("detected"):
        return None
    symbol = str(ctx.get("symbol", "")).strip().upper()
    raw_crowded = state.get("crowded_symbols")
    if not isinstance(raw_crowded, (list, tuple)):
        return None
    crowded = {str(item).strip().upper() for item in raw_crowded}
    if symbol not in crowded:
        return None
    raw_z_by_symbol = state.get("attention_z_by_symbol")
    if not isinstance(raw_z_by_symbol, Mapping):
        return None
    raw_z = raw_z_by_symbol.get(symbol)
    if (
        not isinstance(raw_z, (int, float))
        or isinstance(raw_z, bool)
        or not math.isfinite(float(raw_z))
    ):
        return None
    raw_threshold = state.get("crowded_threshold_z")
    if (
        not isinstance(raw_threshold, (int, float))
        or isinstance(raw_threshold, bool)
        or not math.isfinite(float(raw_threshold))
    ):
        return None
    threshold = max(ATTENTION_FADE_MIN_Z, float(raw_threshold))
    attention_z = float(raw_z)
    if attention_z < threshold:
        return None

    closes = _closes(bars)
    required_bars = max(
        ATTENTION_FADE_SMA_WINDOW, ATTENTION_FADE_TREND_LOOKBACK
    ) + 1
    if len(closes) < required_bars:
        return None
    moving_average = _sma(closes, ATTENTION_FADE_SMA_WINDOW)
    trend_return = _ret(closes, ATTENTION_FADE_TREND_LOOKBACK)
    rsi = _rsi(closes)
    if (
        not math.isfinite(moving_average)
        or moving_average <= 0.0
        or not math.isfinite(trend_return)
        or not math.isfinite(rsi)
    ):
        return None
    extension = closes[-1] / moving_average - 1.0
    price_extension_confirmed = (
        extension >= ATTENTION_FADE_MIN_EXTENSION
        and rsi >= ATTENTION_FADE_MIN_RSI
    )
    trend_regime_confirmed = closes[-1] > moving_average and trend_return > 0.0
    if not price_extension_confirmed or not trend_regime_confirmed:
        return None
    strength = min(
        1.0,
        0.40 * min(attention_z / 4.0, 1.0)
        + 0.35 * min(extension / 0.20, 1.0)
        + 0.25 * min(rsi / 100.0, 1.0),
    )
    return {
        "direction": "short",
        "strength": strength,
        "details": {
            "lane": "attention_state",
            "description": "crowded-attention fade with independent confirmation",
            "attention_z": attention_z,
            "required_attention_z": threshold,
            "price_extension_over_sma50": extension,
            "rsi14": rsi,
            "trend_return_63_sessions": trend_return,
            "price_extension_confirmed": True,
            "trend_regime_confirmed": True,
            "attention_alone_directional": False,
        },
    }


DETECTORS: dict[str, Callable[[Bars, Mapping[str, Any]], dict[str, Any] | None]] = {
    name: obj for name, obj in list(globals().items())
    if name.startswith("detect_") and callable(obj)
}


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------

def _cross_sectional_context(bars_by_symbol: Mapping[str, Bars]) -> dict[str, Any]:
    momentum: dict[str, float] = {}
    vol: dict[str, float] = {}
    advance_flags: dict[str, list[bool]] = {}
    for symbol, bars in bars_by_symbol.items():
        closes = _closes(bars)
        r = _ret(closes, min(252, len(closes) - 22), 21)
        if not math.isnan(r):
            momentum[symbol] = r
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0.0]
        sd = _stdev(rets[-60:]) if len(rets) >= 60 else math.nan
        if not math.isnan(sd):
            vol[symbol] = sd
        advance_flags[symbol] = [closes[i] > closes[i - 1] for i in range(max(1, len(closes) - 12), len(closes))]

    def to_ranks(raw: Mapping[str, float]) -> dict[str, float]:
        ordered = sorted(raw, key=lambda s: raw[s])
        n = max(len(ordered) - 1, 1)
        return {s: i / n for i, s in enumerate(ordered)}

    # Universe advance ratio per recent session (aligned by offset from the end).
    depth = min((len(v) for v in advance_flags.values()), default=0)
    advance_ratios = [
        sum(flags[-depth + i] for flags in advance_flags.values() if len(flags) >= depth) / max(len(advance_flags), 1)
        for i in range(depth)
    ] if depth else []

    proxy_symbol = next(
        (candidate for candidate in ("SPY", "DIA", "QQQ") if candidate in bars_by_symbol),
        sorted(bars_by_symbol)[0] if bars_by_symbol else "",
    )
    benchmark = bars_by_symbol.get(proxy_symbol)
    return {
        "momentum_ranks": to_ranks(momentum),
        "vol_ranks": to_ranks(vol),
        "universe_advance_ratios": advance_ratios,
        "benchmark_closes": _closes(benchmark) if benchmark else None,
        "market_proxy_symbol": proxy_symbol,
    }


def scan_playbook(
    history_root: Path,
    *,
    lane_context: Mapping[str, Any] | None = None,
    max_detections: int = 1_000,
) -> dict[str, Any]:
    """Run every computable playbook setup across the whole spine.

    Deterministic and network-free. ``lane_context`` optionally supplies macro
    and flow lane states; without them, lane-dependent setups report as
    context-unavailable — a typed gap, never a silent skip.
    """
    bars_by_symbol = load_ohlcv_history(Path(history_root))
    summary = playbook_summary()
    if not bars_by_symbol:
        return {
            "artifact_type": "playbook_scan_report",
            "playbook_scan_version": PLAYBOOK_SCAN_VERSION,
            "status": "no_ohlcv_history",
            "playbook": summary,
            "detections": (),
            "profit_or_edge_claimed": False,
            "paper_only": True,
            "live_blocked": True,
            "order_construction_allowed": False,
        }

    shared = _cross_sectional_context(bars_by_symbol)
    if lane_context:
        shared.update(lane_context)

    detections: list[dict[str, Any]] = []
    detector_errors: list[dict[str, str]] = []
    context_unavailable: set[str] = set()
    scannable = computable_setups()
    for setup in scannable:
        detector = DETECTORS.get(setup["computable_detector"])
        if detector is None:
            context_unavailable.add(setup["setup_id"])
            continue
        for symbol, bars in bars_by_symbol.items():
            ctx = {**shared, "symbol": symbol}
            try:
                hit = detector(bars, ctx)
            except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
                detector_errors.append(
                    {
                        "setup_id": str(setup["setup_id"]),
                        "detector": str(setup["computable_detector"]),
                        "symbol": symbol,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
                continue
            if hit is None:
                continue
            selected_setup_id = hit.get("selected_setup_id")
            if (
                selected_setup_id is not None
                and str(selected_setup_id) != str(setup["setup_id"])
            ):
                continue
            body = {
                "setup_id": setup["setup_id"],
                "family": setup["family"],
                "symbol": symbol,
                "as_of_date": str(bars[-1].get("date", "")),
                "direction": hit["direction"],
                "strength": round(float(hit["strength"]), 4),
                "horizon_days": setup["horizon_days"],
                "lineage": setup["lineage"],
                "details": hit["details"],
                "source_playbook_scan_version": PLAYBOOK_SCAN_VERSION,
                "independently_selected_setup": selected_setup_id is not None,
                "framing_selection_policy_version": (
                    BIG_MOVER_SELECTION_POLICY_VERSION
                    if selected_setup_id is not None
                    else None
                ),
                "evidence_status": setup["evidence_status"],
                "is_trade_signal": False,
                "paper_only": True,
                "live_blocked": True,
            }
            detections.append({"detection_id": f"playbook-detection:{canonical_hash(body)[:24]}", **body})

    ranked = sorted(detections, key=lambda d: (-float(d["strength"]), str(d["setup_id"]), str(d["symbol"])))
    ranked = ranked[: max(max_detections, 0)]

    per_family: dict[str, int] = {}
    per_setup: dict[str, int] = {}
    for d in ranked:
        per_family[d["family"]] = per_family.get(d["family"], 0) + 1
        per_setup[d["setup_id"]] = per_setup.get(d["setup_id"], 0) + 1

    return {
        "artifact_type": "playbook_scan_report",
        "playbook_scan_version": PLAYBOOK_SCAN_VERSION,
        "status": "complete",
        "playbook": summary,
        "symbols_scanned": len(bars_by_symbol),
        "setups_scanned": len(scannable),
        "setups_data_gapped": tuple(s["setup_id"] for s in data_gapped_setups()),
        "detector_context_unavailable": tuple(sorted(context_unavailable)),
        "detector_error_count": len(detector_errors),
        "detector_errors": tuple(detector_errors),
        "detection_count": len(ranked),
        "detections_per_family": per_family,
        "detections_per_setup": per_setup,
        "detections": tuple(ranked),
        "evolvable_parameters": dict(SCANNER_EVOLVABLE_PARAMETERS),
        "evolvable_by": "held_out_era_fitness_only_recommend_never_apply",
        # Honesty invariants.
        "every_setup_family_earns_trust_via_forward_settlement": True,
        "profit_or_edge_claimed": False,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
