"""CLI runner for research breakthrough gate V2."""
from __future__ import annotations

import json

from .research_breakthrough_gate_v2 import run_research_breakthrough_gate_v2


def main() -> int:
    summary = run_research_breakthrough_gate_v2()
    print(json.dumps({
        "research_breakthrough_gate_v2_status": summary["research_breakthrough_gate_v2_status"],
        "breakthrough_candidate_count": summary["breakthrough_candidate_count"],
        "watchlist_count": summary["watchlist_count"],
        "watchlist_mutation_required": summary.get("watchlist_mutation_required", False),
        "summary_path": summary["artifact_paths"]["research_breakthrough_gate_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
