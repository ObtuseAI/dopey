"""Dopey signal discovery: deterministic candidate-signal discovery (research stub, no network).

DOPEY-native stub. Discovers candidate signals from a proof bundle without network calls.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class SignalCandidate:
    signal_id: str
    family: str
    direction: str
    confidence: float
    decay_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def discover_signals(proof_bundle: dict) -> list[SignalCandidate]:
    """Derive candidate signals from a ProofBundle dict. Deterministic; no network."""
    family = proof_bundle.get("family", "unknown")
    oos_edge = float(proof_bundle.get("oos_edge", 0.0))
    decay = float(proof_bundle.get("signal_decay", 0.0))
    if oos_edge <= 0:
        return []
    direction = "long" if proof_bundle.get("direction_bias", 0) >= 0 else "short"
    return [
        SignalCandidate(
            signal_id=f"{family}-sig-1",
            family=family,
            direction=direction,
            confidence=round(min(1.0, oos_edge), 6),
            decay_score=round(max(0.0, decay), 6),
        )
    ]
