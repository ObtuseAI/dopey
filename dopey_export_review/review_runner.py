"""Run deterministic static review-artifact generation for DOPEY export bundles."""
from __future__ import annotations

import shutil
from pathlib import Path

from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_export.export_manifest import canonical_export_hash, write_json

from .evidence_map import build_evidence_map, render_dependency_graph
from .review_checklist import build_review_checklist, render_checklist_markdown
from .review_data import (
    append_jsonl,
    copy_proof_status,
    load_review_context,
    manifest_file_hash_status,
    next_build_target,
    repo_relative,
    write_jsonl,
    write_text,
)
from .review_models import (
    EXPORT_REVIEW_VERSION,
    ExportReviewBundle,
    ExportReviewDecision,
    ExportReviewRunResult,
)
from .review_packet import render_executive_summary, render_next_steps, render_safety_summary
from .review_paths import (
    EXPORT_REVIEW_FINDINGS_PATH,
    EXPORT_REVIEW_PROOF_PATH,
    EXPORT_REVIEW_REGISTRY_PATH,
    EXPORT_REVIEW_ROOT,
    LATEST_CHECKLIST_PATH,
    LATEST_DEPENDENCY_GRAPH_PATH,
    LATEST_EVIDENCE_MAP_PATH,
    LATEST_EXECUTIVE_SUMMARY_PATH,
    LATEST_FINDINGS_PATH,
    LATEST_NEXT_STEPS_PATH,
    LATEST_PRIORITY_QUEUE_PATH,
    LATEST_SAFETY_SUMMARY_PATH,
)
from .review_priority import build_review_findings, build_review_priorities, render_priority_queue


def _review_id(source_bundle_id: str, manifest_hash: str, copy_hash: str) -> str:
    digest = canonical_export_hash({
        "source_bundle_id": source_bundle_id,
        "manifest_hash": manifest_hash,
        "copy_hash": copy_hash,
        "review_version": EXPORT_REVIEW_VERSION,
    })
    return f"dopey-export-review-{digest[:12]}"


def _copy_latest_to_review_dir(review_dir: Path, latest_paths: list[Path]) -> list[str]:
    copied: list[str] = []
    for source in latest_paths:
        target = review_dir / source.name
        shutil.copy2(source, target)
        copied.append(str(target))
    return copied


def _build_decision(ctx, hash_status: str, copy_status: str, safety_status: str, credential_status: str) -> ExportReviewDecision:
    ok = hash_status == "pass" and copy_status == "verified" and safety_status == "pass" and credential_status == "pass"
    seed = {
        "decision_id": f"export-review-decision-{ctx.export_manifest.get('bundle_id', '')}",
        "source_bundle_id": str(ctx.export_manifest.get("bundle_id", "")),
        "decision": "offline_handoff_review_ready" if ok else "review_blocked",
        "suitability": "suitable_for_offline_handoff_review" if ok else "not_suitable_until_findings_resolved",
        "reasons": [
            f"hash_status={hash_status}",
            f"copy_status={copy_status}",
            f"safety_status={safety_status}",
            f"credential_status={credential_status}",
        ],
        "limitations": [
            "static review artifacts only",
            "not live performance evidence",
            "no broker access or live execution authority",
        ],
        "next_build_target": next_build_target(ctx),
        "paper_only": True,
        "live_blocked": True,
    }
    return ExportReviewDecision(**seed, reproducibility_hash=canonical_export_hash(seed))


