"""Autonomous accept/reject kernel for open-source and open-data candidates."""
from __future__ import annotations

from typing import Any

from .autonomous_admissibility_models import (
    AutonomousAdmissibilityProofRecord,
    AutonomousDataAdmissibilityDecision,
    AutonomousLicenseAdmissibilityRecord,
    AutonomousProvenanceAdmissibilityRecord,
    AutonomousRepoAdmissibilityDecision,
    AutonomousSourceAdmissibilityRecord,
)
from .autonomy_common import (
    ARTIFACT_ROOT,
    COPYLEFT_LICENSES,
    PERMISSIVE_LICENSES,
    PUBLIC_DOMAIN_LICENSES,
    CandidateInput,
    data_outcome,
    decide_candidate,
    default_admissibility_candidates,
    safety_state,
    stable_hash,
    write_json,
    write_jsonl,
)


ARTIFACT_DIR = ARTIFACT_ROOT / "autonomy"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_admissibility_kernel_summary.json"
SOURCE_RECORDS_PATH = ARTIFACT_DIR / "autonomous_source_admissibility_records.jsonl"
LICENSE_RECORDS_PATH = ARTIFACT_DIR / "autonomous_license_admissibility_records.jsonl"
PROVENANCE_RECORDS_PATH = ARTIFACT_DIR / "autonomous_provenance_admissibility_records.jsonl"
DECISIONS_PATH = ARTIFACT_DIR / "autonomous_admissibility_decisions.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "autonomous_admissibility_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "autonomous_admissibility_proof.jsonl"


def run_autonomous_admissibility_kernel() -> dict[str, Any]:
    candidates = default_admissibility_candidates()
    return evaluate_autonomous_admissibility(candidates)


