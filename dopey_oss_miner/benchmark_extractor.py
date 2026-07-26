"""Dopey benchmark extractor: mine proof/benchmark artifacts from quarantined records.

Forked verbatim from Blunder inflow proof_artifact_miner.py (Z:\\BFORK-20260630-020500\\blunder\\
inflow\\proof_artifact_miner.py). Renamed module; internal import re-routed to dopey_oss_miner
models. Candidates require replay before any promotion.

DOPEY lineage: Blunder inflow/proof_artifact_miner.py -> dopey_oss_miner.benchmark_extractor
"""
from __future__ import annotations

from ._models import DopeyInflowRecord


def mine_proof_artifact(record: DopeyInflowRecord, normalized_text: str) -> list[dict[str, object]]:
    lowered = normalized_text.lower()
    candidates: list[dict[str, object]] = []
    if record["source_type"] in {"proof_ledger", "validation_summary"} or "pass" in lowered:
        candidates.append({
            "candidate_id": f"{record['record_id']}-validation-rule",
            "target_type": "ValidationRule",
            "title": "Preserve proof-ledger validation before promotion",
            "evidence_record_id": record["record_id"],
            "requires_replay": True,
        })
    if "rollback" in lowered or "demotion" in lowered:
        candidates.append({
            "candidate_id": f"{record['record_id']}-rollback-rule",
            "target_type": "RuntimeStabilityRule",
            "title": "Require rollback or demotion path before active skill promotion",
            "evidence_record_id": record["record_id"],
            "requires_replay": True,
        })
    return candidates
