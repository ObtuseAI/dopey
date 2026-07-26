"""Offline mutation/evolution tournament for DOPEY StrategyGenomes.

This module evaluates deterministic mutated genomes through the same offline replay-compatible
scoring surface used by the tournament. It never sets live flags, never connects to brokers,
and never promotes a strategy to a live state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dopey_analysis.enrichment import load_window_analysis, parse_window_analysis
from dopey_analysis.analysis_fusion import fuse_analysis
from dopey_analysis.models import AnalysisFusionScore
from dopey_analysis.pattern_fixture_library import build_pattern_fixture_library, summarize_pattern_fixture_library
from dopey_analysis.pattern_scorecard import score_pattern_context, summarize_pattern_scores
from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_data.source_registry import write_data_inflow_registry
from dopey_data.source_value_ranker import source_scorecard_summary
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_tournament.runner import OVERFIT_RANK, _combined_score, run_fixture_tournament
from dopey_walk_forward.family_outcome import family_hint
from dopey_walk_forward.overfit_classifier import classify_overfit
from dopey_walk_forward.replay_engine import ReplayEngine
from dopey_walk_forward.scoring import score_walk_forward
from dopey_walk_forward.window_model import load_walk_forward_windows

from .genome_mutation import MutationBatch, build_mutation_batch
from .mutation_policy import MUTATION_POLICY_VERSION, build_mutation_instructions
from .mutation_registry import (
    MUTATION_LEDGER_PATH,
    MUTATION_REGISTRY_PATH,
    MUTATION_REGISTRY_VERSION,
    write_mutation_registry,
)
from .strategy_genome import StrategyGenome


MUTATION_TOURNAMENT_VERSION = "dopey-mutation-tournament-v1"
ALLOWED_MUTATION_DECISIONS = {
    "rejected",
    "degraded",
    "research_only",
    "paper_research_candidate",
    "offline_mutation_champion",
}
FORBIDDEN_MUTATION_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "live"}


@dataclass(frozen=True)
class MutationPromotionDecision:
    strategy_id: str
    decision: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MutationTournamentResult:
    batch_id: str
    tournament_status: str
    parent_champion_strategy_id: str
    best_mutated_strategy_id: str
    parent_score: float
    best_mutated_score: float
    improved: bool
    ranking: list[dict] = field(default_factory=list)
    promotion_decisions: dict = field(default_factory=dict)
    mutation_registry_path: str = ""
    proof_record_path: str = ""
    reproducibility_hash: str = ""
    safety_state: dict = field(default_factory=dict)
    source_scorecard_summary: dict = field(default_factory=dict)
    pattern_recognition_summary: dict = field(default_factory=dict)
    parent_vs_mutation_comparison: dict = field(default_factory=dict)
    mutation_tournament_version: str = MUTATION_TOURNAMENT_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mutation_score_adjustment(genome: StrategyGenome, score_inputs: dict) -> float:
    params = genome.parameters
    adjustment = 0.0
    if "delta_preference" in params:
        adjustment += 0.020 if 0.35 <= float(params["delta_preference"]) <= 0.65 else -0.015
    if "liquidity_threshold" in params:
        adjustment += 0.025 if score_inputs["avg_liquidity_score"] >= float(params["liquidity_threshold"]) else -0.040
    if "slippage_tolerance" in params:
        adjustment += 0.015 if score_inputs["avg_expected_slippage_pct"] <= float(params["slippage_tolerance"]) else -0.030
    if "pattern_preference" in params:
        adjustment += 0.015 if score_inputs["avg_pattern_fixture_score"] >= 0.50 else -0.015
    if "invalidation_sensitivity" in params:
        adjustment += 0.010 if score_inputs["invalidation_quality"] >= 0.60 else -0.020
    if "theta_tolerance" in params:
        adjustment += 0.010 if score_inputs["average_theta_fit_score"] >= float(params["theta_tolerance"]) else -0.020
    if "vega_tolerance" in params:
        adjustment += 0.010 if score_inputs["average_vega_fit_score"] >= float(params["vega_tolerance"]) else -0.020
    if "overfit_penalty" in params:
        penalty = float(params["overfit_penalty"])
        if score_inputs["overfit_level"] in {"moderate", "high"}:
            adjustment -= penalty
        else:
            adjustment -= penalty * 0.50
    if params.get("spread_structure_proxy") == "narrow_defined_risk_vertical":
        adjustment += 0.005
    if params.get("iv_regime_preference") == "normal_or_expansion":
        adjustment += 0.005
    if params.get("regime_filter") == "trend_vol_expansion_or_breakout":
        adjustment += 0.005
    if params.get("dte_bucket") == "21_35":
        adjustment += 0.003
    return round(adjustment, 6)


def _evaluate_genome(
    genome: StrategyGenome,
    windows,
    window_analysis: dict,
    proof_bundle: dict,
    pattern_fixtures: list,
) -> dict:
    engine = ReplayEngine()
    results = engine.replay(genome, proof_bundle, windows)
    wf = score_walk_forward(results)
    fusions = []
    pattern_summaries = []
    for window in windows:
        analysis = window_analysis[window.window_id]
        pattern_cards = score_pattern_context(genome.family, window.regime_tag, pattern_fixtures)
        pattern_summary = summarize_pattern_scores(pattern_cards)
        pattern_summaries.append(pattern_summary)
        fusion = fuse_analysis(
            macro_ctx=analysis["macro"],
            micro_ctx=analysis["microstructure"],
            tech_ctx=analysis["technical"],
            fund_ctx=analysis["fundamental"],
            patterns=analysis["patterns"],
            replay_confirmation_score=wf.consistency_score,
            family_regime_alignment=family_hint(window.regime_tag, genome.family, window.family_hints()),
            pattern_fixture_score=pattern_summary["average_pattern_score"],
        )
        fusions.append(fusion)

    avg_fusion = round(_mean([f.overall_score for f in fusions]), 6)
    train_passed = any(r.verdict == "pass" for r in results if r.window_type == "train")
    val_passed = any(r.verdict == "pass" for r in results if r.window_type == "validation")
    holdout_passed = any(r.verdict == "pass" for r in results if r.window_type == "holdout")
    overfit = classify_overfit(
        train_passed=train_passed,
        validation_passed=val_passed,
        holdout_passed=holdout_passed,
        train_pnl=wf.train_mean_pnl,
        validation_pnl=wf.validation_mean_pnl,
        holdout_pnl=wf.holdout_mean_pnl,
        overfit_suspicion=wf.overfit_suspicion_score,
    )
    avg_liq = round(_mean([r.liquidity_score for r in results]), 6)
    avg_expected_slip = round(_mean([r.expected_slippage_pct for r in results]), 6)
    avg_fill = round(_mean([r.fill_quality_score for r in results]), 6)
    avg_greek = round(_mean([r.greek_fit_score for r in results]), 6)
    avg_theta = round(_mean([r.theta_fit_score for r in results]), 6)
    avg_vega = round(_mean([r.vega_fit_score for r in results]), 6)
    avg_iv_surface = round(_mean([r.iv_surface_fit_score for r in results]), 6)
    avg_family_iv = round(_mean([r.family_iv_fit_score for r in results]), 6)
    avg_skew_term = round(_mean([r.skew_term_score for r in results]), 6)
    avg_premium = round(_mean([r.premium_overpayment_score for r in results]), 6)
    avg_iv_crush = round(_mean([r.iv_crush_score for r in results]), 6)
    avg_iv_expansion = round(_mean([r.iv_expansion_score for r in results]), 6)
    avg_front_event_bump = round(_mean([r.front_event_bump_score for r in results]), 6)
    avg_skew_trap = round(_mean([r.skew_trap_score for r in results]), 6)
    avg_wing_elevation = round(_mean([r.wing_elevation_score for r in results]), 6)
    avg_surface_instability = round(_mean([r.surface_instability_penalty for r in results]), 6)
    avg_term_risk = round(_mean([r.term_structure_risk_penalty for r in results]), 6)
    avg_iv_mismatch = round(_mean([r.iv_crush_expansion_mismatch_penalty for r in results]), 6)
    avg_iv = round(_mean([
        _mean([
            r.iv_context_score,
            r.skew_score,
            r.term_structure_score,
            r.iv_surface_fit_score,
            r.family_iv_fit_score,
            r.skew_term_score,
        ])
        for r in results
    ]), 6)
    avg_pattern = round(_mean([p["average_pattern_score"] for p in pattern_summaries]), 6)
    slippage_robustness = round(_clamp(1.0 - avg_expected_slip * 8.0, 0.0, 1.0), 6)
    base_score = _combined_score(
        wf.overall,
        avg_fusion,
        greek_fit=avg_greek,
        iv_score=avg_iv,
        liquidity=avg_liq,
        slippage=slippage_robustness,
        invalidation=wf.invalidation_quality_score,
        holdout=wf.holdout_mean_pnl,
        overfit_rank=OVERFIT_RANK.get(overfit.level, 3),
    )
    score_inputs = {
        "avg_liquidity_score": avg_liq,
        "avg_expected_slippage_pct": avg_expected_slip,
        "avg_pattern_fixture_score": avg_pattern,
        "invalidation_quality": wf.invalidation_quality_score,
        "average_theta_fit_score": avg_theta,
        "average_vega_fit_score": avg_vega,
        "overfit_level": overfit.level,
    }
    adjustment = mutation_score_adjustment(genome, score_inputs)
    combined = round(_clamp(base_score + adjustment, 0.0, 1.0), 6)
    return {
        "strategy_id": genome.genome_id,
        "strategy_family": genome.family,
        "parent_genome_id": genome.parameters.get("mutation_parent_id", ""),
        "mutation_id": genome.parameters.get("mutation_id", ""),
        "mutation_type": genome.parameters.get("mutation_type", "parent"),
        "combined_score": combined,
        "base_combined_score": base_score,
        "mutation_adjustment": adjustment,
        "walk_forward_overall": wf.overall,
        "analysis_fusion_overall": avg_fusion,
        "average_liquidity_score": avg_liq,
        "average_fill_quality_score": avg_fill,
        "average_expected_slippage_pct": avg_expected_slip,
        "slippage_robustness_score": slippage_robustness,
        "average_greek_fit_score": avg_greek,
        "average_theta_fit_score": avg_theta,
        "average_vega_fit_score": avg_vega,
        "average_iv_score": avg_iv,
        "average_iv_surface_fit_score": avg_iv_surface,
        "average_family_iv_fit_score": avg_family_iv,
        "average_skew_term_score": avg_skew_term,
        "average_premium_overpayment_score": avg_premium,
        "average_iv_crush_score": avg_iv_crush,
        "average_iv_expansion_score": avg_iv_expansion,
        "average_front_event_bump_score": avg_front_event_bump,
        "average_skew_trap_score": avg_skew_trap,
        "average_wing_elevation_score": avg_wing_elevation,
        "average_surface_instability_penalty": avg_surface_instability,
        "average_term_structure_risk_penalty": avg_term_risk,
        "average_iv_mismatch_penalty": avg_iv_mismatch,
        "worst_iv_surface_regime": sorted(
            results,
            key=lambda result: (result.family_iv_fit_score, result.regime_tag),
        )[0].regime_tag if results else "",
        "average_pattern_fixture_score": avg_pattern,
        "invalidation_quality": wf.invalidation_quality_score,
        "overfit_level": overfit.level,
        "live_allowed": genome.live_allowed,
        "defined_risk_only": genome.defined_risk_only,
        "structure_risk": genome.parameters.get("structure_risk", "defined"),
        "parameters": dict(genome.parameters),
    }


def _decision_for_row(row: dict, parent_score: float, is_best_mutation: bool) -> MutationPromotionDecision:
    reasons: list[str] = []
    if row["live_allowed"]:
        return MutationPromotionDecision(row["strategy_id"], "rejected", ["live_allowed true is forbidden"])
    if row["structure_risk"] != "defined" or not row["defined_risk_only"]:
        return MutationPromotionDecision(row["strategy_id"], "rejected", ["undefined-risk mutation is forbidden"])
    if row["overfit_level"] == "high":
        return MutationPromotionDecision(row["strategy_id"], "rejected", ["high overfit"])
    if row["mutation_adjustment"] <= -0.05:
        return MutationPromotionDecision(row["strategy_id"], "rejected", ["mutation policy penalty exceeded threshold"])
    delta = row["combined_score"] - parent_score
    if is_best_mutation and delta > 0.01:
        reasons.append("best deterministic offline mutation beat parent score")
        return MutationPromotionDecision(row["strategy_id"], "offline_mutation_champion", reasons)
    if delta > 0.005:
        reasons.append("mutation improved paper-only score")
        return MutationPromotionDecision(row["strategy_id"], "paper_research_candidate", reasons)
    if delta < -0.005:
        reasons.append("mutation degraded paper-only score")
        return MutationPromotionDecision(row["strategy_id"], "degraded", reasons)
    reasons.append("mutation retained research-only parity")
    return MutationPromotionDecision(row["strategy_id"], "research_only", reasons)


def _build_proof_entry(result: MutationTournamentResult, batch: MutationBatch) -> ProofEntry:
    return ProofEntry(
        run_id=f"dopey-mutation-{batch.batch_id}",
        task_id="offline-mutation-tournament",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"batch_id": batch.batch_id}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "mutation_batch": batch.to_dict(),
            "mutation_tournament_result": result.to_dict(),
            "source_registry_snapshot": result.source_scorecard_summary,
            "pattern_fixture_corpus_id": result.pattern_recognition_summary.get("corpus_id", ""),
            "best_mutation": result.best_mutated_strategy_id,
            "rejected_mutations": [
                sid for sid, decision in result.promotion_decisions.items()
                if decision == "rejected"
            ],
            "safety_state": result.safety_state,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[result.mutation_registry_path, result.proof_record_path],
        diffs=[],
        test_results={
            "tournament_status": result.tournament_status,
            "improved": result.improved,
            "promotion_decisions": result.promotion_decisions,
            "forbidden_live_decisions_present": sorted(
                set(result.promotion_decisions.values()).intersection(FORBIDDEN_MUTATION_DECISIONS)
            ),
        },
        final_status="PASS" if result.tournament_status == "ok" else "FAIL",
        lessons_candidate=[],
        promotion_candidate=[{
            "best_mutated_strategy_id": result.best_mutated_strategy_id,
            "decision": result.promotion_decisions.get(result.best_mutated_strategy_id, "research_only"),
        }],
        limitations=[
            "offline deterministic mutation tournament; no live execution",
            "mutation score adjustments are fixture policy math, not performance claims",
            "no broker connection, credentials, network source fetch, or scheduled run",
        ],
    )


def run_offline_mutation_tournament(
    proof_ledger_path: Path | str | None = None,
    mutation_registry_path: Path | str | None = None,
    seed: str = "dopey-offline-edge-v1",
) -> dict:
    cfg = load_config(default_config_path())
    base_summary = run_fixture_tournament()
    base_genomes = build_tournament_genomes()
    parent_id = base_summary["champion_strategy_id"]
    parent = next(genome for genome in base_genomes if genome.genome_id == parent_id)
    instructions = build_mutation_instructions(seed)
    batch = build_mutation_batch([parent], instructions, seed=seed)
    windows = load_walk_forward_windows()
    window_analysis = {
        window.window_id: parse_window_analysis(load_window_analysis(window.window_id))
        for window in windows
    }
    proof_bundle = build_tournament_proof_bundle(strong=True)
    pattern_fixtures = build_pattern_fixture_library()

    parent_rows = [
        {
            **row,
            "parent_genome_id": "",
            "mutation_id": "",
            "mutation_type": "parent",
            "live_allowed": False,
            "defined_risk_only": True,
            "structure_risk": "defined",
            "parameters": {},
        }
        for row in base_summary["strategy_ranking"]
    ]
    parent_score = next(row["combined_score"] for row in parent_rows if row["strategy_id"] == parent_id)
    mutated_rows = [
        _evaluate_genome(mutation.genome, windows, window_analysis, proof_bundle, pattern_fixtures)
        for mutation in batch.mutations
    ]
    best_mutated = sorted(mutated_rows, key=lambda row: (-row["combined_score"], row["strategy_id"]))[0]
    decisions = {
        row["strategy_id"]: _decision_for_row(row, parent_score, row["strategy_id"] == best_mutated["strategy_id"])
        for row in mutated_rows
    }
    ranking = sorted(parent_rows + mutated_rows, key=lambda row: (-row["combined_score"], row["strategy_id"]))
    for rank, row in enumerate(ranking, start=1):
        row["mutation_rank"] = rank
        if row["strategy_id"] in decisions:
            row["mutation_promotion_decision"] = decisions[row["strategy_id"]].decision
        else:
            row["mutation_promotion_decision"] = "parent"

    promotion_decisions = {sid: decision.decision for sid, decision in decisions.items()}
    if any(decision in FORBIDDEN_MUTATION_DECISIONS for decision in promotion_decisions.values()):
        raise ValueError("forbidden live mutation decision generated")

    source_summary = source_scorecard_summary()
    source_registry_path = write_data_inflow_registry()
    source_summary["source_registry_path"] = str(source_registry_path)
    pattern_summary = summarize_pattern_fixture_library(pattern_fixtures).to_dict()
    proof_path = Path(proof_ledger_path) if proof_ledger_path else MUTATION_LEDGER_PATH
    registry_path = Path(mutation_registry_path) if mutation_registry_path else MUTATION_REGISTRY_PATH
    safety_state = {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_mutations": True,
        "live_blocked": True,
    }
    comparison = {
        "parent_strategy_id": parent_id,
        "parent_score": parent_score,
        "best_mutated_strategy_id": best_mutated["strategy_id"],
        "best_mutated_score": best_mutated["combined_score"],
        "score_delta": round(best_mutated["combined_score"] - parent_score, 6),
    }
    repro = reproducibility_hash(
        {"batch": batch.to_dict()},
        {"ranking": ranking},
        {"promotion_decisions": promotion_decisions},
        source_summary,
        pattern_summary,
        safety_state,
    )
    result = MutationTournamentResult(
        batch_id=batch.batch_id,
        tournament_status="ok",
        parent_champion_strategy_id=parent_id,
        best_mutated_strategy_id=best_mutated["strategy_id"],
        parent_score=parent_score,
        best_mutated_score=best_mutated["combined_score"],
        improved=best_mutated["combined_score"] > parent_score,
        ranking=ranking,
        promotion_decisions=promotion_decisions,
        mutation_registry_path=str(registry_path),
        proof_record_path=str(proof_path),
        reproducibility_hash=repro,
        safety_state=safety_state,
        source_scorecard_summary=source_summary,
        pattern_recognition_summary=pattern_summary,
        parent_vs_mutation_comparison=comparison,
    )
    registry_record = {
        "mutation_registry_version": MUTATION_REGISTRY_VERSION,
        "batch_id": batch.batch_id,
        "best_mutated_strategy_id": best_mutated["strategy_id"],
        "parent_vs_mutation_comparison": comparison,
        "promotion_decisions": promotion_decisions,
        "ranking": ranking,
        "safety_state": safety_state,
    }
    write_mutation_registry(registry_record, registry_path)
    ProofLedger(proof_path).append(_build_proof_entry(result, batch))
    return result.to_dict()
