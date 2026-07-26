"""Dopey tournament runner entry point.

Usage:
    python -m dopey_tournament.run_fixture_tournament

Runs the full offline deterministic multi-strategy paper tournament and prints a concise JSON
summary. No broker connection, no credentials, no live order placement, no network.
"""
from __future__ import annotations

import json

from .runner import run_fixture_tournament


def main() -> int:
    summary = run_fixture_tournament()
    concise = {
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "tournament_status": summary["tournament_status"],
        "champion_strategy_id": summary["champion_strategy_id"],
        "runner_up_strategy_id": summary["runner_up_strategy_id"],
        "windows_replayed": summary["windows_replayed"],
        "strategies_evaluated": summary["strategies_evaluated"],
        "champion_registry_path": summary["champion_registry_path"],
        "proof_record_path": summary["proof_record_path"],
        "live_blocked": summary["live_blocked"],
        "promotion_decisions": summary["promotion_decisions"],
        "overfit_summary": summary["overfit_summary"],
        "family_scorecard": summary["family_scorecard"],
        "reproducibility_hash": summary["reproducibility_hash"],
    }
    print(json.dumps(concise, indent=2))
    return 0 if summary["tournament_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
