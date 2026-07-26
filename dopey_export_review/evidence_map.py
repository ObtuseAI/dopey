"""Deterministic evidence map and dependency graph for DOPEY export reviews."""
from __future__ import annotations

from pathlib import Path

from dopey_export.export_manifest import canonical_export_hash

from .review_data import ExportReviewContext, audit_artifact_specs, repo_relative
from .review_models import ExportReviewEvidenceMap


def _reference(path: Path | str, role: str) -> dict:
    target = Path(path)
    return {
        "role": role,
        "path": str(target),
        "exists": target.exists(),
        "relative_path": repo_relative(target) if target.exists() else str(target),
    }


def _artifact_path(ctx: ExportReviewContext, relative_path: str) -> Path:
    return ctx.source_export_path / relative_path


def build_evidence_map(ctx: ExportReviewContext) -> ExportReviewEvidenceMap:
    manifest_files: list[dict] = []
    missing: list[dict] = []
    for artifact in ctx.export_manifest.get("artifacts", []) or []:
        rel = str(artifact.get("relative_export_path", ""))
        target = _artifact_path(ctx, rel)
        entry = {
            "artifact_id": str(artifact.get("artifact_id", "")),
            "artifact_type": str(artifact.get("artifact_type", "")),
            "relative_export_path": rel,
            "path": str(target),
            "exists": target.exists(),
            "sha256": str(artifact.get("sha256", "")),
        }
        manifest_files.append(entry)
        if not target.exists():
            missing.append({"path": str(target), "reason": "manifest_reference_missing", "artifact_id": entry["artifact_id"]})

    target_dir_value = str(ctx.export_copy_proof.get("target_dir", ""))
    target_dir = Path(target_dir_value) if target_dir_value else None
    copy_files = []
    if target_dir is not None and target_dir.is_dir():
        for file_path in sorted(path for path in target_dir.rglob("*") if path.is_file()):
            copy_files.append({
                "path": str(file_path),
                "relative_path": file_path.relative_to(target_dir).as_posix(),
                "exists": True,
            })

    top_strategy = str(ctx.reporting_summary.get("top_strategy", ""))
    top_family = str(ctx.reporting_summary.get("top_family", ""))
    report_links = [
        {
            "report": "DOPEY_VALIDATION_REPORT.md",
            "sources": [
                _reference(ctx.manifest_registry_path, "export_manifest_registry"),
                _reference(ctx.copy_proof_registry_path, "copy_proof_registry"),
            ],
        },
        {
            "report": "DOPEY_ARTIFACT_COMPACTION_EXPORT_VERIFIER_REPORT.md",
            "sources": [
                _reference(ctx.manifest_registry_path, "export_manifest_registry"),
                _reference(ctx.source_export_path / "EXPORT_MANIFEST.json", "bundle_manifest"),
            ],
        },
    ]
    dashboard_links = [
        {
            "dashboard_artifact": "dashboard_index",
            "sources": [
                _reference(ctx.source_export_path / "artifacts/reporting/dashboard_index.json", "dashboard_index"),
                _reference(ctx.source_export_path / "artifacts/reporting/strategy_report_cards.jsonl", "strategy_cards"),
                _reference(ctx.source_export_path / "artifacts/reporting/family_report_cards.jsonl", "family_cards"),
            ],
        }
    ]
    strategy_links = [
        {
            "strategy_id": top_strategy,
            "sources": [
                "tournament_ledger",
                "walk_forward_ledger",
                "ensemble_registry",
                "meta_governor_registry",
                "strategy_report_cards",
            ],
        }
    ]
    family_links = [
        {
            "strategy_family": top_family,
            "sources": [
                "family_report_cards",
                "scenario_report_cards",
                "failure_mode_registry",
                "regime_holdout_corpus_v2_registry",
                "walk_forward_consistency_registry",
            ],
        }
    ]
    audit_links = audit_artifact_specs()
    seed = {
        "map_id": f"export-review-evidence-map-{ctx.export_manifest.get('bundle_id', '')}",
        "source_bundle_id": str(ctx.export_manifest.get("bundle_id", "")),
        "source_export_path": str(ctx.source_export_path),
        "report_to_source_artifacts": report_links,
        "dashboard_to_source_artifacts": dashboard_links,
        "strategy_to_evidence_layers": strategy_links,
        "family_to_evidence_layers": family_links,
        "manifest_to_exported_files": manifest_files,
        "copy_proof_to_target_files": copy_files,
        "audit_to_artifact_specs": audit_links,
        "missing_references": missing,
    }
    return ExportReviewEvidenceMap(
        map_id=seed["map_id"],
        source_bundle_id=seed["source_bundle_id"],
        source_export_path=seed["source_export_path"],
        report_to_source_artifacts=report_links,
        dashboard_to_source_artifacts=dashboard_links,
        strategy_to_evidence_layers=strategy_links,
        family_to_evidence_layers=family_links,
        manifest_to_exported_files=manifest_files,
        copy_proof_to_target_files=copy_files,
        audit_to_artifact_specs=audit_links,
        missing_references=missing,
        reproducibility_hash=canonical_export_hash(seed),
    )


def render_dependency_graph(evidence_map: ExportReviewEvidenceMap) -> str:
    lines = ["# DOPEY Export Review Dependency Graph", ""]
    lines.append(f"- source_bundle_id: `{evidence_map.source_bundle_id}`")
    lines.append("- static_graph: `true`")
    lines.append("- external_dependencies: `none`")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append('  manifest["Export manifest"] --> files["Exported files"]')
    lines.append('  copy["Copy proof"] --> shared["Shared target files"]')
    lines.append('  dashboard["Dashboard index"] --> strategy["Strategy report cards"]')
    lines.append('  dashboard --> family["Family report cards"]')
    lines.append('  audit["Audit report"] --> specs["Audit artifact specs"]')
    lines.append('  review["Review packet"] --> manifest')
    lines.append('  review --> copy')
    lines.append('  review --> dashboard')
    lines.append('  review --> audit')
    lines.append("```")
    return "\n".join(lines) + "\n"
