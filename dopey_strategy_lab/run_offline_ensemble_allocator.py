"""CLI for the deterministic DOPEY offline ensemble strategy allocator."""
from __future__ import annotations

import json

from .ensemble_allocator import run_offline_ensemble_allocator


def main() -> int:
    summary = run_offline_ensemble_allocator()
    concise = {
        "allocator_status": summary["allocator_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "candidates_loaded": summary["candidates_loaded"],
        "families_allocated": summary["families_allocated"],
        "top_strategy": summary["top_strategy"],
        "top_family": summary["top_family"],
        "single_champion_score": summary["single_champion_score"],
        "equal_weight_score": summary["equal_weight_score"],
        "allocator_weighted_score": summary["allocator_weighted_score"],
        "overfit_adjusted_score": summary["overfit_adjusted_score"],
        "best_ensemble_variant": summary["best_ensemble_variant"],
        "weights_sum": summary["weights_sum"],
        "live_blocked": summary["live_blocked"],
        "ensemble_registry_path": summary["ensemble_registry_path"],
        "proof_record_path": summary["proof_record_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["allocator_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
