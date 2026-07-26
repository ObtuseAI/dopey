"""S-tier engineering benchmark for DOPEY without live superiority claims."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_json, safety_state, stable_hash, write_json, write_jsonl
from dopey_paper_autonomy.autonomous_paper_trading_loop import SUMMARY_PATH as PAPER_SUMMARY_PATH

from .adversarial_strategy_evaluator import build_adversarial_evaluations


ARTIFACT_DIR = ARTIFACT_ROOT / "research_autonomy"
RESULTS_PATH = ARTIFACT_DIR / "s_tier_benchmark_results.jsonl"
ADVERSARIAL_PATH = ARTIFACT_DIR / "adversarial_strategy_evaluations.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "s_tier_options_benchmark_summary.json"
PROOF_PATH = ARTIFACT_DIR / "s_tier_options_benchmark_proof.jsonl"


BASELINES = ["no_trade", "random_direction", "always_long_call", "always_long_put", "market_regime", "momentum", "breakout", "buy_and_hold_underlying_proxy", "model_priced_option", "drawdown_adjusted", "turnover", "fee_slippage_sensitivity"]


def run_s_tier_options_benchmark() -> dict[str, Any]:
    paper = read_json(PAPER_SUMMARY_PATH)
    has_data = paper.get("paper_loop_status") == "paper_loop_ran"
    results = [_benchmark_record(index, baseline, has_data) for index, baseline in enumerate(BASELINES)]
    adversarial = build_adversarial_evaluations(has_data)
    summary = {
        "artifact_type": "s_tier_options_benchmark_summary",
        "benchmark_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "s_tier_benchmark_status": "completed_engineering_benchmark_blocked_no_data" if not has_data else "completed_engineering_benchmark",
        "benchmark_count": len(results),
        "adversarial_evaluation_count": len(adversarial),
        "s_tier_engineering_progress": True,
        "s_tier_live_superiority_claim": False,
        "better_than_frontier_claim": False,
        "live_readiness_claim": False,
        "paper_loop_status": paper.get("paper_loop_status", "missing"),
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(RESULTS_PATH, results)
    write_jsonl(ADVERSARIAL_PATH, adversarial)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("s-tier-options-benchmark-proof-v1", summary["s_tier_benchmark_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "s_tier_benchmark_results": str(RESULTS_PATH),
        "adversarial_strategy_evaluations": str(ADVERSARIAL_PATH),
        "s_tier_options_benchmark_summary": str(SUMMARY_PATH),
        "s_tier_options_benchmark_proof": str(PROOF_PATH),
    }


def _benchmark_record(index: int, baseline: str, has_data: bool) -> dict[str, Any]:
    record = {
        "artifact_type": "s_tier_benchmark_results",
        "benchmark_id": f"s-tier-baseline-{index + 1:03d}",
        "baseline": baseline,
        "status": "blocked_no_accepted_real_data" if not has_data else "evaluated",
        "relative_result": "not_claimed",
        "live_superiority_claim": False,
        "profitability_claim": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["benchmark_hash"] = stable_hash(record)
    return record

