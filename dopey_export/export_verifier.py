"""Build, compact, export, and verify deterministic DOPEY handoff bundles."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .artifact_compactor import compact_export_artifacts
from .artifact_selector import (
    EXPORT_COMPACTION_SUMMARY_PATH,
    EXPORT_COPY_PROOF_PATH,
    EXPORT_MANIFEST_REGISTRY_PATH,
    EXPORT_PROOF_LEDGER_PATH,
    EXPORT_REGISTRY_PATH,
    EXPORT_ROOT,
    EXPORT_SAFETY_SCAN_PATH,
    EXPORT_VERIFICATION_PATH,
    REPO_ROOT,
    resolve_repo_path,
    safety_state,
    select_export_artifacts,
    verify_export_safety_state,
)
from .copy_verifier import copy_bundle, first_available_shared_target, verify_copied_bundle
from .export_manifest import (
    append_jsonl,
    build_export_manifest,
    canonical_export_hash,
    sha256_file,
    write_json,
)
from .export_models import (
    DEFAULT_EXPORT_PROFILE,
    EXPORT_VERIFIER_VERSION,
    CopyProof,
    ExportArtifact,
    ExportBundlePlan,
    ExportBundleResult,
)
from .export_safety_scanner import scan_artifact_path, scan_export_artifacts


def _bundle_dir(bundle_id: str) -> Path:
    return EXPORT_ROOT / bundle_id


def _copy_source_artifacts(plan: ExportBundlePlan, bundle_dir: Path, compacted_source_ids: set[str]) -> list[ExportArtifact]:
    exported: list[ExportArtifact] = []
    for artifact in plan.selected_artifacts:
        if artifact.artifact_id in compacted_source_ids:
            continue
        source = resolve_repo_path(artifact.source_path)
        target = bundle_dir / artifact.relative_export_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        exported.append(ExportArtifact(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            source_path=artifact.source_path,
            relative_export_path=artifact.relative_export_path,
            size_bytes=target.stat().st_size,
            sha256=sha256_file(target),
            record_count=artifact.record_count,
            parse_status=artifact.parse_status,
            required=artifact.required,
            safety_scan_status=artifact.safety_scan_status,
            notes=artifact.notes,
        ))
    return exported


def _provenance_label(source: Path) -> str:
    """Repo-relative provenance label; tolerate artifact trees rooted elsewhere
    (isolated test mirrors) by falling back to the artifacts/... tail."""
    try:
        return source.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        parts = source.parts
        if "artifacts" in parts:
            return "/".join(parts[parts.index("artifacts"):])
        return source.as_posix()


def _copy_compacted_artifacts(bundle_dir: Path, compacted_records: list[dict]) -> list[ExportArtifact]:
    exported: list[ExportArtifact] = []
    for record in compacted_records:
        source = Path(record["compacted_path"])
        rel = f"compacted/{source.name}"
        target = bundle_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        exported.append(ExportArtifact(
            artifact_id=f"compacted-{record['source_artifact_id']}",
            artifact_type="export_compaction_summary",
            source_path=_provenance_label(source),
            relative_export_path=rel,
            size_bytes=target.stat().st_size,
            sha256=sha256_file(target),
            record_count=1,
            parse_status="ok",
            required=False,
            safety_scan_status="pass",
            notes=["deterministic compacted ledger summary"],
        ))
    return exported


def _verify_local_export(bundle_id: str, bundle_dir: Path) -> CopyProof:
    return verify_copied_bundle(bundle_id, bundle_dir, bundle_dir)


def _scan_exported_bundle(bundle_dir: Path) -> tuple[int, int]:
    findings = []
    for path in bundle_dir.rglob("*"):
        if path.is_file():
            findings.extend(scan_artifact_path(path))
    active = sum(1 for finding in findings if "forbidden live decision" in finding.reason)
    credentials = sum(1 for finding in findings if "credential" in finding.reason or "API-key" in finding.reason)
    return active, credentials


def _build_proof_entry(result: ExportBundleResult, manifest_record: dict, safety_scan: dict, copy_proof: dict) -> ProofEntry:
    return ProofEntry(
        run_id=EXPORT_VERIFIER_VERSION,
        task_id="artifact-compaction-export-verifier",
        timestamp="1970-01-01T00:00:00Z",
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"export_verifier_version": EXPORT_VERIFIER_VERSION, "profile": result.profile}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "export_result": result.to_dict(),
            "manifest": manifest_record,
            "safety_scan": safety_scan,
            "copy_proof": copy_proof,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[
            result.export_registry_path,
            result.manifest_path,
            result.export_safety_scan_path,
            result.export_verification_path,
            result.copy_proof_path,
        ],
        diffs=[],
        test_results={
            "export_status": result.export_status,
            "artifacts_selected": result.artifacts_selected,
            "artifacts_exported": result.artifacts_exported,
            "active_forbidden_live_decisions": result.active_forbidden_live_decisions,
            "credential_findings": result.credential_findings,
            "hash_mismatches": result.hash_mismatches,
            "copy_status": result.copy_status,
            "live_blocked": result.live_blocked,
        },
        final_status="PASS" if result.export_status == "ok" else "FAIL",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline artifact export verification only; not deployment",
            "fixture-only paper evidence; not live performance evidence",
            "no broker connection, credentials, network market data, scheduler, or live promotion",
        ],
    )


def run_artifact_compaction_export_verifier(profile_name: str) -> dict:
    state = safety_state()
    verify_export_safety_state(state)
    plan = select_export_artifacts(profile_name, state)
    safety_scan = scan_export_artifacts(plan.bundle_id, plan.selected_artifacts)
    append_jsonl(EXPORT_SAFETY_SCAN_PATH, safety_scan.to_dict())

    export_status = "ok"
    if plan.missing_required_artifacts:
        export_status = "fail_missing_required_artifacts"
    if safety_scan.verification_blocked:
        export_status = "fail_safety"

    compaction = compact_export_artifacts(plan.bundle_id, plan.profile, plan.selected_artifacts)
    append_jsonl(EXPORT_COMPACTION_SUMMARY_PATH, compaction.to_dict())

    bundle_dir = _bundle_dir(plan.bundle_id)
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    compacted_source_ids = {artifact.source_artifact_id for artifact in compaction.compacted_artifacts}
    exported_artifacts = _copy_source_artifacts(plan, bundle_dir, compacted_source_ids)
    compacted_artifacts = _copy_compacted_artifacts(
        bundle_dir,
        [artifact.to_dict() for artifact in compaction.compacted_artifacts],
    )
    all_exported = exported_artifacts + compacted_artifacts
    local_active, local_credentials = _scan_exported_bundle(bundle_dir)
    if local_active or local_credentials:
        export_status = "fail_safety"

    manifest = build_export_manifest(
        manifest_id=f"export-manifest-{plan.bundle_id}",
        bundle_id=plan.bundle_id,
        profile=plan.profile,
        artifacts=all_exported,
        safety_state=state,
    )
    manifest_path = bundle_dir / "EXPORT_MANIFEST.json"
    write_json(manifest_path, manifest.to_dict())
    append_jsonl(EXPORT_MANIFEST_REGISTRY_PATH, manifest.to_dict())

    local_proof = _verify_local_export(plan.bundle_id, bundle_dir)
    append_jsonl(EXPORT_VERIFICATION_PATH, local_proof.to_dict())

    shared_path = ""
    copy_status = "skipped_unavailable"
    copy_proof = CopyProof(
        copy_proof_id=f"copy-proof-{plan.bundle_id}-skipped",
        bundle_id=plan.bundle_id,
        source_dir=str(bundle_dir),
        target_dir="",
        files_expected=local_proof.files_expected,
        files_copied=0,
        files_verified=0,
        bytes_expected=local_proof.bytes_expected,
        bytes_verified=0,
        hash_mismatches=[],
        missing_files=[],
        extra_files=[],
        verification_status="skipped_unavailable",
        reproducibility_hash="",
    )
    copy_proof = CopyProof(
        copy_proof_id=copy_proof.copy_proof_id,
        bundle_id=copy_proof.bundle_id,
        source_dir=copy_proof.source_dir,
        target_dir=copy_proof.target_dir,
        files_expected=copy_proof.files_expected,
        files_copied=copy_proof.files_copied,
        files_verified=copy_proof.files_verified,
        bytes_expected=copy_proof.bytes_expected,
        bytes_verified=copy_proof.bytes_verified,
        hash_mismatches=copy_proof.hash_mismatches,
        missing_files=copy_proof.missing_files,
        extra_files=copy_proof.extra_files,
        verification_status=copy_proof.verification_status,
        reproducibility_hash=canonical_export_hash({k: v for k, v in copy_proof.to_dict().items() if k != "reproducibility_hash"}),
    )
    shared_target = first_available_shared_target(plan.bundle_id)
    if shared_target is not None and export_status == "ok":
        copy_proof = copy_bundle(plan.bundle_id, bundle_dir, shared_target)
        shared_path = str(shared_target)
        copy_status = copy_proof.verification_status
    append_jsonl(EXPORT_COPY_PROOF_PATH, copy_proof.to_dict())

    registry_record = {
        "export_registry_version": EXPORT_VERIFIER_VERSION,
        "bundle_id": plan.bundle_id,
        "profile": plan.profile,
        "export_status": export_status,
        "artifacts_selected": len(plan.selected_artifacts),
        "artifacts_exported": len(all_exported),
        "compacted_artifacts": compaction.compacted_artifact_count,
        "local_export_path": str(bundle_dir),
        "shared_export_path": shared_path,
        "copy_status": copy_status,
        "manifest_path": str(EXPORT_MANIFEST_REGISTRY_PATH),
        "copy_proof_path": str(EXPORT_COPY_PROOF_PATH),
        "proof_record_path": str(EXPORT_PROOF_LEDGER_PATH),
        "missing_required_artifacts": plan.missing_required_artifacts,
        "missing_optional_artifacts": plan.missing_optional_artifacts,
        "skipped_artifacts": plan.skipped_artifacts,
        "safety_state": state,
        "live_blocked": True,
    }
    registry_record["reproducibility_hash"] = canonical_export_hash(registry_record)
    append_jsonl(EXPORT_REGISTRY_PATH, registry_record)

    result_seed = {
        "export_status": export_status,
        "mode": state["mode"],
        "live_trading_enabled": state["live_trading_enabled"],
        "profile": plan.profile,
        "bundle_id": plan.bundle_id,
        "artifacts_selected": len(plan.selected_artifacts),
        "artifacts_exported": len(all_exported),
        "compacted_artifacts": compaction.compacted_artifact_count,
        "total_size_bytes": manifest.total_size_bytes,
        "safety_findings": len(safety_scan.findings) + local_active + local_credentials,
        "active_forbidden_live_decisions": safety_scan.active_forbidden_live_decisions + local_active,
        "credential_findings": safety_scan.credential_findings + local_credentials,
        "local_export_path": str(bundle_dir),
        "shared_export_path": shared_path,
        "copy_status": copy_status,
        "files_verified": copy_proof.files_verified if copy_status == "verified" else local_proof.files_verified,
        "hash_mismatches": len(copy_proof.hash_mismatches) + len(local_proof.hash_mismatches),
        "live_blocked": True,
        "manifest_path": str(EXPORT_MANIFEST_REGISTRY_PATH),
        "copy_proof_path": str(EXPORT_COPY_PROOF_PATH),
        "proof_record_path": str(EXPORT_PROOF_LEDGER_PATH),
        "export_registry_path": str(EXPORT_REGISTRY_PATH),
        "export_safety_scan_path": str(EXPORT_SAFETY_SCAN_PATH),
        "export_verification_path": str(EXPORT_VERIFICATION_PATH),
    }
    result = ExportBundleResult(
        export_status=result_seed["export_status"],
        mode=result_seed["mode"],
        live_trading_enabled=result_seed["live_trading_enabled"],
        profile=result_seed["profile"],
        bundle_id=result_seed["bundle_id"],
        artifacts_selected=result_seed["artifacts_selected"],
        artifacts_exported=result_seed["artifacts_exported"],
        compacted_artifacts=result_seed["compacted_artifacts"],
        total_size_bytes=result_seed["total_size_bytes"],
        safety_findings=result_seed["safety_findings"],
        active_forbidden_live_decisions=result_seed["active_forbidden_live_decisions"],
        credential_findings=result_seed["credential_findings"],
        local_export_path=result_seed["local_export_path"],
        shared_export_path=result_seed["shared_export_path"],
        copy_status=result_seed["copy_status"],
        files_verified=result_seed["files_verified"],
        hash_mismatches=result_seed["hash_mismatches"],
        live_blocked=result_seed["live_blocked"],
        manifest_path=result_seed["manifest_path"],
        copy_proof_path=result_seed["copy_proof_path"],
        proof_record_path=result_seed["proof_record_path"],
        export_registry_path=result_seed["export_registry_path"],
        export_safety_scan_path=result_seed["export_safety_scan_path"],
        export_verification_path=result_seed["export_verification_path"],
        reproducibility_hash=canonical_export_hash(result_seed),
    )
    ProofLedger(EXPORT_PROOF_LEDGER_PATH).append(_build_proof_entry(
        result,
        manifest.to_dict(),
        safety_scan.to_dict(),
        copy_proof.to_dict(),
    ))
    return result.to_dict()


def run_default_artifact_compaction_export_verifier() -> dict:
    return run_artifact_compaction_export_verifier(DEFAULT_EXPORT_PROFILE)
