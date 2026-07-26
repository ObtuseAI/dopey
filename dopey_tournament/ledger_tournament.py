"""Dopey tournament proof-ledger + champion registry writers.

Builds a ProofEntry for a tournament run and writes a local champion registry JSON. Offline;
no network. Reproducibility-hashed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.proof_ledger import ProofEntry
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .models import TournamentResult, StrategyTournamentScore, ChampionRegistryEntry


CHAMPION_REGISTRY_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "champion_registry"
CHAMPION_REGISTRY_PATH = CHAMPION_REGISTRY_DIR / "champion_registry.jsonl"
TOURNAMENT_LEDGER_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "tournaments"
TOURNAMENT_LEDGER_PATH = TOURNAMENT_LEDGER_DIR / "dopey_tournament.jsonl"


def build_tournament_proof_entry(run_id: str, *, result: TournamentResult,
                                 strategy_scores: list[StrategyTournamentScore],
                                 repro_hash: str) -> ProofEntry:
    """Assemble a ProofEntry for a tournament run."""
    ts = datetime.now(timezone.utc).isoformat()
    final_status = "PASS" if result.tournament_status == "ok" else "FAIL"
    return ProofEntry(
        run_id=run_id,
        task_id=f"tournament-{result.tournament_id}",
        timestamp=ts,
        input_hash=repro_hash,
        plan_hash=reproducibility_hash({"tournament_id": result.tournament_id}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "strategy_ranking": result.strategy_ranking,
            "family_scorecard": result.family_scorecard,
            "overfit_summary": result.overfit_summary,
            "promotion_decisions": result.promotion_decisions,
            "strategy_scores": [s.to_dict() for s in strategy_scores],
            # restored corpus / lane evidence (the tests audit these):
            "corpus_id": result.corpus_id,
            "window_count": result.window_count,
            "regime_tags_covered": result.regime_tags_covered,
            "family_replay_summaries": result.family_replay_summaries,
            "analysis_fusion_summaries": result.analysis_fusion_summaries,
            "champion": result.champion_strategy_id,
            "runner_up": result.runner_up_strategy_id,
            "safety_state": result.safety_state,
            "liquidity_model_version": result.liquidity_model_version,
            "slippage_model_version": result.slippage_model_version,
            "slippage_liquidity_summary": result.slippage_liquidity_summary,
            "worst_slippage_regimes": result.worst_slippage_regimes,
            "best_fill_quality_regimes": result.best_fill_quality_regimes,
            "greeks_validation_model_version": result.greeks_validation_model_version,
            "iv_fixture_model_version": result.iv_fixture_model_version,
            "iv_surface_expansion_version": result.iv_surface_expansion_version,
            "greek_iv_summary": result.greek_iv_summary,
            "iv_surface_expansion_summary": result.iv_surface_expansion_summary,
            "worst_greek_risk_regimes": result.worst_greek_risk_regimes,
            "best_greek_fit_regimes": result.best_greek_fit_regimes,
            "source_scorecard_summary": result.source_scorecard_summary,
            "pattern_recognition_summary": result.pattern_recognition_summary,
            "mutation_evolution_summary": result.mutation_evolution_summary,
            "structure_builder_summary": result.structure_builder_summary,
            "failure_mode_summary": result.failure_mode_summary,
            "macro_event_summary": result.macro_event_summary,
            "fundamental_summary": result.fundamental_summary,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[s.strategy_id for s in strategy_scores],
        diffs=[],
        test_results={
            "champion": result.champion_strategy_id,
            "runner_up": result.runner_up_strategy_id,
            "promotion_decisions": result.promotion_decisions,
            "overfit_summary": result.overfit_summary,
            "greeks_validation_model_version": result.greeks_validation_model_version,
            "iv_fixture_model_version": result.iv_fixture_model_version,
            "iv_surface_expansion_version": result.iv_surface_expansion_version,
        },
        final_status=final_status,
        lessons_candidate=[],
        promotion_candidate=[{"champion": result.champion_strategy_id,
                              "decision": result.promotion_decisions.get(result.champion_strategy_id, "research_only")}],
        limitations=[
            "fixture-based offline multi-strategy tournament; no live execution; no real market quality implied",
            "deterministic simulated replay + analysis fusion; no network or credentials used",
            "paper-only promotion target; live promotion is impossible from this path",
        ],
    )


def write_champion_registry(entry: ChampionRegistryEntry,
                            path: Path | None = None) -> Path:
    """Append a champion registry entry to a local JSONL registry."""
    p = path or CHAMPION_REGISTRY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    return p
