from __future__ import annotations

import math

from dopey_analysis.indicator_foundry import (
    PRIMITIVES,
    bollinger_pct_b,
    candidate_series,
    ema_cross_spread,
    generate_candidates,
    rank_ic,
    rsi,
    stochastic_k,
    williams_r,
)


def test_classic_primitive_bounds_and_signs() -> None:
    rising = [100.0 + i for i in range(60)]
    falling = [200.0 - i for i in range(60)]
    assert rsi(rising, 59) > 70.0
    assert rsi(falling, 59) < 30.0
    assert ema_cross_spread(rising, 59) > 0.0
    assert ema_cross_spread(falling, 59) < 0.0
    highs = [value * 1.01 for value in rising]
    lows = [value * 0.99 for value in rising]
    k = stochastic_k(rising, highs, lows, 59)
    assert 0.0 <= k <= 100.0 and k > 80.0
    assert -100.0 <= williams_r(rising, highs, lows, 59) <= 0.0
    assert 0.0 <= bollinger_pct_b(rising, 59) <= 1.5


def test_candidate_grammar_enumeration_and_series_math() -> None:
    candidates = generate_candidates()
    ids = [candidate["candidate_id"] for candidate in candidates]
    assert len(ids) == len(set(ids))
    names = sorted(PRIMITIVES)
    expected = len(names) * (len(names) - 1) // 2 * 2 + len(names)
    assert len(candidates) == expected
    prims = {"a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "b": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]}
    diff = candidate_series({"op": "diff", "inputs": ["a", "b"]}, prims)
    assert diff == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    lag = candidate_series({"op": "lagdiv", "inputs": ["a"], "lag": 5}, prims)
    assert lag[-1] == 5.0 and lag[0] == 0.0


def test_rank_ic_detects_signal_and_rejects_noise() -> None:
    n = 200
    forwards = [math.sin(i * 0.7) * 0.01 for i in range(n)]
    predictive = [value * 3.0 for value in forwards]
    anti = [-value for value in predictive]
    flat = [float(i % 2) for i in range(n)]
    assert rank_ic(predictive, forwards) > 0.9
    assert rank_ic(anti, forwards) < -0.9
    assert abs(rank_ic(flat, forwards)) < 0.2
    assert rank_ic(predictive[:10], forwards[:10]) == 0.0  # insufficient sample guard
