"""CLI entry point for read-only detector evidence contract hardening."""
from __future__ import annotations

import json

from .read_only_detector_evidence_validator import validate_read_only_detector_post_run_evidence_contract


def main() -> int:
    result = validate_read_only_detector_post_run_evidence_contract()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["evidence_contract_status"] in {"evidence_contract_complete", "evidence_contract_manual_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
