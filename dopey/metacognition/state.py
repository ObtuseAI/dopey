"""Typed metacognitive states and control outputs."""

from __future__ import annotations

from enum import StrEnum


class KnowledgeBoundary(StrEnum):
    KNOWN = "KNOWN"
    PARTIALLY_KNOWN = "PARTIALLY_KNOWN"
    UNKNOWN = "UNKNOWN"
    OUTSIDE_AUTHORITY = "OUTSIDE_AUTHORITY"


class ControlOutput(StrEnum):
    CONTINUE = "CONTINUE"
    EXPAND_EVIDENCE = "EXPAND_EVIDENCE"
    ADD_ADVERSARY = "ADD_ADVERSARY"
    CHANGE_STRATEGY = "CHANGE_STRATEGY"
    REPLAY_HISTORY = "REPLAY_HISTORY"
    ESCALATE_MODEL = "ESCALATE_MODEL"
    NARROW_SCOPE = "NARROW_SCOPE"
    ABSTAIN = "ABSTAIN"
    TERMINATE = "TERMINATE"