def evaluate_autonomous_admissibility(candidates: list[CandidateInput]) -> dict[str, Any]:
    source_records: list[dict[str, Any]] = []
    license_records: list[dict[str, Any]] = []
    provenance_records: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    for candidate in candidates:
        decision = decide_candidate(candidate)
        reasons = _reason_codes(candidate, decision)
        source_records.append(AutonomousSourceAdmissibilityRecord(
            source_id=candidate.source_id,
            source_name=candidate.name,
            source_family=candidate.family,
            source_url=candidate.source_url,
            decision=decision,
            reason_codes=reasons,
            paper_only=True,
            live_blocked=True,
        ).to_dict())
        license_records.append(AutonomousLicenseAdmissibilityRecord(
            source_id=candidate.source_id,
            license_id=candidate.license_id,
            license_known=bool(candidate.license_id),
            license_machine_verified=candidate.machine_readable_license,
            license_decision=decision,
            copyleft_reference_only=candidate.license_id in COPYLEFT_LICENSES,
            reason_codes=reasons,
        ).to_dict())
        provenance_records.append(AutonomousProvenanceAdmissibilityRecord(
            source_id=candidate.source_id,
            source_url=candidate.source_url,
            provenance_url=candidate.provenance_url,
            provenance_machine_verified=bool(candidate.provenance_url) and candidate.machine_readable_terms,
            no_credentials=not candidate.credentials_required,
            not_broker_or_live=not candidate.broker_or_live_source,
            not_sample_or_fixture=not candidate.sample_or_fixture,
            reason_codes=reasons,
        ).to_dict())
        ingest_allowed = data_outcome(candidate) == "accepted_for_internal_research_ingest"
        decisions.append(AutonomousDataAdmissibilityDecision(
            source_id=candidate.source_id,
            decision=decision,
            evidence_allowed=decision.startswith("accepted_"),
            ingest_allowed=ingest_allowed,
            fetch_allowed=ingest_allowed and bool(candidate.direct_download_url),
            reason_codes=reasons,
        ).to_dict())
        repo_import_mode = _repo_import_mode(candidate, decision)
        decisions.append(AutonomousRepoAdmissibilityDecision(
            source_id=candidate.source_id,
            decision=decision,
            import_mode=repo_import_mode,
            repo_allowed_as_reference=repo_import_mode == "reference_only",
            repo_allowed_as_adapter_candidate=repo_import_mode == "adapter_candidate",
            repo_allowed_as_sandbox_candidate=repo_import_mode == "sandbox_candidate",
            reason_codes=reasons,
        ).to_dict())
        if not decision.startswith("accepted_"):
            flags.append(_flag(candidate.source_id, decision, reasons))
    accepted_count = sum(1 for record in source_records if str(record["decision"]).startswith("accepted_"))
    rejected_count = sum(1 for record in source_records if str(record["decision"]).startswith("rejected_"))
    quarantined_count = sum(1 for record in source_records if str(record["decision"]).startswith("quarantined_"))
    terminal_block_count = sum(1 for record in source_records if record["decision"] == "terminal_block")
    proof = AutonomousAdmissibilityProofRecord(
        proof_id="autonomous-admissibility-proof-v1",
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        quarantined_count=quarantined_count,
        terminal_block_count=terminal_block_count,
        no_manual_review_status_emitted=True,
        no_human_review_required=True,
        paper_only=True,
        live_blocked=True,
    ).to_dict()
    summary = {
        "artifact_type": "autonomous_admissibility_kernel_summary",
        "admissibility_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "source_count": len(source_records),
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "quarantined_count": quarantined_count,
        "terminal_block_count": terminal_block_count,
        "no_manual_review_status_emitted": True,
        "unknown_license_auto_reject": True,
        "ambiguous_terms_auto_reject": True,
        "credentials_auto_reject": True,
        "paid_or_proprietary_auto_reject": True,
        "broker_or_live_auto_reject": True,
        "sample_or_fixture_auto_reject_as_evidence": True,
        "alpha_vantage_excluded": True,
        "network_fetch_performed": False,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(SOURCE_RECORDS_PATH, source_records)
    write_jsonl(LICENSE_RECORDS_PATH, license_records)
    write_jsonl(PROVENANCE_RECORDS_PATH, provenance_records)
    write_jsonl(DECISIONS_PATH, decisions)
    write_jsonl(QUALITY_FLAGS_PATH, flags)
    write_jsonl(PROOF_PATH, [proof])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_admissibility_kernel_summary": str(SUMMARY_PATH),
        "autonomous_source_admissibility_records": str(SOURCE_RECORDS_PATH),
        "autonomous_license_admissibility_records": str(LICENSE_RECORDS_PATH),
        "autonomous_provenance_admissibility_records": str(PROVENANCE_RECORDS_PATH),
        "autonomous_admissibility_decisions": str(DECISIONS_PATH),
        "autonomous_admissibility_quality_flags": str(QUALITY_FLAGS_PATH),
        "autonomous_admissibility_proof": str(PROOF_PATH),
    }


def _repo_import_mode(candidate: CandidateInput, decision: str) -> str:
    if not decision.startswith("accepted_"):
        return "rejected"
    if candidate.license_id in COPYLEFT_LICENSES or candidate.broker_or_live_source:
        return "reference_only"
    if candidate.license_id in PERMISSIVE_LICENSES or candidate.license_id in PUBLIC_DOMAIN_LICENSES:
        return "adapter_candidate"
    return "sandbox_candidate"


def _reason_codes(candidate: CandidateInput, decision: str) -> list[str]:
    reasons: list[str] = [decision]
    if not candidate.license_id:
        reasons.append("license_missing")
    if not candidate.machine_readable_terms:
        reasons.append("terms_not_machine_verified")
    if candidate.credentials_required:
        reasons.append("credentials_required")
    if candidate.broker_or_live_source:
        reasons.append("broker_or_live_source")
    if candidate.paid_or_proprietary:
        reasons.append("paid_or_proprietary")
    if candidate.scrape_only:
        reasons.append("scrape_only")
    if candidate.sample_or_fixture:
        reasons.append("sample_or_fixture")
    return sorted(set(reasons))


def _flag(source_id: str, decision: str, reason_codes: list[str]) -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_admissibility_quality_flag",
        "flag_id": f"autonomous-admissibility-{source_id}",
        "source_id": source_id,
        "severity": "info" if decision.startswith("rejected_") else "warning",
        "reason_code": decision,
        "reason_codes": reason_codes,
        "message": "Candidate was not accepted by autonomous machine-verifiable gates.",
        "paper_only": True,
        "live_blocked": True,
    }
    record["flag_hash"] = stable_hash(record)
    return record
