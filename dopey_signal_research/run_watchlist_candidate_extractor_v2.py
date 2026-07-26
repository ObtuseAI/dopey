"""CLI runner for watchlist candidate extractor V2."""
from __future__ import annotations

import json

from .watchlist_candidate_extractor_v2 import run_watchlist_candidate_extractor_v2


def main() -> int:
    summary = run_watchlist_candidate_extractor_v2()
    print(json.dumps({
        "watchlist_extractor_status": summary["watchlist_extractor_status"],
        "watchlist_candidate_count": summary["watchlist_candidate_count"],
        "generic_label_repair_count": summary["generic_label_repair_count"],
        "summary_path": summary["artifact_paths"]["watchlist_candidate_extractor_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
