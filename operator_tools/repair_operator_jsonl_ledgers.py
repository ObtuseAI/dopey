"""Normalize legacy one-record-array JSONL lines without losing evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from dopey_research_pipeline.artifact_io import write_json_atomic, write_jsonl_atomic


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
TARGET_PATHS: Final[tuple[Path, ...]] = (
    REPO_ROOT / "artifacts" / "dopey" / "nightly" / "nightly_ledger.jsonl",
    REPO_ROOT / "artifacts" / "dopey" / "soak" / "soak_log.jsonl",
)
PROOF_PATH: Final[Path] = (
    REPO_ROOT / "artifacts" / "dopey" / "observability" / "operator_jsonl_normalization_proof.json"
)
NORMALIZATION_VERSION: Final[str] = "dopey-operator-jsonl-normalization-v1"


def normalize_jsonl_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    records: list[dict[str, Any]] = []
    legacy_wrapper_count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, list):
            if len(value) != 1 or not isinstance(value[0], dict):
                raise TypeError(
                    f"operator JSONL legacy line must contain exactly one object: path={path}, line={line_number}"
                )
            value = value[0]
            legacy_wrapper_count += 1
        if not isinstance(value, dict):
            raise TypeError(f"operator JSONL line must be an object: path={path}, line={line_number}")
        records.append(value)
    return records, legacy_wrapper_count


def _record_sequence_hash(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def repair_operator_jsonl_ledgers(paths: tuple[Path, ...], proof_path: Path) -> dict[str, Any]:
    repairs: list[dict[str, Any]] = []
    for path in paths:
        before_bytes = path.read_bytes() if path.exists() else b""
        records, wrapper_count = normalize_jsonl_records(path)
        record_sequence_hash = _record_sequence_hash(records)
        if wrapper_count:
            write_jsonl_atomic(path, records, keep_backup=True)
        after_records, remaining_wrapper_count = normalize_jsonl_records(path)
        if after_records != records or remaining_wrapper_count:
            raise RuntimeError(
                f"operator JSONL normalization verification failed: path={path}, "
                f"remaining_wrappers={remaining_wrapper_count}"
            )
        repairs.append(
            {
                "path": str(path),
                "path_status": "normalized" if wrapper_count else "already_normalized_or_missing",
                "record_count": len(records),
                "legacy_wrapper_count_removed": wrapper_count,
                "before_sha256": hashlib.sha256(before_bytes).hexdigest(),
                "after_sha256": hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest(),
                "record_sequence_hash": record_sequence_hash,
                "backup_path": str(path.with_name(path.name + ".bak")) if wrapper_count else "",
                "records_deleted": 0,
                "records_reordered": False,
            }
        )
    proof: dict[str, Any] = {
        "artifact_type": "operator_jsonl_normalization_proof",
        "normalization_version": NORMALIZATION_VERSION,
        "repair_count": sum(record["path_status"] == "normalized" for record in repairs),
        "records_deleted": 0,
        "records_reordered": False,
        "repairs": repairs,
    }
    write_json_atomic(proof_path, proof)
    return proof


def main() -> int:
    print(json.dumps(repair_operator_jsonl_ledgers(TARGET_PATHS, PROOF_PATH), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
