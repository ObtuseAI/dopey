"""Sandbox folder contracts for future approved open-source imports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .oss_models import OSS_STACK_VERSION, OssSandboxImportPlan


REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = REPO_ROOT / "dopey_open_source_vendor"
REFERENCE_ONLY_DIR = VENDOR_ROOT / "reference_only"
SANDBOX_CANDIDATES_DIR = VENDOR_ROOT / "sandbox_candidates"
ADAPTER_CANDIDATES_DIR = VENDOR_ROOT / "adapter_candidates"
MANIFESTS_DIR = VENDOR_ROOT / "manifests"
OSS_IMPORT_MANIFEST_TEMPLATE_PATH = MANIFESTS_DIR / "OSS_IMPORT_MANIFEST.template.json"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "open_source"
OSS_SANDBOX_IMPORT_PLAN_PATH = ARTIFACT_DIR / "oss_sandbox_import_plan.json"


def build_oss_sandbox_import_plan() -> OssSandboxImportPlan:
    return OssSandboxImportPlan(
        artifact_type="oss_sandbox_import_plan",
        oss_stack_version=OSS_STACK_VERSION,
        plan_id="oss-sandbox-import-plan-v1",
        reference_only_folder="dopey_open_source_vendor/reference_only/",
        sandbox_candidates_folder="dopey_open_source_vendor/sandbox_candidates/",
        adapter_candidates_folder="dopey_open_source_vendor/adapter_candidates/",
        manifests_folder="dopey_open_source_vendor/manifests/",
        manifest_template_path="dopey_open_source_vendor/manifests/OSS_IMPORT_MANIFEST.template.json",
        repo_cloned_count=0,
        dependency_installed_count=0,
        external_code_imported_count=0,
        external_code_executed_count=0,
        approval_required=True,
        paper_only=True,
        live_blocked=True,
        plan_hash="",
    )


def write_oss_sandbox_import_plan() -> dict[str, Any]:
    for folder in [REFERENCE_ONLY_DIR, SANDBOX_CANDIDATES_DIR, ADAPTER_CANDIDATES_DIR, MANIFESTS_DIR]:
        folder.mkdir(parents=True, exist_ok=True)
    _write_manifest_template()
    record = build_oss_sandbox_import_plan().to_dict()
    _write_json(OSS_SANDBOX_IMPORT_PLAN_PATH, record)
    return {**record, "artifact_path": str(OSS_SANDBOX_IMPORT_PLAN_PATH)}


def _write_manifest_template() -> None:
    record = {
        "manifest_id": "OPERATOR_FILLED_OSS_IMPORT_MANIFEST",
        "oss_stack_version": OSS_STACK_VERSION,
        "candidate_id": "REQUIRED",
        "source_repo_name": "REQUIRED",
        "source_repo_url": "REQUIRED",
        "source_commit_or_release": "REQUIRED_IF_APPROVED",
        "license_name": "REQUIRED",
        "license_review_status": "manual_review_required",
        "security_review_status": "manual_review_required",
        "approval_record": "REQUIRED_BEFORE_ANY_IMPORT",
        "import_mode": "reference_only",
        "repo_cloned_by_dopey": False,
        "dependency_installed_by_dopey": False,
        "external_code_imported": False,
        "external_code_executed": False,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "paper_only": True,
        "live_blocked": True,
    }
    _write_json(OSS_IMPORT_MANIFEST_TEMPLATE_PATH, record)


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
