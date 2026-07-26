"""Discover high-value research questions from governed knowledge signals."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from dopey.protocols.identity import canonical_hash

from .schema import DiscoveryQuestion, KnowledgeSignal, KnowledgeSignalType


_QUESTION_TEMPLATES: Final[dict[KnowledgeSignalType, str]] = {
    KnowledgeSignalType.BOTTLENECK: "Which discovery method reduces this bottleneck without weakening protected constraints: {statement}?",
    KnowledgeSignalType.CONTRADICTION: "Which representation or reasoning method resolves this contradiction: {statement}?",
    KnowledgeSignalType.UNKNOWN: "What minimum experiment can turn this unknown into calibrated evidence: {statement}?",
    KnowledgeSignalType.REPEATED_FAILURE: "Which alternative problem-solving method prevents this repeated failure: {statement}?",
    KnowledgeSignalType.CAPABILITY_GAP: "Which reusable cognitive method can supply this missing capability: {statement}?",
    KnowledgeSignalType.OPPORTUNITY: "Which general method can capture and transfer this opportunity: {statement}?",
}


def _validate_signal(signal: KnowledgeSignal) -> None:
    if not signal["signal_id"].strip() or not signal["domain_id"].strip() or not signal["statement"].strip():
        raise ValueError(f"knowledge signal identity and statement are required: signal_id={signal['signal_id']}")
    for field in ("severity", "novelty", "expected_reuse"):
        value = float(signal[field])
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"knowledge signal score must be within [0, 1]: signal_id={signal['signal_id']}, field={field}, value={value}"
            )


def discover_research_questions(
    signals: Sequence[KnowledgeSignal],
    question_budget: int,
) -> tuple[DiscoveryQuestion, ...]:
    if question_budget <= 0:
        raise ValueError(f"discovery question budget must be positive: question_budget={question_budget}")
    if len({signal["signal_id"] for signal in signals}) != len(signals):
        raise ValueError("knowledge signals contain duplicate identities")
    ranked: list[tuple[float, str, KnowledgeSignal]] = []
    for signal in signals:
        _validate_signal(signal)
        priority = (
            0.45 * signal["severity"]
            + 0.25 * signal["novelty"]
            + 0.30 * signal["expected_reuse"]
        )
        ranked.append((priority, signal["signal_id"], signal))
    questions: list[DiscoveryQuestion] = []
    for priority, _, signal in sorted(ranked, key=lambda item: (-item[0], item[1]))[:question_budget]:
        question = _QUESTION_TEMPLATES[signal["signal_type"]].format(statement=signal["statement"])
        identity = canonical_hash(
            {
                "source_signal_id": signal["signal_id"],
                "question": question,
                "evidence_ids": signal["evidence_ids"],
            }
        )
        questions.append(
            {
                "question_id": f"cognitive-question:{identity[:24]}",
                "source_signal_id": signal["signal_id"],
                "signal_type": signal["signal_type"].value,
                "domain_id": signal["domain_id"],
                "question": question,
                "priority": round(priority, 8),
                "evidence_ids": signal["evidence_ids"],
            }
        )
    return tuple(questions)
