"""CLI runner for research breakthrough gate V4."""
from __future__ import annotations

import json

from dopey_signal_research.research_breakthrough_gate_v4 import run_research_breakthrough_gate_v4


def main() -> int:
    summary = run_research_breakthrough_gate_v4()
    print(
        json.dumps(
            {
                "research_breakthrough_gate_v4_status": summary["research_breakthrough_gate_v4_status"],
                "breakthrough_candidate_count": summary.get("breakthrough_candidate_count", 0),
                "watchlist_count": summary.get("watchlist_count", 0),
                "summary_path": summary["artifact_paths"]["research_breakthrough_gate_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
