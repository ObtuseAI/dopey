"""Swing-target discovery: fuse option-outcome tails with signed stock movers.

Two inputs the trader named, combined:

1. **Option winners and losers** (from ``option_roi_discovery``) mark where
   convexity paid or failed and where volatility and attention concentrated.
2. **The biggest stock gainers and decliners** are ranked independently so a
   one-direction tape cannot hide the opposite tail.

A name that is *both* a big mover and stretched into an overbought/oversold
extreme — and that *also* appears in either option-outcome tail — receives the
highest research priority. Each mover is examined under competing continuation
and mean-reversion hypotheses rather than being forced into a fade.

Honesty contract
----------------
Overbought/oversold mean reversion is a *hypothesis that often fails* — a
stretched name can keep running. Nothing here is a trade signal or an edge
claim. Targets are ``paper_only`` / ``live_blocked`` research flags that must
clear the same forward-evaluation gate (leakage, random-entry baseline, PBO,
deflated Sharpe, held-out era, forward paper settlement) before they mean
anything. No order-construction capability exists in this module.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .option_roi_discovery import discover_option_roi_strategies

MIN_BARS = 30
RSI_PERIOD = 14
SMA_WINDOW = 20
ZSCORE_WINDOW = 20
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
ZSCORE_EXTREME = 2.0


def _f(value: object) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return math.nan
    return out


def load_ohlcv_history(history_root: Path) -> dict[str, list[dict[str, float]]]:
    """Load ``<root>/<SYMBOL>.csv`` daily bars, date-sorted, per symbol."""
    bars_by_symbol: dict[str, list[dict[str, float]]] = {}
    root = Path(history_root)
    if not root.is_dir():
        return bars_by_symbol
    for csv_path in sorted(root.glob("*.csv")):
        try:
            text = csv_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rows: list[dict[str, float]] = []
        reader = csv.DictReader(text.splitlines())
        for row in reader:
            close = _f(row.get("close"))
            if not (close > 0.0) or not row.get("date"):
                continue
            rows.append(
                {
                    "date": row["date"].strip(),  # type: ignore[dict-item]
                    "open": _f(row.get("open")),
                    "high": _f(row.get("high")),
                    "low": _f(row.get("low")),
                    "close": close,
                    "volume": _f(row.get("volume")),
                }
            )
        if len(rows) >= MIN_BARS:
            rows.sort(key=lambda r: r["date"])
            bars_by_symbol[csv_path.stem.upper()] = rows
    return bars_by_symbol


def _rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> float:
    if len(closes) <= period:
        return math.nan
    gains, losses = 0.0, 0.0
    for prev, cur in zip(closes[-period - 1 : -1], closes[-period:]):
        change = cur - prev
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _sma(values: Sequence[float], window: int) -> float:
    if len(values) < window:
        return math.nan
    return sum(values[-window:]) / window


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return math.nan
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def compute_mover_metrics(bars: Sequence[Mapping[str, float]]) -> dict[str, float] | None:
    """Latest-session stretch metrics. None if history is too short."""
    if len(bars) < MIN_BARS:
        return None
    closes = [float(b["close"]) for b in bars]
    latest_close = closes[-1]
    prev_close = closes[-2]
    latest_return = latest_close / prev_close - 1.0 if prev_close > 0.0 else 0.0

    returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0.0]
    window_returns = returns[-ZSCORE_WINDOW:]
    mean_ret = sum(window_returns) / len(window_returns) if window_returns else 0.0
    sd_ret = _stddev(window_returns)
    return_zscore = (latest_return - mean_ret) / sd_ret if sd_ret and sd_ret > 0.0 else 0.0

    sma20 = _sma(closes, SMA_WINDOW)
    pct_from_sma = (latest_close / sma20 - 1.0) if sma20 and sma20 > 0.0 else 0.0
    sd_close = _stddev(closes[-SMA_WINDOW:])
    bollinger_pct_b = (
        (latest_close - (sma20 - 2.0 * sd_close)) / (4.0 * sd_close)
        if sd_close and sd_close > 0.0 and not math.isnan(sma20)
        else 0.5
    )
    rsi = _rsi(closes)

    metrics = {
        "latest_close": latest_close,
        "latest_return": latest_return,
        "return_zscore": return_zscore,
        "rsi_14": rsi,
        "pct_from_sma20": pct_from_sma,
        "bollinger_pct_b": bollinger_pct_b,
    }
    if any(not math.isfinite(v) for v in metrics.values()):
        return None
    return metrics


def _mover_record(
    symbol: str,
    metrics: Mapping[str, float],
    direction: str,
    rank: int,
) -> dict[str, Any]:
    if direction not in {"up", "down"}:
        raise ValueError(f"direction must be up or down: direction={direction}")
    return {
        "symbol": symbol,
        "direction": direction,
        "direction_rank": rank,
        "latest_close": round(float(metrics["latest_close"]), 6),
        "latest_return_pct": round(float(metrics["latest_return"]) * 100.0, 4),
        "return_zscore": round(float(metrics["return_zscore"]), 4),
        "rsi_14": round(float(metrics["rsi_14"]), 2),
        "pct_from_sma20": round(float(metrics["pct_from_sma20"]) * 100.0, 4),
        "bollinger_pct_b": round(float(metrics["bollinger_pct_b"]), 4),
        "is_trade_signal": False,
    }


def rank_symbol_movers(
    metrics_by_symbol: Mapping[str, Mapping[str, float]],
    biggest_mover_count: int,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Return balanced signed tails: largest gainers and largest decliners."""
    if biggest_mover_count < 0:
        raise ValueError(
            f"biggest_mover_count must be non-negative: biggest_mover_count={biggest_mover_count}"
        )
    side_limit = 0 if biggest_mover_count == 0 else max(1, biggest_mover_count // 2)
    gainers = sorted(
        (
            (symbol, metrics)
            for symbol, metrics in metrics_by_symbol.items()
            if float(metrics["latest_return"]) > 0.0
        ),
        key=lambda item: (-float(item[1]["latest_return"]), item[0]),
    )[:side_limit]
    decliners = sorted(
        (
            (symbol, metrics)
            for symbol, metrics in metrics_by_symbol.items()
            if float(metrics["latest_return"]) < 0.0
        ),
        key=lambda item: (float(item[1]["latest_return"]), item[0]),
    )[:side_limit]
    return (
        tuple(
            _mover_record(symbol, metrics, "up", index)
            for index, (symbol, metrics) in enumerate(gainers, start=1)
        ),
        tuple(
            _mover_record(symbol, metrics, "down", index)
            for index, (symbol, metrics) in enumerate(decliners, start=1)
        ),
    )


def _stretch_state(metrics: Mapping[str, float]) -> str:
    overbought = (
        metrics["rsi_14"] >= RSI_OVERBOUGHT
        or metrics["bollinger_pct_b"] >= 1.0
        or metrics["return_zscore"] >= ZSCORE_EXTREME
    )
    oversold = (
        metrics["rsi_14"] <= RSI_OVERSOLD
        or metrics["bollinger_pct_b"] <= 0.0
        or metrics["return_zscore"] <= -ZSCORE_EXTREME
    )
    if overbought and not oversold:
        return "overbought"
    if oversold and not overbought:
        return "oversold"
    return "neutral"


def _stretch_score(metrics: Mapping[str, float], state: str) -> float:
    """Interpretable 0..1 extremity, NOT a probability of profit."""
    rsi = metrics["rsi_14"]
    rsi_component = (
        (rsi - RSI_OVERBOUGHT) / (100.0 - RSI_OVERBOUGHT)
        if state == "overbought"
        else (RSI_OVERSOLD - rsi) / RSI_OVERSOLD
        if state == "oversold"
        else 0.0
    )
    z_component = min(abs(metrics["return_zscore"]) / 4.0, 1.0)
    return round(max(0.0, min(1.0, 0.5 * max(rsi_component, 0.0) + 0.5 * z_component)), 6)


def _continuation_evidence(
    bars: Sequence[Mapping[str, float]],
    metrics: Mapping[str, float],
) -> dict[str, Any]:
    """Evidence the latest big move CONTINUES rather than reverts.

    Documented continuation conditions (gap-and-go, O'Neil follow-through,
    turtle adds): the move aligns with the standing trend, closes strong in
    its own direction, and carries real participation.
    """
    latest = float(metrics["latest_return"])
    trend_aligned = (latest > 0.0 and metrics["pct_from_sma20"] > 0.0) or (
        latest < 0.0 and metrics["pct_from_sma20"] < 0.0
    )
    bar = bars[-1]
    high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
    loc = (close - low) / (high - low) if high > low else 0.5
    strong_close = loc >= 0.7 if latest > 0.0 else loc <= 0.3
    volumes = [float(b.get("volume", 0.0)) for b in bars]
    avg_vol = sum(volumes[-21:-1]) / 20.0 if len(volumes) >= 21 else 0.0
    participation = avg_vol > 0.0 and volumes[-1] / avg_vol >= 1.5
    score = round(0.4 * trend_aligned + 0.3 * strong_close + 0.3 * participation, 6)
    return {
        "trend_aligned": trend_aligned,
        "strong_close": strong_close,
        "close_location": round(loc, 4),
        "participation": participation,
        "continuation_score": score,
    }


def discover_swing_targets(
    history_root: Path,
    *,
    chains_root: Path | None = None,
    biggest_mover_count: int = 40,
    max_targets: int = 25,
) -> dict[str, Any]:
    """Fuse biggest movers + option winners -> overbought/oversold swing targets.

    Deterministic, network-free, promotion-ineligible.
    """
    bars_by_symbol = load_ohlcv_history(Path(history_root))
    if not bars_by_symbol:
        return {
            "artifact_type": "swing_target_discovery_report",
            "swing_target_discovery_version": "dopey-swing-target-discovery-v2",
            "status": "no_ohlcv_history",
            "top_gainers": (),
            "top_decliners": (),
            "biggest_movers": (),
            "swing_targets": (),
            "profit_or_edge_claimed": False,
            "paper_only": True,
            "live_blocked": True,
            "order_construction_allowed": False,
        }

    # 1. Per-symbol stretch metrics.
    metrics_by_symbol: dict[str, dict[str, float]] = {}
    for symbol, bars in bars_by_symbol.items():
        metrics = compute_mover_metrics(bars)
        if metrics is not None:
            metrics_by_symbol[symbol] = metrics

    # 2. Signed leaderboards. An absolute-value board can silently fill with a
    #    single direction; balanced tails guarantee that gainers and decliners
    #    are both inspected every run.
    top_gainers, top_decliners = rank_symbol_movers(metrics_by_symbol, biggest_mover_count)
    mover_board = tuple(
        sorted(
            (*top_gainers, *top_decliners),
            key=lambda row: (-abs(float(row["latest_return_pct"])), str(row["symbol"])),
        )
    )
    mover_symbols = {str(row["symbol"]) for row in mover_board}

    # 3. Yesterday's option winners (attention/vol) — optional cross-reference.
    option_winner_symbols: set[str] = set()
    option_loser_symbols: set[str] = set()
    option_status = "not_requested"
    if chains_root is not None:
        report = discover_option_roi_strategies(Path(chains_root))
        option_status = report["status"]
        option_winner_symbols = {str(w["symbol"]).upper() for w in report.get("top_winners", ())}
        option_loser_symbols = {str(w["symbol"]).upper() for w in report.get("top_losers", ())}

    # 4. Emit swing targets. Every big mover is examined under BOTH framings —
    #    momentum continuation (the move keeps going) and mean reversion (the
    #    move fades). These are competing hypotheses: context evidence scores
    #    them, forward settlement arbitrates them. Keeping only the fade was a
    #    scope bug; a big mover in a confirmed trend with participation is a
    #    documented continuation setup (gap-and-go / O'Neil follow-through).
    targets: list[dict[str, Any]] = []
    for mover in mover_board:
        symbol = str(mover["symbol"])
        metrics = metrics_by_symbol[symbol]
        state = _stretch_state(metrics)
        bars = bars_by_symbol[symbol]
        continuation = _continuation_evidence(bars, metrics)
        had_option_winner = symbol in option_winner_symbols
        had_option_loser = symbol in option_loser_symbols
        had_option_extreme = had_option_winner or had_option_loser

        framings: list[tuple[str, str, float]] = []
        if state != "neutral":
            reversion_bias = "mean_reversion_short" if state == "overbought" else "mean_reversion_long"
            framings.append(("mean_reversion", reversion_bias, _stretch_score(metrics, state)))
        if continuation["continuation_score"] >= 0.5:
            momentum_bias = (
                "momentum_continuation_long" if metrics["latest_return"] > 0.0
                else "momentum_continuation_short"
            )
            framings.append(("momentum_continuation", momentum_bias, continuation["continuation_score"]))

        for framing, bias, score in framings:
            body = {
                "symbol": symbol,
                "latest_close": round(metrics["latest_close"], 6),
                "latest_return_pct": round(metrics["latest_return"] * 100.0, 4),
                "return_zscore": round(metrics["return_zscore"], 4),
                "rsi_14": round(metrics["rsi_14"], 2),
                "pct_from_sma20": round(metrics["pct_from_sma20"] * 100.0, 4),
                "bollinger_pct_b": round(metrics["bollinger_pct_b"], 4),
                "stretch_state": state,
                "framing": framing,
                "competing_hypotheses": len(framings) > 1,
                "continuation_evidence": continuation,
                "swing_bias": bias,
                "stretch_score": round(score, 6),
                "is_biggest_mover": True,
                "mover_direction": str(mover["direction"]),
                "mover_direction_rank": int(mover["direction_rank"]),
                "coincides_with_option_winner": had_option_winner,
                "coincides_with_option_loser": had_option_loser,
                "coincides_with_option_extreme": had_option_extreme,
                # priority ranks research attention only — never a profit estimate.
                "research_priority": round(score * (1.25 if had_option_extreme else 1.0), 6),
                "is_trade_signal": False,
                "hypothesis": (
                    "mean_reversion_often_fails_requires_forward_validation"
                    if framing == "mean_reversion"
                    else "continuation_often_fails_requires_forward_validation"
                ),
                "required_forward_checks": (
                    "leakage_audit",
                    "random_entry_baseline",
                    "probability_of_backtest_overfitting",
                    "deflated_sharpe",
                    "held_out_era",
                    "forward_paper_settlement",
                ),
                "paper_only": True,
                "live_blocked": True,
            }
            target_id = f"swing-target:{canonical_hash(body)[:24]}"
            targets.append({"target_id": target_id, **body})

    ranked = sorted(
        targets, key=lambda t: (-float(t["research_priority"]), str(t["symbol"]))
    )[: max(max_targets, 0)]

    return {
        "artifact_type": "swing_target_discovery_report",
        "swing_target_discovery_version": "dopey-swing-target-discovery-v2",
        "status": "complete",
        "symbols_scored": len(metrics_by_symbol),
        "biggest_mover_count": len(mover_symbols),
        "gainer_count": len(top_gainers),
        "decliner_count": len(top_decliners),
        "top_gainers": top_gainers,
        "top_decliners": top_decliners,
        "biggest_movers": mover_board,
        "option_winner_cross_reference": option_status,
        "option_winner_symbol_count": len(option_winner_symbols),
        "option_loser_symbol_count": len(option_loser_symbols),
        "swing_target_count": len(ranked),
        "overbought_count": sum(1 for t in ranked if t["stretch_state"] == "overbought"),
        "oversold_count": sum(1 for t in ranked if t["stretch_state"] == "oversold"),
        "mean_reversion_framings": sum(1 for t in ranked if t["framing"] == "mean_reversion"),
        "momentum_continuation_framings": sum(
            1 for t in ranked if t["framing"] == "momentum_continuation"
        ),
        "swing_targets": tuple(ranked),
        # Honesty invariants — BOTH framings are unvalidated hypotheses.
        "mean_reversion_is_an_unvalidated_hypothesis": True,
        "momentum_continuation_is_an_unvalidated_hypothesis": True,
        "profit_or_edge_claimed": False,
        "targets_require_forward_validation_before_meaning": True,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
