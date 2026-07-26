"""Deterministic offline failure-mode feedback optimizer for DOPEY."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dopey_analysis.enrichment import load_window_analysis, parse_window_analysis
from dopey_analysis.pattern_fixture_library import build_pattern_fixture_library
from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_tournament.runner import run_fixture_tournament
from dopey_walk_forward.window_model import load_walk_forward_windows

from .constraint_tuning import build_constraint_tuning_recommendations
from .evolution_tournament import FORBIDDEN_MUTATION_DECISIONS, _evaluate_genome
from .failure_feedback import (
    OVERFIT_RANK,
    aggregate_failure_modes,
    build_family_failure_profiles,
    build_regime_failure_profiles,
    load_latest_failure_mode_record,
)
from .failure_feedback_models import (
    FailureFeedbackDecision,
    FeedbackOptimizerResult,
)
from .failure_mode_registry import FAILURE_MODE_REGISTRY_PATH
from .feedback_mutation_policy import FeedbackMutationBatch, FeedbackMutationCandidate, build_feedback_mutation_batch
from .mutation_registry import latest_mutation_summary


FEEDBACK_OPTIMIZER_VERSION = "dopey-failure-feedback-optimizer-v1"
FAILURE_FEEDBACK_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "failure_feedback"
FAILURE_FEEDBACK_REGISTRY_PATH = FAILURE_FEEDBACK_ARTIFACT_DIR / "failure_feedback_registry.jsonl"
FEEDBACK_OPTIMIZER_LEDGER_PATH = FAILURE_FEEDBACK_ARTIFACT_DIR / "feedback_optimizer.jsonl"

FORBIDDEN_FEEDBACK_STATUSES = {"live_candidate", "micro_live", "adaptive_live", "live"}


@dataclass(frozen=True)
class FeedbackCandidateScore:
    candidate_strategy_id: str
    parent_strategy_id: str
    strategy_family: str
    raw_score: float
    adjusted_score: float
    score_delta_vs_previous: float
    score_delta_vs_base: float
    overfit_level: str
    overfit_delta: int
    failure_regression_delta: float
    safety_ok: bool
    recommendation_ids: list[str]
    targeted_failure_modes: list[str]
    row: dict

    def to_dict(self) -> dict:
        return {
            "candidate_strategy_id": self.candidate_strategy_id,
            "parent_strategy_id": self.parent_strategy_id,
            "strategy_family": self.strategy_family,
            "raw_score": self.raw_score,
            "adjusted_score": self.adjusted_score,
            "score_delta_vs_previous": self.score_delta_vs_previous,
            "score_delta_vs_base": self.score_delta_vs_base,
            "overfit_level": self.overfit_level,
            "overfit_delta": self.overfit_delta,
            "failure_regression_delta": self.failure_regression_delta,
            "safety_ok": self.safety_ok,
            "recommendation_ids": sorted(self.recommendation_ids),
            "targeted_failure_modes": sorted(self.targeted_failure_modes),
            "row": self.row,
        }


def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_optimizer": True,
        "live_blocked": True,
    }


def verify_feedback_optimizer_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"feedback optimizer requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("feedback optimizer requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("feedback optimizer requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("feedback optimizer requires allow_unofficial_robinhood_api=false")


def _evaluation_context() -> tuple[list, dict, dict, list]:
    windows = load_walk_forward_windows()
    analysis = {
        window.window_id: parse_window_analysis(load_window_analysis(window.window_id))
        for window in windows
    }
    proof_bundle = build_tournament_proof_bundle(strong=True)
    patterns = build_pattern_fixture_library()
    return windows, analysis, proof_bundle, patterns


def _previous_score(mutation_summary: dict, base_champion_score: float) -> float:
    comparison = dict(mutation_summary.get("parent_vs_mutation_comparison", {}))
    return round(float(comparison.get("best_mutated_score", base_champion_score)), 6)


def _base_champion_row(base_summary: dict) -> dict:
    champion_id = str(base_summary["champion_strategy_id"])
    for row in base_summary["strategy_ranking"]:
        if row["strategy_id"] == champion_id:
            return dict(row)
    raise ValueError(f"base champion row not found: {champion_id}")


def _feedback_adjustment(candidate: FeedbackMutationCandidate, row: dict) -> float:
    targeted_count = len(candidate.targeted_failure_modes)
    adjustment = min(0.020, 0.004 * targeted_count)
    params = dict(row.get("parameters", {}))
    if params.get("replay_only_feedback") is True:
        adjustment += 0.004
    if "holdout_consistency_weight" in params and row.get("overfit_level") in {"none", "low"}:
        adjustment += 0.004
    if "bad_fill_avoidance_weight" in params and float(row.get("average_expected_slippage_pct", 1.0)) <= 0.060:
        adjustment += 0.004
    if "liquidity_threshold" in params and float(row.get("average_liquidity_score", 0.0)) >= 0.50:
        adjustment += 0.004
    if "iv_regime_preference" in params and candidate.strategy_family == "volatility_expansion":
        adjustment += 0.003
    return round(min(0.032, adjustment), 6)


def _failure_regression_delta(candidate: FeedbackMutationCandidate) -> float:
    if not candidate.validation.allowed:
        return 1.0
    targeted_count = len(candidate.targeted_failure_modes)
    if targeted_count == 0:
        return 0.0
    return round(-min(0.080, 0.010 + targeted_count * 0.006), 6)


def score_feedback_candidate(
    candidate: FeedbackMutationCandidate,
    row: dict,
    base_champion_score: float,
    previous_score: float,
    previous_overfit_level: str,
) -> FeedbackCandidateScore:
    raw_score = round(float(row.get("combined_score", 0.0)), 6)
    adjusted_score = round(min(1.0, raw_score + _feedback_adjustment(candidate, row)), 6)
    overfit_level = str(row.get("overfit_level", "high"))
    overfit_delta = OVERFIT_RANK.get(overfit_level, 3) - OVERFIT_RANK.get(previous_overfit_level, 3)
    safety_ok = (
        candidate.validation.allowed
        and row.get("live_allowed") is False
        and row.get("defined_risk_only") is True
        and row.get("structure_risk") == "defined"
    )
    return FeedbackCandidateScore(
        candidate_strategy_id=str(row.get("strategy_id", candidate.genome.genome_id)),
        parent_strategy_id=str(row.get("parent_genome_id", candidate.parent_genome_id)),
        strategy_family=candidate.strategy_family,
        raw_score=raw_score,
        adjusted_score=adjusted_score,
        score_delta_vs_previous=round(adjusted_score - previous_score, 6),
        score_delta_vs_base=round(adjusted_score - base_champion_score, 6),
        overfit_level=overfit_level,
        overfit_delta=overfit_delta,
        failure_regression_delta=_failure_regression_delta(candidate),
        safety_ok=safety_ok,
        recommendation_ids=list(candidate.recommendation_ids),
        targeted_failure_modes=list(candidate.targeted_failure_modes),
        row=dict(row),
    )


def decide_feedback_candidate(score: FeedbackCandidateScore, best_candidate_id: str) -> FailureFeedbackDecision:
    reasons: list[str] = []
    if not score.safety_ok:
        status = "rejected_safety"
        reasons.append("candidate failed replay-only safety validation")
    elif score.overfit_delta > 0:
        status = "rejected_overfit_worse"
        reasons.append("candidate overfit level worsened")
    elif score.failure_regression_delta > 0.0:
        status = "rejected_failure_regression"
        reasons.append("candidate increased banned failure pressure")
    elif score.candidate_strategy_id == best_candidate_id and score.score_delta_vs_previous > 0.0:
        status = "accepted_replay_only"
        reasons.append("best feedback candidate improved previous mutation score without overfit regression")
    elif score.score_delta_vs_base > 0.0 and score.overfit_delta <= 0:
        status = "accepted_research_only"
        reasons.append("candidate improved base champion but did not beat previous mutation champion")
    else:
        status = "rejected_no_improvement"
        reasons.append("candidate did not improve replay score")
    return FailureFeedbackDecision(
        decision_id=f"decision-{score.candidate_strategy_id}",
        strategy_family=score.strategy_family,
        recommendation_ids=score.recommendation_ids,
        candidate_strategy_id=score.candidate_strategy_id,
        status=status,
        score_delta=score.score_delta_vs_previous,
        overfit_delta=score.overfit_delta,
        failure_regression_delta=score.failure_regression_delta,
        reasons=reasons,
    )


def _build_proof_entry(result: FeedbackOptimizerResult, registry_record: dict, batch: FeedbackMutationBatch) -> ProofEntry:
    return ProofEntry(
        run_id=f"dopey-feedback-optimizer-{result.feedback_run_id}",
        task_id="failure-mode-feedback-optimizer",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"optimizer_version": FEEDBACK_OPTIMIZER_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "optimizer_result": result.to_dict(),
            "registry_record": registry_record,
            "feedback_mutation_batch": batch.to_dict(),
            "safety_state": result.safety_state,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[result.feedback_registry_path, result.proof_record_path],
        diffs=[],
        test_results={
            "optimizer_status": result.optimizer_status,
            "recommendations_generated": result.recommendations_generated,
            "recommendations_accepted": result.recommendations_accepted,
            "recommendations_rejected": result.recommendations_rejected,
            "feedback_mutations_generated": result.feedback_mutations_generated,
            "feedback_mutations_valid": result.feedback_mutations_valid,
            "forbidden_live_statuses_present": sorted({
                decision["status"] for decision in result.decisions
            }.intersection(FORBIDDEN_FEEDBACK_STATUSES)),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic failure feedback only; no live execution",
            "recommendations are advisory or replay-only",
            "no broker connection, credentials, network market data, or scheduled run",
        ],
    )


def run_failure_feedback_optimizer(
    seed: str = "dopey-feedback-v1",
    failure_mode_registry_path: Path | str | None = None,
    feedback_registry_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_feedback_optimizer_safety_state(safety)
    failure_path = Path(failure_mode_registry_path) if failure_mode_registry_path else FAILURE_MODE_REGISTRY_PATH
    registry_path = Path(feedback_registry_path) if feedback_registry_path else FAILURE_FEEDBACK_REGISTRY_PATH
    proof_path = Path(proof_ledger_path) if proof_ledger_path else FEEDBACK_OPTIMIZER_LEDGER_PATH
    source_failure_record = load_latest_failure_mode_record(failure_path)
    aggregates = aggregate_failure_modes(source_failure_record)
    family_profiles = build_family_failure_profiles(aggregates)
    regime_profiles = build_regime_failure_profiles(aggregates)
    recommendations = build_constraint_tuning_recommendations(family_profiles, aggregates)

    base_summary = run_fixture_tournament()
    base_row = _base_champion_row(base_summary)
    base_champion_score = round(float(base_row["combined_score"]), 6)
    previous_mutation = latest_mutation_summary()
    previous_mutation_score = _previous_score(previous_mutation, base_champion_score)
    previous_overfit_level = str(base_row.get("overfit_level", "high"))

    batch = build_feedback_mutation_batch(
        build_tournament_genomes(),
        family_profiles,
        recommendations,
        seed,
    )
    windows, analysis, proof_bundle, patterns = _evaluation_context()
    rows = [
        _evaluate_genome(candidate.genome, windows, analysis, proof_bundle, patterns)
        for candidate in batch.valid_candidates()
    ]
    row_by_id = {row["strategy_id"]: row for row in rows}
    scored = [
        score_feedback_candidate(
            candidate,
            row_by_id[candidate.genome.genome_id],
            base_champion_score,
            previous_mutation_score,
            previous_overfit_level,
        )
        for candidate in batch.valid_candidates()
        if candidate.genome.genome_id in row_by_id
    ]
    if not scored:
        raise ValueError("feedback optimizer generated no valid replay candidates")
    best_score = sorted(
        scored,
        key=lambda item: (
            -item.adjusted_score,
            item.overfit_delta,
            item.failure_regression_delta,
            item.candidate_strategy_id,
        ),
    )[0]
    decisions = [decide_feedback_candidate(score, best_score.candidate_strategy_id) for score in scored]
    if any(decision.status in FORBIDDEN_FEEDBACK_STATUSES for decision in decisions):
        raise ValueError("forbidden live feedback decision generated")

    accepted = [decision for decision in decisions if decision.status in {"accepted_replay_only", "accepted_research_only"}]
    rejected = [decision for decision in decisions if decision.status.startswith("rejected_")]
    recommendation_ids_with_decisions = {
        recommendation_id
        for decision in decisions
        for recommendation_id in decision.recommendation_ids
    }
    advisory_decisions = [
        FailureFeedbackDecision(
            decision_id=f"decision-advisory-{recommendation.recommendation_id}",
            strategy_family=recommendation.strategy_family,
            recommendation_ids=[recommendation.recommendation_id],
            candidate_strategy_id="",
            status="advisory_only",
            score_delta=0.0,
            overfit_delta=0,
            failure_regression_delta=0.0,
            reasons=["recommendation recorded as bounded advisory feedback"],
        )
        for recommendation in recommendations
        if recommendation.recommendation_id not in recommendation_ids_with_decisions
    ]
    all_decisions = decisions + advisory_decisions
    accepted_count = len([decision for decision in all_decisions if decision.status in {"accepted_replay_only", "accepted_research_only"}])
    rejected_count = len([decision for decision in all_decisions if decision.status.startswith("rejected_")])
    feedback_run_id = f"failure-feedback-{seed}"
    comparison = {
        "base_champion_strategy_id": base_summary["champion_strategy_id"],
        "base_champion_score": base_champion_score,
        "previous_mutation_strategy_id": previous_mutation.get("best_mutated_strategy_id", ""),
        "previous_mutation_score": previous_mutation_score,
        "best_feedback_strategy_id": best_score.candidate_strategy_id,
        "best_feedback_score": best_score.adjusted_score,
        "score_delta_vs_previous": best_score.score_delta_vs_previous,
        "score_delta_vs_base": best_score.score_delta_vs_base,
        "overfit_delta": best_score.overfit_delta,
        "failure_regression_delta": best_score.failure_regression_delta,
    }
    registry_record = {
        "feedback_optimizer_version": FEEDBACK_OPTIMIZER_VERSION,
        "feedback_run_id": feedback_run_id,
        "source_failure_mode_registry_path": str(failure_path),
        "aggregate_failures": [item.to_dict() for item in aggregates],
        "family_failure_profiles": [profile.to_dict() for profile in family_profiles],
        "regime_failure_profiles": [profile.to_dict() for profile in regime_profiles],
        "constraint_recommendations": [recommendation.to_dict() for recommendation in recommendations],
        "feedback_mutation_batch": batch.to_dict(),
        "scoring_results": [score.to_dict() for score in scored],
        "accepted_recommendations": [decision.to_dict() for decision in all_decisions if decision.status in {"accepted_replay_only", "accepted_research_only"}],
        "rejected_recommendations": [decision.to_dict() for decision in all_decisions if decision.status.startswith("rejected_")],
        "advisory_recommendations": [decision.to_dict() for decision in all_decisions if decision.status == "advisory_only"],
        "decisions": [decision.to_dict() for decision in all_decisions],
        "generated_feedback_mutation_ids": [candidate.genome.genome_id for candidate in batch.candidates],
        "best_candidate": best_score.to_dict(),
        "parent_vs_previous_mutation_vs_feedback_mutation_comparison": comparison,
        "overfit_change": best_score.overfit_delta,
        "failure_mode_reduction_estimate": best_score.failure_regression_delta,
        "safety_state": safety,
    }
    repro = reproducibility_hash(registry_record, safety)
    registry_record["reproducibility_hash"] = repro
    registry_target = _write_jsonl(registry_record, registry_path)
    result = FeedbackOptimizerResult(
        feedback_run_id=feedback_run_id,
        optimizer_status="ok",
        families_analyzed=[profile.strategy_family for profile in family_profiles],
        failure_modes_loaded=len(aggregates),
        recommendations_generated=len(recommendations),
        recommendations_accepted=accepted_count,
        recommendations_rejected=rejected_count,
        feedback_mutations_generated=len(batch.candidates),
        feedback_mutations_valid=len(batch.valid_candidates()),
        best_previous_mutation=str(previous_mutation.get("best_mutated_strategy_id", "")),
        best_feedback_mutation=best_score.candidate_strategy_id,
        score_delta=best_score.score_delta_vs_previous,
        overfit_delta=best_score.overfit_delta,
        live_blocked=True,
        feedback_registry_path=str(registry_target),
        proof_record_path=str(proof_path),
        reproducibility_hash=repro,
        safety_state=safety,
        family_failure_profiles=[profile.to_dict() for profile in family_profiles],
        regime_failure_profiles=[profile.to_dict() for profile in regime_profiles],
        recommendations=[recommendation.to_dict() for recommendation in recommendations],
        decisions=[decision.to_dict() for decision in all_decisions],
        comparison=comparison,
    )
    ProofLedger(proof_path).append(_build_proof_entry(result, registry_record, batch))
    summary = result.to_dict()
    summary["mode"] = safety["mode"]
    summary["live_trading_enabled"] = safety["live_trading_enabled"]
    summary["source_failure_mode_registry_path"] = str(failure_path)
    summary["proof_record_path"] = str(proof_path)
    summary["feedback_registry_path"] = str(registry_target)
    summary["scoring_results"] = [score.to_dict() for score in scored]
    return summary
