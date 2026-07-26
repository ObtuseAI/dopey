"""Integration coverage for mutation genealogy and budget telemetry."""
from __future__ import annotations

import json
from pathlib import Path

from dopey_evolution.mutation_genealogy import build_mutation_genealogy


def test_mutation_genealogy_exposes_edges_rejections_and_trial_budget(tmp_path: Path) -> None:
    registry = tmp_path / "mutation_registry.jsonl"
    dossier = tmp_path / "latest_dossier.json"
    output = tmp_path / "mutation_genealogy.json"
    registry_record = {
        "batch_id": "batch-test",
        "mutations_generated": 3,
        "mutations_valid": 2,
        "mutations_rejected": 1,
        "scorecards": [{
            "strategy_id": "genome-alpha-spy-fixture-v1-mut-one",
            "parent_strategy_id": "genome-alpha-spy-fixture-v1",
            "family": "alpha",
            "adjusted_score": 0.6,
            "score_delta": 0.1,
            "promotion_decision": "offline_mutation_champion",
            "reasons": ["improved deterministic score"],
            "failure_constraint_penalty": 0.0,
        }, {
            "strategy_id": "genome-alpha-spy-fixture-v1-mut-two",
            "parent_strategy_id": "genome-alpha-spy-fixture-v1",
            "family": "alpha",
            "adjusted_score": 0.5,
            "score_delta": 0.0,
            "promotion_decision": "degraded",
            "reasons": ["did not improve"],
            "failure_constraint_penalty": 0.1,
        }],
        "ranking": [{
            "strategy_id": "genome-alpha-spy-fixture-v1-mut-one",
            "mutation_id": "mut-one",
            "mutation_type": "threshold",
            "walk_forward_overall": 0.6,
            "slippage_robustness_score": 0.7,
            "average_liquidity_score": 0.8,
            "parameters": {"entry_rule": "x", "mutation_id": "mut-one"},
        }, {
            "strategy_id": "genome-alpha-spy-fixture-v1-mut-two",
            "mutation_id": "mut-two",
            "mutation_type": "threshold",
            "walk_forward_overall": 0.5,
            "slippage_robustness_score": 0.6,
            "average_liquidity_score": 0.7,
            "parameters": {"entry_rule": "y", "mutation_id": "mut-two"},
        }],
        "promotion_decisions": {
            "genome-alpha-spy-fixture-v1-mut-one": "offline_mutation_champion",
            "genome-alpha-spy-fixture-v1-mut-two": "degraded",
            "genome-alpha-spy-fixture-v1-mut-unsafe": "rejected",
        },
        "rejected_mutations": [{
            "reasons_by_id": {"genome-alpha-spy-fixture-v1-mut-unsafe": ["undefined risk forbidden"]},
        }],
    }
    registry.write_text(json.dumps(registry_record, sort_keys=True) + "\n", encoding="utf-8")
    dossier.write_text(json.dumps({
        "frontier_status": "diagnostic_only_no_eligible_candidates",
        "frontier_candidate_ids": ["breakout|long_call"],
    }), encoding="utf-8")

    result = build_mutation_genealogy(registry, dossier, output)

    assert result["explorer_status"] == "complete"
    assert result["historical_search_budget"]["mutation_attempt_count"] == 3
    assert result["historical_search_budget"]["trial_accounting_complete"] is True
    assert result["pruned_branch_count"] == 2
    assert "genome-alpha-spy-fixture-v1-mut-one" in result["mutation_pareto_frontier_ids"]
    assert result["search_method"] == "deterministic_bounded_mutation_graph_not_a_star"
    assert len(result["generation_history"]) == 1
    assert result["generation_history"][0]["record_hash"]
    assert result["champion_dynamics"]["stability_claim_allowed"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["promotion_allowed"] is False
