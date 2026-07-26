"""Dopey paper research pipeline runner.

Usage:
    python -m dopey_research_pipeline.run_fixture_pipeline

Runs the full offline deterministic paper-only pipeline and prints a concise JSON summary.
No broker connection, no credentials, no live order placement.
"""
from __future__ import annotations

import json

from .pipeline import run_pipeline


def main() -> int:
    summary = run_pipeline()
    concise = {
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "pipeline_status": summary["pipeline_status"],
        "strategy_id": summary["strategy_id"],
        "execution_intent_id": summary["execution_intent_id"],
        "paper_order_id": summary["paper_order_id"],
        "proof_record_path": summary["proof_record_path"],
        "live_blocked": summary["live_blocked"],
        "promotion_decision": summary["promotion_decision"]["decision"],
        "aggression_score": summary["aggression_score"],
        "validation_valid": summary["validation_verdict"]["valid"],
        "paper_fill_ok": summary["paper_fill"]["ok"],
        "simulated_fill_price": summary["paper_fill"]["simulated_fill_price"],
        "simulated_slippage": summary["paper_fill"]["simulated_slippage"],
    }
    print(json.dumps(concise, indent=2))
    return 0 if summary["pipeline_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
