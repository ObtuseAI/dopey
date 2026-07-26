"""Deterministic hash audit for the offline evidence replay harness.

Recomputes reproducibility hashes over stored records and detects hash drift. Only artifact
types whose bundles used the canonical single-record hash formula are strictly compared;
others are recorded as hash-present info cases (their multi-part formula is not recomputed
from the stored record alone).
"""
from __future__ import annotations

import hashlib
import json

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .evidence_models import HashDriftFinding, ReplayAuditCase


# Artifact types whose stored reproducibility_hash is the canonical single-record hash
# (recomputable from the stored record alone).
STRICT_HASH_TYPES = frozenset({
    "ensemble_registry",
    "meta_governor_registry",
    "meta_governor_decisions",
    "walk_forward_consistency_registry",
    "regime_holdout_corpus_v2_registry",
    "fundamental_registry",
    "reporting_dashboard_index",
    "strategy_report_cards",
    "family_report_cards",
    "export_manifest",
    "export_copy_proof",
    "export_review_registry",
    "export_review_evidence_map",
    "export_review_checklist",
})


def canonical_record_hash(record: dict) -> str:
    """Single-part canonical hash over the record excluding its own reproducibility_hash."""
    stripped = {k: v for k, v in record.items() if k != "reproducibility_hash"}
    return reproducibility_hash(stripped)


def raw_record_hash(record: dict) -> str:
    """Raw sorted-JSON SHA256 over the full record (used for digests)."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def audit_record_hash(artifact_type: str, record: dict, record_index: int) -> tuple[ReplayAuditCase | None, HashDriftFinding | None]:
    stored = str(record.get("reproducibility_hash", ""))
    case_id = f"hash-{artifact_type}-{record_index}"
    if not stored:
        return None, None
    if artifact_type not in STRICT_HASH_TYPES:
        case = ReplayAuditCase(
            case_id=case_id,
            artifact_type=artifact_type,
            audit_kind="hash",
            expected=stored,
            recomputed="(multi-part formula; not recomputed)",
            passed=True,
            notes="reproducibility_hash present; bundle used a multi-part formula not recomputed from stored record",
        )
        return case, None
    recomputed = canonical_record_hash(record)
    passed = recomputed == stored
    case = ReplayAuditCase(
        case_id=case_id,
        artifact_type=artifact_type,
        audit_kind="hash",
        expected=stored,
        recomputed=recomputed,
        passed=passed,
        notes="strict single-record hash recompute" if passed else "hash drift detected",
    )
    finding = None if passed else HashDriftFinding(
        case_id=case_id,
        artifact_type=artifact_type,
        stored_hash=stored,
        recomputed_hash=recomputed,
        severity="error",
    )
    return case, finding
