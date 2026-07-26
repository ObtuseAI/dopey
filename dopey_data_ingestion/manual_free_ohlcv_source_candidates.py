"""Manual-only free/public OHLCV source candidates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .manual_ohlcv_staging_models import MANUAL_OHLCV_STAGING_VERSION, ManualOhlcvSourceCandidate


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "manual_ohlcv_staging"
MANUAL_FREE_OHLCV_SOURCE_CANDIDATES_PATH = ARTIFACT_DIR / "manual_free_ohlcv_source_candidates.jsonl"


def manual_free_ohlcv_source_candidate_records() -> list[dict[str, Any]]:
    candidates = [
        _candidate(
            "manual-exchange-etf-ohlcv",
            "Manually downloaded exchange or ETF OHLCV files",
            "daily_ohlcv",
            "operator_manual_download_or_export",
            "Broad equity or ETF coverage depends on the venue/export chosen by the operator.",
            "High if source universe omits delisted symbols or only includes current constituents.",
            "Operator must record export date and source reference.",
            "CSV headers vary by exchange or ETF sponsor.",
        ),
        _candidate(
            "stooq-style-manual-export",
            "Stooq-style OHLCV manual export candidate",
            "daily_ohlcv",
            "operator_manual_browser_export",
            "Coverage varies by symbol and market; operator must verify adjusted data semantics.",
            "Possible if source uses current lists or omits unavailable histories.",
            "Files may lag market close or update schedules.",
            "Column names and adjusted close conventions must be mapped manually.",
        ),
        _candidate(
            "yahoo-finance-manual-download",
            "Yahoo Finance manual-download candidate",
            "daily_ohlcv",
            "operator_manual_download",
            "Symbol coverage is convenient but terms/license must be reviewed by the operator.",
            "Possible if manually selecting currently known symbols.",
            "Download timestamp and adjusted price semantics must be recorded.",
            "CSV schema is usually simple but not accepted without manifest/provenance.",
        ),
        _candidate(
            "nasdaq-public-reference-file",
            "Nasdaq public reference file candidate if license permits",
            "market_context",
            "operator_manual_download_if_terms_permit",
            "Useful for reference metadata only when terms permit local research use.",
            "Reference files may reflect current listings only.",
            "Reference snapshots must include export date.",
            "Reference schema is not OHLCV and must stay in market_context.",
        ),
        _candidate(
            "cboe-public-reference-file",
            "CBOE public reference file candidate if license permits",
            "market_context",
            "operator_manual_download_if_terms_permit",
            "Potential options/reference context only; not options edge evidence.",
            "Reference universes can be current-only.",
            "Operator must record publication or export date.",
            "Schema may require manual normalization and cannot be treated as OHLCV.",
        ),
        _candidate(
            "sec-edgar-context",
            "SEC EDGAR metadata/fundamental context candidate",
            "market_context",
            "operator_manual_export_or_local_file",
            "Fundamental context only; not OHLCV and not options evidence.",
            "Issuer metadata can change over time.",
            "Filing metadata can be stale relative to market data.",
            "EDGAR metadata belongs in context files, not daily OHLCV.",
        ),
        _candidate(
            "fred-macro-rates-manual-csv",
            "FRED macro/rates manual CSV export candidate",
            "market_context",
            "operator_manual_csv_export",
            "Macro/rates context only; operator must record series and license/terms review.",
            "Low for macro series but symbol-level survivorship does not apply.",
            "Macro series can revise; operator must record vintage/export date.",
            "Series schema is context data and must not be mixed into OHLCV.",
        ),
        _candidate(
            "github-hosted-data-license-reviewed",
            "GitHub-hosted data candidate only if license/provenance explicitly permits use",
            "daily_ohlcv",
            "operator_manual_clone_or_download_outside_dopey_then_stage",
            "Allowed only after explicit license/provenance review by operator.",
            "High unless repository documents universe construction and delisting handling.",
            "Repository data can be stale or unmaintained.",
            "Schema and data generation process must be reviewed before staging.",
        ),
    ]
    return [candidate.to_dict() for candidate in candidates]


def write_manual_free_ohlcv_source_candidates() -> dict[str, Any]:
    records = manual_free_ohlcv_source_candidate_records()
    _write_jsonl(MANUAL_FREE_OHLCV_SOURCE_CANDIDATES_PATH, records)
    return {
        "source_candidate_count": len(records),
        "evidence_allowed_count": sum(1 for record in records if record["evidence_allowed"]),
        "manual_review_required_count": sum(1 for record in records if record["manual_review_required"]),
        "alpha_vantage_excluded": not any("alpha vantage" in record["source_name"].lower() for record in records),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "paper_only": True,
        "live_blocked": True,
        "artifact_paths": {"manual_free_ohlcv_source_candidates": str(MANUAL_FREE_OHLCV_SOURCE_CANDIDATES_PATH)},
    }


def _candidate(
    source_candidate_id: str,
    source_name: str,
    dataset_family: str,
    manual_access_mode: str,
    coverage_notes: str,
    survivorship_bias_risk: str,
    staleness_risk: str,
    schema_risk: str,
) -> ManualOhlcvSourceCandidate:
    return ManualOhlcvSourceCandidate(
        artifact_type="manual_free_ohlcv_source_candidates",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        source_candidate_id=source_candidate_id,
        source_name=source_name,
        dataset_family=dataset_family,
        manual_access_mode=manual_access_mode,
        requires_terms_review=True,
        license_status="operator_review_required",
        provenance_status="operator_review_required",
        commercial_use_uncertain=True,
        redistribution_uncertain=True,
        coverage_notes=coverage_notes,
        survivorship_bias_risk=survivorship_bias_risk,
        staleness_risk=staleness_risk,
        schema_risk=schema_risk,
        evidence_allowed=False,
        manual_review_required=True,
        not_fetched_by_dopey=True,
        credentials_required=False,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        not_strategy_promotion=True,
        candidate_hash="",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
