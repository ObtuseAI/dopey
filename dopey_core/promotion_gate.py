"""Dopey promotion gate: lesson / skill promotion decisions.

Forked from Blunder engine (Z:\\Obtuse\\engine\\blunder\\engine.py); the evaluate_lessons
promotion logic was split out into this module as part of the Dopey rename/decomposition.
A lesson is promoted only if it meets ALL criteria (real run + evidence + reusable + safe +
verified). Logic preserved verbatim.

DOPEY lineage: Blunder engine.py (evaluate_lessons) -> dopey_core.promotion_gate
"""
from __future__ import annotations


def evaluate_lessons(candidates: list[dict]) -> dict:
    """Promote a lesson only if it meets ALL criteria (real run + evidence + reusable + safe + verified)."""
    promoted, rejected = [], []
    for c in candidates:
        reasons = []
        if not c.get("from_real_run"):
            reasons.append("not from a real run")
        if not c.get("evidence"):
            reasons.append("no evidence")
        if not c.get("improved_or_prevented_failure"):
            reasons.append("did not improve/prevent failure")
        if not c.get("reusable"):
            reasons.append("not reusable")
        if c.get("weakens_safety"):
            reasons.append("would weaken safety")
        if not c.get("validator_or_replay_checked"):
            reasons.append("not validator/replay checked")
        if reasons:
            rejected.append({**c, "reject_reasons": reasons})
        else:
            promoted.append(c)
    return {"promoted": promoted, "rejected": rejected}
