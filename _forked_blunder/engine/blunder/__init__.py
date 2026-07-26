"""Blunder — the proof-driven recursive AI work engine inside the Obtuse platform.

Loop:  intake -> plan -> mock trial -> execute -> validate -> repair -> ledger -> learn -> (repeat).

This package is the FIRST runnable implementation of the Obtuse P0 "Build Lane" items
(Blunder capability implementation / autonomy loop / proof-ledger integration). It is intentionally
stdlib-only and side-effect-sandboxed: real execution writes only inside a per-run work directory, and
nothing risky/irreversible/external runs without an explicit human gate.
"""

from .core import (  # noqa: F401
    BLUNDER_VERSION,
    FinalStatus,
    MockResult,
    ValidationResult,
    RiskLevel,
    TaskType,
    WorkPacket,
    classify_action,
    intake,
    sha256_text,
    sha256_obj,
)
