"""CLI runner for V4 preflight."""
from __future__ import annotations

import json

from dopey_validation.public_signal_research_v4_preflight import run_public_signal_research_v4_preflight


def main() -> int:
    summary = run_public_signal_research_v4_preflight()
    print(
        json.dumps(
            {
                "public_signal_research_v4_preflight_status": summary["public_signal_research_v4_preflight_status"],
                "v3_mutation_queue_count": summary.get("v3_mutation_queue_count", 0),
                "v3_top_profit_factor": summary.get("v3_top_profit_factor", 0.0),
                "summary_path": summary["artifact_paths"]["public_signal_research_v4_preflight_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
