"""Deterministic reviewer priority queue for DOPEY export review artifacts."""
from __future__ import annotations

from dopey_export.export_models import ExportSafetyFinding

from .review_data import ExportReviewContext, next_build_target, top_known_gaps
from .review_models import ExportReviewFinding, ExportReviewPriority


def build_review_findings(ctx: ExportReviewContext, hash_status: str, copy_status: str) -> list[ExportReviewFinding]:
    findings: list[ExportReviewFinding] = []
    if int(ctx.export_safety_scan.get("active_forbidden_live_decisions", 0)) > 0:
        findings.append(ExportReviewFinding(
            finding_id="review-finding-safety-active-live",
            severity="safety_error",
            category="safety",
            artifact_path=str(ctx.source_export_path),
            summary="Export safety scan reported active forbidden live decisions.",
            evidence={"active_forbidden_live_decisions": ctx.export_safety_scan.get("active_forbidden_live_decisions", 0)},
            recommended_action="Stop review and repair safety state before any handoff.",
            paper_only=True,
            live_related=True,
        ))
    if int(ctx.export_safety_scan.get("credential_findings", 0)) > 0:
        findings.append(ExportReviewFinding(
            finding_id="review-finding-credential-scan",
            severity="safety_error",
            category="credential_scan",
            artifact_path=str(ctx.source_export_path),
            summary="Credential-like content was reported by the export safety scan.",
            evidence={"credential_findings": ctx.export_safety_scan.get("credential_findings", 0)},
            recommended_action="Remove credential-bearing artifacts and rerun export verification.",
            paper_only=True,
            live_related=True,
        ))
    if hash_status != "pass":
        findings.append(ExportReviewFinding(
            finding_id="review-finding-hash-status",
            severity="error",
            category="hash",
            artifact_path=str(ctx.manifest_registry_path),
            summary="Manifest hash verification did not pass.",
            evidence={"hash_status": hash_status},
            recommended_action="Rerun export verifier and compare manifest hashes.",
            paper_only=True,
            live_related=False,
        ))
    if copy_status != "verified":
        findings.append(ExportReviewFinding(
            finding_id="review-finding-copy-proof",
            severity="error",
            category="copy_proof",
            artifact_path=str(ctx.copy_proof_registry_path),
            summary="Copy proof is not verified.",
            evidence={"copy_status": copy_status},
            recommended_action="Re-copy the bundle or inspect shared-folder availability.",
            paper_only=True,
            live_related=False,
        ))

    findings.append(ExportReviewFinding(
        finding_id="review-finding-manifest-ready",
        severity="info",
        category="manifest",
        artifact_path=str(ctx.manifest_registry_path),
        summary="Export manifest is available for offline handoff review.",
        evidence={"artifact_count": ctx.export_manifest.get("artifact_count", 0)},
        recommended_action="Confirm manifest first, then inspect copy proof and audit summary.",
        paper_only=True,
        live_related=False,
    ))
    findings.append(ExportReviewFinding(
        finding_id="review-finding-safety-clean",
        severity="info",
        category="safety",
        artifact_path=str(ctx.source_export_path),
        summary="Safety state remains research-only and live-blocked.",
        evidence={
            "mode": ctx.safety_state.get("mode", ""),
            "live_trading_enabled": ctx.safety_state.get("live_trading_enabled", True),
            "active_forbidden_live_decisions": ctx.export_safety_scan.get("active_forbidden_live_decisions", 0),
            "credential_findings": ctx.export_safety_scan.get("credential_findings", 0),
        },
        recommended_action="Keep review offline; do not treat bundle as deployment evidence.",
        paper_only=True,
        live_related=True,
    ))
    for index, gap in enumerate(top_known_gaps(ctx), start=1):
        findings.append(ExportReviewFinding(
            finding_id=f"review-finding-gap-{index:02d}",
            severity="warning",
            category="gap",
            artifact_path=str(ctx.source_export_path / "artifacts/audit/evidence_gap_plan.jsonl"),
            summary=f"Evidence gap queued for human review: {gap}.",
            evidence={"gap_category": gap},
            recommended_action="Review the audit gap plan and decide whether the next build should address this gap.",
            paper_only=True,
            live_related=False,
        ))
    findings.append(ExportReviewFinding(
        finding_id="review-finding-next-step",
        severity="note",
        category="next_step",
        artifact_path=str(ctx.source_export_path),
        summary=f"Next recommended build target is {next_build_target(ctx)}.",
        evidence={"next_build_target": next_build_target(ctx)},
        recommended_action="Build deterministic export review comparison/diff artifacts next.",
        paper_only=True,
        live_related=False,
    ))
    return findings


def build_review_priorities(ctx: ExportReviewContext, findings: list[ExportReviewFinding], hash_status: str, copy_status: str) -> list[ExportReviewPriority]:
    priorities: list[ExportReviewPriority] = []
    rank = 1
    for finding in findings:
        if finding.severity == "safety_error":
            priorities.append(ExportReviewPriority(
                priority_id=f"review-priority-{rank:02d}-safety",
                rank=rank,
                artifact_path=finding.artifact_path,
                reason=finding.summary,
                severity=finding.severity,
                recommended_action=finding.recommended_action,
                reviewer_note="Safety findings block verified handoff review.",
                category=finding.category,
            ))
            rank += 1
    checks = [
        ("manifest", str(ctx.manifest_registry_path), f"Confirm manifest status is {hash_status}.", "Review artifact count, bundle hash, and required artifacts."),
        ("copy_proof", str(ctx.copy_proof_registry_path), f"Confirm copy proof status is {copy_status}.", "Verify shared target matches local bundle by hash."),
        ("audit", str(ctx.source_export_path / "artifacts/audit/evidence_replay_audit_summary.md"), "Inspect audit summary.", "Focus on hash, schema, consistency, and safety verdicts."),
        ("reporting", str(ctx.source_export_path / "artifacts/reporting/dashboard_index.json"), "Inspect dashboard index.", "Confirm top strategy, top family, and paper-only safety state."),
        ("strategy_evidence", str(ctx.source_export_path / "artifacts/reporting/strategy_report_cards.jsonl"), "Inspect strategy and family cards.", "Check top positive and negative drivers before handoff."),
        ("gap", str(ctx.source_export_path / "artifacts/audit/evidence_gap_plan.jsonl"), "Inspect top evidence gaps.", "Review gap categories before choosing the next build target."),
        ("next_step", str(ctx.source_export_path), f"Confirm next build target is {next_build_target(ctx)}.", "Recommended next target stays offline and review-focused."),
    ]
    for category, path, reason, note in checks:
        priorities.append(ExportReviewPriority(
            priority_id=f"review-priority-{rank:02d}-{category}",
            rank=rank,
            artifact_path=path,
            reason=reason,
            severity="info" if category not in {"gap"} else "warning",
            recommended_action="Inspect this artifact before approving the offline handoff.",
            reviewer_note=note,
            category=category,
        ))
        rank += 1
    return priorities


def render_priority_queue(priorities: list[ExportReviewPriority]) -> str:
    lines = ["# DOPEY Export Review Priority Queue", ""]
    lines.append("- fixture_only: `true`")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append("")
    for priority in priorities:
        lines.append(f"## {priority.rank}. {priority.category}")
        lines.append(f"- severity: `{priority.severity}`")
        lines.append(f"- artifact_path: `{priority.artifact_path}`")
        lines.append(f"- reason: {priority.reason}")
        lines.append(f"- recommended_action: {priority.recommended_action}")
        lines.append(f"- reviewer_note: {priority.reviewer_note}")
        lines.append("")
    return "\n".join(lines)
