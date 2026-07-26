"""Tests for the 2026-07 hardening pass: atomic IO, market calendar, sentinels,
forward-book risk math, foundry v2 statistics, walk entry policy, supervisor diffs."""

from __future__ import annotations

import json
import math
from datetime import date

import pytest

from dopey_analysis.indicator_foundry import (
    _standardize,
    empirical_null_bar,
    quote_features_for_rows,
    rank_ic,
)
from dopey_analysis.market_context_fusion import _external_entry_veto_reasons
from dopey_autonomy.run_resilient_research_supervisor import diff_stage_states
from dopey_backtest import forward_paper_walk as walk
from dopey_backtest.forward_evidence_integrity import build_integrity_summary
from dopey_backtest import baseline_arbitration
from dopey_backtest import era_walk_forward
from dopey.chronos.market_calendar import build_market_session_evidence
from dopey_core.market_calendar import is_trading_day, trading_days_between
from operator_tools.operator_fetch_news_context import (
    REQUIRED_SOURCE_IDS,
    SUPPLEMENTAL_SOURCE_IDS,
    TREASURY_SPEC,
    news_source_coverage,
    parse_treasury_press_releases,
)
from operator_tools.operator_fetch_option_chains import load_open_contract_requirements
from dopey_data_ingestion.data_freshness_sentinel import classify_lag
from dopey_research_pipeline.artifact_io import read_json_guarded, write_json_atomic
from dopey_risk_engine.forward_book_risk import (
    attribute_open_position,
    dollar_greeks,
    year_fraction,
)
from dopey_risk_engine.forward_entry_guard import prospective_entry_rejection_reasons


def test_atomic_write_backup_and_guarded_read(tmp_path) -> None:
    target = tmp_path / "state.json"
    write_json_atomic(target, {"generation": 1}, keep_backup=True)
    write_json_atomic(target, {"generation": 2}, keep_backup=True)
    record, source = read_json_guarded(target)
    assert record == {"generation": 2} and source == "primary"
    target.write_text("{corrupt", encoding="utf-8")  # torn write simulation
    record, source = read_json_guarded(target)
    assert record == {"generation": 1} and source == "backup"
    assert read_json_guarded(tmp_path / "absent.json") == (None, "missing")


def test_market_calendar_sessions() -> None:
    assert not is_trading_day(date(2026, 7, 3))  # July 4th observed
    assert not is_trading_day(date(2026, 7, 4))  # Saturday
    assert is_trading_day(date(2026, 7, 9))
    # Fri 2026-07-02 -> Thu 2026-07-09: skip holiday Fri 3rd + weekend = Mon-Thu
    assert trading_days_between(date(2026, 7, 2), date(2026, 7, 9)) == 4
    assert trading_days_between(date(2026, 7, 9), date(2026, 7, 9)) == 0
    assert not is_trading_day(date(2028, 7, 4))
    assert is_trading_day(date(2028, 1, 3))
    evidence = build_market_session_evidence(date(2028, 1, 3))
    assert evidence["is_trading_day"] is True
    assert evidence["paper_only"] is True
    assert evidence["live_blocked"] is True
    assert evidence["not_execution_authority"] is True


def test_freshness_classification_thresholds() -> None:
    assert classify_lag("chain_archive", 0) == "green"
    assert classify_lag("chain_archive", 2) == "amber"
    assert classify_lag("chain_archive", 5) == "red_stale"
    assert classify_lag("ohlcv_spine", None) == "red_missing"


def test_dollar_greeks_and_attribution_identity() -> None:
    greeks = {"delta": 0.5, "gamma": 0.02, "vega": 0.15, "theta": -0.05}
    dollars = dollar_greeks(greeks, spot=100.0)
    assert dollars["delta_dollars"] == 5000.0
    assert dollars["gamma_dollars_per_1pct"] == round(
        0.02 * 0.01 * 100.0 * 100.0 * 100.0, 2
    )
    assert dollars["vega_dollars_per_vol_pt"] == 15.0
    assert dollars["theta_dollars_per_day"] == -5.0
    position = {
        "position_id": "t-1",
        "symbol": "SPY",
        "candidate_strategy": "long_call",
        "option_type": "call",
        "strike": 100.0,
        "expiry": "2026-08-08",
        "entry_date": "2026-07-01",
        "entry_spot": 100.0,
        "entry_iv": 0.20,
        "entry_bid": 2.40,
        "entry_ask": 2.60,
        "entry_fill": 2.6065,
    }
    row = {"underlying_spot": 103.0, "implied_vol": 0.22, "bid": 4.10, "ask": 4.30}
    result = attribute_open_position(position, row, as_of="2026-07-09")
    # exact identity: unrealized == mid_move - friction (gap must be numerically zero)
    assert abs(result["attribution_identity_gap"]) < 1e-9
    buckets = (
        result["direction_pnl"]
        + result["volatility_pnl"]
        + result["decay_pnl"]
        + result["residual_pnl"]
    )
    assert abs(buckets - result["mid_move"]) < 1e-6
    assert result["direction_pnl"] > 0  # long call, spot up
    assert result["decay_pnl"] < 0  # 8 days of theta
    assert year_fraction("2026-07-09", "2026-07-09") == 0.0


