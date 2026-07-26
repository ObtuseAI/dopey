"""CLI runner for public champion hardening live gate status V3."""
from __future__ import annotations

import json

from dopey_live_gate.public_champion_hardening_live_gate_status_v3 import run_public_champion_hardening_live_gate_status_v3


def main() -> int:
    summary = run_public_champion_hardening_live_gate_status_v3()
    print(json.dumps({
        "live_gate_status": summary["live_gate_status"],
        "hardened_public_paper_champion_count": summary["hardened_public_paper_champion_count"],
        "conditional_public_paper_champion_count": summary["conditional_public_paper_champion_count"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "official_robinhood_market_data_allowed": summary["official_robinhood_market_data_allowed"],
        "summary_path": summary["artifact_paths"]["public_champion_hardening_live_gate_status_v3"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
