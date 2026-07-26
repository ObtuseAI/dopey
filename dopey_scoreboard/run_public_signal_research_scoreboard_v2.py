"""CLI runner for public signal research scoreboard V2."""
from __future__ import annotations

import json

from .public_signal_research_scoreboard_v2 import run_public_signal_research_scoreboard_v2


def main() -> int:
    summary = run_public_signal_research_scoreboard_v2()
    print(json.dumps({
        "scoreboard_status": summary["scoreboard_status"],
        "v2_symbol_count": summary.get("v2_symbol_count", 0),
        "mutation_queue_count": summary.get("mutation_queue_count", 0),
        "summary_path": summary["artifact_paths"]["public_signal_research_scoreboard_v2"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
