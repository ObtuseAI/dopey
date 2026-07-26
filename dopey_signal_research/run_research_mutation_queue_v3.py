"""CLI runner for research mutation queue V3."""
from __future__ import annotations

import json

from dopey_signal_research.research_mutation_queue_v3 import run_research_mutation_queue_v3


def main() -> int:
    summary = run_research_mutation_queue_v3()
    print(
        json.dumps(
            {
                "research_mutation_queue_v3_status": summary["research_mutation_queue_v3_status"],
                "mutation_queue_count": summary.get("mutation_queue_count", 0),
                "summary_path": summary["artifact_paths"]["research_mutation_queue_v3_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
