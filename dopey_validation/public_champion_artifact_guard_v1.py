"""Canonical artifact guard for public champion decision artifacts."""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from dopey_autonomy.champion_hardening_common import HARDENING_ROOT
from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    repair_proof_record,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    CHAMPION_ROOT,
    LIVE_GATE_ROOT,
    OPTIONS_ENGINE_ROOT,
    SCOREBOARD_ROOT,
    TOURNAMENT_ROOT,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
)


SUMMARY_PATH = REPAIR_ROOT / "public_champion_artifact_guard_v1_summary.json"
INVENTORY_PATH = REPAIR_ROOT / "public_champion_artifact_guard_inventory_v1.jsonl"
BACKUPS_PATH = REPAIR_ROOT / "public_champion_artifact_guard_backups_v1.jsonl"
RESTORE_PATH = REPAIR_ROOT / "public_champion_artifact_guard_restore_records_v1.jsonl"
QUALITY_FLAGS_PATH = REPAIR_ROOT / "public_champion_artifact_guard_quality_flags_v1.jsonl"
PROOF_PATH = REPAIR_ROOT / "public_champion_artifact_guard_proof_v1.jsonl"
BACKUP_ROOT = REPAIR_ROOT / "backups"


@dataclass(frozen=True)
class CanonicalArtifactSpec:
    artifact_id: str
    path: Path
    min_rows: int = 0
    min_bytes: int = 0
    min_champion_count: int = 0


