"""Run the DOPEY mutation population and structure-builder bundle."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_analysis.enrichment import load_window_analysis, parse_window_analysis
from dopey_analysis.pattern_fixture_library import build_pattern_fixture_library
from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_data.source_value_ranker import source_scorecard_summary
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_tournament.runner import run_fixture_tournament
from dopey_walk_forward.window_model import load_walk_forward_windows

from .evolution_tournament import FORBIDDEN_MUTATION_DECISIONS, _evaluate_genome
from .failure_mode_miner import mine_failure_modes
from .failure_mode_registry import FAILURE_MODE_REGISTRY_PATH, write_failure_mode_registry
from .mutation_constraints import constraint_updates_from_failure_modes
from .mutation_population import MutationPopulationBatch, build_mutation_population
from .mutation_registry import MUTATION_ARTIFACT_DIR, MUTATION_REGISTRY_PATH, MUTATION_REGISTRY_VERSION, write_mutation_registry
from .mutation_scorecard import score_population_candidate


MUTATION_POPULATION_BUNDLE_VERSION = "dopey-mutation-population-bundle-v1"
MUTATION_POPULATION_LEDGER_PATH = MUTATION_ARTIFACT_DIR / "dopey_mutation_population_bundle.jsonl"


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_mutations": True,
        "live_blocked": True,
    }


def _evaluation_context() -> tuple[list, dict, dict, list]:
    windows = load_walk_forward_windows()
    analysis = {
        window.window_id: parse_window_analysis(load_window_analysis(window.window_id))
        for window in windows
    }
    proof_bundle = build_tournament_proof_bundle(strong=True)
    patterns = build_pattern_fixture_library()
    return windows, analysis, proof_bundle, patterns


def _unsafe_rejection_records(batch: MutationPopulationBatch) -> list[dict]:
    return [
        {
            "genome_id": record.genome.genome_id,
            "family": record.genome.family,
            "mutation_id": record.mutation_id,
            "mutation_type": record.mutation_type,
            "reasons": record.validation.reasons,
        }
        for record in batch.rejected_records()
    ]


def _build_proof_entry(summary: dict, batch: MutationPopulationBatch, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=f"dopey-mutation-population-{summary['mutation_batch_id']}",
        task_id="mutation-population-and-structure-builder-bundle",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=summary["reproducibility_hash"],
        plan_hash=reproducibility_hash({"bundle_version": MUTATION_POPULATION_BUNDLE_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "bundle_summary": summary,
            "mutation_population_batch": batch.to_dict(),
            "mutation_registry_record": registry_record,
            "failure_mode_summary": summary["failure_mode_summary"],
            "source_scorecard_summary": summary["source_scorecard_summary"],
            "pattern_recognition_summary": summary["pattern_recognition_summary"],
            "safety_state": summary["safety_state"],
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[
            summary["mutation_registry_path"],
            summary["failure_mode_registry_path"],
            summary["proof_record_path"],
        ],
        diffs=[],
        test_results={
            "bundle_status": summary["bundle_status"],
            "mutations_generated": summary["mutations_generated"],
            "mutations_valid": summary["mutations_valid"],
            "mutations_rejected": summary["mutations_rejected"],
            "failure_modes_detected": summary["failure_modes_detected"],
            "forbidden_live_decisions_present": sorted(
                set(summary["promotion_decisions"].values()).intersection(FORBIDDEN_MUTATION_DECISIONS)
            ),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[{
            "best_mutation": summary["best_mutation"],
            "decision": summary["promotion_decisions"].get(summary["best_mutation"], "research_only"),
        }],
        limitations=[
            "offline deterministic mutation population only; no live execution",
            "structure builder uses fixture option candidates only",
            "failure-mode mining is deterministic evidence extraction, not market prediction",
            "no broker connection, credentials, network source fetch, or schedule",
        ],
    )


def run_mutation_population_bundle(
    seed: str = "dopey-population-v1",
    mutation_registry_path: Path | str | None = None,
    failure_mode_registry_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    base_summary = run_fixture_tournament()
    base_rows = list(base_summary["strategy_ranking"])
    parent_score_by_id = {row["strategy_id"]: float(row["combined_score"]) for row in base_rows}
    parents = build_tournament_genomes()
    batch = build_mutation_population(parents, seed)
    windows, analysis, proof_bundle, patterns = _evaluation_context()

    validation_by_id = {record.genome.genome_id: record.validation for record in batch.records}
    valid_records = batch.valid_records()
    evaluated_rows = [
        _evaluate_genome(record.genome, windows, analysis, proof_bundle, patterns)
        for record in valid_records
    ]
    unsafe_rejections = _unsafe_rejection_records(batch)
    failure_registry = mine_failure_modes(base_rows, evaluated_rows, unsafe_rejections)
    failure_modes = [mode.to_dict() for mode in failure_registry.failure_modes]
    constraint_updates = constraint_updates_from_failure_modes(failure_modes)

    preliminary_scorecards = [
        score_population_candidate(
            row,
            parent_score_by_id.get(row.get("parent_genome_id", ""), 0.0),
            validation_by_id[row["strategy_id"]],
            constraint_updates,
            False,
        )
        for row in evaluated_rows
    ]
    best_prelim = sorted(
        [score for score in preliminary_scorecards if score.promotion_decision != "rejected"],
        key=lambda score: (-score.adjusted_score, score.strategy_id),
    )[0]
    scorecards = [
        score_population_candidate(
            row,
            parent_score_by_id.get(row.get("parent_genome_id", ""), 0.0),
            validation_by_id[row["strategy_id"]],
            constraint_updates,
            row["strategy_id"] == best_prelim.strategy_id,
        )
        for row in evaluated_rows
    ]
    scorecard_by_id = {score.strategy_id: score for score in scorecards}
    for row in evaluated_rows:
        score = scorecard_by_id[row["strategy_id"]]
        row["population_adjusted_score"] = score.adjusted_score
        row["population_score_delta"] = score.score_delta
        row["population_result_category"] = score.result_category
        row["mutation_promotion_decision"] = score.promotion_decision
        row["failure_constraint_penalty"] = score.failure_constraint_penalty

    best_scorecard = sorted(scorecards, key=lambda score: (-score.adjusted_score, score.strategy_id))[0]
    best_row = next(row for row in evaluated_rows if row["strategy_id"] == best_scorecard.strategy_id)
    parent_id = best_row.get("parent_genome_id", "")
    parent_score = parent_score_by_id.get(parent_id, 0.0)
    comparison = {
        "parent_strategy_id": parent_id,
        "parent_score": round(parent_score, 6),
        "best_mutated_strategy_id": best_scorecard.strategy_id,
        "best_mutated_score": best_scorecard.adjusted_score,
        "score_delta": best_scorecard.score_delta,
    }
    promotion_decisions = {score.strategy_id: score.promotion_decision for score in scorecards}
    for record in batch.rejected_records():
        promotion_decisions[record.genome.genome_id] = "rejected"
    if any(decision in FORBIDDEN_MUTATION_DECISIONS for decision in promotion_decisions.values()):
        raise ValueError("forbidden live mutation decision generated")

    registry_path = Path(mutation_registry_path) if mutation_registry_path else MUTATION_REGISTRY_PATH
    failure_path = Path(failure_mode_registry_path) if failure_mode_registry_path else FAILURE_MODE_REGISTRY_PATH
    proof_path = Path(proof_ledger_path) if proof_ledger_path else MUTATION_POPULATION_LEDGER_PATH
    source_summary = source_scorecard_summary()
    pattern_summary = base_summary.get("pattern_recognition_summary", {})
    family_coverage = sorted({record.genome.family for record in batch.valid_records()})
    rejected_summary = {
        "unsafe_rejected_count": len(batch.rejected_records()),
        "unsafe_rejected_ids": [record.genome.genome_id for record in batch.rejected_records()],
        "reasons_by_id": {
            record.genome.genome_id: record.validation.reasons for record in batch.rejected_records()
        },
    }
    failure_mode_record = failure_registry.to_dict()
    failure_mode_record["batch_id"] = batch.batch_id
    failure_mode_record["safety_state"] = safety
    failure_mode_path = write_failure_mode_registry(failure_mode_record, failure_path)
    failure_summary = {
        "failure_modes_detected": len(failure_registry.failure_modes),
        "top_failure_modes": [
            {
                "failure_mode_id": mode.failure_mode_id,
                "affected_family": mode.affected_family,
                "severity": mode.severity,
                "recurrence_count": mode.recurrence_count,
                "mitigation_hint": mode.mitigation_hint,
                "recommended_mutation_constraint_update": mode.recommended_mutation_constraint_update,
            }
            for mode in failure_registry.failure_modes[:10]
        ],
        "constraint_updates": [update.to_dict() for update in constraint_updates],
    }
    registry_record = {
        "mutation_registry_version": MUTATION_REGISTRY_VERSION,
        "bundle_version": MUTATION_POPULATION_BUNDLE_VERSION,
        "batch_id": batch.batch_id,
        "mutations_generated": len(batch.records),
        "mutations_valid": len(batch.valid_records()),
        "mutations_rejected": len(batch.rejected_records()),
        "family_coverage": family_coverage,
        "best_mutated_strategy_id": best_scorecard.strategy_id,
        "parent_vs_mutation_comparison": comparison,
        "promotion_decisions": promotion_decisions,
        "scorecards": [score.to_dict() for score in scorecards],
        "ranking": sorted(evaluated_rows, key=lambda row: (-row["population_adjusted_score"], row["strategy_id"])),
        "rejected_mutations": rejected_summary,
        "failure_mode_summary": failure_summary,
        "safety_state": safety,
    }
    write_mutation_registry(registry_record, registry_path)

    repro = reproducibility_hash(
        batch.to_dict(),
        registry_record,
        failure_mode_record,
        source_summary,
        pattern_summary,
        safety,
    )
    summary = {
        "bundle_status": "ok",
        "mode": safety["mode"],
        "live_trading_enabled": safety["live_trading_enabled"],
        "mutation_batch_id": batch.batch_id,
        "mutations_generated": len(batch.records),
        "mutations_valid": len(batch.valid_records()),
        "mutations_rejected": len(batch.rejected_records()),
        "best_parent": parent_id,
        "best_mutation": best_scorecard.strategy_id,
        "best_delta": best_scorecard.score_delta,
        "parent_vs_mutation_comparison": comparison,
        "family_mutation_coverage": family_coverage,
        "failure_modes_detected": len(failure_registry.failure_modes),
        "live_blocked": safety["live_blocked"],
        "proof_record_path": str(proof_path),
        "mutation_registry_path": str(registry_path),
        "failure_mode_registry_path": str(failure_mode_path),
        "promotion_decisions": promotion_decisions,
        "rejected_mutation_summary": rejected_summary,
        "failure_mode_summary": failure_summary,
        "source_scorecard_summary": source_summary,
        "pattern_recognition_summary": pattern_summary,
        "safety_state": safety,
        "reproducibility_hash": repro,
    }
    ProofLedger(proof_path).append(_build_proof_entry(summary, batch, registry_record))

    # Refresh tournament/champion proof once failure and population registries exist.
    refreshed = run_fixture_tournament()
    summary["refreshed_tournament_proof_path"] = refreshed["proof_record_path"]
    summary["refreshed_champion_registry_path"] = refreshed["champion_registry_path"]
    return summary


def main() -> None:
    print(json.dumps(run_mutation_population_bundle(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
