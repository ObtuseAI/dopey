"""CLI runner for discovery signal family generator V1."""
from __future__ import annotations

import json

from .discovery_signal_family_generator_v1 import run_discovery_signal_family_generator_v1


def main() -> int:
    summary = run_discovery_signal_family_generator_v1()
    print(json.dumps({
        "discovery_signal_family_status": summary["discovery_signal_family_status"],
        "candidate_family_count": summary["candidate_family_count"],
        "new_family_count": summary["new_family_count"],
        "summary_path": summary["artifact_paths"]["discovery_signal_family_generator_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
