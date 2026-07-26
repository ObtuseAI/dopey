from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from dopey_equity_swing.contract_selector import (
    black_scholes_delta,
    load_option_chain_snapshot,
    load_short_rate,
    select_strategic_contracts,
)
from dopey_equity_swing.context_evidence import (
    append_context_decision_records,
    build_context_decision_records,
    build_context_decision_velocity,
    build_context_evidence_gate,
)
from dopey_equity_swing.context_outcomes import resolve_decision_path
from dopey_equity_swing.cross_asset import (
    build_cross_asset_regime,
    build_series_state,
    load_cross_asset_snapshot,
)
from dopey_equity_swing.fundamentals import (
    load_earnings_dates,
    resolve_fundamental_snapshot,
    score_fundamental_snapshot,
)
from dopey_equity_swing.market_structure import (
    Bar,
    analyze_multi_timeframe_structure,
    confirmed_pivots,
    resample_bars,
)
from dopey_equity_swing.reverse_engineering import (
    build_retrospective_events,
    mine_strategy_candidates,
)
from dopey_equity_swing.news_context import (
    apply_external_context,
    build_news_intelligence,
    load_news_snapshot,
)
from dopey_equity_swing.snapshot_resolution import (
    build_earnings_evidence,
    resolve_earnings_snapshot,
    resolve_option_snapshot,
)
from dopey_equity_swing.thesis import build_equity_swing_thesis
from dopey_market_intake.macro_context_gate import (
    load_macro_lanes,
    run_macro_context_gate,
)


def _bars(count: int, drift: float) -> list[Bar]:
    start = date(2020, 1, 1)
    rows: list[Bar] = []
    for index in range(count):
        close = 100.0 + drift * index + 2.0 * ((index % 20) / 20.0)
        rows.append(
            Bar(
                date=(start + timedelta(days=index)).isoformat(),
                open=close - 0.25,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                adjusted_close=close,
                volume=1_000_000 + index * 1_000,
            )
        )
    return rows


def test_missing_fundamental_subscores_fail_closed_to_no_trade() -> None:
    rows = _bars(420, 0.12)
    structure = analyze_multi_timeframe_structure("TEST", rows)

    thesis = build_equity_swing_thesis(
        "TEST",
        rows,
        structure,
        {"bullish_score": 1.0, "bearish_score": 0.0},
        {},
        None,
    )

    assert thesis["trade_intent"] == "no_trade"
    assert "missing_or_invalid_fundamental_support_scores" in thesis["reason_codes"]


def test_resampling_and_pivots_preserve_confirmation_timing() -> None:
    rows = _bars(20, 0.0)
    rows[7]["high"] = 130.0
    pivots = confirmed_pivots(rows, 2)
    resistance = next(
        pivot
        for pivot in pivots
        if pivot["pivot_date"] == rows[7]["date"] and pivot["role"] == "resistance"
    )
    assert resistance["confirmed_at"] == rows[9]["date"]
    weekly = resample_bars(rows, "weekly")
    assert len(weekly) < len(rows)
    assert sum(row["volume"] for row in weekly) == sum(row["volume"] for row in rows)


def test_multi_timeframe_structure_is_paper_only_and_intraday_honest() -> None:
    result = analyze_multi_timeframe_structure("TEST", _bars(420, 0.08))
    assert result["structure_status"] == "complete"
    assert result["paper_only"] is True
    assert result["live_blocked"] is True
    assert (
        result["intraday_timeframes_status"]
        == "unavailable_no_local_intraday_history_not_synthesized"
    )
    assert {record["timeframe"] for record in result["timeframes"]} == {
        "daily",
        "weekly",
        "monthly",
    }


def test_fundamentals_are_peer_relative_and_confirmation_only() -> None:
    rows = [
        _fundamental(
            "STRONG", 0.30, 0.25, 12.0, 2_000_000_000.0, 100_000_000.0, 300_000_000.0
        ),
        _fundamental(
            "WEAK", -0.20, -0.15, 55.0, -500_000_000.0, 900_000_000.0, 50_000_000.0
        ),
    ]
    scored = score_fundamental_snapshot(rows, date(2026, 1, 2))
    assert (
        scored["STRONG"]["bullish_support_score"]
        > scored["WEAK"]["bullish_support_score"]
    )
    assert scored["STRONG"]["directional_use"] == "confirmation_or_contradiction_only"
    assert scored["WEAK"]["live_blocked"] is True
    assert scored["STRONG"]["future_observation_consumed"] is False


