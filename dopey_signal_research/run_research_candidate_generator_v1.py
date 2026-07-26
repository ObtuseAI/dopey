"""CLI runner for research candidate generator V1."""
from __future__ import annotations

import json

from .research_candidate_generator_v1 import run_research_candidate_generator_v1


def main() -> int:
    summary = run_research_candidate_generator_v1()
    print(json.dumps({
        "research_candidate_generator_status": summary["research_candidate_generator_status"],
        "candidate_count": summary["candidate_count"],
        "family_count": summary["family_count"],
        "summary_path": summary["artifact_paths"]["research_candidate_generator_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
