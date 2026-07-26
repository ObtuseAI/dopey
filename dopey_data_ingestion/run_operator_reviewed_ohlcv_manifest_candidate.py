"""CLI writer for operator-reviewed OHLCV manifest candidates."""
from __future__ import annotations

import json

from .operator_reviewed_ohlcv_manifest_candidate import build_operator_reviewed_manifest_candidate


def run_operator_reviewed_ohlcv_manifest_candidate() -> dict:
    return build_operator_reviewed_manifest_candidate()


def main() -> int:
    result = run_operator_reviewed_ohlcv_manifest_candidate()
    print(json.dumps({
        "manifest_candidate_status": result["manifest_candidate_status"],
        "staged_file_count": result["staged_file_count"],
        "candidate_manifest_is_evidence": result["candidate_manifest_is_evidence"],
        "manifest_candidate_path": result["manifest_candidate_path"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
