"""License and safety gates for open-source candidates."""
from __future__ import annotations

from .oss_models import OSS_STACK_VERSION, OssLicenseSecurityResult


PERMISSIVE_LICENSE_TOKENS: frozenset[str] = frozenset({"MIT", "Apache-2.0", "BSD-style"})


def build_oss_license_security_results(candidates: list[dict]) -> list[OssLicenseSecurityResult]:
    return [_result(candidate) for candidate in candidates]


def oss_license_security_records(candidates: list[dict]) -> list[dict]:
    return [result.to_dict() for result in build_oss_license_security_results(candidates)]


def build_oss_candidate_scorecard(candidates: list[dict], results: list[dict]) -> dict:
    return {
        "artifact_type": "oss_candidate_scorecard",
        "oss_stack_version": OSS_STACK_VERSION,
        "candidate_count": len(candidates),
        "reference_only_count": sum(1 for candidate in candidates if candidate["import_mode"] == "reference_only"),
        "sandbox_candidate_count": sum(1 for candidate in candidates if candidate["import_mode"] == "sandbox_candidate"),
        "adapter_candidate_count": sum(1 for candidate in candidates if candidate["import_mode"] == "adapter_candidate"),
        "rejected_count": sum(1 for candidate in candidates if candidate["import_mode"] == "rejected"),
        "manual_review_required_count": sum(1 for result in results if result["gate_status"] in {"manual_review_required", "adapter_candidate_manual_review"}),
        "terminal_block_count": sum(1 for result in results if result["gate_status"] == "terminal_block"),
        "repo_cloned_count": 0,
        "dependency_installed_count": 0,
        "external_code_imported_count": 0,
        "external_code_executed_count": 0,
        "paper_only": True,
        "live_blocked": True,
    }


def _result(candidate: dict) -> OssLicenseSecurityResult:
    license_name = str(candidate["license_name"])
    import_mode = str(candidate["import_mode"])
    unknown_license = "unknown" in license_name.lower() or "mixed" in license_name.lower()
    copyleft = "GPL" in license_name
    stale = str(candidate["maintenance_status"]) in {"stale", "unclear"}
    dangerous_dependencies = str(candidate["dependency_risk"]) == "high"
    broker_live = str(candidate["live_trading_risk"]) == "high" or str(candidate["broker_integration_risk"]) == "high"
    credentials = str(candidate["credential_risk"]) in {"medium", "high"}
    network = str(candidate["network_fetch_risk"]) in {"medium", "high"}
    reason_codes: list[str] = []
    if unknown_license:
        reason_codes.append("unknown_license_manual_review")
    if copyleft:
        reason_codes.append("copyleft_manual_review")
    if stale:
        reason_codes.append("stale_repo_manual_review")
    if dangerous_dependencies:
        reason_codes.append("dangerous_dependencies_manual_review")
    if broker_live:
        reason_codes.append("broker_or_live_trading_manual_review")
    if credentials:
        reason_codes.append("credential_handling_manual_review")
    if network:
        reason_codes.append("network_fetching_manual_review")
    license_compatible = license_name in PERMISSIVE_LICENSE_TOKENS and not unknown_license and not copyleft
    if import_mode == "rejected":
        status = "rejected"
    elif unknown_license:
        status = "manual_review_required"
    elif import_mode == "adapter_candidate":
        status = "adapter_candidate_manual_review"
    elif reason_codes:
        status = "manual_review_required"
    elif import_mode == "sandbox_candidate":
        status = "sandbox_import_candidate"
    else:
        status = "reference_only_allowed"
    return OssLicenseSecurityResult(
        artifact_type="oss_license_security_results",
        oss_stack_version=OSS_STACK_VERSION,
        candidate_id=str(candidate["candidate_id"]),
        gate_status=status,
        license_compatible=license_compatible,
        unknown_license_block=unknown_license,
        copyleft_manual_review=copyleft,
        stale_repo_manual_review=stale,
        dangerous_dependencies_manual_review=dangerous_dependencies,
        broker_live_trading_manual_review=broker_live,
        credential_handling_manual_review=credentials,
        network_fetching_manual_review=network,
        import_isolation_required=True,
        sandbox_test_required=True,
        no_direct_promotion_authority=True,
        no_direct_broker_authority=True,
        no_direct_scheduler_authority=True,
        reason_codes=reason_codes or ["reference_review_required"],
        paper_only=True,
        live_blocked=True,
        gate_hash="",
    )
