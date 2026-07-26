"""Integration coverage for the domain-independent intelligence research engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from dopey.intelligence_research.dopey_adapter import build_dopey_knowledge_state
from dopey.intelligence_research.evaluator import evaluate_cognitive_method
from dopey.intelligence_research.execution import (
    _execute_policy,
    compile_cognitive_method_policy,
)
from dopey.intelligence_research.evidence_cycle import (
    run_cognitive_evidence_cycle,
    synthesize_cognitive_method_evidence,
)
from dopey.intelligence_research.genome import build_cognitive_genome
from dopey.intelligence_research.runtime import run_intelligence_research_cycle
from dopey.intelligence_research.schema import (
    BoundCognitiveTrialResult,
    CognitiveMethodEvidence,
)
from dopey.intelligence_research.theory import build_theory_candidate
from dopey.intelligence_research.task_store import (
    build_visible_task_suite,
    load_independent_task_store,
    write_task_store,
)
from dopey.protocols.identity import canonical_hash


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_cognitive_policy_rejects_unknown_operation() -> None:
    candidate = cast(
        object,
        {
            "candidate_id": "candidate",
            "support": 0.5,
        },
    )
    policy = cast(
        object,
        {
            "policy_id": "policy",
            "method_id": "method",
            "operator": "ANALOGY",
            "nodes": (
                {
                    "operation": "UNKNOWN",
                    "feature": "support",
                    "weight": 1.0,
                },
            ),
        },
    )

    with pytest.raises(ValueError, match="unsupported cognitive policy operation"):
        _execute_policy(candidate, policy)


def _passing_evidence(method_id: str) -> CognitiveMethodEvidence:
    return cast(
        CognitiveMethodEvidence,
        {
            "method_id": method_id,
            "source_discovery_cycle_hash": "1" * 64,
            "source_task_store_content_hash": "2" * 64,
            "promotion_metrics_source": (
                "worst_case_across_trusted_independent_hidden_partitions"
            ),
            "hidden_partition_metrics": {},
            "visible_samples": 100,
            "private_samples": 80,
            "external_samples": 60,
            "real_task_samples": 40,
            "domain_count": 4,
            "replication_count": 7,
            "effect_size": 0.09,
            "effect_interval_lower": 0.02,
            "calibration_improvement": 0.04,
            "transfer_score": 0.78,
            "efficiency_score": 0.72,
            "complexity_score": 0.21,
            "deterministic": True,
            "evaluator_independent": True,
            "reward_hacking_detected": False,
            "constitutional_violation": False,
        },
    )


def _run_discovery_cycle(
    root: Path,
    issued_at: datetime,
    generation: int,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    readiness = root / "readiness.json"
    schedule = root / "schedule.json"
    autoresearch = root / "autoresearch.json"
    promotion = root / "promotion.json"
    _write(readiness, {"bottlenecks": []})
    _write(schedule, {"lane_statuses": {}})
    _write(autoresearch, {"candidate_count": 2, "finding_status": "evidence_steered"})
    _write(promotion, {"cycle_status": "evaluation_complete_no_activations"})
    state = build_dopey_knowledge_state(
        readiness,
        schedule,
        autoresearch,
        promotion,
        root / "llm_research.json",
        issued_at,
    )
    return run_intelligence_research_cycle(
        state,
        root / "discovery",
        4,
        4,
        2,
        generation,
        issued_at,
    )


def _bound_trial(
    index: int,
    partition: str,
    domain_id: str,
    quality_delta: float,
    evaluator_independent: bool,
    source_discovery_cycle_hash: str,
    source_task_store_content_hash: str,
) -> BoundCognitiveTrialResult:
    challenger_correct = quality_delta > 0.0
    execution_trial_id = f"execution-trial:{index}"
    identity = canonical_hash(
        {
            "execution_trial_id": execution_trial_id,
            "source_discovery_cycle_hash": source_discovery_cycle_hash,
            "source_task_store_content_hash": source_task_store_content_hash,
        }
    )
    return {
        "trial_id": f"cognitive-trial:{identity[:24]}",
        "execution_trial_id": execution_trial_id,
        "source_discovery_cycle_hash": source_discovery_cycle_hash,
        "source_task_store_content_hash": source_task_store_content_hash,
        "experiment_id": "experiment:test",
        "method_id": "method:test",
        "task_id": f"task:{index}",
        "domain_id": domain_id,
        "partition": partition,
        "baseline_candidate_id": "baseline",
        "challenger_candidate_id": "challenger",
        "expected_candidate_id": ("challenger" if challenger_correct else "baseline"),
        "baseline_correct": not challenger_correct,
        "challenger_correct": challenger_correct,
        "quality_delta": quality_delta,
        "calibration_delta": 0.1,
        "cost_delta": 0.1,
        "deterministic": True,
        "evaluator_independent": evaluator_independent,
    }


def test_dopey_domain_drives_scientific_discovery_without_self_promotion(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.json"
    schedule = tmp_path / "schedule.json"
    autoresearch = tmp_path / "autoresearch.json"
    promotion = tmp_path / "promotion.json"
    _write(
        readiness,
        {
            "bottlenecks": [
                {
                    "bottleneck_id": "resolved_context_decisions",
                    "remaining": 200,
                    "required": 200,
                },
                {
                    "bottleneck_id": "already_resolved",
                    "remaining": 0,
                    "required": 10,
                },
            ]
        },
    )
    _write(
        schedule,
        {
            "lane_statuses": {
                "nightly_validation": {"status": "inconclusive_timeout"},
                "autonomous_strategy_research": {
                    "status": "degraded_evidence",
                    "evidence_verification": {
                        "verification_status": "stale"
                    },
                },
            }
        },
    )
    _write(
        autoresearch,
        {
            "candidate_count": 24,
            "finding_status": "missing_findings_exploration_only",
        },
    )
    _write(promotion, {"cycle_status": "missing_promotion_evidence"})
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    state = build_dopey_knowledge_state(
        readiness,
        schedule,
        autoresearch,
        promotion,
        tmp_path / "llm_research.json",
        issued_at,
    )

    signal_types = {signal["signal_type"].value for signal in state["signals"]}
    assert {
        "BOTTLENECK",
        "CONTRADICTION",
        "UNKNOWN",
        "REPEATED_FAILURE",
        "CAPABILITY_GAP",
        "OPPORTUNITY",
    } <= signal_types
    bottlenecks = tuple(
        signal
        for signal in state["signals"]
        if signal["signal_type"].value == "BOTTLENECK"
    )
    assert len(bottlenecks) == 1
    assert bottlenecks[0]["severity"] == 1.0
    failures = tuple(
        signal
        for signal in state["signals"]
        if signal["signal_type"].value == "REPEATED_FAILURE"
    )
    assert len(failures) == 2
    assert any(
        "inconclusive_timeout" in signal["statement"] for signal in failures
    )
    assert any("degraded_evidence" in signal["statement"] for signal in failures)

    cycle = run_intelligence_research_cycle(
        state, tmp_path / "output", 8, 16, 2, 1, issued_at
    )
    assert cycle["cycle_status"] == "cognitive_experiments_queued"
    assert cycle["mission"] == "discover_better_ways_of_discovering"
    assert len(cycle["discovery_questions"]) == len(state["signals"])
    assert len(cycle["cognitive_hypotheses"]) == 16
    assert (
        len({record["creativity_operator"] for record in cycle["cognitive_hypotheses"]})
        == 8
    )
    assert len(cycle["experiments"]) == 16
    assert all(
        record["cross_domain_promotion_blocked"] is False
        for record in cycle["experiments"]
    )
    assert cycle["automatic_cognitive_method_activation_count"] == 0
    assert cycle["human_review_required_for_qualified_activation"] is False
    assert cycle["authority_effect"] == "none"
    assert cycle["paper_only"] is True and cycle["live_blocked"] is True
    assert (tmp_path / "output" / "cognitive_world_model.json").exists()


def test_cognitive_method_requires_cross_domain_replication_before_theory(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.json"
    schedule = tmp_path / "schedule.json"
    autoresearch = tmp_path / "autoresearch.json"
    promotion = tmp_path / "promotion.json"
    _write(readiness, {"bottlenecks": []})
    _write(schedule, {"lane_statuses": {}})
    _write(autoresearch, {"candidate_count": 1, "finding_status": "evidence_steered"})
    _write(promotion, {"cycle_status": "evaluation_complete_no_activations"})
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    state = build_dopey_knowledge_state(
        readiness,
        schedule,
        autoresearch,
        promotion,
        tmp_path / "llm_research.json",
        issued_at,
    )
    cycle = run_intelligence_research_cycle(
        state, tmp_path / "output", 4, 4, 3, 1, issued_at
    )
    hypothesis = cycle["cognitive_hypotheses"][0]
    policy = compile_cognitive_method_policy(hypothesis)
    assert policy["method_id"] == hypothesis["method_id"]
    assert policy["nodes"][0]["operation"] == "BASELINE_PRIOR"
    assert sum(node["weight"] for node in policy["nodes"]) == pytest.approx(1.0)

    blocked_evidence = _passing_evidence(hypothesis["method_id"])
    blocked_evidence["domain_count"] = 1
    blocked = evaluate_cognitive_method(blocked_evidence)
    assert blocked["promotion_state"] == "REAL_TASK_VALIDATED"
    assert blocked["automatic_cognitive_method_activation_allowed"] is False
    assert "domain_count" in blocked["failed_thresholds"]

    evidence = _passing_evidence(hypothesis["method_id"])
    evaluation = evaluate_cognitive_method(evidence)
    assert evaluation["promotion_state"] == "THEORY_CANDIDATE"
    assert evaluation["automatic_cognitive_method_activation_allowed"] is True
    assert evaluation["human_review_required"] is False
    theory = build_theory_candidate(hypothesis, evidence, evaluation)
    assert theory["theory_state"] == "GENERAL_LAW_CANDIDATE"
    assert theory["authority_effect"] == "none"

    genome = build_cognitive_genome(
        (),
        1,
        (hypothesis["method_id"],),
        ("scientific_discovery_loop_v1",),
        (hypothesis["creativity_operator"],),
        ("uncertainty_first_planning_v1",),
        ("independent_hidden_evaluator_v1",),
        ("scientific_theory_memory_v1",),
        ("competing_cognitive_organism_v1",),
    )
    assert genome["authority_surfaces_evolvable"] is False
    assert genome["truth_surfaces_evolvable"] is False


def test_visible_cross_domain_execution_synthesizes_evidence_but_cannot_activate(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.json"
    schedule = tmp_path / "schedule.json"
    autoresearch = tmp_path / "autoresearch.json"
    promotion = tmp_path / "promotion.json"
    _write(readiness, {"bottlenecks": []})
    _write(schedule, {"lane_statuses": {}})
    _write(autoresearch, {"candidate_count": 2, "finding_status": "evidence_steered"})
    _write(promotion, {"cycle_status": "evaluation_complete_no_activations"})
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    state = build_dopey_knowledge_state(
        readiness,
        schedule,
        autoresearch,
        promotion,
        tmp_path / "llm_research.json",
        issued_at,
    )
    output_root = tmp_path / "output"
    run_intelligence_research_cycle(state, output_root, 4, 8, 2, 1, issued_at)

    evaluation = run_cognitive_evidence_cycle(
        output_root / "latest_cycle.json",
        tmp_path / "empty-independent-store",
        output_root,
        16,
        issued_at,
    )

    assert (
        evaluation["cycle_status"]
        == "visible_evaluation_complete_waiting_independent_partitions"
    )
    assert evaluation["evidence_status"] == "evaluation_complete"
    assert evaluation["visible_task_count"] == 384
    assert evaluation["trial_count"] == 384
    assert evaluation["automatic_cognitive_method_activation_count"] == 0
    assert evaluation["missing_independent_partitions"] == [
        "PRIVATE_SELECTION",
        "EXTERNAL_GENERALIZATION",
        "REAL_TASK_FORWARD",
    ]
    assert all(
        record["visible_samples"] == 48 for record in evaluation["method_evidence"]
    )
    assert all(
        record["promotion_state"] == "QUARANTINED"
        for record in evaluation["evaluations"]
    )
    assert all(
        record["failed_thresholds"] == ["evaluator_independent"]
        for record in evaluation["evaluations"]
    )
    assert (
        json.loads(
            (output_root / "activated_cognitive_genomes.json").read_text(
                encoding="utf-8"
            )
        )
        == []
    )


def test_relabelled_visible_tasks_are_rejected_as_partition_contamination(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.json"
    schedule = tmp_path / "schedule.json"
    autoresearch = tmp_path / "autoresearch.json"
    promotion = tmp_path / "promotion.json"
    _write(readiness, {"bottlenecks": []})
    _write(schedule, {"lane_statuses": {}})
    _write(autoresearch, {"candidate_count": 2, "finding_status": "evidence_steered"})
    _write(promotion, {"cycle_status": "evaluation_complete_no_activations"})
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    state = build_dopey_knowledge_state(
        readiness,
        schedule,
        autoresearch,
        promotion,
        tmp_path / "llm_research.json",
        issued_at,
    )
    output_root = tmp_path / "output"
    run_intelligence_research_cycle(state, output_root, 2, 2, 2, 1, issued_at)
    task_store_root = tmp_path / "task-store"
    base_tasks = build_visible_task_suite(16)
    partition_files = {
        "PRIVATE_SELECTION": "private_selection_tasks.jsonl",
        "EXTERNAL_GENERALIZATION": "external_generalization_tasks.jsonl",
        "REAL_TASK_FORWARD": "real_task_forward_tasks.jsonl",
    }
    for partition, filename in partition_files.items():
        tasks = []
        for task in base_tasks:
            candidate_id_map = {
                candidate["candidate_id"]: (
                    f"{partition.lower()}:{candidate['candidate_id']}"
                )
                for candidate in task["candidates"]
            }
            tasks.append(
                {
                    **task,
                    "task_id": f"{partition.lower()}:{task['task_id']}",
                    "domain_id": f"{partition.lower()}:{task['domain_id']}",
                    "task_family": f"{partition.lower()}:{task['task_family']}",
                    "partition": partition,
                    "expected_candidate_id": candidate_id_map[
                        task["expected_candidate_id"]
                    ],
                    "candidates": tuple(
                        {
                            **candidate,
                            "candidate_id": candidate_id_map[candidate["candidate_id"]],
                        }
                        for candidate in task["candidates"]
                    ),
                    "evaluator_version": task["evaluator_version"],
                    "source_provenance": f"independently_sealed_{partition.lower()}_v1",
                }
            )
        write_task_store(task_store_root / filename, tuple(tasks))

    with pytest.raises(ValueError, match="task contamination"):
        run_cognitive_evidence_cycle(
            output_root / "latest_cycle.json",
            task_store_root,
            output_root,
            16,
            issued_at,
        )


def test_local_raw_task_store_cannot_claim_independent_evaluator_status(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.json"
    schedule = tmp_path / "schedule.json"
    autoresearch = tmp_path / "autoresearch.json"
    promotion = tmp_path / "promotion.json"
    _write(readiness, {"bottlenecks": []})
    _write(schedule, {"lane_statuses": {}})
    _write(autoresearch, {"candidate_count": 2, "finding_status": "evidence_steered"})
    _write(promotion, {"cycle_status": "evaluation_complete_no_activations"})
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    state = build_dopey_knowledge_state(
        readiness,
        schedule,
        autoresearch,
        promotion,
        tmp_path / "llm_research.json",
        issued_at,
    )
    output_root = tmp_path / "output"
    run_intelligence_research_cycle(state, output_root, 2, 2, 2, 1, issued_at)
    task_store_root = tmp_path / "task-store"
    base_tasks = build_visible_task_suite(16)
    partition_files = {
        "PRIVATE_SELECTION": "private_selection_tasks.jsonl",
        "EXTERNAL_GENERALIZATION": "external_generalization_tasks.jsonl",
        "REAL_TASK_FORWARD": "real_task_forward_tasks.jsonl",
    }
    for partition_index, (partition, filename) in enumerate(partition_files.items()):
        tasks = []
        for task_index, task in enumerate(base_tasks):
            candidates = [dict(candidate) for candidate in task["candidates"]]
            candidates[0]["novelty"] = (
                0.1 + (partition_index * len(base_tasks) + task_index) / 10_000
            )
            tasks.append(
                {
                    **task,
                    "task_id": f"{partition.lower()}:{task['task_id']}",
                    "partition": partition,
                    "candidates": tuple(candidates),
                    "source_provenance": f"local_raw_{partition.lower()}_v1",
                }
            )
        write_task_store(task_store_root / filename, tasks)

    evaluation = run_cognitive_evidence_cycle(
        output_root / "latest_cycle.json",
        task_store_root,
        output_root,
        16,
        issued_at,
    )

    assert (
        evaluation["cycle_status"]
        == "evaluation_complete_blocked_untrusted_independent_task_store"
    )
    assert evaluation["automatic_cognitive_method_activation_count"] == 0
    assert evaluation["independent_task_store_audit"]["evaluator_independent"] is False
    assert (
        evaluation["independent_task_store_audit"]["signature_verification_status"]
        == "not_configured"
    )
    assert (
        evaluation["independent_task_store_audit"]["os_isolation_status"]
        == "not_verified"
    )
    assert all(
        record["promotion_state"] == "QUARANTINED"
        and "evaluator_independent" in record["failed_thresholds"]
        for record in evaluation["evaluations"]
    )


def test_every_hidden_partition_must_pass_without_visible_vote_dilution() -> None:
    source_cycle_hash = "a" * 64
    source_store_hash = "b" * 64
    trials: list[BoundCognitiveTrialResult] = []
    next_index = 0
    partition_specs = (
        ("VISIBLE_DEVELOPMENT", 384, 1.0, False),
        ("PRIVATE_SELECTION", 40, -1.0, True),
        ("EXTERNAL_GENERALIZATION", 30, 1.0, True),
        ("REAL_TASK_FORWARD", 20, 1.0, True),
    )
    for (
        partition,
        sample_count,
        quality_delta,
        evaluator_independent,
    ) in partition_specs:
        for partition_index in range(sample_count):
            next_index += 1
            trials.append(
                _bound_trial(
                    next_index,
                    partition,
                    f"domain:{partition_index % 3}",
                    quality_delta,
                    evaluator_independent,
                    source_cycle_hash,
                    source_store_hash,
                )
            )

    evidence = synthesize_cognitive_method_evidence(
        "method:test",
        trials,
        source_cycle_hash,
        source_store_hash,
    )
    evaluation = evaluate_cognitive_method(evidence)

    assert evidence["effect_size"] == -1.0
    assert (
        evidence["hidden_partition_metrics"]["PRIVATE_SELECTION"]["effect_size"] == -1.0
    )
    assert evaluation["promotion_state"] == "REAL_TASK_VALIDATED"
    assert evaluation["automatic_cognitive_method_activation_allowed"] is False
    assert "effect_size" in evaluation["failed_thresholds"]

    passing_trials = [
        {
            **trial,
            "quality_delta": 1.0,
            "baseline_correct": False,
            "challenger_correct": True,
            "expected_candidate_id": "challenger",
        }
        for trial in trials
    ]
    passing_evidence = synthesize_cognitive_method_evidence(
        "method:test",
        cast(list[BoundCognitiveTrialResult], passing_trials),
        source_cycle_hash,
        source_store_hash,
    )
    passing_evaluation = evaluate_cognitive_method(passing_evidence)

    assert passing_evaluation["promotion_state"] == "THEORY_CANDIDATE"
    assert passing_evaluation["automatic_cognitive_method_activation_allowed"] is True


def test_discovery_cycle_requires_exact_hash_and_binds_ledger_identity(
    tmp_path: Path,
) -> None:
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    discovery_root = tmp_path / "source"
    discovery = _run_discovery_cycle(discovery_root, issued_at, 1)
    discovery_path = discovery_root / "discovery" / "latest_cycle.json"
    evidence_root = tmp_path / "evidence"

    evidence = run_cognitive_evidence_cycle(
        discovery_path,
        tmp_path / "empty-task-store",
        evidence_root,
        2,
        issued_at,
    )

    assert evidence["source_discovery_cycle_hash"] == discovery["cycle_hash"]
    assert all(
        record["source_discovery_cycle_hash"] == discovery["cycle_hash"]
        for record in evidence["method_evidence"]
    )
    first_trial = json.loads(
        (evidence_root / "cognitive_trial_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    identity = canonical_hash(
        {
            "execution_trial_id": first_trial["execution_trial_id"],
            "source_discovery_cycle_hash": discovery["cycle_hash"],
            "source_task_store_content_hash": evidence[
                "source_task_store_content_hash"
            ],
        }
    )
    assert first_trial["trial_id"] == f"cognitive-trial:{identity[:24]}"

    invalid_hash = dict(discovery)
    invalid_hash["cycle_hash"] = "0" * 64
    invalid_hash_path = tmp_path / "invalid-hash.json"
    _write(invalid_hash_path, invalid_hash)
    with pytest.raises(ValueError, match="content hash mismatch"):
        run_cognitive_evidence_cycle(
            invalid_hash_path,
            tmp_path / "empty-task-store",
            tmp_path / "invalid-hash-output",
            2,
            issued_at,
        )
    assert not (tmp_path / "invalid-hash-output").exists()

    unexpected_field = {**discovery, "unexpected": "self-authored-schema"}
    unexpected_body = {
        key: value for key, value in unexpected_field.items() if key != "cycle_hash"
    }
    unexpected_field["cycle_hash"] = canonical_hash(unexpected_body)
    unexpected_path = tmp_path / "unexpected-field.json"
    _write(unexpected_path, unexpected_field)
    with pytest.raises(ValueError, match="invalid schema"):
        run_cognitive_evidence_cycle(
            unexpected_path,
            tmp_path / "empty-task-store",
            tmp_path / "unexpected-field-output",
            2,
            issued_at,
        )
    assert not (tmp_path / "unexpected-field-output").exists()


def test_task_store_content_hash_binds_source_provenance(tmp_path: Path) -> None:
    visible_tasks = build_visible_task_suite(1)
    source_task = visible_tasks[0]
    candidates = [dict(candidate) for candidate in source_task["candidates"]]
    candidates[0]["novelty"] = 0.123456
    base_independent_task = {
        **source_task,
        "task_id": "private-task:content-hash-proof",
        "partition": "PRIVATE_SELECTION",
        "candidates": tuple(candidates),
    }
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_task_store(
        first_root / "private_selection_tasks.jsonl",
        (
            {
                **base_independent_task,
                "source_provenance": "sealed-source:first",
            },
        ),
    )
    write_task_store(
        second_root / "private_selection_tasks.jsonl",
        (
            {
                **base_independent_task,
                "source_provenance": "sealed-source:second",
            },
        ),
    )

    _first_tasks, first_audit = load_independent_task_store(
        first_root,
        visible_tasks,
    )
    _second_tasks, second_audit = load_independent_task_store(
        second_root,
        visible_tasks,
    )

    assert (
        first_audit["task_store_semantic_hash"]
        == second_audit["task_store_semantic_hash"]
    )
    assert (
        first_audit["partition_fingerprint_hashes"]
        == second_audit["partition_fingerprint_hashes"]
    )
    assert (
        first_audit["task_store_content_hash"]
        != second_audit["task_store_content_hash"]
    )
    assert first_audit["task_store_hash"] == first_audit["task_store_content_hash"]


def test_ledger_conflict_cannot_publish_or_partially_append_latest(
    tmp_path: Path,
) -> None:
    issued_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    discovery_root = tmp_path / "source"
    _run_discovery_cycle(discovery_root, issued_at, 1)
    discovery_path = discovery_root / "discovery" / "latest_cycle.json"
    baseline_root = tmp_path / "baseline"
    run_cognitive_evidence_cycle(
        discovery_path,
        tmp_path / "empty-task-store",
        baseline_root,
        2,
        issued_at,
    )
    baseline_cycle = json.loads(
        (baseline_root / "cognitive_evidence_cycle_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    conflicting_cycle = {
        **baseline_cycle,
        "cycle_status": "rewritten_after_evaluation",
    }
    target_root = tmp_path / "target"
    target_root.mkdir(parents=True, exist_ok=True)
    sentinel_latest = {"cycle_status": "prior_verified_latest"}
    _write(target_root / "latest_evidence_cycle.json", sentinel_latest)
    (target_root / "cognitive_evidence_cycle_ledger.jsonl").write_text(
        json.dumps(conflicting_cycle, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicts with existing identity"):
        run_cognitive_evidence_cycle(
            discovery_path,
            tmp_path / "empty-task-store",
            target_root,
            2,
            issued_at,
        )

    assert (
        json.loads(
            (target_root / "latest_evidence_cycle.json").read_text(encoding="utf-8")
        )
        == sentinel_latest
    )
    assert not (target_root / "cognitive_trial_ledger.jsonl").exists()
    assert not (target_root / "cognitive_method_evidence.json").exists()
