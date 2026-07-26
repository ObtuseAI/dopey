"""Deploy a verified DOPEY code release without touching operational evidence state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, TypedDict


CONFIRMATION = "paper_research_code_only"
GIT_INSPECTION_TIMEOUT_SECONDS = 30
SOURCE_DIRECTORY_NAMES = frozenset({"dopey", "operator_tools"})
OPERATOR_SUFFIXES = frozenset({".cmd", ".ps1", ".py"})
CONFIG_SUFFIXES = frozenset({".json", ".toml", ".yaml", ".yml"})
PROTECTED_STATE_PREFIXES = (
    "artifacts/",
    "dopey_data/history/",
    "dopey_data/market_lake/",
    "dopey_data/real/",
)


class ReleaseFile(TypedDict):
    relative_path: str
    source_sha256: str
    target_sha256_before: str
    target_status: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _relative(path: Path, root: Path) -> str:
    if not _is_within(path, root):
        raise ValueError(f"release path escapes root: path={path}, root={root}")
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_source_directory(path: Path) -> bool:
    return path.name in SOURCE_DIRECTORY_NAMES or path.name.startswith("dopey_")


def collect_release_paths(source_root: Path) -> tuple[Path, ...]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"source repository is missing: source_root={source_root}")
    paths: set[Path] = set()
    for directory in source_root.iterdir():
        if not directory.is_dir() or not _is_source_directory(directory):
            continue
        suffixes = OPERATOR_SUFFIXES if directory.name == "operator_tools" else frozenset({".py"})
        for candidate in directory.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in suffixes and "__pycache__" not in candidate.parts:
                paths.add(candidate.resolve())
    config_root = source_root / "configs"
    if config_root.is_dir():
        for candidate in config_root.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in CONFIG_SUFFIXES:
                paths.add(candidate.resolve())
    pyproject = source_root / "pyproject.toml"
    if pyproject.is_file():
        paths.add(pyproject.resolve())
    if not paths:
        raise RuntimeError(f"no deployable source files found: source_root={source_root}")
    relative_paths = [_relative(path, source_root) for path in paths]
    protected = [
        relative_path
        for relative_path in relative_paths
        if any(relative_path.startswith(prefix) for prefix in PROTECTED_STATE_PREFIXES)
    ]
    if protected:
        raise RuntimeError(f"release inventory contains protected state paths: paths={protected}")
    return tuple(sorted(paths, key=lambda path: _relative(path, source_root)))


def _git_commit(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_INSPECTION_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "unable to resolve source commit: "
            f"source_root={source_root}, return_code={completed.returncode}, stderr={completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _git_dirty(source_root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_INSPECTION_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "unable to inspect source repository: "
            f"source_root={source_root}, return_code={completed.returncode}, stderr={completed.stderr.strip()}"
        )
    return bool(completed.stdout.strip())


def build_release_plan(source_root: Path, target_root: Path) -> dict[str, Any]:
    if source_root.resolve() == target_root.resolve():
        raise ValueError(f"source and target repositories must differ: root={source_root.resolve()}")
    if not target_root.is_dir():
        raise FileNotFoundError(f"target repository is missing: target_root={target_root}")
    source_commit = _git_commit(source_root)
    release_files: list[ReleaseFile] = []
    for source_path in collect_release_paths(source_root):
        relative_path = _relative(source_path, source_root)
        target_path = target_root / Path(relative_path)
        source_hash = _sha256(source_path)
        target_hash = _sha256(target_path) if target_path.is_file() else ""
        release_files.append(
            {
                "relative_path": relative_path,
                "source_sha256": source_hash,
                "target_sha256_before": target_hash,
                "target_status": (
                    "unchanged" if target_hash == source_hash else "update" if target_hash else "create"
                ),
            }
        )
    inventory_hash = _canonical_hash(
        [{"relative_path": item["relative_path"], "source_sha256": item["source_sha256"]} for item in release_files]
    )
    release_id = f"dopey-code-release-{source_commit[:12]}-{inventory_hash[:12]}"
    return {
        "artifact_type": "dopey_code_release_plan",
        "release_version": "dopey-code-release-v1",
        "release_id": release_id,
        "source_root": str(source_root.resolve()),
        "target_root": str(target_root.resolve()),
        "source_commit": source_commit,
        "source_dirty": _git_dirty(source_root),
        "inventory_hash": inventory_hash,
        "file_count": len(release_files),
        "create_count": sum(item["target_status"] == "create" for item in release_files),
        "update_count": sum(item["target_status"] == "update" for item in release_files),
        "unchanged_count": sum(item["target_status"] == "unchanged" for item in release_files),
        "files": release_files,
        "protected_state_prefixes": list(PROTECTED_STATE_PREFIXES),
        "paper_only": True,
        "live_blocked": True,
        "broker_authority": False,
        "order_authority": False,
    }


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_atomic(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(source_path, temporary)
        os.replace(temporary, target_path)
    finally:
        temporary.unlink(missing_ok=True)


def _rollback_changed_files(
    changed_records: list[dict[str, Any]],
    source_root: Path,
    target_root: Path,
) -> list[dict[str, str]]:
    rollback_records: list[dict[str, str]] = []
    for item in reversed(changed_records):
        relative_path = str(item["relative_path"])
        target_path = target_root / Path(relative_path)
        backup_path_text = str(item.get("backup_path", ""))
        backup_path = Path(backup_path_text) if backup_path_text else None
        status = "not_required"
        if item["target_status"] == "update" and backup_path is not None and backup_path.is_file():
            _copy_atomic(backup_path, target_path)
            status = "restored_backup"
        elif item["target_status"] == "create" and target_path.is_file():
            source_path = source_root / Path(relative_path)
            if source_path.is_file() and _sha256(target_path) == _sha256(source_path):
                target_path.unlink()
                status = "removed_release_created_file"
            else:
                status = "preserved_unmatched_created_path"
        rollback_records.append({"relative_path": relative_path, "rollback_status": status})
    return list(reversed(rollback_records))


def apply_release_plan(plan: dict[str, Any], confirmation: str) -> dict[str, Any]:
    if confirmation != CONFIRMATION:
        raise PermissionError(f"code release requires confirmation={CONFIRMATION}")
    if plan.get("source_dirty") is not False:
        raise RuntimeError("code release refuses a dirty source repository")
    if plan.get("paper_only") is not True or plan.get("live_blocked") is not True:
        raise RuntimeError("code release rejects a non-paper or live-enabled plan")
    source_root = Path(str(plan["source_root"])).resolve()
    target_root = Path(str(plan["target_root"])).resolve()
    if _git_commit(source_root) != str(plan["source_commit"]):
        raise RuntimeError("source commit changed after release planning")
    if (target_root / "artifacts" / "dopey" / "acceleration" / "acceleration_cycle.lock").exists():
        raise RuntimeError("code release refuses to deploy while the acceleration cycle lock exists")
    rebuilt = build_release_plan(source_root, target_root)
    if rebuilt["inventory_hash"] != plan["inventory_hash"]:
        raise RuntimeError("source inventory changed after release planning")
    release_id = str(plan["release_id"])
    backup_root = target_root / "artifacts" / "dopey" / "deployment" / "code_release_backups" / release_id
    manifest_path = target_root / "artifacts" / "dopey" / "deployment" / "latest_code_release.json"
    changed_records: list[dict[str, Any]] = []
    for item in plan["files"]:
        relative_path = str(item["relative_path"])
        source_path = source_root / Path(relative_path)
        target_path = target_root / Path(relative_path)
        if not _is_within(source_path, source_root) or not _is_within(target_path, target_root):
            raise ValueError(f"release file escapes repository roots: relative_path={relative_path}")
        backup_path = backup_root / Path(relative_path)
        if target_path.is_file() and item["target_status"] != "unchanged":
            _copy_atomic(target_path, backup_path)
        changed_records.append({**item, "backup_path": str(backup_path) if backup_path.is_file() else ""})
    prepared = {
        **{key: value for key, value in plan.items() if key != "files"},
        "artifact_type": "dopey_code_release_manifest",
        "deployment_status": "prepared",
        "backup_root": str(backup_root),
        "manifest_path": str(manifest_path),
        "files": changed_records,
    }
    _write_json_atomic(backup_root / "release_manifest.json", prepared)
    copied_records: list[dict[str, Any]] = []
    try:
        for item in changed_records:
            relative_path = str(item["relative_path"])
            source_path = source_root / Path(relative_path)
            target_path = target_root / Path(relative_path)
            if item["target_status"] != "unchanged":
                _copy_atomic(source_path, target_path)
            target_hash_after = _sha256(target_path)
            if target_hash_after != item["source_sha256"]:
                raise RuntimeError(
                    "release verification failed: "
                    f"relative_path={relative_path}, expected={item['source_sha256']}, actual={target_hash_after}"
                )
            copied_records.append(
                {
                    **item,
                    "target_sha256_after": target_hash_after,
                    "verification_status": "verified",
                }
            )
    except Exception as error:
        rollback_records = _rollback_changed_files(changed_records, source_root, target_root)
        failed_manifest = {
            **prepared,
            "deployment_status": "failed_rolled_back",
            "failure_type": type(error).__name__,
            "failure_message": str(error),
            "rollback_records": rollback_records,
            "rollback_complete": all(
                item["rollback_status"]
                in {"not_required", "restored_backup", "removed_release_created_file"}
                for item in rollback_records
            ),
        }
        _write_json_atomic(backup_root / "release_manifest.json", failed_manifest)
        _write_json_atomic(manifest_path, failed_manifest)
        raise RuntimeError(
            "code release failed and rollback was attempted: "
            f"release_id={release_id}, rollback_complete={failed_manifest['rollback_complete']}"
        ) from error
    manifest = {
        **{key: value for key, value in plan.items() if key != "files"},
        "artifact_type": "dopey_code_release_manifest",
        "deployment_status": "complete_verified",
        "backup_root": str(backup_root),
        "manifest_path": str(manifest_path),
        "files": copied_records,
        "verification_hash": _canonical_hash(copied_records),
    }
    _write_json_atomic(backup_root / "release_manifest.json", manifest)
    _write_json_atomic(manifest_path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("plan", "apply"), required=True)
    parser.add_argument("--confirmation", type=str, required=False)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    plan = build_release_plan(arguments.source_root, arguments.target_root)
    result = apply_release_plan(plan, str(arguments.confirmation or "")) if arguments.mode == "apply" else plan
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
