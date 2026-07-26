"""CLI runner for research tournament V1."""
from __future__ import annotations

import json

from .research_tournament_v1 import run_research_tournament_v1


def main() -> int:
    summary = run_research_tournament_v1()
    print(json.dumps({
        "research_tournament_status": summary["research_tournament_status"],
        "family_count": summary["family_count"],
        "candidate_breakthrough_count": summary["candidate_breakthrough_count"],
        "top_family": summary.get("top_family", ""),
        "summary_path": summary["artifact_paths"]["research_tournament_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
