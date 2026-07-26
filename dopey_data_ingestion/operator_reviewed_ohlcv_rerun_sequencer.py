"""Sequence local-only reviewed OHLCV rerun gates and decisions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_analysis.run_real_signal_validation_gate import run_real_signal_validation_gate
from dopey_data.run_real_ohlcv_history_spine_activation import run_real_ohlcv_history_spine_activation

from .local_staging_contract import REPO_ROOT
from .manual_free_ohlcv_source_candidates import write_manual_free_ohlcv_source_candidates
from .manual_ohlcv_import_fix_engine import write_manual_ohlcv_import_fix_plan
from .manual_ohlcv_manifest_draft import write_manual_ohlcv_manifest_draft
from .manual_ohlcv_preflight_linter import write_manual_ohlcv_preflight
from .manual_ohlcv_staging_checklist import write_manual_ohlcv_staging_checklist
from .operator_ohlcv_source_review_contract import write_operator_source_review_contract
from .operator_reviewed_ohlcv_final_manifest_status import evaluate_operator_reviewed_final_manifest_status
from .operator_reviewed_ohlcv_manifest_candidate import build_operator_reviewed_manifest_candidate
from .operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvRerunStep,
    OperatorReviewedOhlcvValidationDecision,
)
from .operator_reviewed_ohlcv_staged_file_detector import detect_operator_reviewed_staged_files
from .run_local_ohlcv_import_validator import run_local_ohlcv_import_validator


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
RERUN_STEPS_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_rerun_steps.jsonl"
RERUN_DECISION_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_rerun_decision.json"


def run_operator_reviewed_ohlcv_rerun_sequence() -> dict[str, Any]:
    source_review = write_operator_source_review_contract()
    staged = detect_operator_reviewed_staged_files()
    source_candidates = write_manual_free_ohlcv_source_candidates()
    checklist = write_manual_ohlcv_staging_checklist()
    manifest_draft = write_manual_ohlcv_manifest_draft()
    manifest_candidate = build_operator_reviewed_manifest_candidate()
    final_manifest = evaluate_operator_reviewed_final_manifest_status()
    preflight = write_manual_ohlcv_preflight()
    local = run_local_ohlcv_import_validator()
    fix_plan = write_manual_ohlcv_import_fix_plan()
    history = run_real_ohlcv_history_spine_activation()
    signals = run_real_signal_validation_gate()
    summary = _combined_summary(source_review, staged, source_candidates, manifest_draft, manifest_candidate, final_manifest, preflight, local, fix_plan, history, signals)
    steps = _steps(source_review, staged, source_candidates, checklist, manifest_draft, manifest_candidate, final_manifest, preflight, local, fix_plan, history, signals, summary)
    decision = _decision(summary)
    _write_jsonl(RERUN_STEPS_PATH, steps)
    _write_json(RERUN_DECISION_PATH, decision)
    return {**summary, "steps": steps, "decision_record": decision, "artifact_paths": {"operator_reviewed_ohlcv_rerun_steps": str(RERUN_STEPS_PATH), "operator_reviewed_ohlcv_rerun_decision": str(RERUN_DECISION_PATH)}}


def _combined_summary(
    source_review: dict[str, Any],
    staged: dict[str, Any],
    source_candidates: dict[str, Any],
    manifest_draft: dict[str, Any],
    manifest_candidate: dict[str, Any],
    final_manifest: dict[str, Any],
    preflight: dict[str, Any],
    local: dict[str, Any],
    fix_plan: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    status = _stage_status(source_review, staged, final_manifest, preflight, local, history, signals)
    decision = _stage_decision(status, source_review, staged, final_manifest, preflight, local, history, signals)
    record = {
        "operator_reviewed_stage_status": status,
        "operator_reviewed_stage_decision": decision,
        "source_review_status": str(source_review.get("status", "operator_review_packet_missing")),
        "source_review_valid": bool(source_review.get("source_review_valid", False)),
        "source_candidate_count": int(source_candidates.get("source_candidate_count", 0)),
        "evidence_allowed_count": int(source_candidates.get("evidence_allowed_count", 0)),
        "staged_file_count": int(staged.get("staged_file_count", 0)),
        "manifest_draft_status": str(manifest_draft.get("draft_status", "manual_staging_required")),
        "manifest_candidate_status": str(manifest_candidate.get("manifest_candidate_status", "blocked_missing_staged_files")),
        "final_manifest_status": str(final_manifest.get("final_manifest_status", "final_manifest_missing")),
        "preflight_status": str(preflight.get("preflight_status", "manual_staging_required")),
        "local_ohlcv_status": str(local.get("local_ohlcv_status", "missing_local_ohlcv_files")),
        "local_ohlcv_import_decision": str(local.get("local_ohlcv_import_decision", "blocked_missing_local_ohlcv")),
        "fix_plan_status": str(fix_plan.get("fix_plan_status", "manual_staging_required")),
        "history_spine_activation_status": str(history.get("history_spine_activation_status", "blocked_missing_local_ohlcv")),
        "real_signal_validation_status": str(signals.get("real_signal_validation_status", "blocked_missing_valid_real_history")),
        "real_data_files_present": bool(staged.get("real_data_files_present", False) and local.get("real_data_files_present", False)),
        "valid_real_dataset": bool(local.get("valid_real_dataset", False)),
        "real_history_used": bool(history.get("real_history_used", False)),
        "real_signal_evidence": bool(signals.get("real_signal_evidence", False)),
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
        "next_recommended_target": _next_target(status, final_manifest, local, history, signals),
    }
    return record


def _stage_status(
    source_review: dict[str, Any],
    staged: dict[str, Any],
    final_manifest: dict[str, Any],
    preflight: dict[str, Any],
    local: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
) -> str:
    if staged.get("terminal_block") is True or final_manifest.get("final_manifest_status") == "terminal_block" or source_review.get("status") == "terminal_block":
        return "terminal_block"
    if int(staged.get("staged_file_count", 0)) == 0:
        return "operator_files_missing"
    if source_review.get("status") != "operator_review_packet_valid":
        return str(source_review.get("status", "operator_review_packet_missing"))
    if preflight.get("preflight_status") in {"preflight_fail", "terminal_block"}:
        return "staged_files_preflight_failed" if preflight.get("preflight_status") != "terminal_block" else "terminal_block"
    if local.get("local_ohlcv_status") != "local_ohlcv_validation_pass":
        return "staged_files_validator_failed"
    if history.get("history_spine_activation_status") != "real_ohlcv_history_spine_activation_pass":
        return "history_activation_blocked"
    if signals.get("real_signal_validation_status") != "real_signal_validation_pass":
        return "real_signal_validation_blocked"
    return "real_signal_validation_passed_no_promotion"


def _stage_decision(
    status: str,
    source_review: dict[str, Any],
    staged: dict[str, Any],
    final_manifest: dict[str, Any],
    preflight: dict[str, Any],
    local: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
) -> str:
    if status == "terminal_block":
        return "terminal_block"
    if int(staged.get("staged_file_count", 0)) == 0:
        return "operator_must_stage_reviewed_files"
    if source_review.get("status") != "operator_review_packet_valid":
        return "operator_must_complete_source_review_packet"
    if final_manifest.get("final_manifest_status") != "final_manifest_ready_for_validator":
        return "operator_must_complete_final_manifest"
    if preflight.get("preflight_status") in {"preflight_fail", "terminal_block"}:
        return "operator_must_fix_preflight"
    if local.get("local_ohlcv_status") != "local_ohlcv_validation_pass":
        return "operator_must_fix_validator_errors"
    if history.get("history_spine_activation_status") != "real_ohlcv_history_spine_activation_pass":
        return "operator_must_fix_history_activation_errors"
    if signals.get("real_signal_validation_status") != "real_signal_validation_pass":
        return "operator_must_fix_real_signal_validation_errors"
    return "real_ohlcv_signal_evidence_ready_no_promotion"


def _next_target(
    status: str,
    final_manifest: dict[str, Any],
    local: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
) -> str:
    if status == "operator_files_missing":
        return "DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES"
    if final_manifest.get("final_manifest_status") != "final_manifest_ready_for_validator":
        return "DOPEY_OPERATOR_FINALIZE_REAL_DATA_MANIFEST_AND_RERUN_VALIDATOR"
    if local.get("local_ohlcv_status") == "local_ohlcv_validation_pass" and history.get("history_spine_activation_status") != "real_ohlcv_history_spine_activation_pass":
        return "DOPEY_REPAIR_REAL_OHLCV_HISTORY_ACTIVATION"
    if history.get("history_spine_activation_status") == "real_ohlcv_history_spine_activation_pass" and signals.get("real_signal_validation_status") == "real_signal_validation_pass":
        return "DOPEY_REAL_OHLCV_SIGNAL_BACKTESTER_V1"
    return "DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES"


def _steps(
    source_review: dict[str, Any],
    staged: dict[str, Any],
    source_candidates: dict[str, Any],
    checklist: dict[str, Any],
    manifest_draft: dict[str, Any],
    manifest_candidate: dict[str, Any],
    final_manifest: dict[str, Any],
    preflight: dict[str, Any],
    local: dict[str, Any],
    fix_plan: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [
        ("01-source-review-packet", "source_review_packet", source_review.get("status", "operator_review_packet_missing"), summary["operator_reviewed_stage_decision"], source_review),
        ("02-staged-file-detector", "staged_file_detector", staged.get("status", "operator_files_missing"), summary["operator_reviewed_stage_decision"], staged),
        ("03-manual-source-candidate-guide", "manual_source_candidate_guide", "written", summary["operator_reviewed_stage_decision"], source_candidates),
        ("04-manual-staging-checklist", "manual_staging_checklist", "written", summary["operator_reviewed_stage_decision"], checklist),
        ("05-manifest-draft-helper", "manifest_draft_helper", manifest_draft.get("draft_status", "manual_staging_required"), summary["operator_reviewed_stage_decision"], manifest_draft),
        ("06-manifest-candidate-builder", "manifest_candidate_builder", manifest_candidate.get("manifest_candidate_status", "blocked_missing_staged_files"), summary["operator_reviewed_stage_decision"], manifest_candidate),
        ("07-final-manifest-status", "final_manifest_status", final_manifest.get("final_manifest_status", "final_manifest_missing"), summary["operator_reviewed_stage_decision"], final_manifest),
        ("08-preflight-linter", "preflight_linter", preflight.get("preflight_status", "manual_staging_required"), summary["operator_reviewed_stage_decision"], preflight),
        ("09-local-ohlcv-validator", "local_ohlcv_validator", local.get("local_ohlcv_status", "missing_local_ohlcv_files"), summary["operator_reviewed_stage_decision"], local),
        ("10-manual-import-fix-engine", "manual_import_fix_engine", fix_plan.get("fix_plan_status", "manual_staging_required"), summary["operator_reviewed_stage_decision"], fix_plan),
        ("11-history-spine-activation-gate", "history_spine_activation_gate", history.get("history_spine_activation_status", "blocked_missing_local_ohlcv"), summary["operator_reviewed_stage_decision"], history),
        ("12-real-signal-validation-gate", "real_signal_validation_gate", signals.get("real_signal_validation_status", "blocked_missing_valid_real_history"), summary["operator_reviewed_stage_decision"], signals),
        ("13-combined-summary", "combined_summary", summary["operator_reviewed_stage_status"], summary["operator_reviewed_stage_decision"], summary),
    ]
    return [_step(step_id, step_name, status, decision, payload) for step_id, step_name, status, decision, payload in rows]


def _step(step_id: str, step_name: str, status: Any, decision: str, payload: dict[str, Any]) -> dict[str, Any]:
    return OperatorReviewedOhlcvRerunStep(
        artifact_type="operator_reviewed_ohlcv_rerun_steps",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        step_id=step_id,
        step_name=step_name,
        status=str(status),
        decision=decision,
        artifact_paths=payload.get("artifact_paths", {}) if isinstance(payload.get("artifact_paths", {}), dict) else {},
        terminal_block=str(status) == "terminal_block",
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
        step_hash="",
    ).to_dict()


def _decision(summary: dict[str, Any]) -> dict[str, Any]:
    return OperatorReviewedOhlcvValidationDecision(
        artifact_type="operator_reviewed_ohlcv_rerun_decision",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        decision_id="operator-reviewed-ohlcv-rerun-decision-v1",
        operator_reviewed_stage_status=summary["operator_reviewed_stage_status"],
        operator_reviewed_stage_decision=summary["operator_reviewed_stage_decision"],
        reason_codes=[summary["operator_reviewed_stage_status"], summary["local_ohlcv_status"], summary["real_signal_validation_status"]],
        next_recommended_target=summary["next_recommended_target"],
        real_data_files_present=summary["real_data_files_present"],
        valid_real_dataset=summary["valid_real_dataset"],
        real_history_used=summary["real_history_used"],
        real_signal_evidence=summary["real_signal_evidence"],
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
        decision_hash="",
    ).to_dict()


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
