"""CLI runner for public signal research preflight V1."""
from __future__ import annotations

import json

from .public_signal_research_preflight_v1 import run_public_signal_research_preflight_v1


def main() -> int:
    summary = run_public_signal_research_preflight_v1()
    print(json.dumps({
        "public_signal_research_preflight_status": summary["public_signal_research_preflight_status"],
        "prior_repair_status": summary.get("prior_repair_status", ""),
        "active_fixture_symbol_count": summary.get("active_fixture_symbol_count", 0),
        "summary_path": summary["artifact_paths"]["public_signal_research_preflight_v1_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
