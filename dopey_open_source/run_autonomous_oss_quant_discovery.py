"""CLI runner for autonomous OSS quant discovery."""
from __future__ import annotations

import json

from .autonomous_oss_quant_discovery import run_autonomous_oss_quant_discovery


def main() -> int:
    result = run_autonomous_oss_quant_discovery()
    print(json.dumps({
        "open_source_candidate_count": result["open_source_candidate_count"],
        "open_source_accepted_count": result["open_source_accepted_count"],
        "reference_only_count": result["reference_only_count"],
        "summary_path": result["artifact_paths"]["autonomous_oss_discovery_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

