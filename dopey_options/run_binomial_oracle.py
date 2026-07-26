"""Run the deterministic DOPEY CRR binomial validation oracle."""
from __future__ import annotations

import json
from pathlib import Path

from .binomial_oracle import run_binomial_oracle_validation


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    result = run_binomial_oracle_validation(
        REPOSITORY_ROOT / "artifacts" / "dopey" / "options_oracle" / "binomial_oracle_validation.json"
    )
    print(json.dumps({
        "validation_status": result["validation_status"],
        "test_count": result["test_count"],
        "passed_test_count": result["passed_test_count"],
        "failed_test_count": result["failed_test_count"],
        "pricing_source_tier": result["pricing_source_tier"],
        "paper_only": result["paper_only"],
        "live_blocked": result["live_blocked"],
    }, indent=2, sort_keys=True))
    return 0 if result["validation_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