def test_loss_maker_negative_pe_is_not_rewarded_as_cheap_valuation() -> None:
    rows = [
        _fundamental("PROFITABLE", 0.20, 0.20, 20.0, 1_000_000_000.0, 1.0, 2.0),
        _fundamental("PEER30", 0.20, 0.20, 30.0, 1_000_000_000.0, 1.0, 2.0),
        _fundamental("PEER40", 0.20, 0.20, 40.0, 1_000_000_000.0, 1.0, 2.0),
        _fundamental("PEER50", 0.20, 0.20, 50.0, 1_000_000_000.0, 1.0, 2.0),
        _fundamental("PEER60", 0.20, 0.20, 60.0, 1_000_000_000.0, 1.0, 2.0),
        _fundamental("LOSSMAKER", -0.20, -0.30, -18.0, -500_000_000.0, 2.0, 1.0),
    ]

    scored = score_fundamental_snapshot(rows, date(2026, 1, 2))

    assert scored["LOSSMAKER"]["valuation_support_score"] <= 0.5
    assert scored["LOSSMAKER"]["valuation_evidence_status"] == (
        "blocked_missing_positive_valuation_metrics"
    )
    assert (
        "nonpositive_forward_pe_not_meaningful" in scored["LOSSMAKER"]["reason_codes"]
    )
    assert (
        scored["LOSSMAKER"]["valuation_support_score"]
        < scored["PROFITABLE"]["valuation_support_score"]
    )


