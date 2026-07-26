"""CLI runner for the autonomous admissibility kernel."""
from __future__ import annotations

import json

from .autonomous_admissibility_kernel import run_autonomous_admissibility_kernel


def main() -> int:
    result = run_autonomous_admissibility_kernel()
    print(json.dumps({
        "accepted_count": result["accepted_count"],
        "rejected_count": result["rejected_count"],
        "quarantined_count": result["quarantined_count"],
        "terminal_block_count": result["terminal_block_count"],
        "summary_path": result["artifact_paths"]["autonomous_admissibility_kernel_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

