"""Load deterministic local evidence for DOPEY export bundle review artifacts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dopey_audit.artifact_loader import ARTIFACT_SPECS, load_latest_record, load_records
from dopey_core.config import default_config_path, load_config
from dopey_export.artifact_selector import (
    EXPORT_COPY_PROOF_PATH,
    EXPORT_MANIFEST_REGISTRY_PATH,
    EXPORT_PROOF_LEDGER_PATH,
    EXPORT_REGISTRY_PATH,
    EXPORT_SAFETY_SCAN_PATH,
    EXPORT_VERIFICATION_PATH,
    verify_export_safety_state,
)
from dopey_export.copy_verifier import verify_copied_bundle
from dopey_export.export_manifest import canonical_export_hash, sha256_file
from dopey_reporting.data_loader import (
    FAMILY_REPORT_CARDS_PATH,
    REPORTING_BUNDLE_SUMMARY_PATH,
    REPORTING_DASHBOARD_INDEX_JSON,
    STRATEGY_REPORT_CARDS_PATH,
)

from .review_models import NEXT_REVIEW_BUILD_TARGET
from .review_paths import ARTIFACT_ROOT, REPO_ROOT


@dataclass(frozen=True)
class ExportReviewContext:
    safety_state: dict
    export_registry: dict
    export_manifest: dict
    export_safety_scan: dict
    export_copy_proof: dict
    export_verification: dict
    reporting_summary: dict
    dashboard_index: dict
    strategy_cards: list[dict]
    family_cards: list[dict]
    audit_gap_plan: dict
    audit_summary: dict
    source_export_path: Path
    shared_export_path: str
    manifest_registry_path: Path
    copy_proof_registry_path: Path


def safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_review": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_review_safety_state(state: dict) -> None:
    verify_export_safety_state({
        "mode": state["mode"],
        "live_trading_enabled": state["live_trading_enabled"],
        "funded_broker_connections_enabled": state["funded_broker_connections_enabled"],
        "allow_unofficial_robinhood_api": state["allow_unofficial_robinhood_api"],
        "paper_only_export": True,
        "fixture_only": True,
        "live_blocked": state["live_blocked"],
    })


def read_json(path: Path | str) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    text = target.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {}


def read_jsonl(path: Path | str) -> list[dict]:
    return load_records(path)


def write_json(path: Path | str, record: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def write_jsonl(path: Path | str, records: list[dict]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def append_jsonl(path: Path | str, record: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return target


def write_text(path: Path | str, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def repo_relative(path: Path | str) -> str:
    target = Path(path)
    try:
        return target.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(target)


def _source_export_path(export_registry: dict, copy_proof: dict) -> Path:
    raw = export_registry.get("local_export_path") or copy_proof.get("source_dir") or ""
    return Path(str(raw)) if raw else ARTIFACT_ROOT / "exports" / str(export_registry.get("bundle_id", ""))


def load_review_context() -> ExportReviewContext:
    state = safety_state()
    verify_review_safety_state(state)
    export_registry = load_latest_record(EXPORT_REGISTRY_PATH)
    export_manifest = load_latest_record(EXPORT_MANIFEST_REGISTRY_PATH)
    export_safety_scan = load_latest_record(EXPORT_SAFETY_SCAN_PATH)
    export_copy_proof = load_latest_record(EXPORT_COPY_PROOF_PATH)
    export_verification = load_latest_record(EXPORT_VERIFICATION_PATH)
    source_path = _source_export_path(export_registry, export_copy_proof)
    return ExportReviewContext(
        safety_state=state,
        export_registry=export_registry,
        export_manifest=export_manifest,
        export_safety_scan=export_safety_scan,
        export_copy_proof=export_copy_proof,
        export_verification=export_verification,
        reporting_summary=read_json(REPORTING_BUNDLE_SUMMARY_PATH),
        dashboard_index=read_json(REPORTING_DASHBOARD_INDEX_JSON),
        strategy_cards=read_jsonl(STRATEGY_REPORT_CARDS_PATH),
        family_cards=read_jsonl(FAMILY_REPORT_CARDS_PATH),
        audit_gap_plan=load_latest_record(ARTIFACT_ROOT / "audit" / "evidence_gap_plan.jsonl"),
        audit_summary=load_latest_record(ARTIFACT_ROOT / "audit" / "evidence_replay_audit_proof.jsonl"),
        source_export_path=source_path,
        shared_export_path=str(export_registry.get("shared_export_path") or export_copy_proof.get("target_dir") or ""),
        manifest_registry_path=EXPORT_MANIFEST_REGISTRY_PATH,
        copy_proof_registry_path=EXPORT_COPY_PROOF_PATH,
    )


def manifest_file_hash_status(ctx: ExportReviewContext) -> tuple[str, list[dict]]:
    mismatches: list[dict] = []
    for artifact in ctx.export_manifest.get("artifacts", []) or []:
        relative_path = str(artifact.get("relative_export_path", ""))
        target = ctx.source_export_path / relative_path
        if not target.exists():
            mismatches.append({"relative_export_path": relative_path, "reason": "missing"})
            continue
        expected_hash = str(artifact.get("sha256", ""))
        expected_size = int(artifact.get("size_bytes", 0))
        if sha256_file(target) != expected_hash:
            mismatches.append({"relative_export_path": relative_path, "reason": "hash_mismatch"})
        if target.stat().st_size != expected_size:
            mismatches.append({"relative_export_path": relative_path, "reason": "size_mismatch"})
    manifest_hash_ok = canonical_export_hash(ctx.export_manifest) == str(ctx.export_manifest.get("reproducibility_hash", ""))
    if not manifest_hash_ok:
        mismatches.append({"relative_export_path": "export_manifest_registry", "reason": "manifest_reproducibility_hash_mismatch"})
    return ("pass" if not mismatches else "fail", mismatches)


def copy_proof_status(ctx: ExportReviewContext) -> str:
    status = str(ctx.export_copy_proof.get("verification_status", "missing"))
    if status != "verified":
        return status
    target_dir = str(ctx.export_copy_proof.get("target_dir", ""))
    if not target_dir:
        return status
    proof = verify_copied_bundle(str(ctx.export_copy_proof.get("bundle_id", "")), ctx.source_export_path, Path(target_dir))
    return "verified" if proof.verification_status == "verified" else "failed"


def top_known_gaps(ctx: ExportReviewContext) -> list[str]:
    gaps: list[str] = []
    audit_gap_plan = getattr(ctx, "audit_gap_plan", {})
    for gap in audit_gap_plan.get("gaps", []) or []:
        if isinstance(gap, dict):
            category = str(gap.get("category", ""))
            if category:
                gaps.append(category)
    if not gaps:
        gaps.append("deterministic_fixture_only_limitation")
    return gaps


def next_build_target(ctx: ExportReviewContext) -> str:
    target = ctx.audit_gap_plan.get("recommended_build_target", {})
    if isinstance(target, dict) and target.get("target"):
        return NEXT_REVIEW_BUILD_TARGET
    return NEXT_REVIEW_BUILD_TARGET


def audit_artifact_specs() -> list[dict]:
    return [
        {"artifact_type": artifact_type, "relative_path": rel_path, "kind": kind}
        for artifact_type, rel_path, kind, _fields in ARTIFACT_SPECS
    ]
