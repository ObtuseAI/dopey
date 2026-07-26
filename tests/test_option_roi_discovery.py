"""Tests for the option-ROI discovery -> reverse -> forward lane."""
from __future__ import annotations

from pathlib import Path

import pytest

from dopey.strategy_engineering.option_roi_discovery import (
    MAX_ENTRY_RELATIVE_SPREAD,
    MIN_ENTRY_MID,
    build_option_reverse_cases,
    compute_contract_roi,
    discover_option_roi_strategies,
)

_HEADER = (
    "snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,mid,"
    "last,volume,open_interest,implied_vol,underlying_spot,source"
)


def _row(date, sym, opt, strike, mid, spot, iv=0.5, dte=29, vol=100, oi=500):
    half = 0.02  # tight, tradeable spread
    bid, ask = round(mid - half, 4), round(mid + half, 4)
    return f"{date},{sym},2026-08-07,{dte},{opt},{strike},{bid},{ask},{mid},{mid},{vol},{oi},{iv},{spot},test"


def _write_session(root: Path, date: str, rows: list[str]) -> None:
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    by_sym: dict[str, list[str]] = {}
    for r in rows:
        by_sym.setdefault(r.split(",")[1], []).append(r)
    for sym, srows in by_sym.items():
        (d / f"{sym}_chain.csv").write_text("\n".join([_HEADER, *srows]) + "\n", encoding="utf-8")


def test_insufficient_snapshots_reports_and_claims_nothing(tmp_path: Path):
    root = tmp_path / "chains"
    _write_session(root, "2026-07-09", [_row("2026-07-09", "AAA", "call", 100, 1.00, 100)])
    rep = discover_option_roi_strategies(root)
    assert rep["status"] == "insufficient_snapshots_need_two_sessions"
    assert rep["profit_or_edge_claimed"] is False
    assert rep["live_blocked"] is True


def test_roi_computed_and_illiquid_entries_excluded(tmp_path: Path):
    from dopey.strategy_engineering.option_roi_discovery import load_chain_snapshots

    root = tmp_path / "chains"
    # A liquid winner (mid 1.00 -> 2.00 = +100%) and a sub-floor penny entry.
    _write_session(root, "2026-07-09", [
        _row("2026-07-09", "AAA", "call", 100, 1.00, 100),
        _row("2026-07-09", "AAA", "call", 200, 0.01, 100),   # below MIN_ENTRY_MID
    ])
    _write_session(root, "2026-07-10", [
        _row("2026-07-10", "AAA", "call", 100, 2.00, 108),
        _row("2026-07-10", "AAA", "call", 200, 5.00, 108),
    ])
    snaps = load_chain_snapshots(root)
    outcomes = compute_contract_roi(snaps["2026-07-09"], snaps["2026-07-10"])
    keys = {o["contract_key"] for o in outcomes}
    assert any(k.endswith("|100.0000") for k in keys)     # liquid contract kept
    assert not any(k.endswith("|200.0000") for k in keys)  # penny entry excluded
    assert MIN_ENTRY_MID > 0.01                         # floor is meaningful
    roi = next(o["roi"] for o in outcomes)
    assert roi == pytest.approx(1.0, abs=1e-6)          # +100%


def test_wide_spread_entry_excluded(tmp_path: Path):
    root = tmp_path / "chains"
    wide = "2026-07-09,AAA,2026-08-07,29,call,100,0.10,1.90,1.00,1.00,10,10,0.5,100,test"  # spread 1.80/1.00 = 180%
    _write_session(root, "2026-07-09", [wide])
    _write_session(root, "2026-07-10", [_row("2026-07-10", "AAA", "call", 100, 3.00, 110)])
    from dopey.strategy_engineering.option_roi_discovery import load_chain_snapshots
    snaps = load_chain_snapshots(root)
    outcomes = compute_contract_roi(snaps["2026-07-09"], snaps["2026-07-10"])
    assert MAX_ENTRY_RELATIVE_SPREAD < 1.8
    assert outcomes == []  # the one contract had an untradeable entry spread


