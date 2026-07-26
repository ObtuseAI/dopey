"""CLI writer for the operator OHLCV source-review contract."""
from __future__ import annotations

import json

from .operator_ohlcv_source_review_contract import SOURCE_REVIEW_STATUS_PATH, write_operator_source_review_contract


def run_operator_ohlcv_source_review_contract() -> dict:
    return write_operator_source_review_contract()


def main() -> int:
    result = run_operator_ohlcv_source_review_contract()
    print(json.dumps({
        "operator_source_review_status": result["status"],
        "source_review_valid": result["source_review_valid"],
        "evidence_allowed": result["evidence_allowed"],
        "status_path": str(SOURCE_REVIEW_STATUS_PATH),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
