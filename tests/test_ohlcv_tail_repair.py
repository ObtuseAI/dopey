"""Tests for the OHLCV tail-repair safety logic (pure, no network)."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from operator_tools import operator_repair_ohlcv_tail as repair

_H = "date,symbol,open,high,low,close,adjusted_close,volume,source"


def test_detects_high_below_open_or_close():
    # GE 2026-07-16: high 352.25 < open 353.21
    assert repair._row_inconsistent("2026-07-16,GE,353.21,352.25,336.53,345.73,345.73,10,yf") is True
    # MS: high 228.03 < open 228.23
    assert repair._row_inconsistent("2026-07-16,MS,228.23,228.03,215.79,218.37,218.37,10,yf") is True


def test_detects_low_above_open_or_close():
    # ADM 2026-07-17: low 83.79 > open 83.70
    assert repair._row_inconsistent("2026-07-17,ADM,83.70,86.0,83.79,85.90,85.90,10,yf") is True


def test_accepts_consistent_rows():
    assert repair._row_inconsistent("2026-07-16,X,100,105,99,103,103,10,yf") is False
    # exact boundary: high==open, low==close is consistent
    assert repair._row_inconsistent("2026-07-16,X,105,105,100,100,100,10,yf") is False


def test_malformed_rows_are_not_flagged():
    assert repair._row_inconsistent("") is False
    assert repair._row_inconsistent("2026-07-16,X,not,a,number,here,,,") is False
    assert repair._row_inconsistent("date,symbol,open,high,low,close") is False  # header


def test_partition_drops_from_earliest_bad_date_both_inclusive() -> None:
    rows = [
        _H,
        "2026-07-14,GE,100,101,99,100,100,1,yf",   # clean, keep
        "2026-07-15,GE,100,101,99,100,100,1,yf",   # clean, keep
        "2026-07-16,GE,353,352,336,345,345,1,yf",  # bad (earliest)
        "2026-07-17,GE,100,101,99,100,100,1,yf",   # after bad, drop
    ]
    kept, removed = repair._partition_tail(rows, frozenset({"2026-07-16"}))
    assert len(removed) == 2  # 07-16 and 07-17
    assert kept[0] == _H
    assert [r.split(",", 1)[0] for r in kept[1:]] == ["2026-07-14", "2026-07-15"]


def test_repair_candidate_requires_every_removed_evidence_date() -> None:
    original = (
        _H
        + "\n2026-07-15,X,100,101,99,100,100,1,yahoo_finance"
        + "\n2026-07-16,X,100,99,98,99,99,1,yahoo_finance"
        + "\n2026-07-17,X,99,101,98,100,100,1,yahoo_finance\n"
    ).encode("utf-8")
    with pytest.raises(repair.OhlcvTailRepairError, match="every removed evidence row"):
        repair._repair_candidate(
            "X",
            original,
            frozenset({"2026-07-16"}),
            [("2026-07-17", "2026-07-17,X,99,101,98,100,100,1,yahoo_finance")],
        )


def test_main_prepares_candidate_without_mutating_source_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history_dir = tmp_path / "history"
    real_dir = tmp_path / "real"
    history_dir.mkdir()
    real_dir.mkdir()
    original = (
        _H
        + "\n2026-07-15,X,100,101,99,100,100,1,yahoo_finance"
        + "\n2026-07-16,X,100,99,98,99,99,1,yahoo_finance"
        + "\n2026-07-17,X,99,101,98,100,100,1,yahoo_finance\n"
    ).encode("utf-8")
    for root in (history_dir, real_dir):
        (root / "X.csv").write_bytes(original)
    captured: dict[str, object] = {}

    def publish(
        candidates: dict[str, bytes],
        baselines: dict[str, str],
        updated_at: object,
    ) -> dict[str, object]:
        captured["candidates"] = candidates
        captured["baselines"] = baselines
        captured["updated_at"] = updated_at
        assert (history_dir / "X.csv").read_bytes() == original
        assert (real_dir / "X.csv").read_bytes() == original
        return {"dataset_status": "valid_real_dataset"}

    monkeypatch.setattr(repair, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(repair, "REAL_DIR", real_dir)
    monkeypatch.setattr(repair, "SUPERVISOR_LOCK", tmp_path / "supervisor.lock")
    monkeypatch.setattr(repair, "ACCELERATION_LOCK", tmp_path / "acceleration.lock")
    monkeypatch.setattr(repair, "latest_completed_market_session", lambda now: date(2026, 7, 17))
    monkeypatch.setattr(
        repair,
        "collect_new_rows_after_date",
        lambda symbol, last_date, maximum_date: [
            ("2026-07-16", "2026-07-16,X,100,101,98,99,99,1,yahoo_finance"),
            ("2026-07-17", "2026-07-17,X,99,101,98,100,100,1,yahoo_finance"),
        ],
    )
    monkeypatch.setattr(repair, "publish_tail_repair_transaction", publish)

    assert repair.main() == 0
    assert (history_dir / "X.csv").read_bytes() == original
    assert (real_dir / "X.csv").read_bytes() == original
    assert captured["baselines"] == {"X": hashlib.sha256(original).hexdigest()}
    candidate = captured["candidates"]
    assert isinstance(candidate, dict)
    assert b"2026-07-16,X,100,101,98,99" in candidate["X"]
