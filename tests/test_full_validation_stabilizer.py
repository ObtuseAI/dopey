"""Tests: full validation stabilizer diagnostics."""
from __future__ import annotations

import sys

from dopey_validation.full_suite_stabilizer import (
    detect_windows_flush_oserror,
    identify_slow_groups,
    run_command,
    timeout_result,
)


def test_full_suite_stabilizer_collects_tests() -> None:
    result = run_command([sys.executable, "-m", "pytest", "--collect-only", "tests/test_active_trading_policy.py", "-q"], 20)
    assert result.status == "pass"
    assert result.timed_out is False


def test_full_suite_stabilizer_records_timeout_as_inconclusive() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_full_suite_stabilizer_identifies_slow_test_group() -> None:
    class Result:
        command = ["pytest", "slow.py"]
        duration_seconds = 99.0
        status = "pass"
        timed_out = False

    slow = identify_slow_groups([Result()], 10.0)
    assert slow and slow[0]["command"] == "pytest slow.py"


def test_full_suite_stabilizer_does_not_convert_timeout_to_pass() -> None:
    result = timeout_result(["pytest"], 5)
    assert result["timed_out"] is True
    assert result["status"] != "pass"


def test_windows_flush_oserror_is_recorded_if_seen() -> None:
    output = "OSError: [Errno 22] Invalid argument\nException ignored on flushing sys.stdout"
    assert detect_windows_flush_oserror(output) is True
