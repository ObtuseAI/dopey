"""CLI for the deterministic DOPEY stronger walk-forward consistency runner.

Usage:
    python -m dopey_walk_forward.run_stronger_walk_forward_consistency

Runs the offline deterministic stronger-walk-forward consistency replay and prints a
concise JSON summary. No broker connection, no credentials, no live order placement,
no network. Paper-only, fixture-based, live-blocked.
"""
from __future__ import annotations

import json

from .consistency_runner import run_stronger_walk_forward_consistency


def main() -> int:
    summary = run_stronger_walk_forward_consistency()
    concise = {
        "consistency_status": summary["consistency_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "windows_loaded": summary["windows_loaded"],
        "splits_built": summary["splits_built"],
        "strategies_evaluated": summary["strategies_evaluated"],
        "families_evaluated": summary["families_evaluated"],
        "top_consistent_strategy": summary["top_consistent_strategy"],
        "top_consistent_family": summary["top_consistent_family"],
        "holdout_failures": summary["holdout_failures"],
        "overfit_warnings": summary["overfit_warnings"],
        "strong_consistency_count": summary["strong_consistency_count"],
        "live_blocked": summary["live_blocked"],
        "registry_path": summary["registry_path"],
        "proof_record_path": summary["proof_record_path"],
        "summary_path": summary["summary_path"],
        "consistency_replay_path": summary["consistency_replay_path"],
        "consistency_holdout_path": summary["consistency_holdout_path"],
        "family_profile_path": summary["family_profile_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["consistency_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
