"""Integration coverage for autonomous promotion and recursive strategy invention."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from dopey.autoresearch.invention import invent_strategy_candidates
from dopey.autoresearch.experiment_runner import (
    run_deterministic_experiment_evaluation,
)
from dopey.autoresearch.evidence_synthesis import synthesize_promotion_evidence
from dopey.autoresearch.runtime import run_autoresearch_cycle, write_blocked_autoresearch_cycle
from dopey.autoresearch.schema import ResearchFinding
from dopey.autoresearch.taxonomy import RESEARCH_LINEAGES, build_seed_strategies
from dopey.autoresearch.task_suite import build_evaluation_task_suite
from dopey.promotion.gates import evaluate_strategy_promotion
from dopey.promotion.cycle import run_autonomous_promotion_cycle
from dopey.promotion.registry import append_activation_decision
from dopey.promotion.runtime import build_autonomous_promotion_matrix
from dopey.promotion.schema import (
    StrategyPromotionEvidence,
    SymbolPromotionEvidence,
    SymbolStrategyPromotionEvidence,
)
from dopey.promotion.thresholds import AUTONOMOUS_PROMOTION_THRESHOLDS


def _common() -> dict[str, object]:
    return {
        "deterministic_replay": True,
        "leakage_detected": False,
        "revised_data_contamination": False,
        "reward_hacking_detected": False,
        "causal_confidence": 0.82,
        "calibration_error": 0.06,
        "independence_score": 0.75,
        "missing_fraction": 0.01,
        "after_cost_gain": 0.02,
        "contested_gain": 0.006,
        "confidence_interval_lower": 0.003,
    }


def _symbol() -> SymbolPromotionEvidence:
    return cast(SymbolPromotionEvidence, {
        **_common(),
        "symbol_id": "SPY",
        "history_rows": 1_500,
        "replay_samples": 500,
        "private_samples": 200,
        "external_samples": 100,
        "forward_samples": 80,
        "independent_strategies": 4,
    })


def _strategy() -> StrategyPromotionEvidence:
    return cast(StrategyPromotionEvidence, {
        **_common(),
        "strategy_id": "strategy:structural_trend:qualified",
        "lineage_id": "structural_trend",
        "backtest_samples": 1_000,
        "private_samples": 300,
        "external_samples": 120,
        "forward_samples": 90,
        "symbol_count": 12,
        "era_count": 5,
        "regime_count": 4,
        "transfer_score": 0.80,
        "complexity_score": 0.20,
        "abstention_rate": 0.35,
        "evaluator_independent": True,
    })


def _pair() -> SymbolStrategyPromotionEvidence:
    return cast(SymbolStrategyPromotionEvidence, {
        **_common(),
        "symbol_id": "SPY",
        "strategy_id": "strategy:structural_trend:qualified",
        "forward_samples": 40,
        "regime_count": 3,
    })


def test_three_gate_matrix_activates_research_without_human_or_execution_authority(
    tmp_path: Path,
) -> None:
    matrix = build_autonomous_promotion_matrix(
        (_symbol(),),
        (_strategy(),),
        (_pair(),),
        AUTONOMOUS_PROMOTION_THRESHOLDS,
    )

    assert matrix["activated_symbol_ids"] == ["SPY"]
    assert matrix["activated_strategy_ids"] == ["strategy:structural_trend:qualified"]
    assert matrix["activated_symbol_strategy_ids"] == ["SPY::strategy:structural_trend:qualified"]
    assert matrix["automatic_research_activation_count"] == 1
    assert matrix["human_review_required"] is False
    assert matrix["candidate_self_activation_allowed"] is False
    assert matrix["readiness_effect"] == "none"
    assert matrix["execution_effect"] == "none"
    assert matrix["live_blocked"] is True

    decision = matrix["symbol_strategy_gates"][0]
    registry = tmp_path / "activation_decisions.jsonl"
    assert append_activation_decision(registry, decision) is True
    assert append_activation_decision(registry, decision) is False
    assert len(registry.read_text(encoding="utf-8").splitlines()) == 1

    evidence_path = tmp_path / "promotion_evidence.json"
    evidence_path.write_text(
        json.dumps({"symbols": [_symbol()], "strategies": [_strategy()], "pairs": [_pair()]}),
        encoding="utf-8",
    )
    cycle = run_autonomous_promotion_cycle(
        evidence_path,
        tmp_path / "promotion",
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert cycle["cycle_status"] == "evaluation_complete_activated"
    assert cycle["automatic_research_activation_count"] == 1
    assert cycle["human_review_required"] is False
    assert cycle["evaluation_status"] == "complete"


def test_promotion_cycle_preserves_missing_evidence_as_an_explicit_nonactivation(
    tmp_path: Path,
) -> None:
    cycle = run_autonomous_promotion_cycle(
        tmp_path / "missing.json",
        tmp_path / "promotion",
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert cycle["cycle_status"] == "missing_promotion_evidence"
    assert cycle["automatic_research_activation_count"] == 0
    assert cycle["live_blocked"] is True


def test_backtest_only_or_unsafe_strategy_cannot_activate() -> None:
    backtest_only = _strategy()
    backtest_only["private_samples"] = 0
    backtest_only["external_samples"] = 0
    backtest_only["forward_samples"] = 0
    replay_gate = evaluate_strategy_promotion(backtest_only, AUTONOMOUS_PROMOTION_THRESHOLDS)
    assert replay_gate["state"] == "REPLAY_VALIDATED"
    assert replay_gate["automatic_research_activation_allowed"] is False

    unsafe = _strategy()
    unsafe["leakage_detected"] = True
    unsafe_gate = evaluate_strategy_promotion(unsafe, AUTONOMOUS_PROMOTION_THRESHOLDS)
    assert unsafe_gate["state"] == "QUARANTINED"
    assert unsafe_gate["failed_thresholds"] == ["leakage_detected"]

    blocked_matrix = build_autonomous_promotion_matrix(
        (_symbol(),),
        (backtest_only,),
        (_pair(),),
        AUTONOMOUS_PROMOTION_THRESHOLDS,
    )
    pair_gate = blocked_matrix["symbol_strategy_gates"][0]
    assert pair_gate["automatic_research_activation_allowed"] is False
    assert "strategy_gate" in pair_gate["failed_thresholds"]


def test_recursive_invention_preserves_lineage_diversity_and_hidden_evaluator_separation(
    tmp_path: Path,
) -> None:
    seeds = build_seed_strategies()
    candidates = invent_strategy_candidates(seeds, (), len(RESEARCH_LINEAGES), 1)
    assert {record["lineage_id"] for record in candidates} == {
        record["lineage_id"] for record in RESEARCH_LINEAGES
    }
    assert all(record["activation_state"] == "EXPERIMENTAL" for record in candidates)
    assert all(record["candidate_may_grade_itself"] is False for record in candidates)

    finding: ResearchFinding = {
        "finding_id": "failure-1",
        "finding_type": "FAILURE",
        "lineage_id": "technical_momentum",
        "target_gene": "volume_confirmation",
        "direction": "require_independent_participation",
        "evidence_id": "settlement:failure-1",
    }
    steered = invent_strategy_candidates(seeds, (finding,), 1, 2)
    assert steered[0]["mutation_operator"] == "repair_failure"
    assert steered[0]["evidence_parent_ids"] == ("settlement:failure-1",)

    success_finding: ResearchFinding = {
        "finding_id": "success-1",
        "finding_type": "SUCCESS",
        "lineage_id": "technical_momentum",
        "target_gene": "volume_confirmation",
        "direction": "retain_and_retest_on_new_forward_data",
        "evidence_id": "evaluation:success-1",
    }
    success_steered = invent_strategy_candidates(
        seeds,
        (success_finding,),
        len(RESEARCH_LINEAGES) * 2,
        3,
    )
    momentum_candidates = tuple(
        candidate
        for candidate in success_steered
        if candidate["lineage_id"] == "technical_momentum"
    )
    assert len(momentum_candidates) == 2
    assert len({candidate["strategy_id"] for candidate in momentum_candidates}) == 2
    assert all(
        candidate["mutation_operator"] == "retain_success"
        for candidate in momentum_candidates
    )

    tasks = build_evaluation_task_suite()
    private = next(record for record in tasks if record["partition"] == "PRIVATE_SELECTION")
    external = next(record for record in tasks if record["partition"] == "EXTERNAL_GENERALIZATION")
    assert private["selection_authority"] is True
    assert private["item_level_feedback_visible"] is False
    assert "future_data_trap" in private["required_checks"]
    assert external["selection_authority"] is False

    cycle = run_autoresearch_cycle(
        tmp_path,
        (finding,),
        len(RESEARCH_LINEAGES),
        3,
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert cycle["cycle_status"] == "experiments_queued"
    assert cycle["automatic_research_activation_count"] == 0
    assert cycle["human_review_required_for_qualified_activation"] is False
    assert cycle["paper_only"] is True and cycle["live_blocked"] is True
    assert json.loads((tmp_path / "latest_cycle.json").read_text(encoding="utf-8"))["cycle_hash"] == cycle["cycle_hash"]

    champion = dict(seeds[0])
    champion["activation_state"] = "RESEARCH_APPROVED"
    champion["automatic_research_activation_allowed"] = True
    (tmp_path / "champion_strategies.json").write_text(
        json.dumps([champion]),
        encoding="utf-8",
    )
    recursive_cycle = run_autoresearch_cycle(
        tmp_path,
        (),
        len(RESEARCH_LINEAGES),
        4,
        datetime(2026, 7, 15, 16, 0, tzinfo=timezone.utc),
    )
    momentum_child = next(
        record for record in recursive_cycle["candidates"]
        if record["lineage_id"] == champion["lineage_id"]
    )
    assert momentum_child["parent_ids"] == (champion["strategy_id"],)
    assert recursive_cycle["parent_pool_status"] == "approved_champions_plus_seeds"
    assert recursive_cycle["approved_champion_count"] == 1


def test_missing_validated_findings_blocks_generation_without_candidates(tmp_path: Path) -> None:
    blocked = write_blocked_autoresearch_cycle(
        tmp_path,
        tmp_path / "missing_research_findings.json",
        1,
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert blocked["cycle_status"] == "blocked_missing_validated_research_findings"
    assert blocked["generation_started"] is False
    assert blocked["candidate_count"] == 0
    assert blocked["automatic_research_activation_count"] == 0
    assert blocked["execution_effect"] == "none"
    assert blocked["paper_only"] is True and blocked["live_blocked"] is True


def test_deterministic_experiment_runner_closes_feedback_loop_on_pinned_history(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "autoresearch"
    cycle = run_autoresearch_cycle(
        output_root,
        (),
        len(RESEARCH_LINEAGES),
        1,
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    history_root = tmp_path / "history"
    raw_root = history_root / "raw"
    raw_root.mkdir(parents=True)
    data_files: list[dict[str, object]] = []
    symbol_slopes = {"SPY": 0.5, "QQQ": 0.8, "AAPL": 1.0, "MSFT": 1.2}
    for symbol, slope in symbol_slopes.items():
        rows = ["date,symbol,open,high,low,close,adjusted_close,volume,source"]
        for index in range(220):
            close = 50.0 + slope * index
            rows.append(
                f"2025-{1 + index // 28:02d}-{1 + index % 28:02d},{symbol},"
                f"{close - 0.2},{close + 0.1},{close - 0.3},{close},{close},"
                f"{1_000_000 + index * 1_000},fixture"
            )
        payload = ("\n".join(rows) + "\n").encode("utf-8")
        path = raw_root / f"{symbol}.csv"
        path.write_bytes(payload)
        data_files.append(
            {
                "format": "csv",
                "path": f"raw/{symbol}.csv",
                "row_count": 220,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source": "fixture",
                "symbols": [symbol],
            }
        )
    manifest_path = history_root / "history_dataset_manifest.json"
    manifest_path.write_text(
        json.dumps({"data_files": data_files}),
        encoding="utf-8",
    )
    findings_path = tmp_path / "vnext" / "research_findings.json"

    evaluation = run_deterministic_experiment_evaluation(
        output_root / "experiment_ledger.jsonl",
        manifest_path,
        history_root,
        findings_path,
        output_root,
        datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc),
    )

    assert evaluation["evaluation_status"] == "complete"
    assert evaluation["source_cycle_hash"] == cycle["cycle_hash"]
    assert evaluation["compiled_lineage_count"] == 2
    assert evaluation["finding_count"] >= 1
    assert evaluation["candidate_self_grading_allowed"] is False
    assert evaluation["private_selection_item_feedback_exposed"] is False
    assert evaluation["last_verified_at"] == "2026-07-15T13:00:00+00:00"
    assert (
        evaluation["verification_status"]
        == "evaluated_current_source_and_history"
    )
    assert all(
        len(record["candidate_results"]) == record["compiled_candidate_count"]
        for record in evaluation["candidate_evaluations"]
    )
    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    assert {finding["lineage_id"] for finding in findings} <= {
        "technical_momentum",
        "structural_trend",
    }
    evaluation_ledger = output_root / "experiment_evaluation_ledger.jsonl"
    first_line_count = len(evaluation_ledger.read_text(encoding="utf-8").splitlines())
    repeated = run_deterministic_experiment_evaluation(
        output_root / "experiment_ledger.jsonl",
        manifest_path,
        history_root,
        findings_path,
        output_root,
        datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc),
    )
    assert repeated["evaluation_hash"] == evaluation["evaluation_hash"]
    assert repeated["last_verified_at"] == "2026-07-15T14:00:00+00:00"
    assert (
        repeated["verification_status"]
        == "verified_source_and_history_unchanged"
    )
    assert len(evaluation_ledger.read_text(encoding="utf-8").splitlines()) == first_line_count
    verification_ledger = (
        output_root / "experiment_evaluation_verification_ledger.jsonl"
    )
    assert len(verification_ledger.read_text(encoding="utf-8").splitlines()) == 1


def test_promotion_evidence_synthesis_preserves_missing_evidence_without_fake_gates(
    tmp_path: Path,
) -> None:
    autoresearch_root = tmp_path / "autoresearch"
    cycle = run_autoresearch_cycle(
        autoresearch_root,
        (),
        4,
        1,
        datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    predictions = tmp_path / "forward_predictions.jsonl"
    predictions.write_text(
        json.dumps(
            {
                "prediction_id": "prediction-1",
                "symbol": "SPY",
                "prediction_status": "pending_forward_settlement",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    history_root = tmp_path / "history"
    history_root.mkdir()
    (history_root / "SPY.csv").write_text("date,close\n2026-01-01,1\n", encoding="utf-8")
    output_path = autoresearch_root / "promotion_evidence.json"

    synthesis = synthesize_promotion_evidence(
        autoresearch_root / "latest_cycle.json",
        predictions,
        history_root,
        output_path,
        datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc),
    )

    assert synthesis["synthesis_status"] == "complete"
    assert synthesis["eligibility_status"] == "no_eligible_records"
    assert synthesis["symbols"] == []
    assert synthesis["strategies"] == []
    assert synthesis["pairs"] == []
    assert synthesis["eligible_pair_count"] == 0
    assert synthesis["missing_evidence_fabricated"] is False
    assert synthesis["backtest_counted_as_forward"] is False
    assert synthesis["unresolved_symbols"][0]["pending_forward_samples"] == 1
    assert len(synthesis["unresolved_strategies"]) == cycle["candidate_count"]

    promotion = run_autonomous_promotion_cycle(
        output_path,
        autoresearch_root,
        datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc),
    )
    assert promotion["cycle_status"] == "evaluation_complete_no_activations"
    assert promotion["automatic_research_activation_count"] == 0
