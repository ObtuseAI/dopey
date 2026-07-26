"""CLI runner for strategy cohort canonicalizer."""
from __future__ import annotations

import json

from .strategy_id_canonicalizer import run_strategy_id_canonicalizer


def main() -> int:
    summary = run_strategy_id_canonicalizer()
    print(json.dumps({
        "strategy_cohort_status": summary["strategy_cohort_status"],
        "variant_count": summary["variant_count"],
        "micro_cohort_count": summary["micro_cohort_count"],
        "setup_cohort_count": summary["setup_cohort_count"],
        "family_cohort_count": summary["family_cohort_count"],
        "summary_path": summary["artifact_paths"]["strategy_cohort_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
