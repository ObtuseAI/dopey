"""Incremental real-signal engine: append-invariance, grid guards, safe appends.

The cadence grid is positional and anchored at the start, so appending bars
never shifts prior evaluation dates; the incremental state's prefix hash
proves grid alignment per symbol per run. Value revisions of PAST bars are
guarded upstream by the hash-pinned history manifest, not here.
"""
from __future__ import annotations

import json
import math

from dopey_analysis.real_history_signal_engine import (
    EVALUATION_CADENCE_TRADING_DAYS,
    INCREMENTAL_STATE_VERSION,
    _append_jsonl,
    _compute_signal_records,
    _evaluation_dates,
    _incremental_plan,
    _incremental_state,
    _load_jsonl,
    _merged_totals,
)
from dopey_analysis.signal_models import PriceBar, make_signal_series


def _series(symbol: str, count: int):
    from datetime import date, timedelta

    bars = []
    for index in range(count):
        close = 100.0 + 10.0 * math.sin(index * 0.3) + index * 0.05
        bars.append(PriceBar(
            artifact_type="price_bar",
            symbol=symbol,
            date=(date(2025, 1, 1) + timedelta(days=index)).isoformat(),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            adjusted_close=close,
            volume=1000 + index,
            data_source_tier="local_real_history",
            real_history_used=True,
            fixture_only=False,
            not_real_signal_evidence=False,
            paper_only=True,
            live_blocked=True,
            record_hash="",
        ))
    return make_signal_series(symbol, bars, "local_real_history", True, False, False)


def test_appending_bars_never_shifts_prior_evaluation_dates() -> None:
    short = _series("TESTX", 45)
    long = _series("TESTX", 60)
    short_dates = _evaluation_dates(short)
    long_dates = _evaluation_dates(long)
    assert short_dates  # fixture produces a real grid
    assert long_dates[: len(short_dates)] == short_dates
    assert len(long_dates) > len(short_dates)


def test_incremental_plan_extends_verified_prefixes_and_fails_closed() -> None:
    short = _series("TESTX", 45)
    long = _series("TESTX", 60)
    state = _incremental_state({"TESTX": short}, totals={})

    plan = _incremental_plan(state, {"TESTX": long})
    assert plan is not None
    short_dates = _evaluation_dates(short)
    assert plan["TESTX"] == _evaluation_dates(long)[len(short_dates):]

    # a brand-new symbol gets its full grid as "new"
    other = _series("NEWSYM", 60)
    plan = _incremental_plan(state, {"TESTX": long, "NEWSYM": other})
    assert plan["NEWSYM"] == _evaluation_dates(other)

    # A removed symbol requires a full rewrite; otherwise its old signal rows
    # remain in every append-only family ledger and keep reaching backtests.
    two_symbol_state = _incremental_state(
        {"TESTX": short, "DELISTED": _series("DELISTED", 45)},
        totals={},
    )
    assert _incremental_plan(two_symbol_state, {"TESTX": long}) is None

    # shrunk series (revised history) fails closed to full recompute
    assert _incremental_plan(state, {"TESTX": _series("TESTX", 30)}) is None

    # grid-parameter drift fails closed
    drifted = json.loads(json.dumps(state))
    drifted["grid"]["cadence"] = EVALUATION_CADENCE_TRADING_DAYS + 1
    assert _incremental_plan(drifted, {"TESTX": long}) is None
    wrong_version = json.loads(json.dumps(state))
    wrong_version["state_version"] = "other"
    assert _incremental_plan(wrong_version, {"TESTX": long}) is None
    assert wrong_version["state_version"] != INCREMENTAL_STATE_VERSION


def test_incremental_records_equal_full_recompute() -> None:
    """prefix(short-grid) + tail(new dates) == full recompute on the long series."""
    short = _series("TESTX", 45)
    long = _series("TESTX", 60)
    short_dates = _evaluation_dates(short)
    long_dates = _evaluation_dates(long)
    tail_dates = long_dates[len(short_dates):]

    # leak policy makes prefix records identical whether computed on the short
    # or the extended series (bars after signal_date are never consulted)
    fam_short, dir_short, _ = _compute_signal_records({"TESTX": short}, None, {"TESTX": short_dates})
    fam_prefix, dir_prefix, _ = _compute_signal_records({"TESTX": long}, None, {"TESTX": short_dates})
    assert dir_short == dir_prefix
    assert fam_short == fam_prefix

    fam_full, dir_full, points_full = _compute_signal_records({"TESTX": long}, None, {"TESTX": long_dates})
    fam_tail, dir_tail, points_tail = _compute_signal_records({"TESTX": long}, None, {"TESTX": tail_dates})
    assert dir_prefix + dir_tail == dir_full
    for family in fam_full:
        assert fam_prefix[family] + fam_tail[family] == fam_full[family]

    # merged totals equal full-run totals
    base = _merged_totals({}, fam_prefix, dir_prefix, points_full - points_tail)
    merged = _merged_totals(base, fam_tail, dir_tail, points_tail)
    full = _merged_totals({}, fam_full, dir_full, points_full)
    assert merged == full


def test_append_jsonl_matches_full_write(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    first = [{"a": 1}, {"a": 2}]
    second = [{"a": 3}]
    _append_jsonl(path, first)
    _append_jsonl(path, second)
    assert _load_jsonl(path) == first + second
    _append_jsonl(path, [])  # no-op never touches the file
    assert _load_jsonl(path) == first + second
