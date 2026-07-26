"""CLI for the DOPEY larger regime/holdout corpus v2 runner.

Usage:
    python -m dopey_walk_forward.run_regime_holdout_corpus_v2

Runs the offline deterministic corpus v2 replay + v1-vs-v2 consistency comparison and prints
a concise JSON summary. No broker connection, no credentials, no live order placement,
no network. Paper-only, fixture-based, live-blocked.
"""
from __future__ import annotations

import json

from .regime_holdout_runner import run_regime_holdout_corpus_v2


def main() -> int:
    summary = run_regime_holdout_corpus_v2()
    concise = {
        "corpus_v2_status": summary["corpus_v2_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "total_windows": summary["total_windows"],
        "new_windows_added": summary["new_windows_added"],
        "splits_built": summary["splits_built"],
        "strategies_evaluated": summary["strategies_evaluated"],
        "families_evaluated": summary["families_evaluated"],
        "top_consistent_strategy_v2": summary["top_consistent_strategy_v2"],
        "top_consistent_family_v2": summary["top_consistent_family_v2"],
        "holdout_failures": summary["holdout_failures"],
        "overfit_warnings": summary["overfit_warnings"],
        "coverage_score": summary["coverage_score"],
        "live_blocked": summary["live_blocked"],
        "registry_path": summary["registry_path"],
        "proof_record_path": summary["proof_record_path"],
        "summary_path": summary["summary_path"],
        "replay_path": summary["replay_path"],
        "coverage_path": summary["coverage_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["corpus_v2_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
