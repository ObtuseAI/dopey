"""Write DOPEY offline history dataset validation artifacts."""
from __future__ import annotations

import json
import sys
from typing import Any, Final

from dopey_research_pipeline.artifact_io import write_json_atomic, write_jsonl_atomic

from .history_store import HISTORY_MANIFEST_PATH, HISTORY_RAW_DIR, REPO_ROOT, load_history_manifest
from .history_validator import validate_history_dataset


HISTORY_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "history"
HISTORY_DATASET_MANIFEST_ARTIFACT_PATH = HISTORY_ARTIFACT_DIR / "history_dataset_manifest.json"
HISTORY_DATASET_VALIDATION_PATH = HISTORY_ARTIFACT_DIR / "history_dataset_validation.json"
HISTORY_SYMBOL_COVERAGE_PATH = HISTORY_ARTIFACT_DIR / "history_symbol_coverage.jsonl"
HISTORY_QUALITY_FLAGS_PATH = HISTORY_ARTIFACT_DIR / "history_quality_flags.jsonl"
HISTORY_LOADER_PROOF_PATH = HISTORY_ARTIFACT_DIR / "history_loader_proof.jsonl"
HISTORY_SPINE_SUMMARY_PATH = HISTORY_ARTIFACT_DIR / "history_spine_summary.json"
MAX_GENERATION_VALIDATION_ATTEMPTS: Final[int] = 2


def run_history_dataset_validation() -> dict[str, Any]:
    result = _validate_and_publish_current_generation()
    return {
        "history_dataset_validation_status": result["dataset_status"],
        "dataset_status": result["dataset_status"],
        "real_local_data_found": result["summary"]["real_local_data_found"],
        "row_count": result["summary"]["row_count"],
        "symbols_covered": result["summary"]["symbols_covered"],
        "date_range": result["summary"]["date_range"],
        "quality_flags": result["summary"]["quality_flags"],
        "artifact_paths": history_dataset_artifact_paths(),
    }


def _validate_and_publish_current_generation() -> dict[str, Any]:
    last_result_hash = ""
    for attempt in range(1, MAX_GENERATION_VALIDATION_ATTEMPTS + 1):
        result = validate_history_dataset(HISTORY_MANIFEST_PATH, HISTORY_RAW_DIR, True)
        result_manifest_hash = str(result["manifest"].get("manifest_reproducibility_hash", ""))
        current_manifest_hash = str(load_history_manifest(HISTORY_MANIFEST_PATH).manifest_reproducibility_hash)
        last_result_hash = result_manifest_hash
        if not result_manifest_hash or result_manifest_hash != current_manifest_hash:
            _warn_generation_changed(attempt, result_manifest_hash, current_manifest_hash, "before_publish")
            continue
        _publish_validation_result(result)
        published_source_hash = str(load_history_manifest(HISTORY_MANIFEST_PATH).manifest_reproducibility_hash)
        if published_source_hash == result_manifest_hash:
            return result
        _warn_generation_changed(attempt, result_manifest_hash, published_source_hash, "after_publish")
    final_hash = str(load_history_manifest(HISTORY_MANIFEST_PATH).manifest_reproducibility_hash)
    raise RuntimeError(
        "history dataset changed during every validation attempt; stale validation was not published: "
        f"attempts={MAX_GENERATION_VALIDATION_ATTEMPTS}, result_manifest_hash={last_result_hash}, "
        f"current_manifest_hash={final_hash}"
    )


def _publish_validation_result(result: dict[str, Any]) -> None:
    HISTORY_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(HISTORY_DATASET_MANIFEST_ARTIFACT_PATH, result["manifest"])
    write_json_atomic(HISTORY_DATASET_VALIDATION_PATH, result["validation"])
    write_jsonl_atomic(HISTORY_SYMBOL_COVERAGE_PATH, result["coverage_records"])
    write_jsonl_atomic(HISTORY_QUALITY_FLAGS_PATH, result["quality_flags"])
    write_jsonl_atomic(HISTORY_LOADER_PROOF_PATH, result["loader_proof"])
    write_json_atomic(HISTORY_SPINE_SUMMARY_PATH, result["summary"])


def _warn_generation_changed(attempt: int, result_hash: str, current_hash: str, phase: str) -> None:
    print(
        json.dumps(
            {
                "warning": "history_generation_changed_during_validation",
                "attempt": attempt,
                "phase": phase,
                "result_manifest_hash": result_hash,
                "current_manifest_hash": current_hash,
                "stale_validation_published": False,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


def history_dataset_artifact_paths() -> dict[str, str]:
    return {
        "history_dataset_manifest": str(HISTORY_DATASET_MANIFEST_ARTIFACT_PATH),
        "history_dataset_validation": str(HISTORY_DATASET_VALIDATION_PATH),
        "history_symbol_coverage": str(HISTORY_SYMBOL_COVERAGE_PATH),
        "history_quality_flags": str(HISTORY_QUALITY_FLAGS_PATH),
        "history_loader_proof": str(HISTORY_LOADER_PROOF_PATH),
        "history_spine_summary": str(HISTORY_SPINE_SUMMARY_PATH),
    }


def main() -> int:
    result = run_history_dataset_validation()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
