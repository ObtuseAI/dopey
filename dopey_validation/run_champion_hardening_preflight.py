"""CLI runner for champion hardening preflight."""
from __future__ import annotations

import json

from dopey_validation.champion_hardening_preflight import run_champion_hardening_preflight


def main() -> int:
    summary = run_champion_hardening_preflight()
    print(json.dumps({
        "champion_hardening_preflight_status": summary["champion_hardening_preflight_status"],
        "public_paper_champion_count": summary["public_paper_champion_count"],
        "intermediate_simv2_rows": summary["intermediate_simv2_rows"],
        "decision_artifacts_clean": summary["decision_artifacts_clean"],
        "blocker_count": summary["blocker_count"],
        "summary_path": summary["artifact_paths"]["champion_hardening_preflight_summary"],
        "live_trading_enabled": summary["live_trading_enabled"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