def _build_bundle(ctx, review_id: str, hash_status: str, copy_status: str, safety_status: str, credential_status: str, artifacts: list[str]) -> ExportReviewBundle:
    known_gaps = []
    for gap in ctx.audit_gap_plan.get("gaps", []) or []:
        if isinstance(gap, dict) and gap.get("category"):
            known_gaps.append(str(gap["category"]))
    if not known_gaps:
        known_gaps.append("deterministic_fixture_only_limitation")
    seed = {
        "review_id": review_id,
        "source_bundle_id": str(ctx.export_manifest.get("bundle_id", "")),
        "source_export_path": str(ctx.source_export_path),
        "manifest_path": str(ctx.manifest_registry_path),
        "copy_proof_path": str(ctx.copy_proof_registry_path),
        "artifact_count": int(ctx.export_manifest.get("artifact_count", 0)),
        "total_size_bytes": int(ctx.export_manifest.get("total_size_bytes", 0)),
        "hash_status": hash_status,
        "copy_status": copy_status,
        "safety_status": safety_status,
        "credential_scan_status": credential_status,
        "active_forbidden_live_decisions": int(ctx.export_safety_scan.get("active_forbidden_live_decisions", 0)),
        "review_artifact_paths": artifacts,
        "recommended_review_order": [
            "manifest",
            "copy_proof",
            "audit_summary",
            "dashboard_index",
            "strategy_report_cards",
            "family_report_cards",
            "evidence_gaps",
        ],
        "known_gaps": known_gaps,
        "next_build_target": next_build_target(ctx),
        "paper_only": True,
        "live_blocked": True,
    }
    return ExportReviewBundle(**seed, reproducibility_hash=canonical_export_hash(seed))


def _build_proof_entry(result: ExportReviewRunResult, bundle: ExportReviewBundle, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=EXPORT_REVIEW_VERSION,
        task_id="export-bundle-review-assistant-artifacts",
        timestamp="1970-01-01T00:00:00Z",
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"review_version": EXPORT_REVIEW_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "review_result": result.to_dict(),
            "review_bundle": bundle.to_dict(),
            "registry_record": registry_record,
            "source_bundle_id": result.source_bundle_id,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=result.review_artifacts_written,
        diffs=[],
        test_results={
            "review_status": result.review_status,
            "safety_errors": result.safety_errors,
            "warnings": result.warnings,
            "active_forbidden_live_decisions": result.active_forbidden_live_decisions,
            "live_blocked": result.live_blocked,
        },
        final_status="PASS" if result.review_status == "ok" else "FAIL",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "static offline review artifacts only",
            "not a chat agent, server, scheduler, deployment, or broker integration",
            "no credentials, live market data, live orders, or live promotion",
        ],
    )


