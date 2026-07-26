"""Validate operator-supplied OHLCV source-review packets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvSourceReview,
    stable_operator_stage_hash,
)


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
MANIFEST_DIR = REPO_ROOT / "dopey_data" / "real" / "manifests"
OPERATOR_SOURCE_REVIEW_PATH = MANIFEST_DIR / "operator_ohlcv_source_review.json"
OPERATOR_SOURCE_REVIEW_TEMPLATE_PATH = MANIFEST_DIR / "operator_ohlcv_source_review.template.json"
SOURCE_REVIEW_CONTRACT_PATH = ARTIFACT_DIR / "operator_ohlcv_source_review_contract.json"
SOURCE_REVIEW_STATUS_PATH = ARTIFACT_DIR / "operator_ohlcv_source_review_status.json"
VALID_LICENSE_STATUSES: frozenset[str] = frozenset({
    "reviewed_allowed_internal_research",
    "reviewed_restricted_internal_research",
    "reviewed_public_domain",
    "reviewed_open_data_internal_research",
})
BLOCKING_LICENSE_STATUSES: frozenset[str] = frozenset({
    "unknown",
    "unreviewed",
    "missing",
    "unlicensed",
    "template_only",
})
REQUIRED_SOURCE_REVIEW_FIELDS: tuple[str, ...] = (
    "review_id",
    "reviewed_at",
    "reviewed_by",
    "source_name",
    "source_type",
    "source_urls_or_reference_names",
    "download_or_export_dates",
    "dataset_families",
    "provider_terms_reviewed",
    "license_status",
    "license_notes",
    "redistribution_allowed",
    "commercial_use_allowed",
    "internal_research_use_allowed",
    "provenance_notes",
    "survivorship_bias_reviewed",
    "adjusted_price_method_reviewed",
    "corporate_actions_available",
    "operator_affirms_no_credentials",
    "operator_affirms_not_broker_data",
    "operator_affirms_not_live_data",
    "operator_affirms_not_network_fetched_by_dopey",
    "operator_affirms_files_are_not_sample_templates",
    "operator_affirms_no_api_keys_or_tokens",
    "operator_affirms_no_account_balances_or_buying_power",
    "operator_affirms_no_order_or_execution_records",
    "paper_only",
    "live_blocked",
)
AFFIRMATION_FIELDS: tuple[str, ...] = (
    "operator_affirms_no_credentials",
    "operator_affirms_not_broker_data",
    "operator_affirms_not_live_data",
    "operator_affirms_not_network_fetched_by_dopey",
    "operator_affirms_files_are_not_sample_templates",
    "operator_affirms_no_api_keys_or_tokens",
    "operator_affirms_no_account_balances_or_buying_power",
    "operator_affirms_no_order_or_execution_records",
    "paper_only",
    "live_blocked",
)


def template_source_review_packet() -> dict[str, Any]:
    record = {
        "review_id": "TEMPLATE_ONLY_OPERATOR_MUST_REPLACE",
        "reviewed_at": "TEMPLATE_ONLY",
        "reviewed_by": "TEMPLATE_ONLY",
        "source_name": "TEMPLATE_ONLY",
        "source_type": "TEMPLATE_ONLY",
        "source_urls_or_reference_names": [],
        "download_or_export_dates": {},
        "dataset_families": [],
        "provider_terms_reviewed": False,
        "license_status": "template_only",
        "license_notes": "Template only. Not evidence.",
        "redistribution_allowed": False,
        "commercial_use_allowed": False,
        "internal_research_use_allowed": False,
        "provenance_notes": "Template only.",
        "survivorship_bias_reviewed": False,
        "adjusted_price_method_reviewed": False,
        "corporate_actions_available": False,
        "operator_affirms_no_credentials": False,
        "operator_affirms_not_broker_data": False,
        "operator_affirms_not_live_data": False,
        "operator_affirms_not_network_fetched_by_dopey": False,
        "operator_affirms_files_are_not_sample_templates": False,
        "operator_affirms_no_api_keys_or_tokens": False,
        "operator_affirms_no_account_balances_or_buying_power": False,
        "operator_affirms_no_order_or_execution_records": False,
        "paper_only": True,
        "live_blocked": True,
        "template_only": True,
        "sample_only": True,
        "not_real_data": True,
    }
    record["template_hash"] = stable_operator_stage_hash(record)
    return record


def build_source_review_contract() -> dict[str, Any]:
    record = {
        "artifact_type": "operator_ohlcv_source_review_contract",
        "stage_version": OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        "contract_id": "operator-ohlcv-source-review-contract-v1",
        "input_path": str(OPERATOR_SOURCE_REVIEW_PATH),
        "template_path": str(OPERATOR_SOURCE_REVIEW_TEMPLATE_PATH),
        "required_fields": list(REQUIRED_SOURCE_REVIEW_FIELDS),
        "valid_license_statuses": sorted(VALID_LICENSE_STATUSES),
        "blocking_license_statuses": sorted(BLOCKING_LICENSE_STATUSES),
        "never_infer_review_from_source_name_url_or_filename": True,
        "evidence_allowed_without_packet": False,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["contract_hash"] = stable_operator_stage_hash(record)
    return record


def validate_operator_source_review_packet(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _review_record(
            status="operator_review_packet_missing",
            source_review_valid=False,
            evidence_allowed=False,
            missing_fields=[],
            blocking_fields=[],
            license_status="missing",
        )
    raw = _load_json(path)
    missing = [field for field in REQUIRED_SOURCE_REVIEW_FIELDS if field not in raw]
    license_status = str(raw.get("license_status", "missing"))
    blocking_fields = _blocking_review_fields(raw)
    template_only = bool(raw.get("template_only") is True or license_status == "template_only")
    if missing or template_only or license_status in BLOCKING_LICENSE_STATUSES:
        status = "operator_review_packet_incomplete"
        valid = False
    elif blocking_fields:
        status = "terminal_block"
        valid = False
    elif license_status not in VALID_LICENSE_STATUSES:
        status = "operator_review_packet_incomplete"
        valid = False
    else:
        status = "operator_review_packet_valid"
        valid = True
    return _review_record(
        status=status,
        source_review_valid=valid,
        evidence_allowed=valid,
        missing_fields=missing,
        blocking_fields=blocking_fields,
        license_status=license_status,
    )


def write_operator_source_review_contract() -> dict[str, Any]:
    OPERATOR_SOURCE_REVIEW_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not OPERATOR_SOURCE_REVIEW_TEMPLATE_PATH.exists():
        _write_json(OPERATOR_SOURCE_REVIEW_TEMPLATE_PATH, template_source_review_packet())
    contract = build_source_review_contract()
    status = validate_operator_source_review_packet(OPERATOR_SOURCE_REVIEW_PATH)
    _write_json(SOURCE_REVIEW_CONTRACT_PATH, contract)
    _write_json(SOURCE_REVIEW_STATUS_PATH, status)
    return {
        **status,
        "contract_path": str(SOURCE_REVIEW_CONTRACT_PATH),
        "status_path": str(SOURCE_REVIEW_STATUS_PATH),
        "template_path": str(OPERATOR_SOURCE_REVIEW_TEMPLATE_PATH),
    }


def _review_record(
    status: str,
    source_review_valid: bool,
    evidence_allowed: bool,
    missing_fields: list[str],
    blocking_fields: list[str],
    license_status: str,
) -> dict[str, Any]:
    return OperatorReviewedOhlcvSourceReview(
        artifact_type="operator_ohlcv_source_review_status",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        review_id="operator-ohlcv-source-review-status-v1",
        status=status,
        source_review_valid=source_review_valid,
        evidence_allowed=evidence_allowed,
        missing_fields=missing_fields,
        blocking_fields=blocking_fields,
        license_status=license_status,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        strategy_promotion_allowed=False,
        not_options_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        review_hash="",
    ).to_dict()


def _blocking_review_fields(record: dict[str, Any]) -> list[str]:
    failed = [field for field in AFFIRMATION_FIELDS if field in record and record.get(field) is not True]
    if record.get("live_blocked") is not True:
        failed.append("live_blocked")
    if record.get("paper_only") is not True:
        failed.append("paper_only")
    return sorted(set(failed))


def _load_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
