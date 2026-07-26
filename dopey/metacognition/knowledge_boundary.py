"""Determine whether the research problem is within known evidence."""

from __future__ import annotations

from dopey.constitution.authority import Authority

from .state import KnowledgeBoundary


def classify_knowledge_boundary(
    authority: Authority,
    evidence_completeness: float,
    regime_familiarity: float,
) -> KnowledgeBoundary:
    if authority not in frozenset(Authority):
        return KnowledgeBoundary.OUTSIDE_AUTHORITY
    if evidence_completeness >= 0.85 and regime_familiarity >= 0.75:
        return KnowledgeBoundary.KNOWN
    if evidence_completeness >= 0.45 and regime_familiarity >= 0.35:
        return KnowledgeBoundary.PARTIALLY_KNOWN
    return KnowledgeBoundary.UNKNOWN
