"""Dopey source-value ranker: trust score, risk score, and inflow priority.

Forked from Blunder inflow source_trust_scorer.py + inflow_ranker.py (Z:\\BFORK-20260630-020500\\
blunder\\inflow\\). Renamed and merged into one module; both scoring functions preserved
verbatim (only their `blunder.inflow` import paths were re-routed to dopey_oss_miner).

DOPEY lineage: Blunder inflow/source_trust_scorer.py + inflow_ranker.py ->
              dopey_oss_miner.source_value_ranker
"""
from __future__ import annotations

from ._models import DopeyInflowRecord, SourceCandidate
from .license_scanner import license_score


def compute_trust_score(candidate: SourceCandidate, risk_flags: list[str], contradiction_count: int) -> float:
    secret_risk = 3.0 if any("KEY" in flag or "SECRET" in flag or "ENV" in flag for flag in risk_flags) else 0.0
    poison_risk = 2.0 if any("MALWARE" in flag or "EXPLOIT" in flag or "LEAKED" in flag for flag in risk_flags) else 0.0
    staleness_penalty = 0.4 if candidate["freshness_score"] < 0.5 else 0.0
    hallucination_risk = 0.7 if candidate["trust_class"] in {"AGENT_TRACE", "UNTRUSTED_QUARANTINE"} else 0.0
    contradiction_penalty = float(contradiction_count) * 0.35
    incompatibility_penalty = 2.0 if license_score(candidate["license_class"]) < 0 else 0.0
    unreplayable_penalty = 0.5 if candidate["replayability_score"] < 0.5 else 0.0
    score = (
        candidate["authority_score"]
        + license_score(candidate["license_class"])
        + candidate["relevance_score"]
        + candidate["freshness_score"]
        + candidate["reproducibility_score"]
        + candidate["validation_history_score"]
        + candidate["replayability_score"]
        + candidate["internal_alignment_score"]
        - secret_risk
        - poison_risk
        - staleness_penalty
        - hallucination_risk
        - contradiction_penalty
        - incompatibility_penalty
        - unreplayable_penalty
    )
    return round(score, 4)


def compute_risk_score(risk_flags: list[str], license_class: str) -> float:
    base = float(len(risk_flags)) * 0.5
    if license_score(license_class) < 0:
        base += 1.5
    return round(base, 4)


def compute_priority(record: DopeyInflowRecord) -> float:
    current_weakness_match = 1.0 if record["source_type"] in {"failed_validation", "runtime_telemetry"} else 0.45
    recent_failure_match = 1.0 if "failure" in record["source_uri"].lower() or "failed" in record["source_uri"].lower() else 0.35
    proof_value = 1.0 if record["source_type"] in {"proof_ledger", "validation_summary"} else 0.55
    novelty = 0.75 if not record["duplication_flags"] else 0.15
    validator_availability = 0.9 if record["replayability_score"] >= 0.5 else 0.35
    benchmark_relevance = 0.8 if "benchmark" in record["source_uri"].lower() else 0.25
    score = (
        current_weakness_match
        + recent_failure_match
        + record["relevance_score"]
        + proof_value
        + novelty
        + record["replayability_score"]
        + validator_availability
        + benchmark_relevance
        + 0.8
        + 0.85
        - record["risk_score"]
        - (0.5 if record["duplication_flags"] else 0.0)
        - (0.4 if record["freshness_score"] < 0.5 else 0.0)
        - (0.6 if record["authority_score"] < 0.4 else 0.0)
        - (0.5 if record["contradiction_flags"] else 0.0)
        - 0.2
    )
    return round(score, 4)
