"""Nightly stack-stability = verification of the real production supervisor run.

The nightly must never re-run a duplicate multi-hour supervisor (the old soak
design could not fit its window - permanent inconclusive_timeout - and its
concurrent full-spine loads created the memory pressure and mid-write ledger
corruption it existed to detect). Instead it assesses the latest completed
production run from the append-only journal, and it must fail closed: missing,
stale, failed, skipped, or regressed runs are red with named reasons.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from operator_tools import operator_nightly


def _write_journal(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


def _entry(**overrides) -> dict:
    base = {
        "artifact_type": "resilient_research_supervisor_run_journal_entry",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "supervisor_status": "completed",
        "stages_failed_absorbed": 0,
        "stages_skipped_dependency": 0,
        "regressions_vs_previous_run": [],
    }
    base.update(overrides)
    return base


def _verify_with(tmp_path: Path, monkeypatch, entries: list[dict]) -> dict:
    journal = tmp_path / "supervisor_run_journal.jsonl"
    _write_journal(journal, entries)
    monkeypatch.setattr(operator_nightly, "SUPERVISOR_JOURNAL_PATH", journal)
    return operator_nightly._verify_production_stack()


def test_fresh_clean_production_run_is_green(tmp_path, monkeypatch) -> None:
    check = _verify_with(tmp_path, monkeypatch, [_entry()])
    assert check["green"] is True
    assert check["red_reasons"] == []
    assert check["check_mode"] == "production_run_journal_verification"


def test_missing_journal_is_red(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        operator_nightly, "SUPERVISOR_JOURNAL_PATH", tmp_path / "absent.jsonl"
    )
    check = operator_nightly._verify_production_stack()
    assert check["green"] is False
    assert check["red_reasons"] == ["journal_missing"]


def test_stale_production_run_is_red(tmp_path, monkeypatch) -> None:
    stale = (
        datetime.now(timezone.utc)
        - timedelta(hours=operator_nightly.MAX_PRODUCTION_RUN_AGE_HOURS + 5)
    ).isoformat()
    check = _verify_with(tmp_path, monkeypatch, [_entry(run_utc=stale)])
    assert check["green"] is False
    assert any(reason.startswith("stale_production_run") for reason in check["red_reasons"])


def test_failed_or_skipped_stages_are_red(tmp_path, monkeypatch) -> None:
    check = _verify_with(
        tmp_path,
        monkeypatch,
        [_entry(stages_failed_absorbed=2, stages_skipped_dependency=12)],
    )
    assert check["green"] is False
    assert "stages_failed_absorbed:2" in check["red_reasons"]
    assert "stages_skipped_dependency:12" in check["red_reasons"]


def test_stage_regressions_are_red(tmp_path, monkeypatch) -> None:
    check = _verify_with(
        tmp_path,
        monkeypatch,
        [_entry(regressions_vs_previous_run=["indicator_foundry"])],
    )
    assert check["green"] is False
    assert "stage_regressions:1" in check["red_reasons"]
    assert check["stage_regressions"] == ["indicator_foundry"]


def test_only_latest_entry_is_assessed(tmp_path, monkeypatch) -> None:
    bad_old = _entry(stages_failed_absorbed=3)
    good_new = _entry()
    check = _verify_with(tmp_path, monkeypatch, [bad_old, good_new])
    assert check["green"] is True


def test_journal_entry_missing_counts_is_red(tmp_path, monkeypatch) -> None:
    # A journal entry that predates the failure-accounting fields must not
    # silently pass; the -1 defaults trip the nonzero checks.
    entry = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "supervisor_status": "completed",
    }
    check = _verify_with(tmp_path, monkeypatch, [entry])
    assert check["green"] is False


def test_supervisor_early_return_entry_is_red(tmp_path, monkeypatch) -> None:
    check = _verify_with(
        tmp_path,
        monkeypatch,
        [
            _entry(
                supervisor_status="blocked_insufficient_disk_headroom",
                early_return=True,
            )
        ],
    )

    assert check["green"] is False
    assert (
        "supervisor_early_return:blocked_insufficient_disk_headroom"
        in check["red_reasons"]
    )