def run_export_bundle_review_assistant() -> dict:
    ctx = load_review_context()
    hash_status, _hash_findings = manifest_file_hash_status(ctx)
    copy_status = copy_proof_status(ctx)
    safety_status = "pass" if int(ctx.export_safety_scan.get("active_forbidden_live_decisions", 0)) == 0 else "fail"
    credential_status = "pass" if int(ctx.export_safety_scan.get("credential_findings", 0)) == 0 else "fail"
    source_bundle_id = str(ctx.export_manifest.get("bundle_id", ""))
    review_id = _review_id(
        source_bundle_id,
        str(ctx.export_manifest.get("reproducibility_hash", "")),
        str(ctx.export_copy_proof.get("reproducibility_hash", "")),
    )
    review_dir = EXPORT_REVIEW_ROOT / review_id
    review_dir.mkdir(parents=True, exist_ok=True)

    checklist = build_review_checklist(ctx, hash_status, copy_status)
    evidence_map = build_evidence_map(ctx)
    findings = build_review_findings(ctx, hash_status, copy_status)
    priorities = build_review_priorities(ctx, findings, hash_status, copy_status)
    decision = _build_decision(ctx, hash_status, copy_status, safety_status, credential_status)

    write_text(LATEST_CHECKLIST_PATH, render_checklist_markdown(checklist))
    write_json(LATEST_EVIDENCE_MAP_PATH, evidence_map.to_dict())
    write_jsonl(LATEST_FINDINGS_PATH, [finding.to_dict() for finding in findings])
    write_text(LATEST_PRIORITY_QUEUE_PATH, render_priority_queue(priorities))
    write_text(LATEST_SAFETY_SUMMARY_PATH, render_safety_summary(ctx))
    write_text(LATEST_NEXT_STEPS_PATH, render_next_steps(ctx))
    write_text(LATEST_DEPENDENCY_GRAPH_PATH, render_dependency_graph(evidence_map))

    latest_paths = [
        LATEST_CHECKLIST_PATH,
        LATEST_EVIDENCE_MAP_PATH,
        LATEST_FINDINGS_PATH,
        LATEST_PRIORITY_QUEUE_PATH,
        LATEST_SAFETY_SUMMARY_PATH,
        LATEST_NEXT_STEPS_PATH,
        LATEST_DEPENDENCY_GRAPH_PATH,
    ]
    bundle = _build_bundle(ctx, review_id, hash_status, copy_status, safety_status, credential_status, [str(path) for path in latest_paths])
    write_text(LATEST_EXECUTIVE_SUMMARY_PATH, render_executive_summary(ctx, bundle, findings, decision))
    latest_paths.insert(0, LATEST_EXECUTIVE_SUMMARY_PATH)
    copied_paths = _copy_latest_to_review_dir(review_dir, latest_paths)

    write_jsonl(EXPORT_REVIEW_FINDINGS_PATH, [finding.to_dict() for finding in findings])
    safety_errors = sum(1 for finding in findings if finding.severity == "safety_error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    review_status = "ok" if hash_status == "pass" and safety_errors == 0 and credential_status == "pass" else "fail_review"
    result_seed = {
        "review_status": review_status,
        "mode": ctx.safety_state["mode"],
        "live_trading_enabled": ctx.safety_state["live_trading_enabled"],
        "source_bundle_id": source_bundle_id,
        "source_export_path": str(ctx.source_export_path),
        "shared_export_path": ctx.shared_export_path,
        "artifact_count": int(ctx.export_manifest.get("artifact_count", 0)),
        "manifest_status": "pass" if ctx.export_manifest else "missing",
        "copy_proof_status": copy_status,
        "hash_status": hash_status,
        "safety_status": safety_status,
        "credential_status": credential_status,
        "active_forbidden_live_decisions": int(ctx.export_safety_scan.get("active_forbidden_live_decisions", 0)),
        "findings_count": len(findings),
        "safety_errors": safety_errors,
        "warnings": warnings,
        "review_artifacts_written": [str(path) for path in latest_paths] + copied_paths,
        "review_registry_path": str(EXPORT_REVIEW_REGISTRY_PATH),
        "executive_summary_path": str(LATEST_EXECUTIVE_SUMMARY_PATH),
        "checklist_path": str(LATEST_CHECKLIST_PATH),
        "evidence_map_path": str(LATEST_EVIDENCE_MAP_PATH),
        "priority_queue_path": str(LATEST_PRIORITY_QUEUE_PATH),
        "safety_summary_path": str(LATEST_SAFETY_SUMMARY_PATH),
        "proof_record_path": str(EXPORT_REVIEW_PROOF_PATH),
        "live_blocked": True,
    }
    result = ExportReviewRunResult(**result_seed, reproducibility_hash=canonical_export_hash(result_seed))
    registry_record = {
        "review_registry_version": EXPORT_REVIEW_VERSION,
        "review_id": review_id,
        "source_bundle_id": source_bundle_id,
        "source_export_path": str(ctx.source_export_path),
        "shared_export_path": ctx.shared_export_path,
        "review_status": result.review_status,
        "artifact_count": result.artifact_count,
        "manifest_status": result.manifest_status,
        "copy_proof_status": result.copy_proof_status,
        "hash_status": result.hash_status,
        "safety_status": result.safety_status,
        "credential_status": result.credential_status,
        "findings_count": result.findings_count,
        "safety_errors": result.safety_errors,
        "warnings": result.warnings,
        "review_artifacts_written": result.review_artifacts_written,
        "next_build_target": next_build_target(ctx),
        "safety_state": ctx.safety_state,
    }
    registry_record["reproducibility_hash"] = canonical_export_hash(registry_record)
    append_jsonl(EXPORT_REVIEW_REGISTRY_PATH, registry_record)
    ProofLedger(EXPORT_REVIEW_PROOF_PATH).append(_build_proof_entry(result, bundle, registry_record))
    return result.to_dict()
