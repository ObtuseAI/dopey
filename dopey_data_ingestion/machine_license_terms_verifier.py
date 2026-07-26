"""Machine-only license and terms verifier for open-data breakthrough candidates."""
from __future__ import annotations

from collections import Counter
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .exhaustive_open_data_discovery_matrix import CANDIDATE_REGISTRY_PATH, run_exhaustive_open_data_discovery_matrix


ARTIFACT_DIR = ARTIFACT_ROOT / "open_data_breakthrough"
RESULTS_PATH = ARTIFACT_DIR / "machine_license_terms_results.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "machine_license_terms_summary.json"
PROOF_PATH = ARTIFACT_DIR / "machine_license_terms_proof.jsonl"

ACCEPTED_LICENSES = frozenset({"US-PD", "Public-Domain", "CC0-1.0", "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ODC-BY"})


def run_machine_license_terms_verifier() -> dict[str, Any]:
    if not CANDIDATE_REGISTRY_PATH.exists():
        run_exhaustive_open_data_discovery_matrix()
    candidates = read_jsonl(CANDIDATE_REGISTRY_PATH)
    results = [verify_candidate_license_terms(candidate) for candidate in candidates]
    counts = Counter(result["license_terms_status"] for result in results)
    summary = {
        "artifact_type": "machine_license_terms_summary",
        "verifier_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "candidate_count": len(candidates),
        "accepted_license_terms_count": counts.get("accepted_machine_verified", 0),
        "rejected_license_terms_count": sum(count for status, count in counts.items() if status.startswith("rejected_")),
        "license_terms_counts": dict(sorted(counts.items())),
        "no_manual_review_status_count": 0,
        "unknown_license_rejected": True,
        "ambiguous_terms_rejected": True,
        "login_api_key_payment_rejected": True,
        "scrape_only_rejected": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(RESULTS_PATH, results)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("machine-license-terms-proof-v1", "completed", summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def verify_candidate_license_terms(candidate: dict[str, Any]) -> dict[str, Any]:
    status = "accepted_machine_verified"
    reason = ""
    if candidate.get("requires_credentials") or candidate.get("api_key_required"):
        status = "rejected_credentials_required"
        reason = "credentials_or_api_key_required"
    elif candidate.get("requires_login"):
        status = "rejected_login_required"
        reason = "login_required"
    elif candidate.get("requires_payment"):
        status = "rejected_payment_required"
        reason = "payment_required"
    elif candidate.get("requires_scraping"):
        status = "rejected_scrape_only"
        reason = "scrape_only"
    elif not candidate.get("license_name") or not candidate.get("license_machine_verified"):
        status = "rejected_unknown_license"
        reason = "license_missing_or_not_machine_verified"
    elif not candidate.get("terms_machine_verified"):
        status = "rejected_ambiguous_terms"
        reason = "terms_not_machine_verified"
    elif candidate.get("license_name") not in ACCEPTED_LICENSES:
        status = "rejected_ambiguous_terms"
        reason = "license_not_in_machine_allowlist"
    elif candidate.get("machine_admissibility_status") in {"rejected_alpha_vantage", "rejected_tradingview", "rejected_broker_or_live_source"}:
        status = candidate["machine_admissibility_status"]
        reason = candidate.get("reject_reason", status)
    record = {
        "artifact_type": "machine_license_terms_results",
        "candidate_id": candidate["candidate_id"],
        "source_name": candidate["source_name"],
        "license_name": candidate.get("license_name", ""),
        "license_url": candidate.get("license_url", ""),
        "terms_url": candidate.get("terms_url", ""),
        "license_terms_status": status,
        "license_terms_acceptance_allowed": status == "accepted_machine_verified",
        "reject_reason": reason,
        "paper_only": True,
        "live_blocked": True,
    }
    record["result_hash"] = stable_hash(record)
    return record


def artifact_paths() -> dict[str, str]:
    return {
        "machine_license_terms_results": str(RESULTS_PATH),
        "machine_license_terms_summary": str(SUMMARY_PATH),
        "machine_license_terms_proof": str(PROOF_PATH),
    }