def test_foundry_v2_statistics() -> None:
    # train-only standardization: validation values scale by TRAIN stats
    series = [float(value) for value in range(20)]
    flags = [True] * 10 + [False] * 10
    standardized = _standardize(series, flags)
    train_mean = sum(series[:10]) / 10
    assert (
        abs(
            standardized[0]
            - (series[0] - train_mean)
            / (math.sqrt(sum((v - train_mean) ** 2 for v in series[:10]) / 9))
        )
        < 1e-9
    )
    # tie-averaged ranks: constant series correlates zero, planted signal still detected
    forwards = [math.sin(i * 0.7) * 0.01 for i in range(200)]
    assert rank_ic([v * 2 for v in forwards], forwards) > 0.9
    assert abs(rank_ic([1.0, 1.0, 1.0, 1.0] * 50, forwards)) < 1e-9
    # circular-shift null: deterministic, and a planted-signal candidate towers over it
    candidates = {
        "planted": [v * 3 for v in forwards],
        "noise": [float(i % 7) for i in range(200)],
    }
    bar_a = empirical_null_bar(candidates, forwards, shifts=10)
    bar_b = empirical_null_bar(candidates, forwards, shifts=10)
    assert bar_a == bar_b  # deterministic
    assert 0.0 < bar_a < 0.9  # null never reaches the planted |IC| ~ 1.0
    assert rank_ic(candidates["planted"], forwards) > bar_a


def test_quote_features_from_snapshot_rows() -> None:
    rows = [
        {
            "symbol": "SPY",
            "dte_calendar": 30,
            "option_type": "call",
            "strike": 100.0,
            "open_interest": 100,
            "implied_vol": 0.18,
            "underlying_spot": 100.0,
        },
        {
            "symbol": "SPY",
            "dte_calendar": 30,
            "option_type": "put",
            "strike": 100.0,
            "open_interest": 200,
            "implied_vol": 0.22,
            "underlying_spot": 100.0,
        },
    ]
    features = quote_features_for_rows(rows)["SPY"]
    assert features["pc_oi"] == 2.0
    assert abs(features["atm_iv"] - 0.20) < 1e-9
    assert abs(features["iv_skew_put_minus_call"] - 0.04) < 1e-9


