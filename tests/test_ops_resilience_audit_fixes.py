"""Focused regressions for the 2026-07-26 supervisor/ops audit fixes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey.protocols.status_semantics import (
    OperationalStatusClass,
    classify_operational_status,
)
from dopey_acceleration import cycle
from dopey_autonomy import run_resilient_research_supervisor as supervisor
from dopey_autonomy.run_resilient_research_supervisor import (
    STAGES,
    STATUS_KEYS,
    _diff_against_previous_run,
    _extract_status,
    _is_degraded,
)
from dopey_ops.pipeline_forecast_card import score_forecast
from operator_tools import operator_nightly
from operator_tools import operator_weekend_soak as weekend_soak
from operator_tools import process_tree


def test_supervisor_stages_are_topologically_ordered() -> None:
    seen: set[str] = set()
    for stage_name, _runner, dependencies in STAGES:
        assert set(dependencies) <= seen, (
            f"stage {stage_name} appears before dependencies "
            f"{sorted(set(dependencies) - seen)}"
        )
        seen.add(stage_name)


def test_supervisor_recognizes_all_ops_stage_status_fields() -> None:
    expected_statuses = {
        "forecast_card_status": "forecast_card_current",
        "kaizen_status": "kaizen_ledger_current",
        "slo_status": "within_error_budget",
        "book_quality_status": "forward_book_quality_computed",
        "probe_status": "probe_complete",
        "playbook_stage_status": "playbook_research_complete",
    }
    assert set(expected_statuses) <= set(STATUS_KEYS)
    for status_key, status_value in expected_statuses.items():
        assert _extract_status({status_key: status_value}) == status_value


def test_forecast_band_rejects_actual_above_upper_bound() -> None:
    prediction = {
        "predicted_closes_point": 3,
        "predicted_closes_upper": 8,
    }
    assert score_forecast(prediction, actual_closes=4)["within_band"] is True
    assert score_forecast(prediction, actual_closes=9)["within_band"] is False


def test_within_error_budget_is_classified_healthy() -> None:
    assessment = classify_operational_status("within_error_budget")
    assert assessment["status_class"] is OperationalStatusClass.HEALTHY
    assert assessment["failure_signal"] is False
    assert assessment["evidence_trustworthy"] is True
    failure = classify_operational_status("complete_with_failure")
    assert failure["status_class"] is OperationalStatusClass.FAILED


def test_acceleration_lock_uses_process_identity_and_owner_checked_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "acceleration_cycle.lock"
    started_at = "2026-07-26T01:02:03+00:00"
    monkeypatch.setattr(cycle, "LOCK_PATH", lock_path)
    monkeypatch.setattr(
        cycle,
        "_process_started_at_utc",
        lambda _process_id: started_at,
    )

    lock_id = cycle._acquire_lock()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))

    assert payload["lock_id"] == lock_id
    assert payload["process_started_at_utc"] == started_at
    cycle._release_lock("different-owner")
    assert lock_path.exists()
    cycle._release_lock(lock_id)
    assert not lock_path.exists()


def test_acceleration_lock_recovers_reused_pid_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "acceleration_cycle.lock"
    lock_path.write_text(
        json.dumps(
            {
                "lock_id": "stale-owner",
                "pid": 123,
                "process_started_at_utc": "2026-07-25T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cycle, "LOCK_PATH", lock_path)
    monkeypatch.setattr(cycle, "_pid_running", lambda _process_id: True)
    monkeypatch.setattr(
        cycle,
        "_process_identity_matches",
        lambda _process_id, _expected_started_at_utc: False,
    )
    monkeypatch.setattr(
        cycle,
        "_process_started_at_utc",
        lambda _process_id: "2026-07-26T01:02:03+00:00",
    )

    lock_id = cycle._acquire_lock()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))

    assert payload["lock_id"] == lock_id
    assert payload["lock_id"] != "stale-owner"
    cycle._release_lock(lock_id)


def test_soak_does_not_attach_stale_journal_to_passed_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    stale_journal = {
        "run_id": "prior-run",
        "supervisor_status": "all_stages_completed",
        "regressions_vs_previous_run": ["stale-regression"],
    }
    monkeypatch.setattr(weekend_soak, "SOAK_LOG", tmp_path / "soak.jsonl")
    monkeypatch.setattr(
        weekend_soak,
        "_last_journal_entry",
        lambda: stale_journal,
    )
    monkeypatch.setattr(
        weekend_soak,
        "_run",
        lambda _args, timeout: {
            "status": "passed",
            "return_code": 0,
            "output": "",
            "timeout_seconds": timeout,
        },
    )

    record = weekend_soak.soak_iteration(1, None)

    assert record["soak_status"] == "failed"
    assert record["supervisor_command_status"] == "failed"
    assert record["supervisor_status"] == "unverified_missing_matching_journal"
    assert record["stage_regressions"] == []


def test_soak_timeout_tombstones_only_running_supervisor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    active_run_path = tmp_path / "supervisor_active_run.json"
    active_run_path.write_text(
        json.dumps(
            {
                "run_id": "timed-out-run",
                "run_status": "running",
                "heartbeat_at_utc": "2026-07-25T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        weekend_soak,
        "SUPERVISOR_ACTIVE_RUN_PATH",
        active_run_path,
    )

    weekend_soak._tombstone_timed_out_supervisor()
    tombstone = json.loads(active_run_path.read_text(encoding="utf-8"))

    assert tombstone["run_status"] == "terminated_by_weekend_soak_timeout"
    assert tombstone["recorded_as_pass"] is False
    assert tombstone["paper_only"] is True
    assert tombstone["live_blocked"] is True


def test_supervisor_disk_block_is_journal_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "supervisor_run_journal.jsonl"
    monkeypatch.setattr(supervisor, "SUPERVISOR_RUN_JOURNAL_PATH", journal_path)
    monkeypatch.setattr(
        supervisor.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=99, free=1),
    )
    monkeypatch.setattr(supervisor, "MIN_SUPERVISOR_FREE_BYTES", 2)

    summary = supervisor.run_resilient_research_supervisor()
    entry = json.loads(journal_path.read_text(encoding="utf-8"))

    assert summary["supervisor_status"] == "blocked_insufficient_disk_headroom"
    assert summary["journal_visible"] is True
    assert entry["run_id"] == summary["run_id"]
    assert entry["early_return"] is True
    assert entry["participates_in_stage_regression_baseline"] is False


def test_supervisor_concurrent_lock_return_is_journal_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "supervisor_run_journal.jsonl"
    monkeypatch.setattr(supervisor, "SUPERVISOR_RUN_JOURNAL_PATH", journal_path)
    monkeypatch.setattr(
        supervisor.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=1, free=99),
    )
    monkeypatch.setattr(supervisor, "MIN_SUPERVISOR_FREE_BYTES", 2)
    monkeypatch.setattr(supervisor, "_acquire_lock", lambda: None)

    summary = supervisor.run_resilient_research_supervisor()
    entry = json.loads(journal_path.read_text(encoding="utf-8"))

    assert summary["supervisor_status"] == "locked_concurrent_run"
    assert entry["supervisor_status"] == "locked_concurrent_run"
    assert entry["stage_states"] == {}


def test_early_return_journal_does_not_replace_regression_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "supervisor_run_journal.jsonl"
    journal_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "early_return": False,
                        "stage_states": {"alpha": "completed"},
                    }
                ),
                json.dumps(
                    {
                        "early_return": True,
                        "stage_states": {},
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "SUPERVISOR_RUN_JOURNAL_PATH", journal_path)

    regressions, recoveries = _diff_against_previous_run(
        {"alpha": {"stage_status": "completed_degraded"}}
    )

    assert regressions == ["alpha"]
    assert recoveries == []


def test_degraded_status_semantics_close_marker_holes() -> None:
    assert _is_degraded("failed") is True
    assert _is_degraded("invalid_real_dataset") is True
    assert _is_degraded("blocked_missing_history") is True
    assert _is_degraded("no_failures_found") is False
    assert _is_degraded("not_action_ready") is False
    assert _is_degraded("error_budget_breached") is False


def test_windows_process_termination_uses_entire_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class FakeProcess:
        pid = 4321

        def poll(self) -> None:
            return None

        def wait(self, timeout: int) -> int:
            assert timeout == 30
            return 1

    def fake_run(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(process_tree, "_runtime_platform_name", lambda: "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setattr(process_tree.subprocess, "run", fake_run)

    process_tree._terminate_process_tree(FakeProcess())  # type: ignore[arg-type]

    assert calls
    assert calls[0][-4:] == ["/PID", "4321", "/T", "/F"]


def test_nightly_fitness_timeout_is_inconclusive_after_tree_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operator_nightly,
        "run_captured_process_tree",
        lambda _command, _cwd, _environment, timeout_seconds: {
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "process_tree_terminated": True,
        },
    )

    result = operator_nightly._run_fitness_once()

    assert result["score"] == "status=inconclusive_timeout"
    assert result["ok"] is False
    assert result["process_tree_terminated"] is True


def test_acceleration_timeout_is_inconclusive_after_tree_termination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        cycle,
        "load_provider_control",
        lambda: {"instrument_mode": "model_priced_research"},
    )
    monkeypatch.setattr(
        cycle,
        "run_captured_process_tree",
        lambda _command, _cwd, _environment, timeout_seconds: {
            "return_code": None,
            "stdout": "partial",
            "stderr": "",
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "process_tree_terminated": True,
        },
    )

    result = cycle._run_command(
        ["python", "-c", "pass"],
        tmp_path,
        5,
        1,
    )

    assert result["command_status"] == "inconclusive_timeout"
    assert result["process_tree_terminated"] is True
    assert result["stdout_tail"] == "partial"
