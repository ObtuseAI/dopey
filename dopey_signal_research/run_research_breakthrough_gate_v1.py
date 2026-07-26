"""CLI runner for research breakthrough gate V1."""
from __future__ import annotations

import json

from .research_breakthrough_gate_v1 import run_research_breakthrough_gate_v1


def main() -> int:
    summary = run_research_breakthrough_gate_v1()
    print(json.dumps({
        "research_breakthrough_gate_status": summary["research_breakthrough_gate_status"],
        "breakthrough_candidate_count": summary["breakthrough_candidate_count"],
        "watchlist_count": summary["watchlist_count"],
        "summary_path": summary["artifact_paths"]["research_breakthrough_gate_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
