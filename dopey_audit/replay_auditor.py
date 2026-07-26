"""Deterministic replay audit orchestrator (hash + score + schema)."""
from __future__ import annotations

from .artifact_loader import ARTIFACT_SPECS, ARTIFACT_ROOT, _missing_required_fields, load_records
from .evidence_models import (
    EvidenceInventory,
    ReplayAuditCase,
    ReplayAuditResult,
    SchemaDriftFinding,
)
from .hash_auditor import audit_record_hash
from .score_replay import audit_ensemble_score_consistency, replay_ensemble_policy_sum
from pathlib import Path


def audit_schema(artifact_type: str, record: dict, record_index: int) -> tuple[ReplayAuditCase | None, SchemaDriftFinding | None]:
    required = _missing_required_fields(artifact_type, record)
    case_id = f"schema-{artifact_type}-{record_index}"
    if not required:
        return None, None
    # Preserve original spec field names for the report.
    spec = next((s for s in ARTIFACT_SPECS if s[0] == artifact_type), None)
    expected = spec[3] if spec else []
    case = ReplayAuditCase(
        case_id=case_id,
        artifact_type=artifact_type,
        audit_kind="schema",
        expected=",".join(expected),
        recomputed="missing_or_alias:" + ",".join(required),
        passed=False,
        notes="schema drift: required fields missing (aliases not satisfied)",
    )
    return case, SchemaDriftFinding(case_id=case_id, artifact_type=artifact_type, missing_fields=required, severity="warning")


def run_replay_audit(inventory: EvidenceInventory, root: Path | str | None = None) -> ReplayAuditResult:
    """Run hash + score + schema audit across the latest record of each present artifact."""
    base = Path(root) if root else ARTIFACT_ROOT
    cases: list[ReplayAuditCase] = []
    hash_findings = []
    score_findings = []
    schema_findings = []

    for artifact in inventory.artifacts:
        if artifact.status not in {"present", "stale"}:
            continue
        records = load_records(artifact.path)
        if not records:
            continue
        latest = records[-1]
        idx = len(records) - 1
        # hash audit
        case, finding = audit_record_hash(artifact.artifact_type, latest, idx)
        if case:
            cases.append(case)
        if finding:
            hash_findings.append(finding)
        # schema audit
        scase, sfinding = audit_schema(artifact.artifact_type, latest, idx)
        if scase:
            cases.append(scase)
        if sfinding:
            schema_findings.append(sfinding)

    # score replay on ensemble registry latest record
    ensemble_artifact = next((a for a in inventory.artifacts if a.artifact_type == "ensemble_registry"), None)
    if ensemble_artifact and ensemble_artifact.status in {"present", "stale"}:
        ensemble_record = load_records(ensemble_artifact.path)[-1]
        score_findings.extend(audit_ensemble_score_consistency(ensemble_record))
        replayed_sum = round(replay_ensemble_policy_sum(ensemble_record), 6)
        cases.append(ReplayAuditCase(
            case_id="score-ensemble-policy-replay",
            artifact_type="ensemble_registry",
            audit_kind="score",
            expected="1.0",
            recomputed=str(replayed_sum),
            passed=abs(replayed_sum - 1.0) <= 0.05 or replayed_sum == 0.0,
            notes="re-applied allocation policy normalizes accepted weights to 1.0",
        ))

    # verdict
    verdict = "pass"
    if hash_findings:
        verdict = "fail_reproducibility"
    elif schema_findings:
        verdict = "fail_schema"
    elif score_findings:
        verdict = "warning"

    return ReplayAuditResult(
        cases=cases,
        hash_findings=hash_findings,
        score_findings=score_findings,
        schema_findings=schema_findings,
        verdict=verdict,
    )
