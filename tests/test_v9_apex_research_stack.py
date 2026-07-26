from __future__ import annotations

import math

from dopey_analysis.market_structure_engine import (
    SWING_FRACTAL_K,
    VOLUME_Z_THRESHOLD,
    _sr_zones,
    _swing_levels,
    _trap_events,
    _volume_anomalies,
    _vrp_series,
)
from dopey_autonomy.run_resilient_research_supervisor import run_resilient_research_supervisor
from dopey_backtest.real_history_honest_backtester import (
    COMMISSION_PER_SIDE_PREMIUM_UNITS,
    COST_PCT_PER_SIDE,
    apply_trade_costs,
)
from dopey_options.chain_analytics import (
    gamma_exposure_per_strike,
    gamma_flip_strike,
    net_delta_pressure,
    put_call_ratios,
    run_chain_analytics_gate,
    total_gamma_exposure,
)


def _bar_row(date: str, close: float, high: float | None = None, low: float | None = None, volume: int = 1000) -> dict:
    return {
        "date": date,
        "open": close,
        "high": high if high is not None else close * 1.005,
        "low": low if low is not None else close * 0.995,
        "close": close,
        "adjusted_close": close,
        "volume": volume,
    }


def test_apply_trade_costs_net_below_gross_and_marker_flip() -> None:
    record = {"entry_premium": 10.0, "exit_premium": 10.4, "win_loss_marker": "win_model_validation_only"}
    costed = apply_trade_costs(record)
    assert costed["path_pnl_gross_mid"] == 0.4
    expected_entry = round(10.0 * (1.0 + COST_PCT_PER_SIDE) + COMMISSION_PER_SIDE_PREMIUM_UNITS, 6)
    expected_exit = round(10.4 * (1.0 - COST_PCT_PER_SIDE) - COMMISSION_PER_SIDE_PREMIUM_UNITS, 6)
    assert costed["entry_premium"] == expected_entry
    assert costed["exit_premium"] == expected_exit
    assert costed["path_pnl"] == round(expected_exit - expected_entry, 6)
    assert costed["path_pnl"] < costed["path_pnl_gross_mid"]
    assert costed["trade_cost_premium_units"] > 0.0
    # a small mid-gross winner becomes a net loser after costs: marker must flip
    assert costed["win_loss_marker"] == "loss_model_validation_only"


def test_swing_levels_and_sr_zones() -> None:
    closes = [100, 101, 102, 105, 102, 101, 100, 99, 98, 100, 102, 105, 102, 100, 99]
    rows = [_bar_row(f"2025-01-{index + 1:02d}", float(value)) for index, value in enumerate(closes)]
    swings = _swing_levels("TEST", rows)
    highs = [record for record in swings if record["swing_type"] == "swing_high"]
    lows = [record for record in swings if record["swing_type"] == "swing_low"]
    assert any(abs(record["level"] - 105 * 1.005) < 1.0 for record in highs)
    assert any(record["level"] < 99.0 for record in lows)
    zones = _sr_zones("TEST", swings, rows)
    assert any(zone["touch_count"] >= 2 for zone in zones)


def test_bull_trap_detected_and_leak_free_confirmation_lag() -> None:
    # 60 flat bars establish a swing high near 105, then a breakout that fails.
    rows = [_bar_row(f"2025-{1 + index // 28:02d}-{index % 28 + 1:02d}", 100.0) for index in range(50)]
    rows[25] = _bar_row("2025-01-26", 100.0, high=105.0)  # swing high at 105
    for index, close in ((46, 106.0), (47, 103.0)):  # break above 105, fail back below
        rows[index] = _bar_row(rows[index]["date"], close)
    traps = _trap_events("TEST", rows, _swing_levels("TEST", rows))
    bull_traps = [record for record in traps if record["trap_type"] == "bull_trap"]
    assert bull_traps, "failed breakout above swing high must be detected as bull trap"
    trap = bull_traps[0]
    assert trap["detected_at_date"] == trap["fail_date"]
    assert trap["fail_close"] < trap["level"] < trap["break_close"]


