"""Run the manual free/public OHLCV staging and activation stack."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from dopey_analysis.run_real_signal_validation_gate import run_real_signal_validation_gate
from dopey_data.run_real_ohlcv_history_spine_activation import run_real_ohlcv_history_spine_activation
from dopey_core.repo_paths import REPORTS_DIR

from .local_ohlcv_import_models import stable_local_ohlcv_hash
from .local_staging_contract import REPO_ROOT
from .manual_free_ohlcv_source_candidates import write_manual_free_ohlcv_source_candidates
from .manual_ohlcv_import_fix_engine import write_manual_ohlcv_import_fix_plan
from .manual_ohlcv_manifest_draft import write_manual_ohlcv_manifest_draft
from .manual_ohlcv_preflight_linter import write_manual_ohlcv_preflight
from .manual_ohlcv_staging_checklist import write_manual_ohlcv_staging_checklist
from .manual_ohlcv_staging_models import MANUAL_OHLCV_STAGING_VERSION, ManualOhlcvStagingProofRecord, stable_manual_ohlcv_hash
from .run_free_data_provenance_gate import run_free_data_provenance_gate
from .run_local_ohlcv_import_validator import run_local_ohlcv_import_validator


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "local_free_ohlcv_stack"
MANUAL_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "manual_ohlcv_staging"
STACK_SUMMARY_PATH = ARTIFACT_DIR / "local_free_ohlcv_validation_and_activation_stack_summary.json"
STACK_QUALITY_FLAGS_PATH = ARTIFACT_DIR / "local_free_ohlcv_validation_and_activation_stack_quality_flags.jsonl"
STACK_PROOF_PATH = ARTIFACT_DIR / "local_free_ohlcv_validation_and_activation_stack_proof.jsonl"
MANUAL_STAGING_SUMMARY_PATH = MANUAL_ARTIFACT_DIR / "manual_ohlcv_staging_summary.json"
MANUAL_STAGING_PROOF_PATH = MANUAL_ARTIFACT_DIR / "manual_ohlcv_staging_proof.jsonl"
EXPORT_VERIFIER_TIMEOUT_NOTE_PATH = MANUAL_ARTIFACT_DIR / "export_verifier_timeout_note.json"
REPORT_PATH = REPORTS_DIR / "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_ARTIFACT_LEDGER.md"
FREE_INSTRUCTIONS_PATH = REPORTS_DIR / "DOPEY_MANUAL_FREE_OHLCV_STAGING_INSTRUCTIONS.md"
REAL_INSTRUCTIONS_PATH = REPORTS_DIR / "DOPEY_MANUAL_REAL_OHLCV_STAGING_INSTRUCTIONS.md"


def run_local_free_ohlcv_validation_and_activation_stack() -> dict[str, Any]:
    free_data = run_free_data_provenance_gate()
    source_candidates = write_manual_free_ohlcv_source_candidates()
    checklist = write_manual_ohlcv_staging_checklist()
    manifest_draft = write_manual_ohlcv_manifest_draft()
    preflight = write_manual_ohlcv_preflight()
    local = run_local_ohlcv_import_validator()
    fix_plan = write_manual_ohlcv_import_fix_plan()
    history = run_real_ohlcv_history_spine_activation()
    signals = run_real_signal_validation_gate()
    timeout_note = _write_export_verifier_timeout_note()
    fixture_paths = write_fixture_cases()
    summary = _summary(free_data, source_candidates, manifest_draft, preflight, local, fix_plan, history, signals)
    flags = _quality_flags(summary)
    proof = [_proof(summary)]
    _write_json(MANUAL_STAGING_SUMMARY_PATH, {**summary, "artifact_paths": manual_artifact_paths(), "fixture_paths": fixture_paths})
    _write_jsonl(MANUAL_STAGING_PROOF_PATH, proof)
    _write_json(STACK_SUMMARY_PATH, {**summary, "artifact_paths": {**artifact_paths(), **manual_artifact_paths()}, "fixture_paths": fixture_paths})
    _write_jsonl(STACK_QUALITY_FLAGS_PATH, flags)
    _write_jsonl(STACK_PROOF_PATH, proof)
    _write_docs(summary, fixture_paths, checklist, timeout_note)
    _copy_reports_to_shared_folder([REPORT_PATH, LEDGER_PATH, FREE_INSTRUCTIONS_PATH, REAL_INSTRUCTIONS_PATH])
    return {
        **summary,
        "artifact_paths": {**artifact_paths(), **manual_artifact_paths()},
        "fixture_paths": fixture_paths,
        "report_path": str(REPORT_PATH),
        "ledger_path": str(LEDGER_PATH),
    }


def artifact_paths() -> dict[str, str]:
    return {
        "local_free_ohlcv_validation_and_activation_stack_summary": str(STACK_SUMMARY_PATH),
        "local_free_ohlcv_validation_and_activation_stack_quality_flags": str(STACK_QUALITY_FLAGS_PATH),
        "local_free_ohlcv_validation_and_activation_stack_proof": str(STACK_PROOF_PATH),
    }


def manual_artifact_paths() -> dict[str, str]:
    return {
        "manual_ohlcv_staging_summary": str(MANUAL_STAGING_SUMMARY_PATH),
        "manual_ohlcv_staging_proof": str(MANUAL_STAGING_PROOF_PATH),
        "export_verifier_timeout_note": str(EXPORT_VERIFIER_TIMEOUT_NOTE_PATH),
    }


def write_fixture_cases() -> list[str]:
    groups = _manual_fixture_groups()
    output_paths: list[str] = []
    for relative, names in groups.items():
        path = REPO_ROOT / "dopey_data" / "fixtures" / "manual_ohlcv_staging" / relative
        cases = [_fixture_case(index + 1, name) for index, name in enumerate(names)]
        _write_json(path, {"artifact_type": Path(relative).stem, "case_count": len(cases), "cases": cases})
        output_paths.append(str(path))
    return output_paths


def _summary(
    free_data: dict[str, Any],
    source_candidates: dict[str, Any],
    manifest_draft: dict[str, Any],
    preflight: dict[str, Any],
    local: dict[str, Any],
    fix_plan: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    manual_status = _manual_staging_status(manifest_draft, preflight, local, fix_plan)
    manual_decision = _manual_staging_decision(manual_status, preflight, local, fix_plan)
    record = {
        "artifact_type": "manual_ohlcv_staging_summary",
        "stack_version": "dopey-manual-free-ohlcv-staging-local-import-fix-v1",
        "manual_staging_status": manual_status,
        "manual_staging_decision": manual_decision,
        "source_candidate_count": int(source_candidates["source_candidate_count"]),
        "evidence_allowed_count": int(source_candidates["evidence_allowed_count"]),
        "free_data_candidate_count": int(free_data["free_data_candidate_count"]),
        "free_data_evidence_allowed_count": int(free_data["free_data_evidence_allowed_count"]),
        "free_data_manual_review_required_count": int(free_data["free_data_manual_review_required_count"]),
        "hash_record_count": int(manifest_draft["hash_record_count"]),
        "manifest_draft_status": str(manifest_draft["draft_status"]),
        "preflight_status": str(preflight["preflight_status"]),
        "fix_plan_status": str(fix_plan["fix_plan_status"]),
        "local_ohlcv_status": str(local["local_ohlcv_status"]),
        "local_ohlcv_import_decision": str(local["local_ohlcv_import_decision"]),
        "local_ohlcv_fix_advice_status": str(local["fix_advice_status"]),
        "real_data_files_present": bool(local["real_data_files_present"]),
        "valid_real_dataset": bool(local["valid_real_dataset"]),
        "history_spine_activation_status": str(history["history_spine_activation_status"]),
        "real_history_used": bool(history["real_history_used"]),
        "real_signal_validation_status": str(signals["real_signal_validation_status"]),
        "real_signal_evidence": bool(signals["real_signal_evidence"]),
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
        "alpha_vantage_excluded": True,
        "paper_only": True,
        "live_blocked": True,
        "next_recommended_target": "DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR",
    }
    record["summary_hash"] = stable_local_ohlcv_hash(record)
    return record


def _manual_staging_status(manifest_draft: dict[str, Any], preflight: dict[str, Any], local: dict[str, Any], fix_plan: dict[str, Any]) -> str:
    if local.get("local_ohlcv_status") == "local_ohlcv_validation_pass":
        return "validator_pass_ready_for_history_activation"
    if fix_plan.get("fix_plan_status") == "terminal_block" or preflight.get("preflight_status") == "terminal_block":
        return "terminal_block"
    if manifest_draft.get("real_data_files_present") is False:
        return "manual_staging_required"
    if preflight.get("preflight_status") == "preflight_fail":
        return "local_files_detected_repair_required"
    if fix_plan.get("fix_plan_status") == "local_files_detected_repair_required":
        return "local_files_detected_repair_required"
    return "local_files_ready_for_validator"


def _manual_staging_decision(manual_status: str, preflight: dict[str, Any], local: dict[str, Any], fix_plan: dict[str, Any]) -> str:
    if manual_status == "manual_staging_required":
        return "operator_must_stage_files"
    if manual_status == "terminal_block":
        return "operator_must_remove_credentials_or_live_markers"
    if local.get("local_ohlcv_status") == "local_ohlcv_validation_pass":
        return "ready_for_history_spine_activation_after_validator_pass"
    counts = fix_plan.get("fix_group_counts", {}) if isinstance(fix_plan.get("fix_group_counts"), dict) else {}
    if int(counts.get("repair_schema", 0)) > 0:
        return "operator_must_fix_schema"
    if int(counts.get("repair_quality", 0)) > 0:
        return "operator_must_fix_quality"
    if int(counts.get("remove_sample_template_rows", 0)) > 0:
        return "operator_must_remove_sample_or_template_rows"
    if int(counts.get("repair_license_provenance", 0)) > 0:
        return "operator_must_fix_license_provenance"
    if preflight.get("final_manifest_template_only") is True or int(counts.get("complete_manifest", 0)) > 0:
        return "operator_must_complete_manifest"
    return "ready_for_local_ohlcv_validator"


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if summary["manual_staging_status"] != "validator_pass_ready_for_history_activation":
        flags.append(_flag("manual-staging-not-ready", summary["manual_staging_status"]))
    if summary["local_ohlcv_status"] != "local_ohlcv_validation_pass":
        flags.append(_flag("local-ohlcv-not-ready", summary["local_ohlcv_status"]))
    if summary["history_spine_activation_status"] != "real_ohlcv_history_spine_activation_pass":
        flags.append(_flag("history-activation-blocked", summary["history_spine_activation_status"]))
    if summary["real_signal_validation_status"] == "blocked_missing_valid_real_history":
        flags.append(_flag("real-signal-validation-blocked", summary["real_signal_validation_status"]))
    return flags


def _proof(summary: dict[str, Any]) -> dict[str, Any]:
    return ManualOhlcvStagingProofRecord(
        artifact_type="manual_ohlcv_staging_proof",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        proof_id="manual-ohlcv-staging-proof-v1",
        manual_staging_status=summary["manual_staging_status"],
        manual_staging_decision=summary["manual_staging_decision"],
        source_candidate_count=int(summary["source_candidate_count"]),
        evidence_allowed_count=int(summary["evidence_allowed_count"]),
        hash_record_count=int(summary["hash_record_count"]),
        manifest_draft_status=summary["manifest_draft_status"],
        preflight_status=summary["preflight_status"],
        fix_plan_status=summary["fix_plan_status"],
        local_ohlcv_status=summary["local_ohlcv_status"],
        valid_real_dataset=bool(summary["valid_real_dataset"]),
        history_spine_activation_status=summary["history_spine_activation_status"],
        real_signal_validation_status=summary["real_signal_validation_status"],
        real_signal_evidence=bool(summary["real_signal_evidence"]),
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        strategy_promotion_allowed=False,
        paper_only=True,
        live_blocked=True,
        not_strategy_promotion=True,
        proof_hash="",
    ).to_dict()


def _flag(flag_id: str, reason_code: str) -> dict[str, Any]:
    record = {
        "artifact_type": "local_free_ohlcv_validation_and_activation_stack_quality_flags",
        "flag_id": flag_id,
        "severity": "info",
        "reason_code": reason_code,
        "paper_only": True,
        "live_blocked": True,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
    }
    record["flag_hash"] = stable_manual_ohlcv_hash(record)
    return record


def _manual_fixture_groups() -> dict[str, list[str]]:
    groups = {
        "manual_ohlcv_source_candidate_cases.json": [
            "no Alpha Vantage candidate", "manual exchange export", "manual ETF export", "Stooq-style manual export",
            "Yahoo Finance manual download", "Nasdaq reference if license permits", "CBOE reference if license permits",
            "SEC EDGAR context", "FRED macro/rates manual CSV", "GitHub hosted data with explicit license",
            "manual review required", "evidence blocked by default", "credentials not required", "not fetched by DOPEY",
            "commercial use uncertain", "redistribution uncertain", "survivorship risk recorded", "staleness risk recorded",
            "schema risk recorded", "paper only live blocked",
        ],
        "manual_ohlcv_staging_checklist_cases.json": [
            "daily folder required", "market context folder required", "corporate actions folder required", "manifests folder required",
            "date column required", "symbol column required", "open column required", "high column required", "low column required",
            "close column required", "adjusted_close column required", "volume column required", "source column required",
            "dividend optional", "split_factor optional", "provider_record_id optional", "manifest_id required",
            "provider_terms_reviewed required", "license_status required", "download_or_export_dates required",
        ],
        "manual_ohlcv_manifest_draft_cases.json": [
            "no files staged", "one valid CSV staged", "one valid JSONL staged", "hash records empty when no files",
            "hash pass", "row count recorded", "symbol count recorded", "date range recorded", "license unknown",
            "provider terms false", "redistribution false", "not network fetched true", "not credentials true",
            "not broker data true", "not live data true", "draft only is not evidence", "draft does not overwrite final manifest",
            "manifest finalization required", "operator fields listed", "paper only live blocked",
        ],
        "manual_ohlcv_preflight_cases.json": [
            "missing required header", "source missing", "sample-only row", "SAMPLE_ONLY row", "not_real_data=true row",
            "credential token row", "broker marker row", "live marker row", "order marker row", "scheduler marker row",
            "real-sizing marker row", "future date candidate", "high/low inconsistency candidate", "duplicate date/symbol",
            "manifest missing", "manifest draft only", "final manifest present", "final manifest template-only",
            "allowed csv extension", "allowed jsonl extension",
        ],
        "manual_ohlcv_import_fix_cases.json": [
            "stage files fix item", "complete manifest fix item", "repair schema fix item", "repair quality fix item",
            "repair license provenance fix item", "remove sample template fix item", "remove credentials live marker fix item",
            "repair hash mismatch fix item", "manual review required fix item", "ready for validator", "ready for activation after validator pass",
            "unknown license", "reviewed open-data license", "reviewed internal-research license", "unreviewed license blocked",
            "hash mismatch", "hash pass", "no real evidence claim", "no strategy promotion", "terminal block",
        ],
        "manual_ohlcv_staging_summary_cases.json": [
            "combined no files status", "operator must stage files", "local OHLCV missing state preserved",
            "valid real dataset false", "history activation blocked missing local OHLCV", "real signal blocked missing history",
            "real signal evidence false", "network fetch false", "credentials false", "env false", "broker false",
            "strategy promotion false", "no Alpha Vantage", "no Robinhood MCP integration", "live trading disabled",
            "export verifier timeout inconclusive", "full pytest timeout inconclusive", "manifest draft not evidence",
            "OHLCV evidence not options evidence", "next target rerun validator",
        ],
    }
    shared_extra_cases = [
        "no network fetch",
        "no credentials",
        "no .env",
        "no broker",
        "no strategy promotion",
        "paper only",
        "live blocked",
        "not real data ingested",
        "manifest draft not evidence",
        "operator manual review required",
    ]
    return {name: [*cases, *shared_extra_cases] for name, cases in groups.items()}


def _fixture_case(index: int, name: str) -> dict[str, Any]:
    record = {
        "case_id": f"manual-ohlcv-staging-case-{index:03d}",
        "case_name": name,
        "fixture_only": True,
        "sample_only": True,
        "not_real_data": True,
        "not_real_data_ingested": True,
        "paper_only": True,
        "live_blocked": True,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
    }
    record["case_hash"] = stable_manual_ohlcv_hash(record)
    return record


def _write_export_verifier_timeout_note() -> dict[str, Any]:
    record = {
        "artifact_type": "export_verifier_timeout_note",
        "staging_version": MANUAL_OHLCV_STAGING_VERSION,
        "prior_export_verifier_status": "inconclusive_timeout",
        "timeout_counts_as_pass": False,
        "preserve_last_successful_export_record_separately": True,
        "next_export_verifier_needs": "longer_non_capped_lane",
        "export_review_must_not_claim_fresh_copy_proof_success_after_timeout": True,
        "paper_only": True,
        "live_blocked": True,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
    }
    record["note_hash"] = stable_manual_ohlcv_hash(record)
    _write_json(EXPORT_VERIFIER_TIMEOUT_NOTE_PATH, record)
    return record


def _write_docs(summary: dict[str, Any], fixture_paths: list[str], checklist: dict[str, Any], timeout_note: dict[str, Any]) -> None:
    report_lines = [
        "# DOPEY Manual Free OHLCV Staging Or Local Import Fix Report",
        "",
        "## Objective",
        "Build a local-only operator staging and repair path for manually supplied free/public OHLCV files.",
        "",
        "## Alpha Vantage Exclusion",
        "- Alpha Vantage is excluded. No Alpha Vantage candidate, API key path, fetcher, or credential workflow was added.",
        "",
        "## No-Fetch Policy",
        "- DOPEY does not fetch, scrape, download, or credential market data in this bundle.",
        "- Network fetch, broker connection, `.env`, credentials, scheduler, live orders, and real sizing remain blocked.",
        "",
        "## Source Candidate Guide",
        f"- source_candidate_count: `{summary['source_candidate_count']}`",
        f"- evidence_allowed_count: `{summary['evidence_allowed_count']}`",
        "- Every source candidate requires manual license/provenance review before evidence use.",
        "",
        "## Operator Staging Checklist",
        f"- required_folders: `{', '.join(checklist['required_folders'])}`",
        f"- required_daily_ohlcv_columns: `{', '.join(checklist['required_daily_ohlcv_columns'])}`",
        f"- required_manifest_fields: `{', '.join(checklist['required_manifest_fields'])}`",
        "",
        "## Manifest Draft Helper",
        f"- manifest_draft_status: `{summary['manifest_draft_status']}`",
        f"- hash_record_count: `{summary['hash_record_count']}`",
        "- The draft computes local hashes/counts only; it is not import approval or evidence.",
        "",
        "## Preflight Linter",
        f"- preflight_status: `{summary['preflight_status']}`",
        "- Blocks sample/template rows, SAMPLE_ONLY, credentials/tokens, broker/live/order/scheduler/real-sizing markers, future dates, high/low inconsistency, duplicates, and missing source/manifest references.",
        "",
        "## Import Fix Engine",
        f"- fix_plan_status: `{summary['fix_plan_status']}`",
        "- Groups fixes into staging, manifest, schema, quality, license/provenance, sample removal, live-marker removal, hash mismatch, manual review, and ready states.",
        "",
        "## Fixing The No-Files State",
        "- Manually place reviewed CSV/JSONL files under `dopey_data/real/raw/daily_ohlcv/`, rerun the draft helper, complete the final manifest, then rerun the stack.",
        "",
        "## Fixing Schema Errors",
        "- Use the required OHLCV header exactly: `date,symbol,open,high,low,close,adjusted_close,volume,source`.",
        "",
        "## Fixing Quality Errors",
        "- Remove future dates, duplicate date/symbol rows, bad OHLC ranges, nonpositive prices, negative volume, and missing source values.",
        "",
        "## Fixing Manifest/License/Provenance Errors",
        "- Complete provider, terms review, license status, local paths, hashes, row counts, symbol counts, date ranges, source references, export dates, and safety assertions manually.",
        "",
        "## Sample Rows Are Blocked",
        "- Template rows, sample_only rows, not_real_data rows, and SAMPLE_ONLY symbols are fixtures only and cannot appear in real raw paths.",
        "",
        "## Evidence Boundaries",
        "- Valid OHLCV is not options evidence.",
        "- OHLCV validation is not profitability, strategy promotion, or live readiness.",
        "",
        "## Current Stack State",
        f"- manual_staging_status: `{summary['manual_staging_status']}`",
        f"- manual_staging_decision: `{summary['manual_staging_decision']}`",
        f"- local_ohlcv_status: `{summary['local_ohlcv_status']}`",
        f"- valid_real_dataset: `{str(summary['valid_real_dataset']).lower()}`",
        f"- history_spine_activation_status: `{summary['history_spine_activation_status']}`",
        f"- real_signal_validation_status: `{summary['real_signal_validation_status']}`",
        f"- real_signal_evidence: `{str(summary['real_signal_evidence']).lower()}`",
        "",
        "## Safety State",
        "- network_fetch_performed: `false`",
        "- credentials_created: `false`",
        "- env_created: `false`",
        "- broker_connection_used: `false`",
        "- strategy_promotion_allowed: `false`",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "",
        "## Validation Summary",
        "- Targeted tests are in `tests/test_manual_free_ohlcv_staging_or_local_import_fix.py`.",
        "- Full pytest timeout must remain `inconclusive_timeout`, not pass.",
        f"- prior_export_verifier_status: `{timeout_note['prior_export_verifier_status']}`",
        "",
        "## Known Gaps",
        "- No operator-reviewed real OHLCV files are currently accepted unless files pass schema, quality, manifest, license, provenance, and history activation gates.",
        "",
        "## Next Target",
        f"- `{summary['next_recommended_target']}`",
    ]
    _write_text_atomic(REPORT_PATH, "\n".join(report_lines) + "\n")
    ledger_paths = [
        *artifact_paths().values(),
        *manual_artifact_paths().values(),
        str(REPORT_PATH),
        str(LEDGER_PATH),
        str(FREE_INSTRUCTIONS_PATH),
        str(REAL_INSTRUCTIONS_PATH),
        *fixture_paths,
    ]
    _write_ledger(ledger_paths, summary)
    _write_instruction_docs()


def _write_ledger(paths: list[str], summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Manual Free OHLCV Staging Or Local Import Fix Artifact Ledger",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- network_fetch_performed: `false`",
        "- credentials_created: `false`",
        "- env_created: `false`",
        "- broker_connection_used: `false`",
        "- strategy_promotion_allowed: `false`",
        f"- manual_staging_status: `{summary['manual_staging_status']}`",
        "",
        "## Files",
    ]
    for path_text in sorted(set(paths)):
        path = Path(path_text)
        if path.exists():
            lines.append(f"- `{_relative(path)}` records=`{_record_count(path)}` sha256=`{_sha256(path)}`")
    _write_text_atomic(LEDGER_PATH, "\n".join(lines) + "\n")


def _write_instruction_docs() -> None:
    shared = [
        "## Allowed Raw Folders",
        "- `dopey_data/real/raw/daily_ohlcv/`",
        "- `dopey_data/real/raw/market_context/`",
        "- `dopey_data/real/raw/corporate_actions/`",
        "- `dopey_data/real/manifests/`",
        "",
        "## Valid Daily OHLCV Header",
        "```csv",
        "date,symbol,open,high,low,close,adjusted_close,volume,source",
        "```",
        "",
        "## Invalid Blocked Sample Row",
        "```csv",
        "2026-01-01,SAMPLE_ONLY,1,1,1,1,1,0,fixture",
        "```",
        "",
        "## Manifest Draft",
        "- Run `python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft` to compute local hashes and counts.",
        "- The draft writes `dopey_data/real/manifests/real_data_manifest.draft.json` and never overwrites `real_data_manifest.json`.",
        "- The draft is not evidence and not import approval.",
        "",
        "## Manifest Finalization Checklist",
        "- Complete provider, terms review, license status, redistribution status, local paths, hashes, counts, date ranges, source references, export dates, and safety assertions.",
        "- Unknown or unreviewed license remains blocked.",
        "",
        "## Rerun",
        "- Draft helper: `python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft`",
        "- Preflight: `python -m dopey_data_ingestion.run_manual_ohlcv_preflight_linter`",
        "- Validator: `python -m dopey_data_ingestion.run_local_ohlcv_import_validator`",
        "- Combined stack: `python -m dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack`",
        "",
        "## Boundaries",
        "- No API keys.",
        "- No Alpha Vantage.",
        "- No broker data.",
        "- No `.env`.",
        "- No network fetch or scrape.",
        "- No strategy promotion, profitability, options edge, or live readiness claim.",
    ]
    _write_text_atomic(FREE_INSTRUCTIONS_PATH, "# DOPEY Manual Free OHLCV Staging Instructions\n\n" + "\n".join(shared) + "\n")
    _write_text_atomic(REAL_INSTRUCTIONS_PATH, "# DOPEY Manual Real OHLCV Staging Instructions\n\n" + "\n".join(shared) + "\n")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    _write_text_atomic(path, "\n".join(lines) + ("\n" if lines else ""))


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
    if path.suffix == ".json":
        parsed = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(parsed, dict) and isinstance(parsed.get("cases"), list):
            return len(parsed["cases"])
    if path.suffix == ".csv":
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            return max(sum(1 for _row in csv.reader(handle)) - 1, 0)
    return 1


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _copy_reports_to_shared_folder(paths: list[Path]) -> None:
    shared = Path("C:/Users/chris/Desktop/Shared Folder")
    if not shared.exists():
        shared = Path("//FRANKENSTEIN/Shared Folder")
    if not shared.exists():
        return
    target = shared / "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1"
    target.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            (target / path.name).write_bytes(path.read_bytes())


def main() -> int:
    result = run_local_free_ohlcv_validation_and_activation_stack()
    print(json.dumps({
        "manual_staging_status": result["manual_staging_status"],
        "manual_staging_decision": result["manual_staging_decision"],
        "local_ohlcv_status": result["local_ohlcv_status"],
        "history_spine_activation_status": result["history_spine_activation_status"],
        "real_signal_validation_status": result["real_signal_validation_status"],
        "next_recommended_target": result["next_recommended_target"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