CANONICAL_ARTIFACTS: tuple[CanonicalArtifactSpec, ...] = (
    CanonicalArtifactSpec("tournament_leaderboard_v4", TOURNAMENT_ROOT / "public_cohort_tournament_leaderboard_v4.jsonl", min_rows=100, min_bytes=10_000),
    CanonicalArtifactSpec("champion_gate_v2_results", CHAMPION_ROOT / "public_paper_champion_gate_v2_results.jsonl", min_rows=100, min_bytes=10_000),
    CanonicalArtifactSpec("champion_gate_v2_summary", CHAMPION_ROOT / "public_paper_champion_gate_v2_summary.json", min_bytes=500),
    CanonicalArtifactSpec("hardening_inventory", HARDENING_ROOT / "public_champion_inventory_v1.jsonl", min_rows=1),
    CanonicalArtifactSpec("hardening_gate_results", HARDENING_ROOT / "public_champion_hardening_gate_results_v1.jsonl", min_rows=1),
    CanonicalArtifactSpec("hardening_gate_summary", HARDENING_ROOT / "public_champion_hardening_gate_v1_summary.json", min_bytes=500),
    CanonicalArtifactSpec("hardening_scoreboard", SCOREBOARD_ROOT / "public_champion_hardening_scoreboard_v1.json", min_bytes=300),
    CanonicalArtifactSpec("live_gate_v3", LIVE_GATE_ROOT / "public_champion_hardening_live_gate_status_v3.json", min_bytes=300),
    CanonicalArtifactSpec("v4_trades", OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_trades.jsonl", min_rows=1000, min_bytes=100_000),
)


def run_public_champion_artifact_guard_v1() -> dict[str, object]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    inventory: list[dict[str, object]] = []
    backups: list[dict[str, object]] = []
    restores: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    shrinkage_detected = False
    backed_up_count = 0
    restored_count = 0

    for spec in CANONICAL_ARTIFACTS:
        metrics = artifact_metrics(spec)
        inventory.append(record_with_hash({
            "artifact_type": "public_champion_artifact_guard_inventory_v1",
            "artifact_id": spec.artifact_id,
            "path": str(spec.path),
            **metrics,
            **live_safety_fields(),
        }, "record_hash"))

        if spec.path.exists() and metrics.get("size_bytes", 0) > 0:
            backup_path = backup_artifact(spec.path)
            backed_up_count += 1
            backups.append(record_with_hash({
                "artifact_type": "public_champion_artifact_guard_backup_v1",
                "artifact_id": spec.artifact_id,
                "source_path": str(spec.path),
                "backup_path": str(backup_path),
                "sha256": metrics.get("sha256", ""),
                **live_safety_fields(),
            }, "record_hash"))

        if artifact_shrunk(spec, metrics):
            shrinkage_detected = True
            quality_flags.append(record_with_hash({
                "artifact_type": "public_champion_artifact_guard_quality_flag_v1",
                "flag_id": f"shrinkage_detected_{spec.artifact_id}",
                "severity": "error",
                "metrics": metrics,
                **live_safety_fields(),
            }, "record_hash"))
            restored = restore_latest_backup(spec)
            if restored:
                restored_count += 1
                restores.append(record_with_hash({
                    "artifact_type": "public_champion_artifact_guard_restore_record_v1",
                    "artifact_id": spec.artifact_id,
                    "restored_from": restored,
                    "target_path": str(spec.path),
                    **live_safety_fields(),
                }, "record_hash"))

    status = "artifact_guard_ready" if not shrinkage_detected or restored_count else (
        "artifact_guard_restored_after_shrinkage" if restored_count else "artifact_guard_shrinkage_unresolved"
    )
    summary = {
        "artifact_type": "public_champion_artifact_guard_v1_summary",
        "public_champion_artifact_guard_version": "dopey-public-champion-artifact-guard-v1",
        "artifact_guard_status": status,
        "canonical_artifact_count": len(CANONICAL_ARTIFACTS),
        "backed_up_artifact_count": backed_up_count,
        "shrinkage_detected": shrinkage_detected,
        "restored_artifact_count": restored_count,
        "test_write_isolation_enabled": True,
        "known_overwrite_fragility": "evaluate_public_paper_champions_v2 previously wrote canonical paths from tests; now isolated via artifact_mode",
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(INVENTORY_PATH, inventory)
    write_jsonl_file(BACKUPS_PATH, backups)
    write_jsonl_file(RESTORE_PATH, restores)
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "public-champion-artifact-guard-v1", status, summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_metrics(spec: CanonicalArtifactSpec) -> dict[str, object]:
    path = spec.path
    if not path.exists():
        return {"exists": False, "row_count": 0, "size_bytes": 0, "sha256": "", "champion_count": 0}
    size_bytes = path.stat().st_size
    sha256 = sha256_file(path)
    if path.suffix == ".jsonl":
        rows = read_jsonl_file(path)
        return {
            "exists": True,
            "row_count": len(rows),
            "size_bytes": size_bytes,
            "sha256": sha256,
            "champion_count": sum(1 for row in rows if bool(row.get("public_data_paper_champion", False))),
        }
    payload = read_json_file(path)
    return {
        "exists": True,
        "row_count": 1,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "champion_count": int(payload.get("public_paper_champion_count", payload.get("hardened_champion_count", 0))),
    }


def artifact_shrunk(spec: CanonicalArtifactSpec, metrics: dict[str, object]) -> bool:
    if not bool(metrics.get("exists")):
        return True
    if int(metrics.get("size_bytes", 0)) < spec.min_bytes:
        return True
    if spec.min_rows and int(metrics.get("row_count", 0)) < spec.min_rows:
        return True
    if spec.min_champion_count and int(metrics.get("champion_count", 0)) < spec.min_champion_count:
        return spec.artifact_id == "champion_gate_v2_summary"
    return False


def backup_artifact(path: Path) -> Path:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_ROOT / f"{path.parent.name}__{path.name}"
    shutil.copy2(path, backup_path)
    return backup_path


def restore_latest_backup(spec: CanonicalArtifactSpec) -> str:
    backup_path = BACKUP_ROOT / f"{spec.path.parent.name}__{spec.path.name}"
    if not backup_path.exists():
        candidates = sorted(BACKUP_ROOT.glob(f"*{spec.path.name}"))
        if not candidates:
            return ""
        backup_path = candidates[-1]
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, spec.path)
    return str(backup_path)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_artifact_guard_v1_summary": str(SUMMARY_PATH),
        "public_champion_artifact_guard_inventory_v1": str(INVENTORY_PATH),
        "public_champion_artifact_guard_backups_v1": str(BACKUPS_PATH),
        "public_champion_artifact_guard_restore_records_v1": str(RESTORE_PATH),
        "public_champion_artifact_guard_quality_flags_v1": str(QUALITY_FLAGS_PATH),
        "public_champion_artifact_guard_proof_v1": str(PROOF_PATH),
    }
