"""CLI for the DOPEY static tournament performance reporting dashboard bundle."""
from __future__ import annotations

import json

from .reporting_bundle import run_tournament_performance_reporting_bundle


def main() -> int:
    summary = run_tournament_performance_reporting_bundle()
    concise = {
        "reporting_bundle_status": summary["reporting_bundle_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "strategies_reported": summary["strategies_reported"],
        "families_reported": summary["families_reported"],
        "scenarios_reported": summary["scenarios_reported"],
        "attribution_records": summary["attribution_records"],
        "dashboard_artifacts_written": summary["dashboard_artifacts_written"],
        "top_strategy": summary["top_strategy"],
        "top_family": summary["top_family"],
        "audit_status": summary["audit_status"],
        "live_blocked": summary["live_blocked"],
        "dashboard_index_path": summary["dashboard_index_path"],
        "proof_record_path": summary["proof_record_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["reporting_bundle_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
