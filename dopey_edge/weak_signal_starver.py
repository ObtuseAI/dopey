"""Dopey weak-signal starver: downgrade decayed/failed signals (Dummy doctrine, recommend-only).

DOPEY-native stub. Borrows the Dummy "weak-signal starving" doctrine: signals that decay or
fail repeatedly are downgraded and marked for demotion (never deleted). No live exec.
"""
from __future__ import annotations

from .signal_discovery import SignalCandidate


def starve_weak_signals(signals: list[SignalCandidate], decay_threshold: float = 0.4,
                        confidence_floor: float = 0.25) -> list[dict]:
    """Return a downgrade-recommendation list for signals that should be starved/demoted."""
    out = []
    for s in signals:
        if s.decay_score >= decay_threshold or s.confidence < confidence_floor:
            out.append({
                "signal_id": s.signal_id,
                "family": s.family,
                "action": "demote",
                "delete": False,
                "reason": "decay_or_low_confidence",
                "decay_score": s.decay_score,
                "confidence": s.confidence,
            })
    return out
