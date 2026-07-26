"""Run the operator-reviewed OHLCV stage-rerun bundle."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_reviewed_ohlcv_action_packet import write_operator_reviewed_ohlcv_action_packet
from .operator_reviewed_ohlcv_evidence_boundary import write_operator_reviewed_ohlcv_evidence_boundary
from .operator_reviewed_ohlcv_rerun_sequencer import run_operator_reviewed_ohlcv_rerun_sequence
from dopey_core.repo_paths import REPORTS_DIR

from .operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvProofRecord,
    OperatorReviewedOhlcvQualityFlag,
    OperatorReviewedOhlcvStageInput,
    stable_operator_stage_hash,
)


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
STAGE_INPUT_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_stage_input.json"
SUMMARY_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_stage_rerun_summary.json"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_stage_rerun_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_stage_rerun_proof.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_COMMANDS.md"
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "operator_reviewed_ohlcv_stage"


def run_operator_reviewed_ohlcv_stage_rerun() -> dict[str, Any]:
    stage_input = _stage_input()
    _write_json(STAGE_INPUT_PATH, stage_input)
    sequencer = run_operator_reviewed_ohlcv_rerun_sequence()
    boundary = write_operator_reviewed_ohlcv_evidence_boundary()
    summary = _summary(sequencer, boundary)
    action_packet = write_operator_reviewed_ohlcv_action_packet(summary)
    flags = _quality_flags(summary)
    proof = [_proof(summary)]
    fixture_paths = write_operator_reviewed_fixture_cases()
    artifact_paths = _artifact_paths(action_packet, boundary)
    summary_with_paths = {**summary, "artifact_paths": artifact_paths, "fixture_paths": fixture_paths, "report_path": str(REPORT_PATH), "ledger_path": str(LEDGER_PATH)}
    _write_json(SUMMARY_PATH, summary_with_paths)
    _write_jsonl(QUALITY_FLAGS_PATH, flags)
    _write_jsonl(PROOF_PATH, proof)
    _write_commands_doc()
    _write_report(summary_with_paths, action_packet, boundary)
    _write_ledger([*artifact_paths.values(), *fixture_paths, str(REPORT_PATH), str(LEDGER_PATH), str(COMMANDS_PATH)], summary_with_paths)
    _copy_reports_to_shared_folder([REPORT_PATH, LEDGER_PATH, COMMANDS_PATH])
    return summary_with_paths


def write_operator_reviewed_fixture_cases() -> list[str]:
    names = {
        "operator_source_review_cases.json": _case_names("source_review", 24),
        "operator_staged_file_detector_cases.json": _case_names("staged_file_detector", 26),
        "operator_manifest_candidate_cases.json": _case_names("manifest_candidate", 22),
        "operator_final_manifest_status_cases.json": _case_names("final_manifest_status", 26),
        "operator_rerun_sequencer_cases.json": _case_names("rerun_sequencer", 24),
        "operator_action_packet_cases.json": _case_names("action_packet", 22),
        "operator_evidence_boundary_cases.json": _case_names("evidence_boundary", 20),
        "operator_reviewed_stage_summary_cases.json": _case_names("stage_summary", 24),
    }
    paths: list[str] = []
    for file_name, case_names in names.items():
        cases = [_fixture_case(file_name, index + 1, case_name) for index, case_name in enumerate(case_names)]
        path = FIXTURE_DIR / file_name
        _write_json(path, {"artifact_type": Path(file_name).stem, "case_count": len(cases), "cases": cases})
        paths.append(str(path))
    return paths


def _case_names(prefix: str, minimum: int) -> list[str]:
    required = [
        "no files",
        "one CSV staged",
        "one JSONL staged",
        "unsupported extension",
        "symlink outside repo blocked",
        "sample-only row",
        "SAMPLE_ONLY",
        "sample_only=true",
        "not_real_data=true",
        "credential token",
        "broker marker",
        "live order marker",
        "scheduler marker",
        "account balance marker",
        "buying power marker",
        "real sizing marker",
        "source review packet missing",
        "source review packet template-only",
        "source review packet incomplete",
        "source review packet valid",
        "source review operator affirmation false",
        "source review unknown license",
        "source review unreviewed license",
        "source review reviewed allowed internal research",
        "source review reviewed open data internal research",
        "final manifest missing",
        "draft manifest exists",
        "candidate manifest missing files",
        "candidate manifest missing source review",
        "candidate manifest ready",
        "final manifest template-only",
        "final manifest incomplete",
        "final manifest unknown license",
        "final manifest unreviewed license",
        "final manifest reviewed allowed internal research",
        "final manifest reviewed open data internal research",
        "provenance missing",
        "file hash mismatch",
        "file hash pass",
        "row count mismatch",
        "row count pass",
        "preflight missing files",
        "preflight fail",
        "preflight pass manifest incomplete",
        "validator missing files",
        "validator schema fail",
        "validator quality fail",
        "validator license fail",
        "validator pass",
        "history activation blocked",
        "history activation pass",
        "real signal validation blocked",
        "real signal validation pass",
        "action packet for no files",
        "action packet for missing source review",
        "action packet for schema repair",
        "action packet for quality repair",
        "action packet for manifest repair",
        "action packet for license repair",
        "action packet for hash repair",
        "action packet for terminal block",
        "evidence boundary not options evidence",
        "evidence boundary not profitability claim",
        "evidence boundary not live ready",
        "no network fetch",
        "no credentials",
        "no .env",
        "no broker",
        "no Alpha Vantage",
        "no strategy promotion",
        "no options evidence",
        "no profitability claim",
        "no live readiness",
    ]
    names = [f"{prefix}: {name}" for name in required]
    while len(names) < minimum:
        names.append(f"{prefix}: fixture boundary case {len(names) + 1:03d}")
    return names[:minimum]


def _fixture_case(file_name: str, index: int, case_name: str) -> dict[str, Any]:
    record = {
        "case_id": f"{Path(file_name).stem}-{index:03d}",
        "case_name": case_name,
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
    record["case_hash"] = stable_operator_stage_hash(record)
    return record


def _stage_input() -> dict[str, Any]:
    return OperatorReviewedOhlcvStageInput(
        artifact_type="operator_reviewed_ohlcv_stage_input",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        input_id="operator-reviewed-ohlcv-stage-input-v1",
        source_review_path="dopey_data/real/manifests/operator_ohlcv_source_review.json",
        daily_ohlcv_folder="dopey_data/real/raw/daily_ohlcv/",
        market_context_folder="dopey_data/real/raw/market_context/",
        corporate_actions_folder="dopey_data/real/raw/corporate_actions/",
        final_manifest_path="dopey_data/real/manifests/real_data_manifest.json",
        candidate_manifest_path="dopey_data/real/manifests/real_data_manifest.candidate.json",
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
        input_hash="",
    ).to_dict()


def _summary(sequencer: dict[str, Any], boundary: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "operator_reviewed_ohlcv_stage_rerun_summary",
        "stage_version": OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        "operator_reviewed_stage_status": sequencer["operator_reviewed_stage_status"],
        "operator_reviewed_stage_decision": sequencer["operator_reviewed_stage_decision"],
        "source_review_status": sequencer["source_review_status"],
        "source_review_valid": sequencer["source_review_valid"],
        "staged_file_count": sequencer["staged_file_count"],
        "manifest_draft_status": sequencer["manifest_draft_status"],
        "manifest_candidate_status": sequencer["manifest_candidate_status"],
        "final_manifest_status": sequencer["final_manifest_status"],
        "preflight_status": sequencer["preflight_status"],
        "local_ohlcv_status": sequencer["local_ohlcv_status"],
        "local_ohlcv_import_decision": sequencer["local_ohlcv_import_decision"],
        "fix_plan_status": sequencer["fix_plan_status"],
        "history_spine_activation_status": sequencer["history_spine_activation_status"],
        "real_signal_validation_status": sequencer["real_signal_validation_status"],
        "real_data_files_present": sequencer["real_data_files_present"],
        "valid_real_dataset": sequencer["valid_real_dataset"],
        "real_history_used": sequencer["real_history_used"],
        "real_signal_evidence": sequencer["real_signal_evidence"],
        "strategy_promotion_allowed": False,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "paper_only": True,
        "live_blocked": True,
        "not_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "next_recommended_target": sequencer["next_recommended_target"],
        "evidence_boundary_hash": boundary["boundary_hash"],
    }
    record["summary_hash"] = stable_operator_stage_hash(record)
    return record


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if summary["operator_reviewed_stage_status"] != "real_signal_validation_passed_no_promotion":
        flags.append(_flag("operator-reviewed-stage-blocked", summary["operator_reviewed_stage_status"], "Reviewed OHLCV stage remains blocked before evidence."))
    if summary["source_review_status"] != "operator_review_packet_valid":
        flags.append(_flag("source-review-required", summary["source_review_status"], "Operator source-review packet is required."))
    if summary["local_ohlcv_status"] != "local_ohlcv_validation_pass":
        flags.append(_flag("local-ohlcv-validator-blocked", summary["local_ohlcv_status"], "Local OHLCV validator has not passed."))
    if summary["real_signal_validation_status"] != "real_signal_validation_pass":
        flags.append(_flag("real-signal-validation-blocked", summary["real_signal_validation_status"], "Real signal validation cannot pass without valid real history."))
    return flags


def _flag(flag_id: str, reason_code: str, message: str) -> dict[str, Any]:
    return OperatorReviewedOhlcvQualityFlag(
        artifact_type="operator_reviewed_ohlcv_stage_rerun_quality_flags",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        flag_id=flag_id,
        severity="info",
        reason_code=reason_code,
        message=message,
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
        flag_hash="",
    ).to_dict()


def _proof(summary: dict[str, Any]) -> dict[str, Any]:
    return OperatorReviewedOhlcvProofRecord(
        artifact_type="operator_reviewed_ohlcv_stage_rerun_proof",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        proof_id="operator-reviewed-ohlcv-stage-rerun-proof-v1",
        operator_reviewed_stage_status=summary["operator_reviewed_stage_status"],
        operator_reviewed_stage_decision=summary["operator_reviewed_stage_decision"],
        source_review_status=summary["source_review_status"],
        staged_file_count=int(summary["staged_file_count"]),
        manifest_candidate_status=summary["manifest_candidate_status"],
        final_manifest_status=summary["final_manifest_status"],
        local_ohlcv_status=summary["local_ohlcv_status"],
        history_spine_activation_status=summary["history_spine_activation_status"],
        real_signal_validation_status=summary["real_signal_validation_status"],
        real_data_files_present=bool(summary["real_data_files_present"]),
        valid_real_dataset=bool(summary["valid_real_dataset"]),
        real_history_used=bool(summary["real_history_used"]),
        real_signal_evidence=bool(summary["real_signal_evidence"]),
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
        proof_hash="",
    ).to_dict()


def _artifact_paths(action_packet: dict[str, Any], boundary: dict[str, Any]) -> dict[str, str]:
    return {
        "operator_reviewed_ohlcv_stage_input": str(STAGE_INPUT_PATH),
        "operator_ohlcv_source_review_contract": str(ARTIFACT_DIR / "operator_ohlcv_source_review_contract.json"),
        "operator_ohlcv_source_review_status": str(ARTIFACT_DIR / "operator_ohlcv_source_review_status.json"),
        "operator_reviewed_ohlcv_staged_file_status": str(ARTIFACT_DIR / "operator_reviewed_ohlcv_staged_file_status.json"),
        "operator_reviewed_ohlcv_staged_file_inventory": str(ARTIFACT_DIR / "operator_reviewed_ohlcv_staged_file_inventory.jsonl"),
        "operator_reviewed_ohlcv_manifest_candidate": str(ARTIFACT_DIR / "operator_reviewed_ohlcv_manifest_candidate.json"),
        "operator_reviewed_ohlcv_final_manifest_status": str(ARTIFACT_DIR / "operator_reviewed_ohlcv_final_manifest_status.json"),
        "operator_reviewed_ohlcv_rerun_steps": str(ARTIFACT_DIR / "operator_reviewed_ohlcv_rerun_steps.jsonl"),
        "operator_reviewed_ohlcv_rerun_decision": str(ARTIFACT_DIR / "operator_reviewed_ohlcv_rerun_decision.json"),
        "operator_reviewed_ohlcv_evidence_boundary": str(boundary["artifact_path"]),
        "operator_reviewed_ohlcv_action_packet": str(action_packet["json_path"]),
        "operator_reviewed_ohlcv_action_packet_markdown": str(action_packet["markdown_path"]),
        "operator_reviewed_ohlcv_stage_rerun_summary": str(SUMMARY_PATH),
        "operator_reviewed_ohlcv_stage_rerun_quality_flags": str(QUALITY_FLAGS_PATH),
        "operator_reviewed_ohlcv_stage_rerun_proof": str(PROOF_PATH),
    }


def _write_report(summary: dict[str, Any], action_packet: dict[str, Any], boundary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Operator Reviewed OHLCV Stage Rerun Report",
        "",
        "## Objective",
        "Build the local-only operator-supplied reviewed free OHLCV staging, manifest-finalization, validation-rerun, history-activation, and real-signal replay bundle.",
        "",
        "## Current No-Files State",
        f"- operator_reviewed_stage_status: `{summary['operator_reviewed_stage_status']}`",
        f"- operator_reviewed_stage_decision: `{summary['operator_reviewed_stage_decision']}`",
        f"- source_review_status: `{summary['source_review_status']}`",
        f"- staged_file_count: `{summary['staged_file_count']}`",
        f"- real_data_files_present: `{str(summary['real_data_files_present']).lower()}`",
        "",
        "## Operator Source-Review Packet Contract",
        "- Required at `dopey_data/real/manifests/operator_ohlcv_source_review.json`.",
        "- Missing packet is non-terminal but blocks evidence.",
        "- Unknown, unreviewed, missing, unlicensed, and template-only licenses block.",
        "",
        "## Staged-File Detector Summary",
        "- Scans only `dopey_data/real/raw/daily_ohlcv/`, `market_context/`, and `corporate_actions/`.",
        "- Blocks credentials, broker/live/order/scheduler/real-sizing markers, and symlink/outside-repo attempts.",
        "",
        "## Manifest Candidate Summary",
        f"- manifest_candidate_status: `{summary['manifest_candidate_status']}`",
        "- Candidate manifest is not evidence and does not overwrite the final manifest.",
        "",
        "## Final Manifest Status Summary",
        f"- final_manifest_status: `{summary['final_manifest_status']}`",
        "- Final manifest remains required for validation.",
        "",
        "## Rerun Sequencer Summary",
        f"- preflight_status: `{summary['preflight_status']}`",
        f"- local_ohlcv_status: `{summary['local_ohlcv_status']}`",
        f"- fix_plan_status: `{summary['fix_plan_status']}`",
        "",
        "## Action Packet Summary",
        f"- packet_status: `{action_packet['packet_status']}`",
        f"- action_packet_json: `{action_packet['json_path']}`",
        f"- action_packet_markdown: `{action_packet['markdown_path']}`",
        "",
        "## Local Validator Result",
        f"- local_ohlcv_import_decision: `{summary['local_ohlcv_import_decision']}`",
        f"- valid_real_dataset: `{str(summary['valid_real_dataset']).lower()}`",
        "",
        "## History Activation Result",
        f"- history_spine_activation_status: `{summary['history_spine_activation_status']}`",
        f"- real_history_used: `{str(summary['real_history_used']).lower()}`",
        "",
        "## Real Signal Validation Result",
        f"- real_signal_validation_status: `{summary['real_signal_validation_status']}`",
        f"- real_signal_evidence: `{str(summary['real_signal_evidence']).lower()}`",
        "",
        "## Evidence Boundary",
        f"- ohlcv_evidence_possible_only_after_validator_pass: `{str(boundary['ohlcv_evidence_possible_only_after_validator_pass']).lower()}`",
        "- OHLCV is not options evidence, not options quote evidence, and not quote-priced backtest evidence.",
        "- Validation is not strategy promotion, profitability, or live readiness.",
        "",
        "## Alpha Vantage Exclusion",
        "- Alpha Vantage remains excluded. No API key handling, fetcher, credential path, or candidate was added.",
        "",
        "## No-Fetch / No-Scrape Policy",
        "- network_fetch_performed: `false`",
        "- No downloads, scrapes, browser automation, curl, or wget paths are part of this bundle.",
        "",
        "## No Credential / Env Policy",
        "- credentials_created: `false`",
        "- env_created: `false`",
        "",
        "## No Broker / Live Policy",
        "- broker_connection_used: `false`",
        "- live_blocked: `true`",
        "",
        "## No Strategy Promotion Policy",
        "- strategy_promotion_allowed: `false`",
        "",
        "## Validation Summary",
        "- Targeted reviewed-stage tests: `tests/test_operator_reviewed_ohlcv_stage_rerun.py`.",
        "- Export verifier timeout and full pytest timeout remain inconclusive, not pass, when timed out.",
        "",
        "## Known Gaps",
        "- No reviewed local OHLCV files are currently staged.",
        "- Operator source-review packet is required.",
        "- Final manifest must be manually finalized and pass validation.",
        "",
        "## Next Target",
        f"- `{summary['next_recommended_target']}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_commands_doc() -> None:
    lines = [
        "# DOPEY Operator Reviewed OHLCV Stage Rerun Commands",
        "",
        "```powershell",
        "python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun",
        "python -m dopey_data_ingestion.run_operator_ohlcv_source_review_contract",
        "python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_manifest_candidate",
        "python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft",
        "python -m dopey_data_ingestion.run_manual_ohlcv_preflight_linter",
        "python -m dopey_data_ingestion.run_local_ohlcv_import_validator",
        "python -m dopey_data.run_real_ohlcv_history_spine_activation",
        "python -m dopey_analysis.run_real_signal_validation_gate",
        "python -m dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack",
        "```",
        "",
        "No curl, wget, browser automation, API, Alpha Vantage, broker, credential setup, or `.env` commands are part of this packet.",
    ]
    COMMANDS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledger(paths: list[str], summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Operator Reviewed OHLCV Stage Rerun Artifact Ledger",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- network_fetch_performed: `false`",
        "- credentials_created: `false`",
        "- env_created: `false`",
        "- broker_connection_used: `false`",
        "- strategy_promotion_allowed: `false`",
        f"- operator_reviewed_stage_status: `{summary['operator_reviewed_stage_status']}`",
        "",
        "## Files",
    ]
    for path_text in sorted(set(paths)):
        path = Path(path_text)
        if path.exists():
            lines.append(f"- `{_relative(path)}` records=`{_record_count(path)}` sha256=`{_sha256(path)}`")
    LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


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
    target = shared / "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_V1"
    target.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            (target / path.name).write_bytes(path.read_bytes())


def main() -> int:
    result = run_operator_reviewed_ohlcv_stage_rerun()
    print(json.dumps({
        "operator_reviewed_stage_status": result["operator_reviewed_stage_status"],
        "operator_reviewed_stage_decision": result["operator_reviewed_stage_decision"],
        "source_review_status": result["source_review_status"],
        "staged_file_count": result["staged_file_count"],
        "manifest_candidate_status": result["manifest_candidate_status"],
        "final_manifest_status": result["final_manifest_status"],
        "local_ohlcv_status": result["local_ohlcv_status"],
        "history_spine_activation_status": result["history_spine_activation_status"],
        "real_signal_validation_status": result["real_signal_validation_status"],
        "next_recommended_target": result["next_recommended_target"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