def test_volume_anomaly_z_score() -> None:
    rows = [_bar_row(f"2025-03-{index + 1:02d}", 100.0, volume=1000 + (index % 7) * 10) for index in range(25)]
    rows[-1] = _bar_row("2025-03-26", 100.0, volume=1000000)
    anomalies = _volume_anomalies("TEST", rows)
    assert anomalies and anomalies[-1]["volume_z_score"] >= VOLUME_Z_THRESHOLD


def test_vrp_series_math() -> None:
    spy = [_bar_row(f"2025-01-{index + 1:02d}", 100.0 * (1.0 + 0.001 * index)) for index in range(28)]
    vix = [_bar_row(row["date"], 20.0) for row in spy]
    series = _vrp_series(spy, vix)
    assert series
    observation = series[-1]
    assert observation["implied_variance"] == round((20.0 / 100.0) ** 2, 8)
    # realized vol of a smooth +0.1%/day drift is tiny -> implied >> realized -> positive VRP
    assert observation["vrp"] > 0.0


def test_gex_math_and_flip_point() -> None:
    chain = [
        {"strike": 95.0, "option_type": "put", "gamma": 0.02, "open_interest": 5000, "volume": 100, "delta": -0.3},
        {"strike": 105.0, "option_type": "call", "gamma": 0.02, "open_interest": 5000, "volume": 200, "delta": 0.3},
    ]
    spot = 100.0
    per_strike = gamma_exposure_per_strike(chain, spot)
    put_leg = next(item for item in per_strike if item["strike"] == 95.0)
    call_leg = next(item for item in per_strike if item["strike"] == 105.0)
    expected_magnitude = 0.02 * 5000 * 100.0 * spot * spot * 0.01
    assert put_leg["gex_dollar_per_pct"] == -round(expected_magnitude, 2)
    assert call_leg["gex_dollar_per_pct"] == round(expected_magnitude, 2)
    assert total_gamma_exposure(chain, spot) == 0.0
    assert gamma_flip_strike(chain, spot) == 105.0
    ratios = put_call_ratios(chain)
    assert ratios["put_call_oi_ratio"] == 1.0
    assert ratios["put_call_volume_ratio"] == 0.5
    assert net_delta_pressure(chain) == 0.0


def test_chain_analytics_gate_state_consistent() -> None:
    summary = run_chain_analytics_gate()
    if summary["chain_snapshot_status"] == "real_chain_snapshot_validated":
        assert summary["chain_analytics_status"] == "real_chain_analytics_computed"
        assert summary["quote_derived_output_produced"] is True
        assert summary["real_metric_count"] > 0
    else:
        assert summary["chain_analytics_status"].startswith("blocked")
        assert summary["quote_derived_output_produced"] is False
    assert summary["math_validated_on_fixture"] is True
    assert summary["paper_only"] is True and summary["live_blocked"] is True


def test_supervisor_absorbs_failures_and_skips_dependents() -> None:
    def ok_stage() -> dict:
        return {"dataset_status": "ok"}

    def boom_stage() -> dict:
        raise RuntimeError("intentional test failure")

    stages = (
        ("alpha", ok_stage, ()),
        ("bravo", boom_stage, ()),
        ("charlie_depends_on_bravo", ok_stage, ("bravo",)),
        ("delta_independent", ok_stage, ()),
    )
    summary = run_resilient_research_supervisor(stages)
    results = summary["stage_results"]
    assert results["alpha"]["stage_status"] == "completed"
    assert results["bravo"]["stage_status"] == "failed_absorbed"
    assert results["charlie_depends_on_bravo"]["stage_status"] == "skipped_dependency"
    assert results["delta_independent"]["stage_status"] == "completed"
    assert summary["supervisor_status"] == "degraded_with_incidents"
    assert summary["incident_count"] == 1
    assert summary["repair_queue_count"] == 2
    assert summary["strategy_promotion_allowed"] is False


def test_supervisor_failure_never_recorded_as_pass() -> None:
    def boom_stage() -> dict:
        raise ValueError("must not become a pass")

    summary = run_resilient_research_supervisor((("only", boom_stage, ()),))
    assert summary["supervisor_status"] == "all_stages_failed"
    assert summary["stages_completed"] == 0
    assert summary["incident_count"] == 1
