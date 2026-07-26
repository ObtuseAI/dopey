"""Focused seed-precommitment coverage for recursive evolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from dopey.chronos.replay import ReplayEra, ReplayRole
from dopey.evolution import runtime
from dopey.evolution.mutations import propose_genome_mutation
from dopey.genome.schema import PromotionState, ResearchGenome, build_research_genome
from dopey.protocols.identity import canonical_hash
from dopey.simulation.replay import build_replay_observation_manifest


MutationSpec = Mapping[str, Any]


def _parent_genome() -> ResearchGenome:
    agents = ("technical_evidence_agent", "adversarial_agent", "synthesizer_agent")
    return build_research_genome(
        (),
        0,
        agents,
        agents,
        ("RSI", "MACD_HISTOGRAM", "BREADTH"),
        ("daily", "weekly", "monthly"),
        700,
        "stop_on_nonpositive_marginal_utility",
        "reliability_bins_v1",
        "weakest_dimension_capped_synthesis",
        "deterministic",
        ("price", "cross_asset", "news"),
        "objective_template_with_boundary_agent",
        "uncertainty_weighted_world_model_v2",
        "breakout_regime_conditioned_v1",
        "deterministic_prompt_bundle_v1",
        "adversarial_veto_then_abstain",
        PromotionState.SHADOW_ONLY,
    )


def _mutation_specs() -> tuple[MutationSpec, ...]:
    return (
        {
            "surface": "evidence_budgets",
            "value": 800,
            "operator_id": "increase-budget-v1",
        },
        {
            "surface": "stopping_policies",
            "value": "stop_on_low_utility_v2",
            "operator_id": "stopping-v2",
        },
    )


def _eras() -> tuple[ReplayEra, ...]:
    return (
        ReplayEra("held-out-a", "2018-01-01", "2020-12-31", ReplayRole.HELD_OUT),
        ReplayEra("held-out-b", "2021-02-01", "2023-12-31", ReplayRole.HELD_OUT),
    )


def _observations() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "child_id": f"seed-panel-replay-{index:02d}",
            "strategy_id": f"breakout-v{index % 2}",
            "setup_family": "volatility_squeeze_breakout",
            "exit_policy": "swing_exit",
            "dte_bucket": 14,
            "moneyness_bucket": "ATM",
            "direction": "bullish",
            "regime": ("low_volatility" if index < 6 else "normal_volatility"),
            "symbol": ("SPY", "QQQ", "IWM", "DIA")[index % 4],
            "era": "held-out-a" if index < 6 else "held-out-b",
            "signal_value": 1.0 if index % 3 else -1.0,
            "outcome_value": 0.02 if index % 3 else -0.015,
            "baseline_value": 0.001,
            "held_out": True,
            "contested_truth": index % 7 == 0,
        }
        for index in range(12)
    )


def _candidate_manifests(
    parent: ResearchGenome,
    mutation_specs: Sequence[MutationSpec],
    eras: tuple[ReplayEra, ...],
) -> dict[str, dict[str, Any]]:
    observations = _observations()
    manifests: dict[str, dict[str, Any]] = {}
    for specification in mutation_specs:
        candidate = propose_genome_mutation(
            parent,
            str(specification["surface"]),
            specification["value"],
            str(specification["operator_id"]),
        )
        challenger = dict(candidate["challenger_genome"])
        candidate_id = str(candidate["candidate_id"])
        manifests[candidate_id] = dict(
            build_replay_observation_manifest(
                candidate_id,
                str(challenger["genome_id"]),
                eras,
                observations,
                "recursive-evolution-seed-commitment-fixture-v1",
                canonical_hash(
                    {"dataset": "recursive-evolution-seed-commitment-fixture-v1"}
                ),
                "protected-seed-commitment-observation-generator-v1",
            )
        )
    return manifests


def _calibration_summary() -> dict[str, Any]:
    return {
        "settled_total": 0,
        "expected_calibration_error": None,
        "minimum_calibration_sample": 30,
    }


def _derive_precommitment(
    parent: ResearchGenome,
    mutation_specs: Sequence[MutationSpec],
    eras: tuple[ReplayEra, ...],
    manifests: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return runtime.derive_recursive_evolution_seed_precommitment(
        parent,
        mutation_specs,
        eras,
        manifests,
    )


def test_seed_precommitment_is_deterministic_and_candidate_order_independent() -> None:
    parent = _parent_genome()
    mutation_specs = _mutation_specs()
    eras = _eras()
    manifests = _candidate_manifests(parent, mutation_specs, eras)

    forward = _derive_precommitment(parent, mutation_specs, eras, manifests)
    repeated = _derive_precommitment(parent, mutation_specs, eras, manifests)
    reversed_order = _derive_precommitment(
        parent,
        tuple(reversed(mutation_specs)),
        eras,
        manifests,
    )
    shared_candidate = propose_genome_mutation(
        parent,
        str(mutation_specs[0]["surface"]),
        mutation_specs[0]["value"],
        str(mutation_specs[0]["operator_id"]),
    )
    shared_candidate_id = str(shared_candidate["candidate_id"])
    one_candidate = _derive_precommitment(
        parent,
        (mutation_specs[0],),
        eras,
        {shared_candidate_id: manifests[shared_candidate_id]},
    )

    assert forward == repeated == reversed_order == one_candidate
    assert forward["caller_selectable_randomization"] is False
    assert forward["fixed_seed_panel_size"] == runtime.FIXED_SEED_PANEL_SIZE
    assert len(forward["seed_panel"]) == runtime.FIXED_SEED_PANEL_SIZE
    assert len(set(forward["seed_panel"])) == runtime.FIXED_SEED_PANEL_SIZE
    assert {
        "candidate_ids",
        "challenger_genome_ids",
        "dataset_id",
        "observation_generator_version",
        "calibration_summary_hash",
        "bootstrap_iterations",
        "null_shifts",
        "familywise_alpha",
        "minimum_sample",
    }.isdisjoint(forward)
    assert forward["precommitment_hash"] == canonical_hash(
        {
            key: value
            for key, value in forward.items()
            if key
            not in {
                "committed_root_seed",
                "precommitment_hash",
                "seed_panel",
                "seed_commitment_id",
            }
        }
    )
    assert forward["committed_root_seed"] == int(
        str(forward["precommitment_hash"])[:16],
        16,
    )


def test_uncommitted_caller_seed_fails_before_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _parent_genome()
    mutation_specs = (_mutation_specs()[0],)
    eras = _eras()
    manifests = _candidate_manifests(parent, mutation_specs, eras)
    precommitment = _derive_precommitment(
        parent,
        mutation_specs,
        eras,
        manifests,
    )
    replay_calls: list[int] = []

    def replay_must_not_run(
        _genome: ResearchGenome,
        _candidate_id: str,
        _eras_value: tuple[ReplayEra, ...],
        _observation_manifest: Mapping[str, Any],
        _evaluation_spec_hash: str,
        _randomization_policy: str,
        _bootstrap_iterations: int,
        evaluation_seed: int,
        _null_shifts: int,
        _familywise_alpha: float,
        _minimum_sample: int,
    ) -> dict[str, Any]:
        replay_calls.append(evaluation_seed)
        raise AssertionError("replay must not run for an uncommitted caller seed")

    monkeypatch.setattr(runtime, "run_isolated_replay", replay_must_not_run)

    with pytest.raises(ValueError, match="does not match"):
        runtime.run_recursive_evolution_cycle(
            parent,
            mutation_specs,
            eras,
            manifests,
            _calibration_summary(),
            8,
            int(precommitment["committed_root_seed"]) + 1,
            3,
            0.05,
            4,
        )

    assert replay_calls == []


def test_cycle_evaluates_complete_fixed_panel_and_selects_worst_result() -> None:
    parent = _parent_genome()
    expanded_mutation_specs = _mutation_specs()
    mutation_specs = (expanded_mutation_specs[0],)
    eras = _eras()
    expanded_manifests = _candidate_manifests(
        parent,
        expanded_mutation_specs,
        eras,
    )
    shared_candidate = propose_genome_mutation(
        parent,
        str(mutation_specs[0]["surface"]),
        mutation_specs[0]["value"],
        str(mutation_specs[0]["operator_id"]),
    )
    shared_candidate_id = str(shared_candidate["candidate_id"])
    manifests = {
        shared_candidate_id: expanded_manifests[shared_candidate_id],
    }
    precommitment = _derive_precommitment(
        parent,
        mutation_specs,
        eras,
        manifests,
    )

    cycle = runtime.run_recursive_evolution_cycle(
        parent,
        mutation_specs,
        eras,
        manifests,
        _calibration_summary(),
        8,
        int(precommitment["committed_root_seed"]),
        3,
        0.05,
        4,
    )
    repeated_cycle = runtime.run_recursive_evolution_cycle(
        parent,
        mutation_specs,
        eras,
        manifests,
        _calibration_summary(),
        8,
        int(precommitment["committed_root_seed"]),
        3,
        0.05,
        4,
    )
    expanded_cycle = runtime.run_recursive_evolution_cycle(
        parent,
        expanded_mutation_specs,
        eras,
        expanded_manifests,
        _calibration_summary(),
        8,
        int(precommitment["committed_root_seed"]),
        3,
        0.05,
        4,
    )

    candidate_id = str(cycle["candidates"][0]["candidate_id"])
    panel_evaluations = cycle["candidate_seed_panel_evaluations"][candidate_id]
    expected_selection = min(
        enumerate(panel_evaluations),
        key=lambda item: (
            float(item[1]["fitness"]["fitness_score"]),
            item[0],
        ),
    )[1]
    assert cycle["seed_precommitment"] == precommitment
    assert cycle == repeated_cycle
    assert expanded_cycle["seed_precommitment"] == precommitment
    assert (
        cycle["candidate_seed_panels"][candidate_id]
        == expanded_cycle["candidate_seed_panels"][candidate_id]
    )
    assert (
        cycle["attempt_commitment"]["attempt_id"]
        != expanded_cycle["attempt_commitment"]["attempt_id"]
    )
    assert cycle["fixed_seed_panel"] == precommitment["seed_panel"]
    assert cycle["candidate_seed_panels"][candidate_id] == precommitment["seed_panel"]
    assert len(panel_evaluations) == runtime.FIXED_SEED_PANEL_SIZE
    assert {
        int(evaluation["evaluation_seed"]) for evaluation in panel_evaluations
    } == set(precommitment["seed_panel"])
    assert cycle["evaluations"][0] == expected_selection
    assert (
        cycle["candidate_selected_evaluation_seeds"][candidate_id]
        == expected_selection["evaluation_seed"]
    )
    assert cycle["panel_selection_policy"] == (
        runtime.CONSERVATIVE_PANEL_SELECTION_POLICY
    )
    assert cycle["caller_selectable_randomization"] is False
    assert cycle["caller_seed_validated_against_precommitment"] is True
    assert (
        cycle["attempt_commitment"][
            "caller_seed_shopping_within_identical_seed_context_possible"
        ]
        is False
    )
    assert (
        cycle["attempt_commitment"]["external_signed_seed_commitment_present"] is False
    )
    assert (
        cycle["attempt_commitment"]["cycle_artifact_commits_complete_fixed_seed_panel"]
        is True
    )
    assert cycle["trade_authority_granted"] is False
    assert cycle["paper_only"] is True
    assert cycle["live_blocked"] is True
    assert cycle["cycle_hash"] == canonical_hash(
        {key: value for key, value in cycle.items() if key != "cycle_hash"}
    )


def test_equal_fitness_panel_selection_ignores_labels_and_statistical_parameters() -> (
    None
):
    parent = _parent_genome()
    eras = _eras()
    selected_seeds: list[int] = []
    observed_panels: list[tuple[int, ...]] = []

    for operator_id in ("label-a", "label-b", "label-c"):
        mutation_specs = (
            {
                "surface": "evidence_budgets",
                "value": 800,
                "operator_id": operator_id,
            },
        )
        manifests = _candidate_manifests(parent, mutation_specs, eras)
        precommitment = runtime.derive_recursive_evolution_seed_precommitment(
            parent,
            mutation_specs,
            eras,
            manifests,
        )
        cycle = runtime.run_recursive_evolution_cycle(
            parent,
            mutation_specs,
            eras,
            manifests,
            _calibration_summary(),
            8,
            int(precommitment["committed_root_seed"]),
            3,
            0.05,
            4,
        )
        candidate_id = str(cycle["candidates"][0]["candidate_id"])
        panel_evaluations = cycle["candidate_seed_panel_evaluations"][candidate_id]
        assert {
            float(evaluation["fitness"]["fitness_score"])
            for evaluation in panel_evaluations
        } == {0.0}
        selected_seeds.append(
            int(cycle["candidate_selected_evaluation_seeds"][candidate_id])
        )
        observed_panels.append(tuple(int(seed) for seed in cycle["fixed_seed_panel"]))

    mutation_specs = (_mutation_specs()[0],)
    manifests = _candidate_manifests(parent, mutation_specs, eras)
    precommitment = runtime.derive_recursive_evolution_seed_precommitment(
        parent,
        mutation_specs,
        eras,
        manifests,
    )
    for bootstrap_iterations in (9, 10, 11):
        cycle = runtime.run_recursive_evolution_cycle(
            parent,
            mutation_specs,
            eras,
            manifests,
            _calibration_summary(),
            bootstrap_iterations,
            int(precommitment["committed_root_seed"]),
            3,
            0.05,
            4,
        )
        candidate_id = str(cycle["candidates"][0]["candidate_id"])
        panel_evaluations = cycle["candidate_seed_panel_evaluations"][candidate_id]
        assert {
            float(evaluation["fitness"]["fitness_score"])
            for evaluation in panel_evaluations
        } == {0.0}
        selected_seeds.append(
            int(cycle["candidate_selected_evaluation_seeds"][candidate_id])
        )
        observed_panels.append(tuple(int(seed) for seed in cycle["fixed_seed_panel"]))

    assert len(set(observed_panels)) == 1
    assert len(set(selected_seeds)) == 1
    assert selected_seeds[0] == observed_panels[0][0]
