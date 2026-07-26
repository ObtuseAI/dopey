"""CLI runner for research mutation queue V1."""
from __future__ import annotations

import json

from .research_mutation_queue_v1 import run_research_mutation_queue_v1


def main() -> int:
    summary = run_research_mutation_queue_v1()
    print(json.dumps({
        "research_mutation_queue_status": summary["research_mutation_queue_status"],
        "mutation_queue_count": summary["mutation_queue_count"],
        "summary_path": summary["artifact_paths"]["research_mutation_queue_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
