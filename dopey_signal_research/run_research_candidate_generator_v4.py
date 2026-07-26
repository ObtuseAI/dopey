"""CLI runner for V4 candidate generator."""
from __future__ import annotations

import json

from dopey_signal_research.research_candidate_generator_v4 import run_research_candidate_generator_v4


def main() -> int:
    summary = run_research_candidate_generator_v4()
    print(
        json.dumps(
            {
                "research_candidate_generator_v4_status": summary["research_candidate_generator_v4_status"],
                "candidate_count": summary["candidate_count"],
                "subfamily_count": summary["subfamily_count"],
                "summary_path": summary["artifact_paths"]["research_candidate_generator_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
