"""CLI for the deterministic DOPEY failure-mode feedback optimizer."""
from __future__ import annotations

import json

from .feedback_optimizer import run_failure_feedback_optimizer


def main() -> int:
    summary = run_failure_feedback_optimizer()
    concise = {
        "optimizer_status": summary["optimizer_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "feedback_run_id": summary["feedback_run_id"],
        "families_analyzed": summary["families_analyzed"],
        "failure_modes_loaded": summary["failure_modes_loaded"],
        "recommendations_generated": summary["recommendations_generated"],
        "recommendations_accepted": summary["recommendations_accepted"],
        "recommendations_rejected": summary["recommendations_rejected"],
        "feedback_mutations_generated": summary["feedback_mutations_generated"],
        "feedback_mutations_valid": summary["feedback_mutations_valid"],
        "best_previous_mutation": summary["best_previous_mutation"],
        "best_feedback_mutation": summary["best_feedback_mutation"],
        "score_delta": summary["score_delta"],
        "overfit_delta": summary["overfit_delta"],
        "live_blocked": summary["live_blocked"],
        "feedback_registry_path": summary["feedback_registry_path"],
        "proof_record_path": summary["proof_record_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["optimizer_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
