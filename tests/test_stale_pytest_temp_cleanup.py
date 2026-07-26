from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from operator_tools.operator_cleanup_stale_pytest_temp import (
    ActivePytestProcessDetectedError,
    CleanupPolicy,
    build_cleanup_candidates,
    cleanup_stale_pytest_temp,
)


def _session(base: Path, name: str, modified: datetime) -> Path:
    path = base / name
    path.mkdir()
    (path / "payload.bin").write_bytes(b"x" * 16)
    timestamp = modified.timestamp()
    os.utime(path / "payload.bin", (timestamp, timestamp))
    os.utime(path, (timestamp, timestamp))
    return path


def test_cleanup_preserves_recent_and_non_session_paths(tmp_path: Path) -> None:
    observed = datetime(2026, 7, 26, tzinfo=timezone.utc)
    old = _session(tmp_path, "pytest-1", observed - timedelta(hours=48))
    recent_1 = _session(tmp_path, "pytest-2", observed - timedelta(hours=2))
    recent_2 = _session(tmp_path, "pytest-3", observed - timedelta(hours=1))
    unrelated = _session(tmp_path, "other-4", observed - timedelta(hours=72))
    policy = CleanupPolicy(keep_recent_count=2, minimum_age_hours=12.0)

    candidates = build_cleanup_candidates(tmp_path, policy, observed)

    assert [candidate.path for candidate in candidates] == [str(old.resolve())]
    assert candidates[0].estimated_bytes == 16
    assert recent_1.exists()
    assert recent_2.exists()
    assert unrelated.exists()


def test_cleanup_blocks_when_any_pytest_process_is_active(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 7, 26, tzinfo=timezone.utc)
    old = _session(tmp_path, "pytest-1", observed - timedelta(hours=48))

    report = cleanup_stale_pytest_temp(
        tmp_path,
        CleanupPolicy(keep_recent_count=0, minimum_age_hours=12.0),
        True,
        observed,
        ("python -m pytest tests",),
        lambda: (),
    )

    assert report["cleanup_status"] == "blocked_active_pytest_process"
    assert old.exists()


def test_cleanup_does_not_treat_its_own_script_name_as_pytest(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 7, 26, tzinfo=timezone.utc)
    old = _session(tmp_path, "pytest-1", observed - timedelta(hours=48))

    report = cleanup_stale_pytest_temp(
        tmp_path,
        CleanupPolicy(keep_recent_count=0, minimum_age_hours=12.0),
        False,
        observed,
        ("python operator_cleanup_stale_pytest_temp.py --execute",),
        lambda: (),
    )

    assert report["cleanup_status"] == "dry_run_complete"
    assert old.exists()


def test_execute_cleanup_missing_root_is_successful_noop(tmp_path: Path) -> None:
    missing_root = tmp_path / "pytest-of-user"
    observed = datetime(2026, 7, 26, tzinfo=timezone.utc)

    report = cleanup_stale_pytest_temp(
        missing_root,
        CleanupPolicy(keep_recent_count=3, minimum_age_hours=12.0),
        True,
        observed,
        (),
        lambda: (),
    )

    assert report["cleanup_status"] == "cleanup_complete"
    assert report["base_path_status"] == "missing_noop"
    assert report["candidate_count"] == 0
    assert report["removed_count"] == 0
    assert report["estimated_removed_bytes"] == 0
    assert report["actual_free_space_delta_bytes"] is None
    assert not missing_root.exists()


def test_cleanup_executes_only_contained_candidates(tmp_path: Path) -> None:
    observed = datetime(2026, 7, 26, tzinfo=timezone.utc)
    old = _session(tmp_path, "pytest-1", observed - timedelta(hours=48))
    os.chmod(old / "payload.bin", 0o444)
    recent = _session(tmp_path, "pytest-2", observed - timedelta(hours=1))

    report = cleanup_stale_pytest_temp(
        tmp_path,
        CleanupPolicy(keep_recent_count=1, minimum_age_hours=12.0),
        True,
        observed,
        (),
        lambda: (),
    )

    assert report["cleanup_status"] == "cleanup_complete"
    assert report["removed_count"] == 1
    assert report["estimated_removed_bytes"] == 16
    assert report["actual_free_space_delta_bytes"] is None
    assert "pre-delete file sizes" in report["byte_measurement_note"]
    assert not old.exists()
    assert recent.exists()


def test_execute_rechecks_for_active_pytest_before_recursive_delete(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 7, 26, tzinfo=timezone.utc)
    old = _session(tmp_path, "pytest-1", observed - timedelta(hours=48))

    with pytest.raises(
        ActivePytestProcessDetectedError,
        match="appeared after cleanup planning",
    ):
        cleanup_stale_pytest_temp(
            tmp_path,
            CleanupPolicy(keep_recent_count=0, minimum_age_hours=12.0),
            True,
            observed,
            (),
            lambda: ("python -m pytest tests",),
        )

    assert old.exists()
