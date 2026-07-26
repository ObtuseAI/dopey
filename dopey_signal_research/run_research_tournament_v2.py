"""CLI runner for research tournament V2."""
from __future__ import annotations

import json

from .research_tournament_v2 import run_research_tournament_v2


def main() -> int:
    summary = run_research_tournament_v2()
    print(json.dumps({
        "research_tournament_v2_status": summary["research_tournament_v2_status"],
        "family_count": summary["family_count"],
        "top_family": summary.get("top_family", ""),
        "top_symbol_count": summary.get("top_symbol_count", 0),
        "summary_path": summary["artifact_paths"]["research_tournament_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
