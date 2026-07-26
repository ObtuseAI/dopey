"""CLI runner for research candidate generator V2."""
from __future__ import annotations

import json

from .research_candidate_generator_v2 import run_research_candidate_generator_v2


def main() -> int:
    summary = run_research_candidate_generator_v2()
    print(json.dumps({
        "research_candidate_generator_v2_status": summary["research_candidate_generator_v2_status"],
        "candidate_count": summary["candidate_count"],
        "symbol_count": summary["symbol_count"],
        "sector_count": summary["sector_count"],
        "summary_path": summary["artifact_paths"]["research_candidate_generator_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
