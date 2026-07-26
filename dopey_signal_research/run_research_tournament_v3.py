"""CLI runner for research tournament V3."""
from __future__ import annotations

import json

from dopey_signal_research.research_tournament_v3 import run_research_tournament_v3


def main() -> int:
    summary = run_research_tournament_v3()
    print(
        json.dumps(
            {
                "research_tournament_v3_status": summary["research_tournament_v3_status"],
                "improved_vs_v2_count": summary.get("improved_vs_v2_count", 0),
                "top_profit_factor": summary.get("top_profit_factor", 0.0),
                "summary_path": summary["artifact_paths"]["research_tournament_v3_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
