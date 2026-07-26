"""CLI runner for research candidate generator V3."""
from __future__ import annotations

import json

from dopey_signal_research.research_candidate_generator_v3 import run_research_candidate_generator_v3


def main() -> int:
    summary = run_research_candidate_generator_v3()
    print(
        json.dumps(
            {
                "research_candidate_generator_v3_status": summary["research_candidate_generator_v3_status"],
                "candidate_count": summary["candidate_count"],
                "continuation_candidate_count": summary.get("continuation_candidate_count", 0),
                "volume_candidate_count": summary.get("volume_candidate_count", 0),
                "summary_path": summary["artifact_paths"]["research_candidate_generator_v3_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
