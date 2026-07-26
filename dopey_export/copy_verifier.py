"""Local and shared-folder copy verification for DOPEY export bundles."""
from __future__ import annotations

import shutil
from pathlib import Path

from .export_manifest import canonical_export_hash, sha256_file
from .export_models import CopyProof


def _file_map(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }


def verify_copied_bundle(bundle_id: str, source_dir: Path | str, target_dir: Path | str) -> CopyProof:
    source = Path(source_dir)
    target = Path(target_dir)
    source_files = _file_map(source)
    target_files = _file_map(target) if target.exists() else {}
    missing = sorted([rel for rel in source_files if rel not in target_files])
    extra = sorted([rel for rel in target_files if rel not in source_files])
    mismatches: list[str] = []
    verified = 0
    bytes_expected = sum(path.stat().st_size for path in source_files.values())
    bytes_verified = 0
    for rel, source_path in source_files.items():
        target_path = target_files.get(rel)
        if target_path is None:
            continue
        if sha256_file(source_path) != sha256_file(target_path):
            mismatches.append(rel)
            continue
        verified += 1
        bytes_verified += target_path.stat().st_size
    status = "verified" if not missing and not extra and not mismatches and verified == len(source_files) else "failed"
    seed = {
        "copy_proof_id": f"copy-proof-{bundle_id}",
        "bundle_id": bundle_id,
        "source_dir": str(source),
        "target_dir": str(target),
        "files_expected": len(source_files),
        "files_copied": len(target_files),
        "files_verified": verified,
        "bytes_expected": bytes_expected,
        "bytes_verified": bytes_verified,
        "hash_mismatches": sorted(mismatches),
        "missing_files": missing,
        "extra_files": extra,
        "verification_status": status,
    }
    return CopyProof(
        copy_proof_id=seed["copy_proof_id"],
        bundle_id=bundle_id,
        source_dir=seed["source_dir"],
        target_dir=seed["target_dir"],
        files_expected=seed["files_expected"],
        files_copied=seed["files_copied"],
        files_verified=seed["files_verified"],
        bytes_expected=seed["bytes_expected"],
        bytes_verified=seed["bytes_verified"],
        hash_mismatches=seed["hash_mismatches"],
        missing_files=seed["missing_files"],
        extra_files=seed["extra_files"],
        verification_status=seed["verification_status"],
        reproducibility_hash=canonical_export_hash(seed),
    )


def copy_bundle(bundle_id: str, source_dir: Path | str, target_dir: Path | str) -> CopyProof:
    source = Path(source_dir)
    target = Path(target_dir)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return verify_copied_bundle(bundle_id, source, target)


def first_available_shared_target(bundle_id: str) -> Path | None:
    candidates = [
        Path("Z:/") / bundle_id,
        Path("//FRANKENSTEIN/Shared Folder") / bundle_id,
    ]
    for candidate in candidates:
        if candidate.parent.exists():
            return candidate
    return None
