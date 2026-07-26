"""Adversarial proof for empirical squeeze/bubble epistemic gates."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dopey_squeeze_bubble.engine import evaluate_symbol
from dopey_squeeze_bubble.intake import (
    EvidencePathContainmentError,
    IntelligencePaths,
    _contradiction_flags,
    load_symbol_evidence,
)
from dopey_squeeze_bubble.models import (
    EmpiricalIntegrityEvidence,
    FundamentalEvidence,
    MarketLeverageEvidence,
    OptionsPressureEvidence,
    SettlementEvidence,
    ShortCrowdingEvidence,
    SymbolEvidence,
    TechnicalState,
    default_policy,
)


def _integrity(
    contradictions: tuple[str, ...],
    stale_lanes: tuple[str, ...],
    technical_age_days: int,
) -> EmpiricalIntegrityEvidence:
    return EmpiricalIntegrityEvidence(
        observed_at_utc="2026-07-25T00:00:00+00:00",
        path_containment_verified=True,
        technical_source_id="local:EMPIRICAL.csv:sha256:history",
        lane_age_days=(
            ("borrow", 1),
            ("fails_to_deliver", 2),
            ("fundamentals", 1),
            ("market_leverage", 24),
            ("options", 1),
            ("short_crowding", 1),
            ("short_flow", 1),
            ("technical", technical_age_days),
        ),
        lane_observation_counts=(
            ("borrow", 1),
            ("fails_to_deliver", 5),
            ("fundamentals", 1),
            ("market_leverage", 13),
            ("options", 1),
            ("short_crowding", 2),
            ("short_flow", 5),
            ("technical", 300),
        ),
        stale_lanes=stale_lanes,
        future_dated_lanes=(),
        contradiction_flags=contradictions,
    )


def _evidence(integrity: EmpiricalIntegrityEvidence) -> SymbolEvidence:
    return SymbolEvidence(
        symbol="EMPIRICAL",
        technical=TechnicalState(
            as_of_date="2026-07-24",
            close=100.0,
            average_dollar_volume_20d=120_000_000.0,
            average_dollar_volume_5d=180_000_000.0,
            dollar_volume_ratio_5d_20d=1.5,
            signed_volume_pressure_20d=0.45,
            return_5d=0.18,
            return_20d=0.35,
            return_63d=0.50,
            return_252d=1.20,
            volume_ratio_20d=2.4,
            distance_sma20=0.25,
            distance_sma50=0.40,
            distance_sma200=0.90,
            distance_52w_high=-0.01,
            realized_vol_20d=0.80,
            realized_vol_ratio_20d_60d=1.4,
            rsi14=78.0,
            breakout_20d=True,
            breakdown_20d=False,
        ),
        short_crowding=ShortCrowdingEvidence(
            as_of_date="2026-07-24",
            shares_short=8_000_000.0,
            shares_short_prior_month=5_000_000.0,
            short_percent_float=0.40,
            days_to_cover=10.0,
            float_shares=20_000_000.0,
            shares_outstanding=25_000_000.0,
            institutional_ownership=0.60,
            insider_ownership=0.10,
            average_volume=800_000.0,
            borrow_fee_percent=65.0,
            borrow_utilization=0.99,
            borrow_available_shares=10_000.0,
            daily_short_volume_ratio=0.65,
            daily_short_volume_observations=5,
            daily_short_volume_elevated_sessions=5,
            daily_short_volume_median_ratio=0.65,
            daily_short_volume_ratio_dispersion=0.02,
            source_ids=(
                "local:short.csv:sha256:short",
                "local:flow.csv:sha256:flow",
                "local:borrow.csv:sha256:borrow",
            ),
        ),
        settlement=SettlementEvidence(
            as_of_date="20260723",
            latest_fails=300_000.0,
            fails_to_float=0.012,
            observation_count=5,
            elevated_fail_sessions=5,
            threshold_condition_proxy=True,
            official_threshold_listed=True,
            source_ids=("local:ftd.csv:sha256:ftd",),
        ),
        fundamentals=FundamentalEvidence(
            as_of_date="2026-07-24",
            theme="technology",
            market_cap=1_000_000_000.0,
            enterprise_value=900_000_000.0,
            total_revenue=500_000_000.0,
            trailing_pe=30.0,
            forward_pe=25.0,
            price_to_sales=2.0,
            price_to_book=3.0,
            profit_margin=0.10,
            revenue_growth=0.20,
            free_cashflow=50_000_000.0,
            total_debt=100_000_000.0,
            total_cash=150_000_000.0,
            first_trade_date="2015-01-02",
            days_since_first_trade=4210,
            ipo_offer_price=None,
            ipo_offer_amount=None,
            ipo_status="",
            source_ids=("local:fundamentals.csv:sha256:fundamentals",),
        ),
        options=OptionsPressureEvidence(
            as_of_date="2026-07-24",
            quote_derived=True,
            contract_rows=200,
            call_open_interest=500_000.0,
            put_open_interest=100_000.0,
            call_volume=150_000.0,
            put_volume=15_000.0,
            put_call_open_interest_ratio=0.20,
            put_call_volume_ratio=0.10,
            total_gex_dollar_per_pct=-50_000_000.0,
            gamma_flip_strike=100.0,
            atm_implied_vol=0.90,
            source_ids=("local:options.jsonl:sha256:options",),
        ),
        market_leverage=MarketLeverageEvidence(
            as_of_month="2026-07-01",
            margin_debit_millions=1_500_000.0,
            free_credit_millions=390_000.0,
            debit_to_free_credit_ratio=3.85,
            debit_growth_3m=0.15,
            debit_growth_12m=0.40,
            observation_count=13,
            source_ids=("local:margin.csv:sha256:margin",),
        ),
        integrity=integrity,
    )


def test_empirical_squeeze_exposes_persistence_robustness_and_proxy_limits() -> None:
    assessment = evaluate_symbol(_evidence(_integrity((), (), 1)), default_policy())
    squeeze = assessment["squeeze"]

    assert squeeze["status"] == "squeeze_candidate_requires_existing_execution_gates"
    assert squeeze["persistence_score"] >= default_policy().minimum_squeeze_persistence
    assert squeeze["robustness"]["robustness_score"] >= (
        default_policy().minimum_lane_robustness
    )
    assert squeeze["observed_liquidity_stress"]["score"] > 0.0
    assert (
        squeeze["observed_liquidity_stress"]["direct_hidden_liquidity_observed"]
        is False
    )
    assert squeeze["geometry"]["forecast_price_generated"] is False
    assert squeeze["geometry"]["target_price"] is None
    assert assessment["order_construction_allowed"] is False


def test_contradictory_or_stale_evidence_forces_abstention() -> None:
    baseline = _evidence(_integrity((), (), 1))
    contradictory_short = replace(
        baseline.short_crowding,
        short_percent_float=0.10,
    )
    contradiction_flags = _contradiction_flags(
        contradictory_short,
        baseline.settlement,
        baseline.fundamentals,
        baseline.options,
    )
    contradiction = replace(
        baseline,
        short_crowding=contradictory_short,
        integrity=replace(
            baseline.integrity,
            contradiction_flags=contradiction_flags,
        ),
    )
    contradicted = evaluate_symbol(contradiction, default_policy())["squeeze"]
    assert contradicted["status"] == "squeeze_watch_or_blocked"
    assert "contradictory_squeeze_evidence" in contradicted["gate_reasons"]
    assert contradicted["robustness"]["contradiction_penalty"] > 0.0

    stale = _evidence(_integrity((), ("technical",), 30))
    stale_lane = evaluate_symbol(stale, default_policy())["squeeze"]
    assert stale_lane["status"] == "squeeze_watch_or_blocked"
    assert "stale_evidence_detected_and_excluded" in stale_lane["gate_reasons"]
    assert "technical_evidence_stale_or_missing" in stale_lane["gate_reasons"]


def test_evidence_path_escape_fails_before_any_lane_read(tmp_path: Path) -> None:
    root = tmp_path / "governed"
    root.mkdir()
    outside_history = tmp_path / "outside"
    outside_history.mkdir()
    inside = root / "missing"
    paths = IntelligencePaths(
        repository_root=root,
        history_root=outside_history,
        short_crowding_path=inside / "short.csv",
        short_flow_path=inside / "flow.csv",
        fundamentals_path=inside / "fundamentals.csv",
        ftd_path=inside / "ftd.csv",
        borrow_path=inside / "borrow.csv",
        threshold_path=inside / "threshold.csv",
        margin_path=inside / "margin.csv",
        ipo_calendar_path=inside / "ipo.csv",
        chain_metrics_path=inside / "options.jsonl",
    )

    with pytest.raises(EvidencePathContainmentError, match="escapes repository root"):
        load_symbol_evidence(
            paths,
            observed_at=datetime(
                2026,
                7,
                25,
                tzinfo=timezone.utc,
            ),
            maximum_source_age_days=45,
        )
