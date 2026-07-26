"""Operator checklist for manual OHLCV staging."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_ohlcv_license_provenance_validator import required_manifest_template_fields
from .local_staging_contract import REPO_ROOT
from .manual_ohlcv_staging_models import MANUAL_OHLCV_STAGING_VERSION, ManualOhlcvStagingChecklist


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "manual_ohlcv_staging"
MANUAL_OHLCV_STAGING_CHECKLIST_PATH = ARTIFACT_DIR / "manual_ohlcv_staging_checklist.json"
REQUIRED_FOLDERS: tuple[str, ...] = (
    "dopey_data/real/raw/daily_ohlcv/",
    "dopey_data/real/raw/market_context/",
    "dopey_data/real/raw/corporate_actions/",
    "dopey_data/real/manifests/",
)
REQUIRED_DAILY_OHLCV_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "source",
)
RECOMMENDED_OPTIONAL_COLUMNS: tuple[str, ...] = ("dividend", "split_factor", "provider_record_id")
REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    *tuple(required_manifest_template_fields()),
    "source_urls_or_reference_names",
    "download_or_export_dates",
)
BLOCKER_CODES: tuple[str, ...] = (
    "missing_files",
    "missing_manifest",
    "unknown_license",
    "unreviewed_license",
    "missing_source",
    "missing_file_hash",
    "sample_only_rows",
    "SAMPLE_ONLY",
    ".env",
    "credentials_tokens",
    "broker_live_order_scheduler_real_sizing_markers",
    "future_dates",
    "high_low_inconsistency",
    "duplicate_date_symbol_rows",
)


def build_manual_ohlcv_staging_checklist() -> dict[str, Any]:
    checklist = ManualOhlcvStagingChecklist(
        artifact_type="manual_ohlcv_staging_checklist",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        checklist_id="manual-ohlcv-staging-checklist-v1",
        required_folders=list(REQUIRED_FOLDERS),
        required_daily_ohlcv_columns=list(REQUIRED_DAILY_OHLCV_COLUMNS),
        recommended_optional_columns=list(RECOMMENDED_OPTIONAL_COLUMNS),
        required_manifest_fields=list(REQUIRED_MANIFEST_FIELDS),
        blocker_codes=list(BLOCKER_CODES),
        operator_actions=[
            "Place only operator-supplied CSV or JSONL files in the allowed raw folders.",
            "Run the manifest draft helper to compute local hashes and row/date/symbol counts.",
            "Manually review source terms and complete the final manifest before validation can pass.",
            "Remove templates, SAMPLE_ONLY symbols, sample_only rows, not_real_data rows, credentials, and live markers.",
        ],
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        not_strategy_promotion=True,
        checklist_hash="",
    )
    return checklist.to_dict()


def write_manual_ohlcv_staging_checklist() -> dict[str, Any]:
    record = build_manual_ohlcv_staging_checklist()
    _write_json(MANUAL_OHLCV_STAGING_CHECKLIST_PATH, record)
    return {
        **record,
        "artifact_paths": {"manual_ohlcv_staging_checklist": str(MANUAL_OHLCV_STAGING_CHECKLIST_PATH)},
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
