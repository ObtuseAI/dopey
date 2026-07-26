"""Deterministic, path-contained shard plans for DOPEY's curated CI suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import TypedDict


CI_SHARD_PLAN_VERSION = "dopey-ci-shard-plan-v1"
ASSIGNMENT_BASIS = "sha256_path_modulo_shard_count"


class CiShard(TypedDict):
    shard_number: int
    test_files: list[str]


class CiShardPlan(TypedDict):
    plan_version: str
    assignment_basis: str
    manifest_path: str
    manifest_sha256: str
    plan_sha256: str
    shard_count: int
    test_file_count: int
    shards: list[CiShard]


def _canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _resolve_within_repository(repository_root: Path, path: Path) -> Path:
    root = repository_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PermissionError(
            "CI shard input resolves outside the repository: "
            f"repository_root={root}, path={path}, resolved={resolved}"
        ) from error
    return resolved


def _validate_manifest_entry(entry: str) -> str:
    if entry != entry.strip():
        raise ValueError(
            f"CI manifest entry has surrounding whitespace: entry={entry!r}"
        )
    if "\\" in entry:
        raise ValueError(
            f"CI manifest entry must use POSIX separators: entry={entry!r}"
        )
    path = PurePosixPath(entry)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise ValueError(
            f"CI manifest entry is not a contained relative path: entry={entry!r}"
        )
    if len(path.parts) != 2 or path.parts[0] != "tests":
        raise ValueError(
            f"CI manifest entry must be a direct tests/ file: entry={entry!r}"
        )
    if not path.name.startswith("test_") or path.suffix != ".py":
        raise ValueError(f"CI manifest entry is not a pytest file: entry={entry!r}")
    return path.as_posix()


def load_ci_test_manifest(
    repository_root: Path, manifest_path: Path
) -> tuple[str, ...]:
    root = repository_root.resolve(strict=True)
    resolved_manifest = _resolve_within_repository(root, manifest_path)
    entries: list[str] = []
    for line_number, raw_line in enumerate(
        resolved_manifest.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            entry = _validate_manifest_entry(raw_line)
        except ValueError as error:
            raise ValueError(
                f"invalid CI manifest entry: manifest={resolved_manifest}, line={line_number}, error={error}"
            ) from error
        entries.append(entry)
    if not entries:
        raise ValueError(f"CI test manifest is empty: manifest={resolved_manifest}")
    duplicate_entries = sorted(
        entry for entry in set(entries) if entries.count(entry) > 1
    )
    if duplicate_entries:
        raise ValueError(
            "CI test manifest contains duplicate entries: "
            f"manifest={resolved_manifest}, duplicates={duplicate_entries}"
        )
    canonical_entries = tuple(sorted(entries))
    for entry in canonical_entries:
        resolved_test = _resolve_within_repository(root, Path(entry))
        if not resolved_test.is_file():
            raise FileNotFoundError(
                f"CI manifest entry is not a file: manifest={resolved_manifest}, entry={entry}"
            )
    return canonical_entries


def _assignment_index(test_file: str, shard_count: int) -> int:
    digest = hashlib.sha256(test_file.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) % shard_count


def build_ci_shard_plan(
    repository_root: Path,
    manifest_path: Path,
    shard_count: int,
) -> CiShardPlan:
    if shard_count <= 0:
        raise ValueError(f"CI shard count must be positive: shard_count={shard_count}")
    root = repository_root.resolve(strict=True)
    resolved_manifest = _resolve_within_repository(root, manifest_path)
    test_files = load_ci_test_manifest(root, resolved_manifest)
    if shard_count > len(test_files):
        raise ValueError(
            "CI shard count cannot exceed test-file count: "
            f"shard_count={shard_count}, test_file_count={len(test_files)}"
        )
    members: list[list[str]] = [[] for _ in range(shard_count)]
    for test_file in test_files:
        members[_assignment_index(test_file, shard_count)].append(test_file)
    shards: list[CiShard] = [
        {
            "shard_number": index + 1,
            "test_files": sorted(shard_members),
        }
        for index, shard_members in enumerate(members)
    ]
    manifest_bytes = ("\n".join(test_files) + "\n").encode("utf-8")
    plan_body: dict[str, object] = {
        "plan_version": CI_SHARD_PLAN_VERSION,
        "assignment_basis": ASSIGNMENT_BASIS,
        "manifest_path": resolved_manifest.relative_to(root).as_posix(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "shard_count": shard_count,
        "test_file_count": len(test_files),
        "shards": shards,
    }
    plan_sha256 = hashlib.sha256(_canonical_json(plan_body)).hexdigest()
    plan: CiShardPlan = {
        "plan_version": CI_SHARD_PLAN_VERSION,
        "assignment_basis": ASSIGNMENT_BASIS,
        "manifest_path": resolved_manifest.relative_to(root).as_posix(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "plan_sha256": plan_sha256,
        "shard_count": shard_count,
        "test_file_count": len(test_files),
        "shards": shards,
    }
    validate_ci_shard_plan(plan)
    return plan


def validate_ci_shard_plan(plan: CiShardPlan) -> None:
    shard_count = plan["shard_count"]
    shards = plan["shards"]
    if plan["plan_version"] != CI_SHARD_PLAN_VERSION:
        raise ValueError(
            "CI shard plan version mismatch: "
            f"expected={CI_SHARD_PLAN_VERSION}, observed={plan['plan_version']}"
        )
    if plan["assignment_basis"] != ASSIGNMENT_BASIS:
        raise ValueError(
            "CI shard assignment basis mismatch: "
            f"expected={ASSIGNMENT_BASIS}, observed={plan['assignment_basis']}"
        )
    if len(shards) != shard_count:
        raise ValueError(
            "CI shard plan has the wrong shard count: "
            f"expected={shard_count}, observed={len(shards)}"
        )
    observed_numbers = [shard["shard_number"] for shard in shards]
    expected_numbers = list(range(1, shard_count + 1))
    if observed_numbers != expected_numbers:
        raise ValueError(
            "CI shard numbers are not contiguous: "
            f"expected={expected_numbers}, observed={observed_numbers}"
        )
    empty_shards = [
        shard["shard_number"] for shard in shards if not shard["test_files"]
    ]
    if empty_shards:
        raise ValueError(f"CI shard plan contains empty shards: shards={empty_shards}")
    flattened = [test_file for shard in shards for test_file in shard["test_files"]]
    if len(flattened) != plan["test_file_count"]:
        raise ValueError(
            "CI shard plan does not cover the declared file count: "
            f"declared={plan['test_file_count']}, observed={len(flattened)}"
        )
    duplicate_files = sorted(
        test_file for test_file in set(flattened) if flattened.count(test_file) > 1
    )
    if duplicate_files:
        raise ValueError(
            f"CI shard plan assigns files more than once: duplicates={duplicate_files}"
        )
    for shard in shards:
        if shard["test_files"] != sorted(shard["test_files"]):
            raise ValueError(
                "CI shard membership must be sorted: "
                f"shard_number={shard['shard_number']}"
            )
        for test_file in shard["test_files"]:
            _validate_manifest_entry(test_file)
            expected_shard = _assignment_index(test_file, shard_count) + 1
            if shard["shard_number"] != expected_shard:
                raise ValueError(
                    "CI shard membership violates the content-addressed assignment: "
                    f"test_file={test_file}, expected_shard={expected_shard}, "
                    f"observed_shard={shard['shard_number']}"
                )
    plan_body: dict[str, object] = {
        "plan_version": plan["plan_version"],
        "assignment_basis": plan["assignment_basis"],
        "manifest_path": plan["manifest_path"],
        "manifest_sha256": plan["manifest_sha256"],
        "shard_count": plan["shard_count"],
        "test_file_count": plan["test_file_count"],
        "shards": plan["shards"],
    }
    expected_plan_hash = hashlib.sha256(_canonical_json(plan_body)).hexdigest()
    if plan["plan_sha256"] != expected_plan_hash:
        raise ValueError(
            "CI shard plan content hash mismatch: "
            f"expected={expected_plan_hash}, observed={plan['plan_sha256']}"
        )


def select_ci_shard(plan: CiShardPlan, shard_number: int) -> tuple[str, ...]:
    validate_ci_shard_plan(plan)
    if shard_number <= 0 or shard_number > plan["shard_count"]:
        raise ValueError(
            "CI shard number is outside the plan: "
            f"shard_number={shard_number}, shard_count={plan['shard_count']}"
        )
    return tuple(plan["shards"][shard_number - 1]["test_files"])


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or select from DOPEY's deterministic CI shard plan."
    )
    parser.add_argument("command", choices=("plan", "select"))
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--shards", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard", type=int)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    plan = build_ci_shard_plan(
        arguments.repository_root,
        arguments.manifest,
        arguments.shards,
    )
    if arguments.command == "plan":
        text = json.dumps(plan, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    else:
        if arguments.shard is None:
            raise ValueError("--shard is required for the select command")
        selected = select_ci_shard(plan, arguments.shard)
        text = "\n".join(selected) + "\n"
    _write_text_atomic(arguments.output, text)
    print(
        json.dumps(
            {
                "command": arguments.command,
                "manifest_sha256": plan["manifest_sha256"],
                "plan_sha256": plan["plan_sha256"],
                "shard_count": plan["shard_count"],
                "test_file_count": plan["test_file_count"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
