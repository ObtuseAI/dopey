"""Dopey adaptive circuit breaker: deterministic paper-side breaker (no live trip in first pass).

DOPEY-native stub. Trips on paper drawdown / failure bursts; recommends halting new paper entries.
"""
from __future__ import annotations


class AdaptiveCircuitBreaker:
    def __init__(self, drawdown_limit: float = 0.20, failure_burst_limit: int = 3):
        self.drawdown_limit = drawdown_limit
        self.failure_burst_limit = failure_burst_limit
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1

    def record_success(self) -> None:
        self._failures = 0

    def trip(self, drawdown: float) -> dict:
        tripped = drawdown >= self.drawdown_limit or self._failures >= self.failure_burst_limit
        return {
            "tripped": bool(tripped),
            "paper": True,
            "recommendation": "halt_new_paper_entries" if tripped else "continue",
            "drawdown": drawdown,
            "failures": self._failures,
        }
