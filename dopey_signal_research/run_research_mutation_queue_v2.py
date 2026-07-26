"""CLI runner for research mutation queue V2."""
from __future__ import annotations

import json

from .research_mutation_queue_v2 import run_research_mutation_queue_v2


def main() -> int:
    summary = run_research_mutation_queue_v2()
    print(json.dumps({
        "research_mutation_queue_v2_status": summary["research_mutation_queue_v2_status"],
        "mutation_queue_count": summary["mutation_queue_count"],
        "summary_path": summary["artifact_paths"]["research_mutation_queue_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