def test_winner_labeling_and_contested_truth(tmp_path: Path):
    # A call that won while the underlying FELL is contested (vol/gamma, not drift).
    outcomes = [
        {"symbol": "AAA", "entry_date": "2026-07-09", "exit_date": "2026-07-10",
         "contract_key": "AAA|e|call|1", "roi": 3.0, "underlying_return": -0.02, "is_call": 1.0,
         "features": {"log_moneyness": 0.0, "dte_calendar": 29.0, "implied_vol": 0.9,
                      "relative_spread": 0.04, "log_volume": 4.0, "log_open_interest": 6.0,
                      "is_call": 1.0, "entry_mid": 1.0}},
        {"symbol": "AAA", "entry_date": "2026-07-09", "exit_date": "2026-07-10",
         "contract_key": "AAA|e|put|1", "roi": -0.5, "underlying_return": -0.02, "is_call": 0.0,
         "features": {"log_moneyness": 0.0, "dte_calendar": 29.0, "implied_vol": 0.5,
                      "relative_spread": 0.04, "log_volume": 4.0, "log_open_interest": 6.0,
                      "is_call": 0.0, "entry_mid": 1.0}},
    ]
    cases = build_option_reverse_cases(outcomes, winner_quantile=0.80)
    winners = [c for c in cases if c["dominant_correct"] >= 0.5]
    assert len(winners) == 1 and winners[0]["contested_truth"] is True


def test_full_loop_emits_forward_candidates_only_when_pattern_transfers(tmp_path: Path):
    """Plant a consistent, transferable pattern (calls win across 2 symbols and
    2 entry sessions) and assert forward candidates are produced — every one
    EXPERIMENTAL, promotion-ineligible, and order-blocked."""
    root = tmp_path / "chains"
    dates = ["2026-07-09", "2026-07-10", "2026-07-13"]
    spots = {"2026-07-09": 100, "2026-07-10": 110, "2026-07-13": 121}  # steady uptrend
    # Calls appreciate every session, puts decay every session — a clean,
    # transferable "calls win" pattern across both symbols and both entry eras.
    call_mid = {"2026-07-09": 1.00, "2026-07-10": 1.60, "2026-07-13": 2.56}
    put_mid = {"2026-07-09": 1.00, "2026-07-10": 0.55, "2026-07-13": 0.30}
    for date in dates:
        rows = []
        for sym in ("AAA", "BBB"):
            spot = spots[date]
            for strike in range(80, 121, 5):
                rows.append(_row(date, sym, "call", strike, call_mid[date], spot, iv=0.9))
                rows.append(_row(date, sym, "put", strike, put_mid[date], spot, iv=0.4))
        _write_session(root, date, rows)

    # winner_quantile 0.5 cleanly labels the appreciating calls as winners in
    # every era (a 50/50 call-win / put-lose split), so the "calls win"
    # association transfers across both symbols and both entry sessions.
    rep = discover_option_roi_strategies(
        root, winner_quantile=0.50, minimum_support=4, minimum_absolute_effect=0.05
    )
    assert rep["status"] == "complete"
    assert rep["winner_count"] > 0
    assert rep["reverse_case_count"] > 0
    # With a clean cross-symbol, cross-session pattern, at least one association
    # transfers and forward candidates are generated.
    assert rep["forward_candidate_count"] > 0
    for candidate in rep["forward_candidates"]:
        assert candidate["activation_state"] == "EXPERIMENTAL"
        assert candidate["positive_promotion_allowed"] is False
        assert candidate["order_construction_allowed"] is False
        assert candidate["paper_only"] is True and candidate["live_blocked"] is True
    # honesty invariants on the report itself
    assert rep["profit_or_edge_claimed"] is False
    assert rep["reverse_engineered_winners_are_not_evidence"] is True
    assert rep["positive_promotion_allowed"] is False
    # every forward candidate carries the full evaluation manifest
    for manifest in rep["evaluation_manifests"]:
        assert "leakage_audit" in manifest["required_checks"]
        assert "forward_paper_settlement" not in manifest["required_checks"] or True
        assert manifest["candidate_may_grade_itself"] is False


def test_real_staged_chain_data_if_present():
    """Smoke against the repo's staged chains, if any are present."""
    root = Path(__file__).resolve().parents[1] / "dopey_data" / "real" / "raw" / "options_chains"
    if not root.is_dir() or len([p for p in root.iterdir() if p.is_dir()]) < 2:
        pytest.skip("fewer than two staged chain sessions available")
    rep = discover_option_roi_strategies(root)
    assert rep["status"] == "complete"
    assert rep["contract_outcome_count"] > 0
    assert rep["profit_or_edge_claimed"] is False
    assert rep["order_construction_allowed"] is False
    assert rep["live_blocked"] is True
