"""CLI runner for research mutation queue V4."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_queue_v4 import run_research_mutation_queue_v4


def main() -> int:
    summary = run_research_mutation_queue_v4()
    print(
        json.dumps(
            {
                "research_mutation_queue_v4_status": summary["research_mutation_queue_v4_status"],
                "mutation_queue_count": summary.get("mutation_queue_count", 0),
                "summary_path": summary["artifact_paths"]["research_mutation_queue_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
