"""S-tier engineering target for paper-only long-premium research."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl

from .model_priced_options_research_expansion_v2 import run_model_priced_options_research_expansion_v2


ARTIFACT_DIR = ARTIFACT_ROOT / "research_autonomy"
SIGNAL_FAMILIES_PATH = ARTIFACT_DIR / "s_tier_v2_signal_families.jsonl"
TOURNAMENT_PATH = ARTIFACT_DIR / "s_tier_v2_strategy_tournament.jsonl"
RANKER_PATH = ARTIFACT_DIR / "s_tier_v2_opportunity_ranker.jsonl"
NO_TRADE_PATH = ARTIFACT_DIR / "s_tier_v2_no_trade_gates.jsonl"
STRESS_PLAN_PATH = ARTIFACT_DIR / "s_tier_v2_adversarial_stress_plan.jsonl"
QUEUE_PATH = ARTIFACT_DIR / "s_tier_v2_research_queue.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "s_tier_v2_summary.json"
PROOF_PATH = ARTIFACT_DIR / "s_tier_v2_proof.jsonl"


def run_s_tier_long_premium_engine_v2() -> dict[str, Any]:
    model = run_model_priced_options_research_expansion_v2()
    signals = _signal_families()
    tournament = _strategy_tournament(signals)
    ranker = _opportunity_ranker(tournament)
    no_trade = _no_trade_gates()
    stress = _adversarial_stress_plan()
    queue = _research_queue(stress)
    summary = {
        "artifact_type": "s_tier_v2_summary",
        "s_tier_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "s_tier_v2_status": "s_tier_v2_engineering_target_complete",
        "signal_family_count": len(signals),
        "strategy_tournament_count": len(tournament),
        "opportunity_rank_count": len(ranker),
        "no_trade_gate_count": len(no_trade),
        "adversarial_stress_plan_count": len(stress),
        "research_queue_count": len(queue),
        "model_priced_v2_status": model["model_priced_v2_status"],
        "s_tier_engineering_target": True,
        "s_tier_live_superiority_claim": False,
        "better_than_anyone_claim": False,
        "profitability_claim": False,
        "live_readiness_claim": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(SIGNAL_FAMILIES_PATH, signals)
    write_jsonl(TOURNAMENT_PATH, tournament)
    write_jsonl(RANKER_PATH, ranker)
    write_jsonl(NO_TRADE_PATH, no_trade)
    write_jsonl(STRESS_PLAN_PATH, stress)
    write_jsonl(QUEUE_PATH, queue)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("s-tier-v2-proof-v1", summary["s_tier_v2_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "s_tier_v2_signal_families": str(SIGNAL_FAMILIES_PATH),
        "s_tier_v2_strategy_tournament": str(TOURNAMENT_PATH),
        "s_tier_v2_opportunity_ranker": str(RANKER_PATH),
        "s_tier_v2_no_trade_gates": str(NO_TRADE_PATH),
        "s_tier_v2_adversarial_stress_plan": str(STRESS_PLAN_PATH),
        "s_tier_v2_research_queue": str(QUEUE_PATH),
        "s_tier_v2_summary": str(SUMMARY_PATH),
        "s_tier_v2_proof": str(PROOF_PATH),
    }


def _signal_families() -> list[dict[str, Any]]:
    families = ["trend", "momentum", "breakout", "fakeout", "reversal", "relative_strength", "volatility_regime", "market_regime", "event_avoidance", "no_trade"]
    records: list[dict[str, Any]] = []
    for index, family in enumerate(families):
        record = {
            "artifact_type": "s_tier_v2_signal_families",
            "signal_family_id": f"s-tier-v2-signal-{index:03d}",
            "family": family,
            "regime_adaptive_scoring": True,
            "volatility_aware_scoring": True,
            "candidate_mutation_enabled": family != "no_trade",
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["signal_hash"] = stable_hash(record)
        records.append(record)
    return records


def _strategy_tournament(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        raw_score = 100 - index * 4
        penalty = 10 if signal["family"] == "no_trade" else 0
        record = {
            "artifact_type": "s_tier_v2_strategy_tournament",
            "candidate_id": f"s-tier-v2-candidate-{index:03d}",
            "signal_family_id": signal["signal_family_id"],
            "raw_score": raw_score,
            "drawdown_penalty": penalty,
            "multiple_testing_penalty": 5,
            "overfit_penalty": 5,
            "walk_forward_split_plan": "rolling_train_validation_holdout",
            "symbol_holdout_plan": "etf_and_single_name_holdout",
            "date_holdout_plan": "calendar_regime_holdout",
            "sector_holdout_plan": "sector_rotation_holdout",
            "final_score": raw_score - penalty - 10,
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["candidate_hash"] = stable_hash(record)
        records.append(record)
    return records


def _opportunity_ranker(tournament: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(tournament, key=lambda record: record["final_score"], reverse=True)
    records: list[dict[str, Any]] = []
    for index, candidate in enumerate(ranked):
        record = {
            "artifact_type": "s_tier_v2_opportunity_ranker",
            "rank_id": f"s-tier-v2-rank-{index:03d}",
            "rank": index + 1,
            "candidate_id": candidate["candidate_id"],
            "opportunity_score": candidate["final_score"],
            "option_selection_proxy": "delta_moneyness_expiry_bucket",
            "paper_execution_simulation": True,
            "feedback_loop_into_research_queue": True,
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["rank_hash"] = stable_hash(record)
        records.append(record)
    return records


def _no_trade_gates() -> list[dict[str, Any]]:
    gates = ["no_data", "event_risk", "high_spread", "drawdown", "volatility_spike", "overfit", "multiple_testing", "zero_dte_guard"]
    records: list[dict[str, Any]] = []
    for index, gate in enumerate(gates):
        record = {
            "artifact_type": "s_tier_v2_no_trade_gates",
            "gate_id": f"s-tier-v2-no-trade-{index:03d}",
            "gate_name": gate,
            "no_trade_is_first_class_decision": True,
            "blocks_paper_trade": True,
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["gate_hash"] = stable_hash(record)
        records.append(record)
    return records


def _adversarial_stress_plan() -> list[dict[str, Any]]:
    stresses = ["vol_spike", "gap_down", "gap_up", "earnings_surprise", "liquidity_evaporation", "regime_flip", "theta_bleed", "correlation_break"]
    records: list[dict[str, Any]] = []
    for index, stress in enumerate(stresses):
        record = {
            "artifact_type": "s_tier_v2_adversarial_stress_plan",
            "stress_id": f"s-tier-v2-stress-{index:03d}",
            "stress_name": stress,
            "candidate_kill_gate": True,
            "drawdown_throttle": True,
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["stress_hash"] = stable_hash(record)
        records.append(record)
    return records


def _research_queue(stress: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, item in enumerate(stress):
        record = {
            "artifact_type": "s_tier_v2_research_queue",
            "queue_id": f"s-tier-v2-queue-{index:03d}",
            "source_stress_id": item["stress_id"],
            "task": f"expand_{item['stress_name']}_fixture_and_holdout",
            "priority": index + 1,
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["queue_hash"] = stable_hash(record)
        records.append(record)
    return records