def test_fundamentals_use_only_the_exact_market_frontier_slice(tmp_path: Path) -> None:
    path = tmp_path / "fundamentals.csv"
    header = ",".join(_fundamental("TEST", 0.1, 0.1, 20.0, 1.0, 1.0, 1.0))
    old_row = _fundamental("OLD", 0.1, 0.1, 20.0, 1.0, 1.0, 1.0)
    old_row["date"] = "2026-01-01"
    exact_row = _fundamental("EXACT", 0.1, 0.1, 20.0, 1.0, 1.0, 1.0)
    future_row = _fundamental("FUTURE", 0.1, 0.1, 20.0, 1.0, 1.0, 1.0)
    future_row["date"] = "2026-01-03"
    path.write_text(
        "\n".join(
            [
                header,
                ",".join(old_row.values()),
                ",".join(exact_row.values()),
                ",".join(future_row.values()),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = resolve_fundamental_snapshot(path, date(2026, 1, 2))

    assert snapshot["snapshot_date"] == "2026-01-02"
    assert snapshot["snapshot_row_count"] == 1
    assert snapshot["historical_row_count_excluded"] == 1
    assert snapshot["future_row_count_excluded"] == 1
    assert snapshot["maximum_staleness_calendar_days"] == 0
    assert [row["symbol"] for row in snapshot["rows"]] == ["EXACT"]
    assert set(score_fundamental_snapshot(snapshot["rows"], date(2026, 1, 2))) == {
        "EXACT"
    }

    with pytest.raises(ValueError, match="stale fallback is prohibited"):
        resolve_fundamental_snapshot(path, date(2026, 1, 4))
    with pytest.raises(ValueError, match="non-frontier observation"):
        score_fundamental_snapshot([future_row], date(2026, 1, 2))


def test_option_selector_inherits_equity_direction_and_only_ranks_contracts() -> None:
    thesis: dict[str, Any] = {
        "symbol": "TEST",
        "trade_intent": "long_call",
        "direction": "bullish",
        "expected_hold_trading_days": 10,
        "as_of_date": "2026-01-02",
        "earnings_date": None,
        "target_price": 115.0,
    }
    chain = [
        _contract(105.0, 2.0, 2.2, 42, 0.30, 500, 100),
        _contract(110.0, 1.0, 1.2, 42, 0.32, 700, 120),
    ]
    selection = select_strategic_contracts(thesis, chain, 0.04)
    assert selection["selection_status"] == "tracked_contracts_selected"
    assert selection["equity_thesis_direction"] == "bullish"
    assert selection["direction_inherited_not_recomputed"] is True
    assert selection["options_direction_weight"] == 0.0
    assert selection["contract_role"] == "strategic_tracking_only_no_order_authority"
    assert selection["chain_snapshot_identity_verified"] is True

    mismatched = [{**chain[0], "snapshot_date": "2026-01-03"}]
    blocked = select_strategic_contracts(thesis, mismatched, 0.04)
    assert blocked["selection_status"] == "blocked"
    assert blocked["block_reason"] == (
        "option_chain_identity_not_aligned_with_equity_thesis"
    )
    assert blocked["chain_snapshot_identity_verified"] is False


def test_swing_snapshots_resolve_current_hash_pinned_inputs_without_date_constants(
    tmp_path: Path,
) -> None:
    snapshot_date = date(2026, 7, 20)
    earnings_root = tmp_path / "dopey_data" / "real" / "raw" / "earnings_calendar"
    chain_root = tmp_path / "dopey_data" / "real" / "raw" / "options_chains"
    manifest_path = (
        tmp_path / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"
    )
    earnings_root.mkdir(parents=True)
    chain_path = chain_root / snapshot_date.isoformat() / "TEST_chain.csv"
    chain_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True)
    earnings_path = earnings_root / f"{snapshot_date.isoformat()}_earnings.csv"
    earnings_path.write_text(
        "snapshot_date,symbol,earnings_date,source\n"
        "2026-07-20,TEST,2026-08-01,validated_source\n",
        encoding="utf-8",
    )
    chain_path.write_text(
        "snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,mid,last,"
        "volume,open_interest,implied_vol,underlying_spot,source\n"
        "2026-07-20,TEST,2026-08-21,32,call,100,1,1.1,1.05,1.05,100,500,0.3,100,source\n",
        encoding="utf-8",
    )
    relative_chain = chain_path.relative_to(tmp_path).as_posix()
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": "2026-07-20T22:00:00+00:00",
                "snapshot_dates": [snapshot_date.isoformat()],
                "file_hashes": {
                    relative_chain: hashlib.sha256(chain_path.read_bytes()).hexdigest()
                },
                "not_live_data": True,
                "paper_only": True,
                "live_blocked": True,
            }
        ),
        encoding="utf-8",
    )

    earnings = resolve_earnings_snapshot(earnings_root, snapshot_date)
    options = resolve_option_snapshot(
        tmp_path,
        chain_root,
        manifest_path,
        snapshot_date,
        datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert earnings["snapshot_date"] == snapshot_date.isoformat()
    assert earnings["path"] == earnings_path
    assert earnings["symbol_count"] == 1
    assert earnings["covered_symbols"] == ("TEST",)
    assert build_earnings_evidence(earnings, "TEST", "2026-08-01") == {
        "snapshot_date": snapshot_date.isoformat(),
        "snapshot_sha256": earnings["sha256"],
        "snapshot_symbol_count": 1,
        "symbol_covered": True,
        "next_earnings_date": "2026-08-01",
        "source_labels": ["validated_source"],
        "status": "frontier_aligned_symbol_event_observed",
        "live_candidate_event_gate_passed": True,
    }
    assert build_earnings_evidence(earnings, "AAPL", None)["status"] == (
        "unresolved_symbol_absence"
    )
    assert options["status"] == "current_hash_pinned_option_snapshot"
    assert options["path"] == chain_path.parent
    assert options["chain_file_count"] == 1
    assert options["manifest_chain_file_count"] == 1
    assert options["chain_row_count"] == 1
    assert (
        load_option_chain_snapshot(chain_path.parent, snapshot_date)["TEST"][0][
            "snapshot_date"
        ]
        == snapshot_date.isoformat()
    )

    chain_path.write_text(
        chain_path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8"
    )
    blocked = resolve_option_snapshot(
        tmp_path,
        chain_root,
        manifest_path,
        snapshot_date,
        datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    assert blocked["status"] == "blocked_no_current_hash_pinned_option_snapshot"
    assert blocked["path"] is None
    assert blocked["blocker"].startswith("chain_hash_mismatch:")


def test_option_manifest_rejects_missing_and_unexpected_chain_files(
    tmp_path: Path,
) -> None:
    snapshot_date = date(2026, 7, 20)
    chain_root = tmp_path / "dopey_data" / "real" / "raw" / "options_chains"
    snapshot_root = chain_root / snapshot_date.isoformat()
    snapshot_root.mkdir(parents=True)
    manifest_path = tmp_path / "options_data_manifest.json"
    chain_path = snapshot_root / "TEST_chain.csv"
    chain_path.write_text(
        _option_chain_csv(snapshot_date.isoformat(), "TEST", "TEST", ""),
        encoding="utf-8",
    )
    chain_relative = chain_path.relative_to(tmp_path).as_posix()
    missing_relative = (
        (snapshot_root / "MISSING_chain.csv").relative_to(tmp_path).as_posix()
    )
    _write_option_manifest(
        manifest_path,
        snapshot_date,
        {
            chain_relative: hashlib.sha256(chain_path.read_bytes()).hexdigest(),
            missing_relative: "0" * 64,
        },
    )

    missing = resolve_option_snapshot(
        tmp_path,
        chain_root,
        manifest_path,
        snapshot_date,
        datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert missing["status"] == "blocked_no_current_hash_pinned_option_snapshot"
    assert missing["blocker"].startswith("manifest_chain_file_missing:")

    extra_path = snapshot_root / "EXTRA_chain.csv"
    extra_path.write_text(
        _option_chain_csv(snapshot_date.isoformat(), "EXTRA", "EXTRA", ""),
        encoding="utf-8",
    )
    _write_option_manifest(
        manifest_path,
        snapshot_date,
        {chain_relative: hashlib.sha256(chain_path.read_bytes()).hexdigest()},
    )
    unexpected = resolve_option_snapshot(
        tmp_path,
        chain_root,
        manifest_path,
        snapshot_date,
        datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert unexpected["status"] == "blocked_no_current_hash_pinned_option_snapshot"
    assert unexpected["blocker"].startswith("unexpected_chain_files_not_in_manifest:")


@pytest.mark.parametrize(
    ("row_snapshot_date", "row_symbol", "underlying_symbol"),
    [
        ("2026-07-19", "TEST", ""),
        ("2026-07-20", "WRONG", ""),
        ("2026-07-20", "TEST", "WRONG"),
    ],
)
def test_option_manifest_rejects_row_identity_mismatch(
    tmp_path: Path,
    row_snapshot_date: str,
    row_symbol: str,
    underlying_symbol: str,
) -> None:
    snapshot_date = date(2026, 7, 20)
    chain_root = tmp_path / "dopey_data" / "real" / "raw" / "options_chains"
    chain_path = chain_root / snapshot_date.isoformat() / "TEST_chain.csv"
    chain_path.parent.mkdir(parents=True)
    chain_path.write_text(
        _option_chain_csv(
            row_snapshot_date,
            row_symbol,
            "TEST",
            underlying_symbol,
        ),
        encoding="utf-8",
    )
    relative = chain_path.relative_to(tmp_path).as_posix()
    manifest_path = tmp_path / "options_data_manifest.json"
    _write_option_manifest(
        manifest_path,
        snapshot_date,
        {relative: hashlib.sha256(chain_path.read_bytes()).hexdigest()},
    )

    blocked = resolve_option_snapshot(
        tmp_path,
        chain_root,
        manifest_path,
        snapshot_date,
        datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert blocked["status"] == "blocked_no_current_hash_pinned_option_snapshot"
    assert blocked["path"] is None
    assert blocked["blocker"].startswith("chain_row_contract_invalid:")


def test_earnings_loader_uses_nearest_event_when_snapshot_lists_multiple(
    tmp_path,
) -> None:
    path = tmp_path / "earnings.csv"
    path.write_text(
        "snapshot_date,symbol,earnings_date,source\n"
        "2026-01-02,AAPL,2026-04-30,official_fixture\n"
        "2026-01-02,AAPL,2026-02-01,official_fixture\n",
        encoding="utf-8",
    )

    assert load_earnings_dates(path) == {"AAPL": "2026-02-01"}


def test_earnings_inside_hold_window_blocks_contract_tracking() -> None:
    thesis: dict[str, Any] = {
        "symbol": "TEST",
        "trade_intent": "long_put",
        "direction": "bearish",
        "expected_hold_trading_days": 10,
        "as_of_date": "2026-01-02",
        "earnings_date": "2026-01-08",
        "target_price": 85.0,
    }
    result = select_strategic_contracts(
        thesis, [_contract(95.0, 2.0, 2.2, 42, 0.30, 500, 100, "put")], 0.04
    )
    assert result["selection_status"] == "blocked"
    assert result["block_reason"] == "earnings_inside_expected_holding_window"


def test_reverse_engineering_is_retrospective_shadow_only() -> None:
    rows = _bars(260, 0.12)
    for index in range(250, 260):
        rows[index]["high"] += float(index - 249) * 2.0
        rows[index]["close"] += float(index - 249) * 1.5
    events = build_retrospective_events({"TEST": rows}, set(), 5, 10)
    assert events
    assert all(event["features_use_past_only"] is True for event in events)
    assert all(event["future_label_retrospective_only"] is True for event in events)
    candidates = mine_strategy_candidates(events, "2020-07-31")
    assert candidates
    assert all(
        candidate["strategy_promotion_allowed"] is False for candidate in candidates
    )
    assert all(
        candidate["paper_only"] is True and candidate["live_blocked"] is True
        for candidate in candidates
    )


def test_black_scholes_delta_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="requires positive"):
        black_scholes_delta(100.0, 100.0, 0, 0.04, 0.30, "call")


def test_short_rate_rejects_stale_treasury_curve(tmp_path: Path) -> None:
    path = tmp_path / "treasury_yield_curve.csv"
    path.write_text(
        "date,label,maturity_years,yield_pct\n"
        "2026-07-01,1Mo,0.083333,4.25\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside its recency boundary"):
        load_short_rate(path, date(2026, 7, 20))
    assert load_short_rate(path, date(2026, 7, 7)) == pytest.approx(0.0425)


def test_cross_asset_series_tracks_momentum_volatility_and_shock() -> None:
    rows = [
        {
            "date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
            "symbol": "ES",
            "name": "E-mini S&P 500",
            "asset_class": "futures",
            "subclass": "equity_index",
            "close": 5000.0 + index * 5.0,
            "volume": 1000,
            "source": "validated_test_source",
        }
        for index in range(80)
    ]
    decision_date = date.fromisoformat(rows[-1]["date"])
    state = build_series_state(rows, decision_date)
    assert state["directional_score"] > 0.0
    assert state["return_20"] > 0.0
    assert state["annualized_volatility_60d"] >= 0.0
    assert state["asset_class"] == "futures"
    assert state["series_status"] == "usable"


def test_news_context_requires_corroboration_and_preserves_equity_direction() -> None:
    decision_time = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    high_quality_domains = ("www.reuters.com", "apnews.com", "www.ft.com")
    events = [
        {
            "event_id": f"event-{index}",
            "source_id": "gdelt_doc_2",
            "source_type": "global_news_index",
            "source_authority": "secondary_global_coverage_index",
            "query_lane": "global_geopolitical_financial",
            "published_at": "2026-07-12T10:00:00+00:00",
            "title": f"Major oil blockade disruption expands in key strait report {index}",
            "summary": "",
            "url": f"https://{high_quality_domains[index]}/story",
            "source_domain": high_quality_domains[index],
        }
        for index in range(3)
    ]
    intelligence = build_news_intelligence(events, decision_time)
    assert intelligence["corroborated_alert_count"] == 1
    thesis: dict[str, Any] = {
        "symbol": "TEST",
        "direction": "bullish",
        "trade_intent": "long_call",
        "thesis_status": "actionable_shadow_thesis",
        "reason_codes": [],
    }
    regime = {
        "theme_context_scores": {"energy": -0.80},
        "risk_appetite_score": -0.40,
        "systemic_stress_score": 0.80,
    }
    evidence_gate = {
        "evidence_status": "blocked_insufficient_resolved_context_decisions",
        "defensive_veto_allowed": True,
        "positive_context_promotion_allowed": False,
        "context_sizing_allowed": False,
    }
    contextual = apply_external_context(
        thesis, "energy", regime, intelligence, evidence_gate
    )
    assert contextual["direction"] == "bullish"
    assert contextual["trade_intent"] == "no_trade"
    assert contextual["external_context"]["direction_unchanged"] is True
    assert contextual["external_context"]["context_direction_weight"] == 0.0
    assert contextual["external_context"]["positive_context_promotion_allowed"] is False


def test_future_news_is_rejected_from_decision_context() -> None:
    decision_time = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    future_event = {
        "event_id": "future-event",
        "source_id": "gdelt_doc_2",
        "source_type": "global_news_index",
        "source_authority": "secondary_global_coverage_index",
        "query_lane": "global_geopolitical_financial",
        "published_at": "2026-07-13T12:00:00+00:00",
        "title": "War blockade crisis expands",
        "summary": "",
        "url": "https://www.reuters.com/future-story",
        "source_domain": "www.reuters.com",
    }
    intelligence = build_news_intelligence([future_event], decision_time)
    assert intelligence["future_event_rejected_count"] == 1
    assert intelligence["fresh_7d_event_count"] == 0
    assert intelligence["recent_72h_event_count"] == 0


def test_news_conflict_category_rejects_metaphors_and_preserves_energy_disruption() -> (
    None
):
    decision_time = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    titles = (
        "Liquor gangs go to war in local dispute",
        "Stolen war medals returned to family",
        "Ceasefire collapses after strikes and oil waiver is revoked",
    )
    events = [
        {
            "event_id": f"event-{index}",
            "source_id": "gdelt_doc_2",
            "source_type": "global_news_index",
            "source_authority": "secondary_global_coverage_index",
            "query_lane": "global_geopolitical_financial",
            "published_at": "2026-07-12T10:00:00+00:00",
            "title": title,
            "summary": "",
            "url": f"https://example.com/{index}",
            "source_domain": "example.com",
        }
        for index, title in enumerate(titles)
    ]

    intelligence = build_news_intelligence(events, decision_time)

    assert intelligence["category_counts_7d"]["geopolitical_conflict"] == 1
    assert intelligence["category_counts_7d"]["energy_supply"] == 1


def test_cross_asset_staleness_blocks_series_use() -> None:
    rows = [
        {
            "date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
            "symbol": "ES",
            "name": "E-mini S&P 500",
            "asset_class": "futures",
            "subclass": "equity_index",
            "close": 5000.0 + index,
            "volume": 1000,
            "source": "validated_test_source",
            "series_type": "continuous_futures_proxy",
            "contract_metadata_status": "unavailable_provider_continuous_symbol",
        }
        for index in range(80)
    ]
    stale_decision_date = date.fromisoformat(rows[-1]["date"]) + timedelta(days=5)
    state = build_series_state(rows, stale_decision_date)
    assert state["series_status"] == "blocked"
    assert "stale_for_asset_calendar" in state["quality_flags"]


def test_context_evidence_gate_blocks_promotion_without_resolved_decisions(
    tmp_path: Path,
) -> None:
    cross_root = tmp_path / "cross"
    news_root = tmp_path / "news"
    cross_snapshot = cross_root / "20260712T120000Z" / "cross_asset_daily.csv"
    news_snapshot = news_root / "20260712T120000Z" / "news_events.jsonl"
    cross_snapshot.parent.mkdir(parents=True)
    news_snapshot.parent.mkdir(parents=True)
    cross_snapshot.write_text("date,symbol\n", encoding="utf-8")
    news_snapshot.write_text("{}\n", encoding="utf-8")
    (cross_snapshot.parent / "cross_asset_context_manifest.json").write_text(
        '{"dataset_status":"complete"}\n', encoding="utf-8"
    )
    (news_snapshot.parent / "news_context_manifest.json").write_text(
        '{"pipeline_status":"complete"}\n', encoding="utf-8"
    )
    gate = build_context_evidence_gate(
        cross_root,
        news_root,
        tmp_path / "news_ledger.jsonl",
        tmp_path / "decision_ledger.jsonl",
        tmp_path / "outcome_ledger.jsonl",
    )
    assert gate["evidence_status"] == "blocked_insufficient_resolved_context_decisions"
    assert gate["joint_snapshot_day_count"] == 1
    assert gate["calendar_duration_gate_enabled"] is False
    assert gate["minimum_snapshot_days"] is None
    assert (
        gate["snapshot_history_role"]
        == "provenance_and_research_telemetry_not_readiness_duration_gate"
    )
    assert gate["positive_context_promotion_allowed"] is False
    assert gate["context_sizing_allowed"] is False


def test_context_evidence_gate_does_not_require_calendar_duration(
    tmp_path: Path,
) -> None:
    cross_root = tmp_path / "cross"
    news_root = tmp_path / "news"
    cross_snapshot = cross_root / "20260712T120000Z" / "cross_asset_daily.csv"
    news_snapshot = news_root / "20260712T120000Z" / "news_events.jsonl"
    cross_snapshot.parent.mkdir(parents=True)
    news_snapshot.parent.mkdir(parents=True)
    cross_snapshot.write_text("date,symbol\n", encoding="utf-8")
    news_snapshot.write_text("{}\n", encoding="utf-8")
    (cross_snapshot.parent / "cross_asset_context_manifest.json").write_text(
        '{"dataset_status":"complete"}\n', encoding="utf-8"
    )
    (news_snapshot.parent / "news_context_manifest.json").write_text(
        '{"pipeline_status":"complete"}\n', encoding="utf-8"
    )
    outcome_ledger_path = tmp_path / "outcome_ledger.jsonl"
    outcome_records = [{"decision_id": f"decision-{index}"} for index in range(200)]
    outcome_ledger_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in outcome_records)
        + "\n",
        encoding="utf-8",
    )

    gate = build_context_evidence_gate(
        cross_root,
        news_root,
        tmp_path / "news_ledger.jsonl",
        tmp_path / "decision_ledger.jsonl",
        outcome_ledger_path,
    )

    assert gate["joint_snapshot_day_count"] == 1
    assert gate["evidence_status"] == "blocked_pending_purged_walk_forward_validation"
    assert gate["calendar_duration_gate_enabled"] is False


def test_context_outcome_resolves_target_before_invalidation() -> None:
    decision: dict[str, Any] = {
        "entry_reference_price": 100.0,
        "equity_direction": "bullish",
        "target_price": 110.0,
        "invalidation_price": 95.0,
    }
    future = [
        Bar(
            date="2026-01-02",
            open=100.0,
            high=106.0,
            low=99.0,
            close=105.0,
            adjusted_close=105.0,
            volume=1000,
        ),
        Bar(
            date="2026-01-03",
            open=105.0,
            high=111.0,
            low=103.0,
            close=110.0,
            adjusted_close=110.0,
            volume=1000,
        ),
        Bar(
            date="2026-01-04",
            open=110.0,
            high=112.0,
            low=94.0,
            close=96.0,
            adjusted_close=96.0,
            volume=1000,
        ),
    ]
    outcome = resolve_decision_path(decision, future)
    assert outcome["outcome_label"] == "target_hit_before_invalidation"
    assert outcome["target_hit_index"] == 2
    assert outcome["invalidation_hit_index"] == 3


def test_context_decision_ledger_is_idempotent_across_reruns(tmp_path: Path) -> None:
    thesis: dict[str, Any] = {
        "symbol": "TEST",
        "as_of_date": "2026-01-02",
        "direction": "bullish",
        "trade_intent": "long_call",
        "entry_reference_price": 100.0,
        "target_price": 110.0,
        "invalidation_price": 95.0,
        "expected_hold_trading_days": 10,
        "external_context": {
            "original_equity_trade_intent": "long_call",
            "theme": "ai",
            "cross_asset_theme_score": 0.2,
            "news_risk_tone_score": 0.0,
            "context_confirmation_score": 0.15,
            "context_confidence_tier": "context_mixed",
            "systemic_stress_score": 0.3,
            "corroborated_news_alert_present": False,
            "veto_reasons": [],
        },
    }
    cross = {"latest_source_date_max": "2026-01-02"}
    news = {"decision_time": "2026-01-02T20:00:00+00:00", "event_count": 10}
    gate = {"evidence_status": "blocked_insufficient_resolved_context_decisions"}
    first = build_context_decision_records(
        [thesis], cross, news, gate, "2026-01-02T20:01:00+00:00"
    )
    second = build_context_decision_records(
        [thesis], cross, news, gate, "2026-01-02T20:05:00+00:00"
    )
    assert first[0]["decision_id"] == second[0]["decision_id"]
    ledger = tmp_path / "decisions.jsonl"
    assert append_context_decision_records(ledger, first) == 1
    assert append_context_decision_records(ledger, second) == 0
    assert first[0]["semantic_decision_scope"] == "eligible_symbol_session"
    assert first[0]["session_id"] == "2026-01-02"
    velocity = build_context_decision_velocity([thesis])
    assert velocity["eligible_symbol_session_count"] == 1
    assert velocity["unique_semantic_decision_count"] == 1
    assert velocity["readiness_threshold_changed"] is False


def test_real_staged_cross_asset_and_news_inputs_validate_end_to_end() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cross_rows, cross_manifest = load_cross_asset_snapshot(
        repo_root
        / "dopey_data"
        / "real"
        / "raw"
        / "cross_asset"
        / "cross_asset_daily.csv",
        repo_root
        / "dopey_data"
        / "real"
        / "manifests"
        / "cross_asset_context_manifest.json",
    )
    news_events, news_manifest = load_news_snapshot(
        repo_root / "dopey_data" / "real" / "raw" / "news" / "news_events.jsonl",
        repo_root / "dopey_data" / "real" / "manifests" / "news_context_manifest.json",
    )
    macro = run_macro_context_gate()
    lanes = load_macro_lanes()
    cross_decision_date = date.fromisoformat(str(cross_manifest["created_at"])[:10])
    news_decision_time = datetime.fromisoformat(str(news_manifest["created_at"]))
    regime = build_cross_asset_regime(
        cross_rows,
        macro,
        list(lanes["lanes"]["treasury_yield_curve.csv"]),
        cross_decision_date,
    )
    intelligence = build_news_intelligence(news_events, news_decision_time)
    assert cross_manifest["dataset_status"] == "complete"
    assert regime["series_quality"]["usable_count"] == 20
    assert regime["series_quality"]["blocked_count"] == 0
    assert news_manifest["pipeline_status"] == "complete"
    assert intelligence["event_count"] == news_manifest["event_count"]
    assert intelligence["future_event_rejected_count"] == 0


def _fundamental(
    symbol: str,
    growth: float,
    margin: float,
    forward_pe: float,
    free_cashflow: float,
    debt: float,
    cash: float,
) -> dict[str, str]:
    return {
        "date": "2026-01-02",
        "symbol": symbol,
        "theme": "test_theme",
        "in_universe": "1",
        "market_cap": "10000000000",
        "trailing_pe": str(forward_pe),
        "forward_pe": str(forward_pe),
        "price_to_sales": str(forward_pe / 5.0),
        "price_to_book": "3.0",
        "profit_margin": str(margin),
        "revenue_growth": str(growth),
        "free_cashflow": str(free_cashflow),
        "total_debt": str(debt),
        "total_cash": str(cash),
    }


def _option_chain_csv(
    row_snapshot_date: str,
    row_symbol: str,
    expected_symbol: str,
    underlying_symbol: str,
) -> str:
    observed_underlying = underlying_symbol or expected_symbol
    return (
        "snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,mid,last,"
        "volume,open_interest,implied_vol,underlying_spot,underlying_symbol,source\n"
        f"{row_snapshot_date},{row_symbol},2026-08-21,32,call,100,1,1.1,1.05,1.05,"
        f"100,500,0.3,100,{observed_underlying},source\n"
    )


def _write_option_manifest(
    path: Path,
    snapshot_date: date,
    file_hashes: dict[str, str],
) -> None:
    path.write_text(
        json.dumps(
            {
                "created_at": "2026-07-20T22:00:00+00:00",
                "snapshot_dates": [snapshot_date.isoformat()],
                "file_hashes": file_hashes,
                "not_live_data": True,
                "paper_only": True,
                "live_blocked": True,
            }
        ),
        encoding="utf-8",
    )


def _contract(
    strike: float,
    bid: float,
    ask: float,
    dte: int,
    iv: float,
    open_interest: int,
    volume: int,
    option_type: str = "call",
) -> dict[str, Any]:
    return {
        "snapshot_date": "2026-01-02",
        "symbol": "TEST",
        "expiry": "2026-02-13",
        "dte_calendar": dte,
        "option_type": option_type,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0,
        "last": (bid + ask) / 2.0,
        "volume": volume,
        "open_interest": open_interest,
        "implied_vol": iv,
        "underlying_spot": 100.0,
        "source": "test_realistic_contract",
    }
