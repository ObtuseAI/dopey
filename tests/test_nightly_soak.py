"""Integration coverage for truthful timeout handling in the nightly soak."""
from __future__ import annotations

import sys

from operator_tools.operator_weekend_soak import _run


def test_soak_subprocess_timeout_is_inconclusive() -> None:
    result = _run(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        1,
    )

    assert result["status"] == "inconclusive_timeout"
    assert result["return_code"] is None
    assert result["timeout_seconds"] == 1
