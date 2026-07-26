"""Validated cross-sectional breadth, leadership, correlation, and fragility."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash
from dopey_equity_swing.market_structure import Bar


SECTOR_SYMBOLS: tuple[str, ...] = ("XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
INDEX_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "IWM", "DIA")


def _returns(rows: Sequence[Bar], lookback: int) -> list[float]:
    closes = [float(row["close"]) for row in rows[-(lookback + 1) :]]
    return [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes)) if closes[index - 1] > 0.0]


def _period_return(rows: Sequence[Bar], lookback: int) -> float | None:
    if len(rows) <= lookback:
        return None
    prior = float(rows[-lookback - 1]["close"])
    return None if prior <= 0.0 else float(rows[-1]["close"]) / prior - 1.0


def _above_average(rows: Sequence[Bar], lookback: int) -> bool | None:
    if len(rows) < lookback:
        return None
    average = sum(float(row["close"]) for row in rows[-lookback:]) / lookback
    return float(rows[-1]["close"]) > average


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    count = min(len(left), len(right))
    if count < 10:
        return None
    x = list(left[-count:])
    y = list(right[-count:])
    x_mean = sum(x) / count
    y_mean = sum(y) / count
    numerator = sum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y, strict=True))
    x_variance = sum((value - x_mean) ** 2 for value in x)
    y_variance = sum((value - y_mean) ** 2 for value in y)
    denominator = math.sqrt(x_variance * y_variance)
    return None if denominator == 0.0 else numerator / denominator


def build_cross_sectional_context(
    histories: Mapping[str, Sequence[Bar]],
    history_proofs: Mapping[str, Mapping[str, Any]],
    market_time: str,
    return_lookback: int,
    average_lookback: int,
    correlation_lookback: int,
) -> dict[str, Any]:
    if return_lookback <= 0 or average_lookback <= 0 or correlation_lookback <= 1:
        raise ValueError(
            "cross-sectional lookbacks must be positive: "
            f"return={return_lookback}, average={average_lookback}, correlation={correlation_lookback}"
        )
    if not histories:
        raise ValueError("cross-sectional context requires validated histories")
    missing_proofs = sorted(set(histories) - set(history_proofs))
    if missing_proofs:
        raise ValueError(f"cross-sectional histories require provenance proofs: missing_symbols={missing_proofs}")
    invalid_proofs = sorted(
        symbol
        for symbol, proof in history_proofs.items()
        if proof.get("paper_only") is not True
        or proof.get("live_blocked") is not True
        or not proof.get("actual_sha256")
    )
    if invalid_proofs:
        raise ValueError(f"cross-sectional history proofs violate governance: symbols={invalid_proofs}")
    period_returns = {
        symbol: value
        for symbol, rows in histories.items()
        if (value := _period_return(rows, return_lookback)) is not None
    }
    above_average = {
        symbol: value
        for symbol, rows in histories.items()
        if (value := _above_average(rows, average_lookback)) is not None
    }
    positive_fraction = sum(value > 0.0 for value in period_returns.values()) / len(period_returns) if period_returns else 0.0
    above_fraction = sum(above_average.values()) / len(above_average) if above_average else 0.0
    breadth_score = 0.5 * positive_fraction + 0.5 * above_fraction
    breadth_state = (
        "broad_participation" if breadth_score >= 0.65
        else "narrow_participation" if breadth_score <= 0.4
        else "mixed_participation"
    )
    sector_returns = {symbol: period_returns[symbol] for symbol in SECTOR_SYMBOLS if symbol in period_returns}
    sector_ranking = [
        {"symbol": symbol, "return": round(value, 8)}
        for symbol, value in sorted(sector_returns.items(), key=lambda item: (-item[1], item[0]))
    ]
    index_returns = {
        symbol: _returns(histories[symbol], correlation_lookback)
        for symbol in INDEX_SYMBOLS
        if symbol in histories
    }
    pairwise: list[dict[str, Any]] = []
    symbols = sorted(index_returns)
    for left_index, left in enumerate(symbols):
        for right in symbols[left_index + 1 :]:
            value = _correlation(index_returns[left], index_returns[right])
            if value is not None:
                pairwise.append({"left": left, "right": right, "correlation": round(value, 8)})
    average_correlation = sum(float(record["correlation"]) for record in pairwise) / len(pairwise) if pairwise else 0.0
    correlation_state = (
        "high_common_factor" if average_correlation >= 0.8
        else "diversified_or_rotational" if average_correlation <= 0.5
        else "moderate_common_factor"
    )
    spy_return = period_returns.get("SPY", 0.0)
    narrow_index_divergence = spy_return > 0.0 and breadth_score < 0.5
    fragility_score = min(
        1.0,
        0.45 * max(0.0, average_correlation)
        + 0.35 * (1.0 - breadth_score)
        + 0.2 * float(narrow_index_divergence),
    )
    fragility_state = "elevated" if fragility_score >= 0.65 else "watch" if fragility_score >= 0.45 else "contained"
    source_hashes = {symbol: str(history_proofs[symbol]["actual_sha256"]) for symbol in sorted(histories)}
    body: dict[str, Any] = {
        "artifact_type": "validated_cross_sectional_market_context",
        "cross_section_version": "dopey-cross-section-v1",
        "as_of": market_time,
        "validated_symbol_count": len(histories),
        "return_lookback": return_lookback,
        "average_lookback": average_lookback,
        "correlation_lookback": correlation_lookback,
        "breadth": {
            "state": breadth_state,
            "score": round(breadth_score, 8),
            "positive_return_fraction": round(positive_fraction, 8),
            "above_moving_average_fraction": round(above_fraction, 8),
            "sample_count": min(len(period_returns), len(above_average)),
        },
        "sector_leadership": {
            "state": "ranked_validated_sector_etfs" if sector_ranking else "unknown",
            "ranking": sector_ranking,
            "leader": sector_ranking[0]["symbol"] if sector_ranking else None,
            "laggard": sector_ranking[-1]["symbol"] if sector_ranking else None,
        },
        "correlation_structure": {
            "state": correlation_state if pairwise else "unknown",
            "average_index_correlation": round(average_correlation, 8) if pairwise else None,
            "pairs": pairwise,
        },
        "market_fragility": {
            "state": fragility_state,
            "score": round(fragility_score, 8),
            "narrow_index_divergence": narrow_index_divergence,
        },
        "source_hashes": source_hashes,
        "network_fetch_performed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_trade_decision": True,
    }
    content_hash = canonical_hash(body)
    return {
        **body,
        "evidence_id": f"cross-section:{content_hash[:20]}",
        "content_hash": content_hash,
        "provenance": "hash_pinned_governed_real_history_universe",
    }
