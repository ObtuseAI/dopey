"""CLI runner for research tournament V4."""
from __future__ import annotations

import json

from dopey_signal_research.research_tournament_v4 import run_research_tournament_v4


def main() -> int:
    summary = run_research_tournament_v4()
    print(
        json.dumps(
            {
                "research_tournament_v4_status": summary["research_tournament_v4_status"],
                "improved_vs_v3_count": summary.get("improved_vs_v3_count", 0),
                "top_profit_factor": summary.get("top_profit_factor", 0.0),
                "summary_path": summary["artifact_paths"]["research_tournament_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
