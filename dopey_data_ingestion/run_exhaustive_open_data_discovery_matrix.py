"""CLI runner for exhaustive open-data discovery matrix."""
from __future__ import annotations

import json

from .exhaustive_open_data_discovery_matrix import run_exhaustive_open_data_discovery_matrix


def main() -> int:
    result = run_exhaustive_open_data_discovery_matrix()
    print(json.dumps({
        "total_candidates_discovered": result["total_candidates_discovered"],
        "accepted_ohlcv_candidate_count": result["accepted_ohlcv_candidate_count"],
        "accepted_options_candidate_count": result["accepted_options_candidate_count"],
        "rejected_count": result["rejected_count"],
        "summary_path": result["artifact_paths"]["exhaustive_open_data_discovery_matrix_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

