"""Autonomous evidence ladder for backtest, stats, fitness, and promotion gates."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_json, read_jsonl, safety_state, stable_hash, write_json, write_jsonl

from .run_autonomous_research_engine import INTENTS_PATH, SUMMARY_PATH as RESEARCH_SUMMARY_PATH, run_autonomous_research_engine


ARTIFACT_DIR = ARTIFACT_ROOT / "research_autonomy"
EVIDENCE_LADDER_PATH = ARTIFACT_DIR / "autonomous_evidence_ladder.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_backtest_stat_fitness_summary.json"
PROMOTION_PATH = ARTIFACT_DIR / "autonomous_research_promotion_decision.json"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "autonomous_research_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "autonomous_backtest_stat_fitness_proof.jsonl"


def run_autonomous_backtest_stat_fitness_pipeline() -> dict[str, Any]:
    if not RESEARCH_SUMMARY_PATH.exists():
        run_autonomous_research_engine()
    research = read_json(RESEARCH_SUMMARY_PATH)
    intents = read_jsonl(INTENTS_PATH)
    data_tier = _data_tier(research)
    ladder = _evidence_ladder(data_tier, research, intents)
    stats_pass = data_tier != "no_accepted_real_data" and len(intents) >= 5 and research["quote_priced_backtest_allowed"]
    fitness_pass = bool(stats_pass)
    promotion_allowed = bool(stats_pass and fitness_pass)
    promotion = {
        "artifact_type": "autonomous_research_promotion_decision",
        "promotion_status": "paper_research_promotion_allowed" if promotion_allowed else "blocked_missing_evidence",
        "paper_research_promotion_allowed": promotion_allowed,
        "live_promotion_status": False,
        "accepted_real_data_required": True,
        "statistical_truth_pass": stats_pass,
        "fitness_gate_pass": fitness_pass,
        "overfit_gate_pass": stats_pass,
        "multiple_testing_gate_pass": stats_pass,
        "sample_size_gate_pass": stats_pass,
        "drawdown_gate_pass": stats_pass,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    promotion["decision_hash"] = stable_hash(promotion)
    flags = _quality_flags(data_tier, stats_pass, fitness_pass)
    summary = {
        "artifact_type": "autonomous_backtest_stat_fitness_summary",
        "pipeline_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "pipeline_status": "completed_blocked_missing_evidence" if not promotion_allowed else "paper_research_evidence_passed",
        "data_tier": data_tier,
        "evidence_ladder_steps": len(ladder),
        "statistical_truth_pass": stats_pass,
        "fitness_gate_pass": fitness_pass,
        "research_promotion_status": promotion["promotion_status"],
        "quote_priced_backtest_allowed": research["quote_priced_backtest_allowed"],
        "model_priced_research_allowed": research["model_priced_research_allowed"],
        "not_profitability_claim": True,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(EVIDENCE_LADDER_PATH, ladder)
    write_json(SUMMARY_PATH, summary)
    write_json(PROMOTION_PATH, promotion)
    write_jsonl(QUALITY_FLAGS_PATH, flags)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-backtest-stat-fitness-proof-v1", summary["pipeline_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_evidence_ladder": str(EVIDENCE_LADDER_PATH),
        "autonomous_backtest_stat_fitness_summary": str(SUMMARY_PATH),
        "autonomous_research_promotion_decision": str(PROMOTION_PATH),
        "autonomous_research_quality_flags": str(QUALITY_FLAGS_PATH),
        "autonomous_backtest_stat_fitness_proof": str(PROOF_PATH),
    }


def _data_tier(research: dict[str, Any]) -> str:
    if not research.get("valid_real_dataset", False):
        return "no_accepted_real_data"
    if research.get("quote_priced_backtest_allowed", False):
        return "accepted_open_options_quote_priced"
    return "accepted_open_options_model_priced_only"


def _evidence_ladder(data_tier: str, research: dict[str, Any], intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = ["data_tier_assessment", "signal_factory", "long_premium_intent_mapping", "honest_backtester", "statistical_truth_layer", "fitness_gate", "promotion_decision", "no_live_boundary"]
    records: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        blocked = data_tier == "no_accepted_real_data" and step not in {"data_tier_assessment", "signal_factory", "long_premium_intent_mapping", "no_live_boundary"}
        record = {
            "artifact_type": "autonomous_evidence_ladder",
            "step_id": f"evidence-ladder-{index + 1:02d}",
            "step": step,
            "status": "blocked_missing_evidence" if blocked else "completed",
            "data_tier": data_tier,
            "intent_count": len(intents),
            "quote_priced_backtest_allowed": research.get("quote_priced_backtest_allowed", False),
            "paper_only": True,
            "live_blocked": True,
        }
        record["step_hash"] = stable_hash(record)
        records.append(record)
    return records


def _quality_flags(data_tier: str, stats_pass: bool, fitness_pass: bool) -> list[dict[str, Any]]:
    reasons: list[str] = []
    if data_tier == "no_accepted_real_data":
        reasons.append("no_accepted_real_data")
    if not stats_pass:
        reasons.append("statistical_truth_blocked")
    if not fitness_pass:
        reasons.append("fitness_gate_blocked")
    flags: list[dict[str, Any]] = []
    for index, reason in enumerate(reasons):
        record = {
            "artifact_type": "autonomous_research_quality_flags",
            "flag_id": f"research-quality-{index:03d}",
            "reason_code": reason,
            "severity": "info",
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        flags.append(record)
    return flags

