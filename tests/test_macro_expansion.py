"""Tests for the V15 resource expansion: macro gate math, real risk-free rate,
IV inversion, and the Bailey-Lopez de Prado deflated Sharpe."""
from __future__ import annotations

from dopey_market_intake.macro_context_gate import interpolate_yield, positioning_state, vol_term_state
from dopey_options.greeks_engine import bs_greeks, implied_vol_bisection
from dopey_options.risk_free_rate import resolve_risk_free_rate
from dopey_stats.deflated_sharpe import expected_max_sharpe, probabilistic_sharpe


def test_yield_curve_interpolation() -> None:
    rows = [
        {"date": "2026-07-08", "label": "1Mo", "maturity_years": "0.083333", "yield_pct": "4.20"},
        {"date": "2026-07-08", "label": "2Mo", "maturity_years": "0.166667", "yield_pct": "4.40"},
        {"date": "2026-07-01", "label": "1Mo", "maturity_years": "0.083333", "yield_pct": "9.99"},
    ]
    mid = interpolate_yield(rows, 0.125)  # halfway between 1Mo and 2Mo on the LATEST date
    assert mid is not None and abs(mid - 4.30) < 0.01
    assert abs(interpolate_yield(rows, 0.01) - 4.20) < 1e-9  # clamps below shortest tenor
    assert interpolate_yield([], 0.1) is None


def test_vol_term_structure_classification() -> None:
    def rows(short_end: float, long_end: float) -> list[dict[str, str]]:
        return [
            {"date": "2026-07-09", "symbol": "VIX9D", "close": str(short_end)},
            {"date": "2026-07-09", "symbol": "VIX3M", "close": str(long_end)},
            {"date": "2026-07-09", "symbol": "VIX", "close": "15.0"},
            {"date": "2026-07-09", "symbol": "SKEW", "close": "140.0"},
        ]
    assert vol_term_state(rows(14.0, 17.0))["term_structure_state"] == "contango_normal"
    assert vol_term_state(rows(30.0, 22.0))["term_structure_state"] == "backwardation_stress"
    assert vol_term_state(rows(15.0, 15.05))["term_structure_state"] == "flat"


def test_cot_positioning_z_score() -> None:
    rows = [{"report_date": f"2026-{month:02d}-01", "noncomm_net": "1000", "noncomm_short": "0", "noncomm_long": "1000", "open_interest": "5000"} for month in range(1, 7)]
    rows += [{"report_date": f"2025-{month:02d}-01", "noncomm_net": "1000", "noncomm_short": "0", "noncomm_long": "1000", "open_interest": "5000"} for month in range(1, 13)]
    rows[-1] = {**rows[-1]}
    state = positioning_state(rows)
    assert state["reports"] == 18 and abs(state["noncomm_net_z_52w"]) < 1e-6  # constant series -> z ~ 0


def test_risk_free_rate_resolves_from_real_curve_or_falls_back() -> None:
    rate, source = resolve_risk_free_rate()
    assert 0.0 <= rate <= 0.20
    assert source in {"us_treasury_par_yield_curve_30d", "fallback_constant_no_treasury_staged"}


def test_implied_vol_bisection_round_trip() -> None:
    S, K, T, r = 100.0, 100.0, 30 / 365, 0.042
    for true_vol in (0.15, 0.30, 0.80):
        price = bs_greeks(S, K, T, r, true_vol, "call")["price"]
        recovered = implied_vol_bisection(price, S, K, T, r, "call")
        assert recovered is not None and abs(recovered - true_vol) < 1e-4
    put_price = bs_greeks(S, 110.0, T, r, 0.25, "put")["price"]
    recovered_put = implied_vol_bisection(put_price, S, 110.0, T, r, "put")
    assert recovered_put is not None and abs(recovered_put - 0.25) < 1e-4
    assert implied_vol_bisection(0.0, S, K, T, r, "call") is None  # below floor
    assert implied_vol_bisection(S * 2, S, K, T, r, "call") is None  # above ceiling


def test_deflated_sharpe_statistics() -> None:
    assert expected_max_sharpe(1, 0.01) == 0.0  # one trial deflates nothing
    one_hundred = expected_max_sharpe(100, 1.0 / 999)
    ten = expected_max_sharpe(10, 1.0 / 999)
    assert one_hundred > ten > 0.0  # more trials -> higher luck benchmark
    assert abs(probabilistic_sharpe(0.05, 0.05, 1000, 0.0, 3.0) - 0.5) < 1e-9  # at the benchmark
    assert probabilistic_sharpe(0.2, 0.0, 1000, 0.0, 3.0) > 0.999  # strong SR, big n
    assert probabilistic_sharpe(-0.2, 0.0, 1000, 0.0, 3.0) < 0.001
    # negative skew / fat tails must REDUCE confidence vs the normal case
    normal_case = probabilistic_sharpe(0.1, 0.0, 500, 0.0, 3.0)
    ugly_case = probabilistic_sharpe(0.1, 0.0, 500, -1.5, 9.0)
    assert ugly_case < normal_case
