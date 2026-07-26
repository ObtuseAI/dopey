"""Dopey fast invalidation engine: detect thesis failure, emit invalidation events (Dummy doctrine).

DOPEY-native stub. Detects when a strategy thesis has failed and emits invalidation events.
Usable in paper sim now and in future live paths (never auto-sells live; paper-only first pass).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class InvalidationEvent:
    strategy_id: str
    reason: str
    severity: str   # "soft" | "hard"
    action: str     # "monitor" | "close_paper" | "block_live"

    def to_dict(self) -> dict:
        return asdict(self)


def detect_invalidation(strategy_id: str, proof: dict, drawdown: float,
                        max_drawdown: float = 0.20, signal_decay: float = 0.4) -> InvalidationEvent | None:
    """Return an invalidation event if the thesis has failed, else None."""
    if drawdown >= max_drawdown:
        return InvalidationEvent(strategy_id, "max_drawdown_breached", "hard", "close_paper")
    if proof.get("signal_decay", 0) >= signal_decay:
        return InvalidationEvent(strategy_id, "signal_decay_exceeded", "soft", "monitor")
    if proof.get("overfit_flag"):
        return InvalidationEvent(strategy_id, "overfit_detected", "hard", "block_live")
    return None
