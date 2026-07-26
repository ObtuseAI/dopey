from __future__ import annotations

from dopey_analysis.market_context_fusion import _bias, SECTOR_MAP
from dopey_backtest.forward_paper_walk import _discipline_halt, DISCIPLINE_LOSS_STREAK_HALT
from dopey_options.vol_surface_metrics import (
    _put_skew_slope,
    _risk_reversal,
    compute_surface_metrics,
    detect_surface_tears,
)
from dopey_risk_engine.adversarial_stress_engine import SCENARIOS, _shocked_exit_value


def _chain_row(symbol: str, expiry: str, option_type: str, strike: float, iv: float, spot: float) -> dict:
    return {
        "snapshot_date": "2026-07-09", "symbol": symbol, "expiry": expiry, "dte_calendar": 30,
        "option_type": option_type, "strike": strike, "bid": 1.0, "ask": 1.1, "mid": 1.05,
        "last": 1.0, "volume": 10, "open_interest": 100, "implied_vol": iv, "underlying_spot": spot,
        "source": "fixture", "quote_derived": True,
    }


def test_put_skew_slope_negative_when_downside_iv_higher() -> None:
    spot = 100.0
    rows = [
        _chain_row("T", "2026-08-07", "put", 85.0, 0.35, spot),
        _chain_row("T", "2026-08-07", "put", 90.0, 0.30, spot),
        _chain_row("T", "2026-08-07", "put", 95.0, 0.25, spot),
        _chain_row("T", "2026-08-07", "put", 100.0, 0.20, spot),
    ]
    assert _put_skew_slope(rows, spot) < 0.0
    rr_rows = rows + [_chain_row("T", "2026-08-07", "call", 110.0, 0.18, spot)]
    assert _risk_reversal(rr_rows, spot) > 0.0  # OTM put IV rich vs OTM call


def test_surface_metrics_and_tear_detection() -> None:
    spot = 100.0
    near = [_chain_row("T", "2026-07-24", side, strike, iv, spot) for side, strike, iv in
            (("put", 90.0, 0.30), ("put", 95.0, 0.25), ("put", 100.0, 0.20), ("call", 100.0, 0.20), ("call", 110.0, 0.18))]
    far = [_chain_row("T", "2026-09-18", side, strike, iv, spot) for side, strike, iv in
           (("put", 95.0, 0.28), ("put", 100.0, 0.24), ("call", 100.0, 0.24), ("call", 110.0, 0.22))]
    metrics = compute_surface_metrics(near + far, "2026-07-09")
    assert len(metrics) == 1
    record = metrics[0]
    assert record["expiry_count"] == 2
    assert record["term_slope"] > 0.0  # far ATM IV above near
    prior = {**record, "put_skew_slope": record["put_skew_slope"] + 0.05, "term_slope": record["term_slope"],
             "underlying_spot": spot * 0.99, "snapshot_date": "2026-07-08"}
    tears = detect_surface_tears([record], {"T": prior})
    assert tears and tears[0]["tear_type"] == "divergent_put_skew_steepening"


def test_context_bias_matrix() -> None:
    assert _bias(short_gamma=True, sector_aligned=True, vrp_rich=False) == "favorable"
    assert _bias(short_gamma=False, sector_aligned=False, vrp_rich=False) == "unfavorable"
    assert _bias(short_gamma=True, sector_aligned=False, vrp_rich=False) == "neutral"
    assert _bias(short_gamma=True, sector_aligned=True, vrp_rich=True) == "unfavorable"
    assert SECTOR_MAP["NVDA"] == "XLK" and SECTOR_MAP["JPM"] == "XLF"


def _validated_trade(index: int, path_pnl: float, entry_fill: float) -> dict:
    # The tilt governor only counts integrity-VALIDATED closes, and the
    # classifier demands a position_id per trade - fixtures must conform.
    return {
        "position_id": f"fixture-halt-{index}",
        "path_pnl": path_pnl,
        "entry_fill": entry_fill,
        "outcome_integrity_class": "validated_forward_outcome",
        "outcome_integrity_reason_codes": [],
    }


def test_discipline_halt_on_loss_streak_and_drawdown() -> None:
    losses = [_validated_trade(index, -1.0, 5.0) for index in range(DISCIPLINE_LOSS_STREAK_HALT)]
    assert _discipline_halt({"closed_trades": losses}) is not None
    mixed = [_validated_trade(0, 1.0, 5.0), _validated_trade(1, -1.0, 5.0)]
    assert _discipline_halt({"closed_trades": mixed}) is None
    deep_drawdown = [_validated_trade(0, 10.0, 5.0)] + [
        _validated_trade(index, -4.0, 5.0) for index in range(1, 6)
    ]
    assert _discipline_halt({"closed_trades": deep_drawdown}) is not None


def test_stress_scenarios_hurt_long_calls_on_gap_down() -> None:
    position = {
        "position_id": "x", "symbol": "T", "option_type": "call", "strike": 100.0,
        "entry_fill": 5.0, "entry_spot": 100.0, "entry_iv": 0.25,
        "expiry": "2026-08-07", "entry_date": "2026-07-09",
    }
    crash = next(scenario for scenario in SCENARIOS if scenario["scenario_id"] == "black_swan_composite")
    calm = next(scenario for scenario in SCENARIOS if scenario["scenario_id"] == "gap_up_10")
    risk_free_rate = 0.05
    crash_value = _shocked_exit_value(position, crash, risk_free_rate)
    calm_value = _shocked_exit_value(position, calm, risk_free_rate)
    assert crash_value < calm_value
    put_position = {**position, "option_type": "put"}
    assert _shocked_exit_value(put_position, crash, risk_free_rate) > _shocked_exit_value(
        put_position, calm, risk_free_rate
    )


def test_exit_policy_search_grid_shapes() -> None:
    from dopey_evolution.exit_policy_walkforward_search import CURRENT_POLICY, HOLDS, STOPS, TARGETS

    assert (CURRENT_POLICY["stop"], CURRENT_POLICY["target"], CURRENT_POLICY["hold"]) in [
        (stop, target, hold) for stop in STOPS for target in TARGETS for hold in HOLDS
    ]
