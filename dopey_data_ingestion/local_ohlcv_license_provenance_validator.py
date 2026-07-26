"""License and provenance validation for local OHLCV files."""
from __future__ import annotations

from typing import Any

from .local_ohlcv_file_inventory import (
    LocalOhlcvParsedFile,
    REAL_DATA_MANIFEST_PATH,
    load_manifest_record,
    manifest_file_hashes,
    manifest_local_file_paths,
    repo_relative_path,
    sha256_file,
)
from .local_ohlcv_import_models import LOCAL_OHLCV_IMPORT_VERSION, LocalOhlcvLicenseProvenanceResult, stable_local_ohlcv_hash


REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "manifest_id",
    "created_at",
    "dataset_family",
    "provider_name",
    "provider_terms_reviewed",
    "license_status",
    "redistribution_allowed",
    "local_file_paths",
    "file_hashes",
    "row_counts",
    "symbol_counts",
    "date_ranges",
    "schema_version",
    "ingested_by",
    "manual_operator_note",
    "not_broker_data",
    "not_credentials",
    "not_live_data",
    "not_network_fetched_by_dopey",
    "paper_only",
    "live_blocked",
)
VALID_LICENSE_STATUSES: frozenset[str] = frozenset({
    "reviewed_allowed_internal_research",
    "reviewed_restricted_internal_research",
    "reviewed_public_domain",
    "reviewed_open_data_internal_research",
})
INVALID_LICENSE_STATUSES: frozenset[str] = frozenset({"unknown", "unreviewed", "missing", "unlicensed", "template_only"})


def required_manifest_template_fields() -> list[str]:
    return list(REQUIRED_MANIFEST_FIELDS)


def validate_license_provenance_records(parsed_files: list[LocalOhlcvParsedFile]) -> list[dict[str, Any]]:
    manifest = load_manifest_record(REAL_DATA_MANIFEST_PATH)
    if not parsed_files:
        return [_missing_files_record(manifest).to_dict()]
    return [validate_file_license_provenance(parsed, manifest).to_dict() for parsed in parsed_files]


def validate_file_license_provenance(parsed: LocalOhlcvParsedFile, manifest: dict[str, Any]) -> LocalOhlcvLicenseProvenanceResult:
    relative = repo_relative_path(parsed.path)
    missing_fields = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    license_status = str(manifest.get("license_status", "missing")).lower()
    manifest_paths = manifest_local_file_paths(manifest)
    file_hashes = manifest_file_hashes(manifest)
    hash_recorded = relative in file_hashes
    hash_matches = hash_recorded and file_hashes[relative] == sha256_file(parsed.path)
    provider_present = bool(manifest.get("provider_name") and manifest.get("provider_name") != "TEMPLATE_ONLY")
    source_present = bool(manifest.get("source") or manifest.get("source_url_or_name") or provider_present or any(row.get("source", "").strip() for row in parsed.rows))
    template_only = bool(manifest.get("template_only") is True or license_status == "template_only" or manifest.get("manifest_id") == "TEMPLATE_ONLY_NOT_REAL_DATA")
    reasons: list[str] = []
    if not manifest:
        reasons.append("missing_manifest")
    if missing_fields:
        reasons.append("missing_manifest_fields")
    if template_only:
        reasons.append("manifest_template_only")
    if relative not in manifest_paths:
        reasons.append("manifest_file_reference_missing")
    if not provider_present:
        reasons.append("missing_provider")
    if not source_present:
        reasons.append("missing_provenance")
    if not license_status or license_status in INVALID_LICENSE_STATUSES:
        reasons.append("missing_license")
    if manifest.get("provider_terms_reviewed") is not True:
        reasons.append("terms_not_reviewed")
    if not hash_recorded:
        reasons.append("missing_file_hash")
    if hash_recorded and not hash_matches:
        reasons.append("file_hash_mismatch")
    for field in ("not_network_fetched_by_dopey", "not_credentials", "not_broker_data", "not_live_data", "paper_only", "live_blocked"):
        if manifest.get(field) is not True:
            reasons.append(f"{field}_false")
    terminal = (
        (hash_recorded and not hash_matches)
        or manifest.get("not_network_fetched_by_dopey") is False
        or manifest.get("not_credentials") is False
        or manifest.get("not_broker_data") is False
        or manifest.get("not_live_data") is False
    )
    if terminal:
        status = "terminal_block"
    elif "missing_license" in reasons:
        status = "blocked_missing_license"
    elif "missing_provenance" in reasons or "manifest_file_reference_missing" in reasons:
        status = "blocked_missing_provenance"
    elif reasons:
        status = "manual_review_required"
    else:
        status = "provenance_pass"
    return LocalOhlcvLicenseProvenanceResult(
        artifact_type="local_ohlcv_license_provenance_results",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        result_id=f"license-{stable_local_ohlcv_hash({'path': relative})[:12]}",
        dataset_family=parsed.dataset_family,
        local_file_path=relative,
        status=status,
        provider_name_present=provider_present,
        source_present=source_present,
        license_status_present=bool(license_status),
        license_status_accepted=license_status in VALID_LICENSE_STATUSES,
        provider_terms_reviewed=manifest.get("provider_terms_reviewed") is True,
        redistribution_allowed_recorded="redistribution_allowed" in manifest,
        file_hash_recorded=hash_recorded,
        file_hash_matches_manifest=hash_matches,
        provenance_complete=not reasons,
        manifest_template_only=template_only,
        manifest_missing_required_fields=missing_fields,
        reason_codes=reasons,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        license_hash="",
    )


def _missing_files_record(manifest: dict[str, Any]) -> LocalOhlcvLicenseProvenanceResult:
    template_only = bool(manifest.get("template_only") is True or manifest.get("manifest_id") == "TEMPLATE_ONLY_NOT_REAL_DATA")
    return LocalOhlcvLicenseProvenanceResult(
        artifact_type="local_ohlcv_license_provenance_results",
        validator_version=LOCAL_OHLCV_IMPORT_VERSION,
        result_id="license-no-local-ohlcv-files",
        dataset_family="none",
        local_file_path="",
        status="blocked_missing_manifest",
        provider_name_present=False,
        source_present=False,
        license_status_present=False,
        license_status_accepted=False,
        provider_terms_reviewed=False,
        redistribution_allowed_recorded=False,
        file_hash_recorded=False,
        file_hash_matches_manifest=False,
        provenance_complete=False,
        manifest_template_only=template_only,
        manifest_missing_required_fields=[field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest],
        reason_codes=["missing_local_ohlcv_files", "blocked_missing_manifest"],
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        license_hash="",
    )
