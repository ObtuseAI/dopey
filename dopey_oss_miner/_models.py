"""Dopey OSS miner models: source-candidate / inflow-record data structures.

Forked verbatim from Blunder inflow models (Z:\\BFORK-20260630-020500\\blunder\\inflow\\models.py)
and renamed to the Dopey namespace. TypedDict (stdlib typing) is used — no pydantic — matching
the Blunder source. DOPEY uses these for research-grade OSS source discovery / quarantine only.

DOPEY lineage: Blunder inflow/models.py -> dopey_oss_miner._models
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict
from datetime import datetime, timezone
import hashlib


CLASSIFICATION: str = "DOPEY_OSS_MINER_INFLOW_MESH_V1"
TERMINAL_TARGET: str = "DOPEY_OSS_MINER_INFLOW_MESH_V1_READY_WITH_PROOF"

SourceType = Literal[
    "proof_ledger",
    "promotion_ledger",
    "rollback_ledger",
    "validation_summary",
    "failed_validation",
    "self_coding_attempt",
    "runtime_telemetry",
    "dunce_experiment",
    "benchmark_artifact",
    "owned_workspace_file",
    "official_reference",
    "agent_trace",
    "visual_evidence",
    "terminal_log",
    "test_failure",
]

TrustClass = Literal[
    "TRUSTED_INTERNAL",
    "OWNED_WORKSPACE",
    "OFFICIAL_REFERENCE",
    "OPEN_SOURCE_COMPATIBLE",
    "BENCHMARK_CORPUS",
    "AGENT_TRACE",
    "VISUAL_EVIDENCE",
    "RUNTIME_TELEMETRY",
    "VALIDATION_ARTIFACT",
    "FAILURE_ARTIFACT",
    "REPAIR_ARTIFACT",
    "THRESHOLD_ARTIFACT",
    "UNTRUSTED_QUARANTINE",
    "REJECTED",
]


class SourceCandidate(TypedDict):
    source_uri: str
    source_type: str
    trust_class: str
    license_class: str
    path: NotRequired[str]
    inline_text: NotRequired[str]
    authority_score: float
    relevance_score: float
    freshness_score: float
    reproducibility_score: float
    validation_history_score: float
    replayability_score: float
    internal_alignment_score: float


class Paopvol(TypedDict):
    problem: str
    attempt: str
    observation: str
    patch: str
    validation: str
    outcome: str
    lesson: str


class DopeyInflowRecord(TypedDict):
    record_id: str
    source_uri: str
    source_type: str
    trust_class: str
    license_class: str
    authority_score: float
    trust_score: float
    relevance_score: float
    freshness_score: float
    risk_score: float
    replayability_score: float
    content_hash: str
    ingested_at: str
    raw_artifact_path: str
    risk_flags: list[str]
    contradiction_flags: list[str]
    duplication_flags: list[str]
    capability_candidates: list[dict[str, Any]]
    replay_fixtures: list[dict[str, Any]]
    validation_refs: list[str]
    promotion_status: str
    paopvol: Paopvol


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(parts: list[str]) -> str:
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def empty_paopvol() -> Paopvol:
    return {
        "problem": "",
        "attempt": "",
        "observation": "",
        "patch": "",
        "validation": "",
        "outcome": "",
        "lesson": "",
    }


def build_record(
    candidate: SourceCandidate,
    content_hash: str,
    trust_score: float,
    risk_score: float,
    raw_artifact_path: str,
    risk_flags: list[str],
    duplication_flags: list[str],
    promotion_status: str,
) -> DopeyInflowRecord:
    record_id = stable_id([candidate["source_uri"], content_hash])
    return {
        "record_id": record_id,
        "source_uri": candidate["source_uri"],
        "source_type": candidate["source_type"],
        "trust_class": candidate["trust_class"],
        "license_class": candidate["license_class"],
        "authority_score": candidate["authority_score"],
        "trust_score": trust_score,
        "relevance_score": candidate["relevance_score"],
        "freshness_score": candidate["freshness_score"],
        "risk_score": risk_score,
        "replayability_score": candidate["replayability_score"],
        "content_hash": content_hash,
        "ingested_at": utc_now(),
        "raw_artifact_path": raw_artifact_path,
        "risk_flags": risk_flags,
        "contradiction_flags": [],
        "duplication_flags": duplication_flags,
        "capability_candidates": [],
        "replay_fixtures": [],
        "validation_refs": [],
        "promotion_status": promotion_status,
        "paopvol": empty_paopvol(),
    }