def test_walk_tenor_pinning_unique_ids_and_idempotency(tmp_path, monkeypatch) -> None:
    signals = tmp_path / "signals.jsonl"
    signals.write_text(
        json.dumps(
            {
                "signal_id": "sig-1",
                "symbol": "SPY",
                "candidate_strategy": "long_call",
                "signal_date": "2026-07-08",
                "data_source_tier": "local_real_history",
                "confidence_proxy": 0.9,
                "source_signal_family": "test",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(walk, "DIRECTIONAL_SETUP_SIGNALS_PATH", signals)
    context = tmp_path / "entry_context.jsonl"
    context.write_text(
        json.dumps(
            {
                "symbol": "SPY",
                "snapshot_date": "2026-07-09",
                "external_context_status": "complete",
                "long_call_entry_bias": "neutral",
                "long_put_entry_bias": "neutral",
                "long_call_veto_reasons": [],
                "long_put_veto_reasons": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(walk, "ENTRY_CONTEXT_PATH", context)

    def row(dte: int, strike: float, bid: float = 1.0) -> dict:
        return {
            "symbol": "SPY",
            "expiry": f"2026-08-{dte:02d}",
            "dte_calendar": dte,
            "option_type": "call",
            "strike": strike,
            "bid": bid,
            "ask": bid + 0.1,
            "mid": bid + 0.05,
            "last": bid,
            "volume": 10,
            "open_interest": 100,
            "implied_vol": 0.2,
            "underlying_spot": 100.0,
        }

    snapshot = {
        "rows": [row(14, 100.0), row(30, 100.0), row(60, 100.0), row(30, 101.0)]
    }
    ledger = {"open_positions": [], "closed_trades": [], "last_marking_date": ""}
    opened = walk._open_new_positions(ledger, snapshot, "2026-07-09")
    assert len(opened) == 1
    assert (
        int(opened[0]["position_id"].rsplit("-", 1)[1]) == 1
    )  # counter-based unique id
    assert (
        opened[0]["expiry"] == "2026-08-30" and opened[0]["strike"] == 100.0
    )  # ~30 DTE ATM pinned
    # idempotent second pass on the same snapshot date opens nothing
    ledger["open_positions"].extend(opened)
    assert walk._open_new_positions(ledger, snapshot, "2026-07-09") == []
    # one-shot per signal: after the position closes, the same signal cannot re-enter
    ledger["closed_trades"].append(
        {**ledger["open_positions"].pop(0), "path_pnl": -0.5}
    )
    assert walk._open_new_positions(ledger, snapshot, "2026-07-10") == []


def test_walk_rejects_thin_and_wide_contracts_before_selection(
    tmp_path, monkeypatch
) -> None:
    signals = tmp_path / "signals.jsonl"
    signals.write_text(
        json.dumps(
            {
                "signal_id": "sig-liquidity",
                "symbol": "XLI",
                "candidate_strategy": "long_call",
                "signal_date": "2026-07-08",
                "data_source_tier": "local_real_history",
                "confidence_proxy": 0.9,
                "source_signal_family": "relative_strength",
                "reason_codes": ["outperforming_benchmark"],
                "record_hash": "signal-hash",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    context = tmp_path / "entry_context.jsonl"
    context.write_text(
        json.dumps(
            {
                "symbol": "XLI",
                "snapshot_date": "2026-07-09",
                "external_context_status": "complete",
                "long_call_entry_bias": "favorable",
                "long_put_entry_bias": "neutral",
                "long_call_veto_reasons": [],
                "long_put_veto_reasons": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(walk, "DIRECTIONAL_SETUP_SIGNALS_PATH", signals)
    monkeypatch.setattr(walk, "ENTRY_CONTEXT_PATH", context)

    def row(
        strike: float, bid: float, ask: float, volume: int, open_interest: int
    ) -> dict:
        return {
            "symbol": "XLI",
            "expiry": "2026-08-07",
            "dte_calendar": 29,
            "option_type": "call",
            "strike": strike,
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2.0,
            "last": bid,
            "volume": volume,
            "open_interest": open_interest,
            "implied_vol": 0.2,
            "underlying_spot": 100.0,
        }

    snapshot = {
        "rows": [
            row(100.0, 4.0, 4.2, 1, 4),
            row(101.0, 3.0, 4.0, 100, 100),
            row(102.0, 3.8, 4.0, 20, 200),
        ]
    }
    ledger = {"open_positions": [], "closed_trades": [], "last_marking_date": ""}

    opened = walk._open_new_positions(ledger, snapshot, "2026-07-09")

    assert len(opened) == 1
    assert opened[0]["strike"] == 102.0
    assert opened[0]["entry_open_interest"] == 200
    assert opened[0]["entry_volume"] == 20
    assert opened[0]["entry_relative_spread"] <= 0.10
    assert opened[0]["signal_record_hash"] == "signal-hash"


def test_forward_exit_defers_dislocated_quote_until_executable_quote() -> None:
    position = {
        "position_id": "fw-XLE-long_call-2026-07-09-00001",
        "symbol": "XLE",
        "candidate_strategy": "long_call",
        "option_type": "call",
        "entry_fill": 1.0065,
        "expiry": "2026-08-07",
        "strike": 50.0,
        "marking_sessions": 2,
        "missed_marks": 0,
        "last_mark_bid": 1.0,
        "last_mark_date": "2026-07-10",
        "last_executable_bid": 1.0,
        "last_executable_ask": 1.1,
        "last_executable_date": "2026-07-10",
    }
    dislocated_row = {
        "bid": 0.01,
        "ask": 1.99,
        "dte_calendar": 26,
        "volume": 0,
        "open_interest": 100,
        "underlying_spot": 51.0,
    }

    deferred, closed = walk._mark_position(position, dislocated_row, "2026-07-13")

    assert closed is None and deferred is not None
    assert deferred["pending_exit_reason"] == "time_stop_deferred_unreliable_quote"
    assert deferred["last_executable_bid"] == 1.0
    assert deferred["last_observed_bid"] == 0.01
    assert deferred["unreliable_quote_count"] == 1

    executable_row = {
        "bid": 0.80,
        "ask": 0.90,
        "dte_calendar": 25,
        "volume": 20,
        "open_interest": 100,
        "underlying_spot": 50.5,
    }
    still_open, executable_close = walk._mark_position(
        deferred, executable_row, "2026-07-14"
    )

    assert still_open is None and executable_close is not None
    assert executable_close["exit_reason"] == "time_stop_deferred_unreliable_quote"
    assert executable_close["exit_bid"] == 0.80
    assert executable_close["exit_quote_quality_status"] == "executable_quote"


def test_missing_quote_continuity_is_censored_and_excluded_from_statistics() -> None:
    censored = walk._censor_missing_quote_continuity(
        {
            "position_id": "fw-censor-1",
            "entry_fill": 2.0,
            "signal_id": "sig-censor-1",
        },
        "2026-07-20",
        ("contract_quote_continuity_lost", "no_exit_fill_observed"),
    )
    summary, outcomes = build_integrity_summary(
        {"closed_trades": [], "censored_positions": [censored]},
        {},
    )

    assert summary["validated_closed_trade_count"] == 0
    assert summary["censored_outcome_count"] == 1
    assert outcomes["censored"][0]["exit_fill_observed"] is False
    assert outcomes["censored"][0]["win_loss_marker"] == "not_applicable_censored"


def test_quote_collection_preserves_exact_open_contract_identities(tmp_path) -> None:
    ledger_path = tmp_path / "forward_walk_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "open_positions": [
                    {
                        "symbol": "AMD",
                        "expiry": "2026-08-14",
                        "option_type": "call",
                        "strike": 180.0,
                    },
                    {
                        "symbol": "AMD",
                        "expiry": "2026-08-14",
                        "option_type": "call",
                        "strike": 180.0,
                    },
                    {
                        "symbol": "MU",
                        "expiry": "2026-08-21",
                        "option_type": "put",
                        "strike": 150.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    requirements = load_open_contract_requirements(ledger_path)

    assert requirements == {
        "AMD": (("2026-08-14", "call", 180.0),),
        "MU": (("2026-08-21", "put", 150.0),),
    }


def test_prospective_entry_guard_enforces_stress_concentration_and_adversarial_verdicts() -> (
    None
):
    positions = [{"symbol": "SPY", "entry_fill": 10.0}]
    reasons = prospective_entry_rejection_reasons(
        positions,
        "SPY",
        "long_call",
        5.0,
        {
            "long_call_entry_bias": "neutral",
            "gamma_regime": "short_gamma_dislocation",
            "surface_tear_present": True,
        },
        {},
        {"open_position_count": 1, "stress_status": "book_fails_scenario"},
    )

    assert "unverified_existing_book_stress_integrity" in reasons
    assert "projected_entry_does_not_repair_existing_premium_concentration" in reasons
    assert (
        "adversarial_entry_verdict_would_reduce_but_one_contract_cannot_be_reduced"
        in reasons
    )


def test_forward_portfolio_caps_are_fail_closed(tmp_path, monkeypatch) -> None:
    signals_path = tmp_path / "signals.jsonl"
    context_path = tmp_path / "entry_context.jsonl"
    monkeypatch.setattr(walk, "DIRECTIONAL_SETUP_SIGNALS_PATH", signals_path)
    monkeypatch.setattr(walk, "ENTRY_CONTEXT_PATH", context_path)

    def rejection_for(
        existing: list[dict[str, str]],
        symbol: str,
        strategy: str,
        max_open: int,
        max_sector: int,
        max_direction: int,
    ) -> str:
        signal = {
            "signal_id": f"sig-{symbol}-{strategy}",
            "symbol": symbol,
            "candidate_strategy": strategy,
            "signal_date": "2026-07-08",
            "data_source_tier": "local_real_history",
            "confidence_proxy": 0.9,
            "source_signal_family": "test",
        }
        signals_path.write_text(json.dumps(signal) + "\n", encoding="utf-8")
        context_path.write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "snapshot_date": "2026-07-09",
                    "external_context_status": "complete",
                    "long_call_entry_bias": "neutral",
                    "long_put_entry_bias": "neutral",
                    "long_call_veto_reasons": [],
                    "long_put_veto_reasons": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        side = "call" if strategy == "long_call" else "put"
        snapshot = {
            "rows": [
                {
                    "symbol": symbol,
                    "expiry": "2026-08-07",
                    "dte_calendar": 29,
                    "option_type": side,
                    "strike": 100.0,
                    "bid": 4.0,
                    "ask": 4.2,
                    "volume": 20,
                    "open_interest": 100,
                    "implied_vol": 0.2,
                    "underlying_spot": 100.0,
                }
            ]
        }
        # Entry-time stress now prices the existing book in-process, so ledger
        # positions must carry the full contract fields real positions have.
        full_positions = [
            {
                "position_id": f"fw-{spec['symbol']}-{spec['candidate_strategy']}-2026-07-01-{index:05d}",
                "option_type": "call"
                if spec["candidate_strategy"] == "long_call"
                else "put",
                "strike": 100.0,
                "expiry": "2026-08-07",
                "entry_date": "2026-07-01",
                "entry_fill": 4.2,
                "entry_spot": 100.0,
                "entry_iv": 0.2,
                **spec,
            }
            for index, spec in enumerate(existing, start=1)
        ]
        ledger = {
            "open_positions": full_positions,
            "closed_trades": [],
            "last_marking_date": "",
        }
        monkeypatch.setattr(walk, "MAX_OPEN_POSITIONS", max_open)
        monkeypatch.setattr(walk, "MAX_POSITIONS_PER_SECTOR", max_sector)
        monkeypatch.setattr(walk, "MAX_POSITIONS_PER_DIRECTION", max_direction)
        assert walk._open_new_positions(ledger, snapshot, "2026-07-09") == []
        return str(ledger["last_entry_rejections"][0]["reason_codes"][0])

    spy_call = {"symbol": "SPY", "candidate_strategy": "long_call"}
    aapl_call = {"symbol": "AAPL", "candidate_strategy": "long_call"}
    assert (
        rejection_for([spy_call], "SPY", "long_put", 12, 3, 8) == "symbol_already_open"
    )
    assert (
        rejection_for([spy_call], "XLF", "long_put", 1, 3, 8)
        == "portfolio_open_position_cap_reached"
    )
    assert (
        rejection_for([aapl_call], "MSFT", "long_put", 12, 1, 8)
        == "portfolio_sector_cap_reached"
    )
    assert (
        rejection_for([aapl_call], "XLF", "long_call", 12, 3, 1)
        == "portfolio_direction_cap_reached"
    )


def test_baseline_arbitration_uses_paired_month_cluster_inference(monkeypatch) -> None:
    months = [
        "2025-01",
        "2025-02",
        "2025-03",
        "2025-04",
        "2025-05",
        "2025-06",
        "2025-07",
        "2025-08",
        "2025-09",
        "2025-10",
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
    ]
    real_trades: list[dict[str, object]] = []
    baseline_trades: list[dict[str, object]] = []
    for index in range(30):
        trade_id = f"real-{index:03d}"
        month = months[index % len(months)]
        real_trades.append(
            {
                "trade_id": trade_id,
                "signal_family": "quality",
                "candidate_strategy": "long_call",
                "path_pnl": 1.0,
            }
        )
        baseline_trades.append(
            {
                "comparison_cohort_id": "quality|long_call",
                "comparison_trade_id": trade_id,
                "comparison_anchor_month": month,
                "path_pnl": 0.0,
            }
        )
    monkeypatch.setattr(baseline_arbitration, "BOOTSTRAP_ITERATIONS", 200)

    verdicts = baseline_arbitration._verdicts(real_trades, baseline_trades)

    assert len(verdicts) == 1
    assert verdicts[0]["matched_pair_count"] == 30
    assert verdicts[0]["month_cluster_count"] == 15
    assert verdicts[0]["beats_baseline_ci"] is True
    assert verdicts[0]["bootstrap_resampling_unit"] == "anchor_month_cluster"
    assert verdicts[0]["multiple_testing_method"] == "bonferroni"
    with pytest.raises(ValueError, match="baseline pairing is incomplete"):
        baseline_arbitration._verdicts(real_trades, baseline_trades[:-1])


def test_era_diagnostics_surface_near_robust_cohort() -> None:
    rows = [
        {
            "era": "era-a",
            "sample_count": 40,
            "net_pnl": 5.0,
            "profit_factor": 1.2,
            "average_pnl": 0.125,
        },
        {
            "era": "era-b",
            "sample_count": 35,
            "net_pnl": 2.0,
            "profit_factor": 1.1,
            "average_pnl": 0.057,
        },
        {
            "era": "era-c",
            "sample_count": 45,
            "net_pnl": -1.0,
            "profit_factor": 0.9,
            "average_pnl": -0.022,
        },
    ]

    diagnostic = era_walk_forward._cohort_regime_diagnostic("quality|long_call", rows)

    assert diagnostic["diagnostic_status"] == "near_robust_two_of_three_eras"
    assert diagnostic["passing_era_count"] == 2
    assert diagnostic["regime_robust"] is False
    assert diagnostic["failing_eras"][0]["reason_codes"] == [
        "net_pnl_not_positive",
        "profit_factor_not_above_one",
    ]


def test_energy_put_requires_current_external_context_and_respects_conflict_risk() -> (
    None
):
    partial_conflict_context = {
        "status": "blocked_news_manifest_not_complete",
        "geopolitical_conflict_event_count_7d": 22,
        "energy_supply_event_count_7d": 5,
        "energy_theme_context_score": 0.035792,
    }
    conflict_context = {
        "status": "complete",
        "geopolitical_conflict_event_count_7d": 22,
        "energy_supply_event_count_7d": 5,
        "energy_theme_context_score": 0.035792,
    }

    assert _external_entry_veto_reasons(
        "XLE", "long_put", partial_conflict_context
    ) == (
        "energy_short_external_context_unavailable",
        "geopolitical_or_supply_risk_opposes_energy_short",
    )
    assert _external_entry_veto_reasons("XLE", "long_put", conflict_context) == (
        "geopolitical_or_supply_risk_opposes_energy_short",
    )
    assert _external_entry_veto_reasons("XLK", "long_put", conflict_context) == ()


def test_required_official_news_coverage_survives_supplemental_index_failure() -> None:
    treasury_html = b"""
    <time datetime="2026-07-13T14:30:00Z">July 13, 2026</time>
    <a href="/news/press-releases/sb0559">Treasury Sanctions Ransomware Infrastructure</a>
    """
    treasury_events = parse_treasury_press_releases(treasury_html, TREASURY_SPEC)
    assert len(treasury_events) == 1
    assert treasury_events[0]["source_id"] == "us_treasury_press_releases"
    statuses = [
        {
            "source_id": source_id,
            "source_type": "official_rss",
            "authority": "official_us_government",
            "status": "staged",
        }
        for source_id in sorted(REQUIRED_SOURCE_IDS)
    ]
    statuses.extend(
        {
            "source_id": source_id,
            "source_type": "global_news_index",
            "authority": "secondary_global_coverage_index",
            "status": "failed_after_retries_or_parse",
        }
        for source_id in sorted(SUPPLEMENTAL_SOURCE_IDS)
    )

    coverage = news_source_coverage(statuses)

    assert coverage["pipeline_status"] == "complete"
    assert coverage["required_coverage_complete"] is True
    assert coverage["supplemental_source_failure_ids"] == ["gdelt_doc_2"]


def test_walk_discipline_halt_latches() -> None:
    losing = [
        {
            "path_pnl": -1.0,
            "entry_fill": 2.0,
            "position_id": f"p{i}",
            "signal_id": f"s{i}",
            "outcome_integrity_class": "validated_forward_outcome",
        }
        for i in range(5)
    ]
    ledger = {"open_positions": [], "closed_trades": losing, "last_marking_date": ""}
    first = walk._discipline_halt(ledger)
    assert first is not None and "loss_streak" in first
    ledger["last_discipline_halt"] = {
        "date": "2026-07-09",
        "reason": first,
        "cooldown_sessions_remaining": 3,
    }
    ledger["closed_trades"] = ledger["closed_trades"][:-1] + [
        {
            "path_pnl": 5.0,
            "entry_fill": 2.0,
            "position_id": "p5",
            "outcome_integrity_class": "validated_forward_outcome",
        }
    ]
    assert walk._discipline_halt(ledger) is not None  # latched despite window shifting


def test_walk_completed_halt_rearms_only_on_new_closed_evidence() -> None:
    losing = [
        {
            "path_pnl": -1.0,
            "entry_fill": 2.0,
            "exit_date": "2026-07-10",
            "position_id": f"p{i}",
            "signal_id": f"s{i}",
            "outcome_integrity_class": "validated_forward_outcome",
        }
        for i in range(5)
    ]
    ledger = {
        "open_positions": [],
        "closed_trades": losing,
        "last_marking_date": "2026-07-10",
        "last_discipline_halt": {
            "date": "2026-07-10",
            "reason": "loss_streak_halt_5_consecutive",
            "cooldown_sessions_remaining": 0,
            "closed_trade_count_at_halt": 5,
        },
    }

    assert walk._discipline_halt(ledger) is None

    ledger["closed_trades"].append(
        {
            "path_pnl": -1.0,
            "entry_fill": 2.0,
            "exit_date": "2026-07-20",
            "position_id": "p-new-loss",
            "signal_id": "new-loss",
            "outcome_integrity_class": "validated_forward_outcome",
        }
    )
    assert (
        walk._discipline_halt(ledger) == "drawdown_halt_exceeds_30pct_of_premium_spent"
    )


def test_walk_halt_anchor_counts_only_validated_closed_evidence() -> None:
    validated = [
        {
            "path_pnl": -1.0,
            "entry_fill": 2.0,
            "exit_date": "2026-07-10",
            "position_id": f"validated-{index}",
            "signal_id": f"validated-signal-{index}",
            "outcome_integrity_class": "validated_forward_outcome",
        }
        for index in range(5)
    ]
    censored = [
        {
            "path_pnl": -10.0,
            "entry_fill": 2.0,
            "exit_date": "2026-07-10",
            "position_id": f"censored-{index}",
            "signal_id": f"censored-signal-{index}",
            "outcome_integrity_class": "censored_missing_quote_continuity",
        }
        for index in range(20)
    ]
    ledger = {
        "open_positions": [],
        "closed_trades": [*validated, *censored],
        "censored_positions": [],
        "last_marking_date": "2026-07-10",
    }

    latch = walk._new_discipline_halt(
        ledger,
        "2026-07-10",
        "loss_streak_halt_5_consecutive",
    )

    assert latch["closed_trade_count_at_halt"] == 5


def test_supervisor_regression_diff() -> None:
    previous = {"a": "completed", "b": "completed", "c": "failed_absorbed"}
    current = {"a": "failed_absorbed", "b": "completed", "c": "completed"}
    regressions, recoveries = diff_stage_states(previous, current)
    assert regressions == ["a"] and recoveries == ["c"]


def test_entry_time_stress_is_computed_fresh_and_count_matched(
    monkeypatch,
) -> None:
    """The entry guard's stress evidence must be computed on the CURRENT book.

    Regression: the walk used to read yesterday's stress artifact, whose
    open_position_count mismatched today's post-exit book on any day the book
    changed size, rejecting every candidate (stale_existing_book_stress_evidence)
    and permanently jamming refill.
    """
    import copy

    from dopey_risk_engine import adversarial_stress_engine as stress_module
    from dopey_risk_engine.forward_entry_guard import (
        existing_book_stress_rejection_reasons,
    )

    positions = [
        {
            "position_id": "fw-TESTA-long_call-2026-07-01-00001",
            "symbol": "TESTA",
            "option_type": "call",
            "strike": 100.0,
            "expiry": "2026-08-15",
            "entry_date": "2026-07-01",
            "entry_fill": 3.5,
            "entry_spot": 100.0,
            "entry_iv": 0.30,
        },
        {
            "position_id": "fw-TESTB-long_put-2026-07-01-00002",
            "symbol": "TESTB",
            "option_type": "put",
            "strike": 50.0,
            "expiry": "2026-08-15",
            "entry_date": "2026-07-01",
            "entry_fill": 2.0,
            "entry_spot": 50.0,
            "entry_iv": 0.40,
        },
    ]
    monkeypatch.setattr(
        stress_module,
        "load_latest_chain_snapshot",
        lambda: {
            "chain_snapshot_status": "blocked_no_real_chain_data_staged",
            "snapshot_date": "",
            "files_loaded": 0,
            "row_count": 0,
            "symbols": [],
            "reason_codes": [],
            "rows": [],
            "quote_derived": False,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    before = copy.deepcopy(positions)
    summary = stress_module.compute_book_stress(positions)

    # Fresh evidence is count-matched by construction: never stale, never missing.
    assert summary["open_position_count"] == len(positions)
    assert summary["source_forward_book_position_count"] == len(positions)
    assert len(summary["source_forward_book_position_ids_hash"]) == 64
    assert len(summary["source_forward_book_snapshot_hash"]) == 64
    assert summary["stress_policy_version"] == "dopey-adversarial-stress-policy-v2"
    assert len(summary["stress_policy_hash"]) == 64
    assert len(summary["source_quote_snapshot_hash"]) == 64
    assert summary["source_quote_matched_contract_count"] + summary[
        "source_quote_fallback_contract_count"
    ] == len(positions)
    reasons = existing_book_stress_rejection_reasons(positions, summary)
    assert "stale_existing_book_stress_evidence" not in reasons
    assert "missing_existing_book_stress_evidence" not in reasons
    assert "unusable_current_quote_stress_evidence" in reasons

    # Quote enrichment happens on a deep copy; the caller's ledger is untouched.
    assert positions == before

    # Empty book: trivially green and guard-clean.
    empty_summary = stress_module.compute_book_stress([])
    assert empty_summary["stress_status"] == "no_open_positions_book_trivially_survives"
    assert empty_summary["source_forward_book_position_count"] == 0
    assert len(empty_summary["source_forward_book_position_ids_hash"]) == 64
    assert len(empty_summary["source_forward_book_snapshot_hash"]) == 64
    assert empty_summary["source_quote_snapshot_status"] == "not_required_empty_book"
    assert existing_book_stress_rejection_reasons([], empty_summary) == ()


def test_concentration_only_stress_breach_delegates_to_concentration_guard() -> None:
    """A concentration-only breach must not blanket-block entries.

    Exits shrink and concentrate the book; only dilution by non-breaching
    entries can repair it, and concentration_rejection_reasons governs that
    candidate-by-candidate. Scenario-level vulnerability still blanket-blocks.
    """
    from dopey_risk_engine.forward_entry_guard import (
        existing_book_stress_rejection_reasons,
    )
    from dopey_research_pipeline.quality_ledger import reproducibility_hash
    from dopey_risk_engine.adversarial_stress_engine import (
        build_forward_book_binding,
        build_stress_policy_binding,
    )

    positions = [{"symbol": "MU", "entry_fill": 10.0}]
    concentration_only = {
        "artifact_type": "adversarial_stress_summary",
        "open_position_count": 1,
        "stress_status": "book_vulnerable_repair_required",
        "scenario_stress_green": True,
        "concentration_green": False,
        "source_quote_snapshot_status": "real_chain_snapshot_validated",
        "source_quote_snapshot_date": "2026-07-24",
        "source_quote_snapshot_hash": "a" * 64,
        "source_quote_matched_contract_count": 1,
        "source_quote_fallback_contract_count": 0,
        "paper_only": True,
        "live_blocked": True,
        **build_forward_book_binding(positions),
        **build_stress_policy_binding(),
    }
    concentration_only["reproducibility_hash"] = reproducibility_hash(
        concentration_only
    )
    assert existing_book_stress_rejection_reasons(positions, concentration_only) == ()

    # a diluting candidate passes end-to-end; a worsening one still refuses
    diluting = prospective_entry_rejection_reasons(
        positions,
        "AAPL",
        "long_call",
        5.0,
        {"long_call_entry_bias": "neutral"},
        {},
        concentration_only,
    )
    assert "existing_book_stress_not_green" not in diluting
    worsening = prospective_entry_rejection_reasons(
        positions,
        "MU",
        "long_call",
        5.0,
        {"long_call_entry_bias": "neutral"},
        {},
        concentration_only,
    )
    assert "projected_entry_does_not_repair_existing_premium_concentration" in worsening

    # scenario-level vulnerability still blanket-blocks
    scenario_breach = {**concentration_only, "scenario_stress_green": False}
    scenario_breach.pop("reproducibility_hash")
    scenario_breach["reproducibility_hash"] = reproducibility_hash(scenario_breach)
    assert existing_book_stress_rejection_reasons(positions, scenario_breach) == (
        "existing_book_stress_not_green",
    )
    # missing flags fail closed
    legacy = {
        "open_position_count": 1,
        "stress_status": "book_vulnerable_repair_required",
    }
    assert existing_book_stress_rejection_reasons(positions, legacy) == (
        "unverified_existing_book_stress_integrity",
    )
