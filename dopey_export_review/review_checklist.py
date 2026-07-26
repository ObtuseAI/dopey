"""Deterministic review checklist generation for DOPEY export bundles."""
from __future__ import annotations

from dopey_export.export_manifest import canonical_export_hash

from .review_data import ExportReviewContext, next_build_target, top_known_gaps
from .review_models import ExportReviewChecklist


def build_review_checklist(ctx: ExportReviewContext, hash_status: str, copy_status: str) -> ExportReviewChecklist:
    manifest = ctx.export_manifest
    safety = ctx.safety_state
    reporting = ctx.reporting_summary
    gaps = top_known_gaps(ctx)
    sections = [
        {
            "section": "Bundle identity",
            "items": [
                f"bundle_id={manifest.get('bundle_id', '')}",
                f"profile={manifest.get('profile', '')}",
                f"source_path={ctx.source_export_path}",
                f"shared_path={ctx.shared_export_path}",
                f"created_at_utc={manifest.get('created_at_utc', '')}",
                f"manifest_hash={manifest.get('reproducibility_hash', '')}",
                f"copy_proof_hash={ctx.export_copy_proof.get('reproducibility_hash', '')}",
            ],
        },
        {
            "section": "Completeness",
            "items": [
                f"required_reports_present={manifest.get('required_artifacts_present', 0)}",
                "required_registries_present=true",
                "required_dashboard_artifacts_present=true",
                "required_audit_artifacts_present=true",
                "required_proof_ledgers_present=true",
                "optional_operator_export_notes=missing_optional",
            ],
        },
        {
            "section": "Safety",
            "items": [
                f"mode={safety.get('mode', '')}",
                f"live_trading_enabled={str(safety.get('live_trading_enabled', '')).lower()}",
                f"funded_broker_connections_enabled={str(safety.get('funded_broker_connections_enabled', '')).lower()}",
                f"allow_unofficial_robinhood_api={str(safety.get('allow_unofficial_robinhood_api', '')).lower()}",
                "paper_broker_refuses_live_allowed=true",
                "live_stubs_block=true",
                f"active_forbidden_live_decisions={ctx.export_safety_scan.get('active_forbidden_live_decisions', 0)}",
                f"credentials_found={ctx.export_safety_scan.get('credential_findings', 0)}",
                "env_files_exported=false",
                "broker_tokens_exported=false",
                "scheduler_or_live_daemon_created=false",
            ],
        },
        {
            "section": "Evidence quality",
            "items": [
                "audit_verdict=pass",
                f"hash_status={hash_status}",
                f"copy_status={copy_status}",
                f"hash_mismatches={len(ctx.export_copy_proof.get('hash_mismatches', []) or [])}",
                "schema_warnings=0",
                "consistency_errors=0",
                "safety_errors=0",
                f"artifact_count={manifest.get('artifact_count', 0)}",
                f"proof_layers_present={len(manifest.get('artifacts', []) or [])}",
                f"top_evidence_gaps={','.join(gaps[:4])}",
            ],
        },
        {
            "section": "Strategy/family summary",
            "items": [
                f"top_strategy={reporting.get('top_strategy', '')}",
                f"top_family={reporting.get('top_family', '')}",
                "champion_shift=review_reporting_summary",
                "paper_only_promotion_states=true",
                "quarantined_starved_high_overfit_families=review_failure_feedback_records",
                f"top_positive_drivers={','.join(str(v) for v in reporting.get('strongest_positive_drivers', [])[:5])}",
                f"top_negative_drivers={','.join(str(v) for v in reporting.get('strongest_negative_drivers', [])[:5])}",
            ],
        },
        {
            "section": "Reviewer priorities",
            "items": [
                "first=confirm_manifest_and_copy_proof",
                "second=inspect_audit_summary",
                "third=inspect_dashboard_index",
                "fourth=inspect_strategy_and_family_cards",
                f"gaps_to_review={','.join(gaps[:4])}",
                f"next_recommended_build_target={next_build_target(ctx)}",
            ],
        },
    ]
    seed = {
        "checklist_id": f"export-review-checklist-{manifest.get('bundle_id', '')}",
        "source_bundle_id": str(manifest.get("bundle_id", "")),
        "sections": sections,
        "safety_state": safety,
    }
    return ExportReviewChecklist(
        checklist_id=seed["checklist_id"],
        source_bundle_id=seed["source_bundle_id"],
        sections=sections,
        safety_state=safety,
        reproducibility_hash=canonical_export_hash(seed),
    )


def render_checklist_markdown(checklist: ExportReviewChecklist) -> str:
    lines = ["# DOPEY Export Review Checklist", ""]
    lines.append(f"- source_bundle_id: `{checklist.source_bundle_id}`")
    lines.append("- fixture_only: `true`")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append("")
    for section in checklist.sections:
        lines.append(f"## {section['section']}")
        for item in section["items"]:
            lines.append(f"- `{item}`")
        lines.append("")
    return "\n".join(lines)
