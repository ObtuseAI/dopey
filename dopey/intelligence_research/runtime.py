"""One bounded scientific cycle that researches cognitive methods."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .creativity import generate_cognitive_hypotheses
from .discovery import discover_research_questions
from .experiments import design_cognitive_experiments
from .schema import CognitiveKnowledgeState


COGNITIVE_ROLES: tuple[str, ...] = (
    "problem_analyst",
    "research_scientist",
    "inventor",
    "systems_thinker",
    "statistician",
    "optimizer",
    "skeptic",
    "simplifier",
    "simulation_designer",
    "experimentalist",
    "theory_builder",
    "knowledge_curator",
    "meta_thinker",
)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_ledger(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def _world_model(
    state: CognitiveKnowledgeState,
    question_ids: Sequence[str],
    method_ids: Sequence[str],
    experiment_ids: Sequence[str],
) -> dict[str, Any]:
    signal_nodes = [
        {
            "node_id": signal["signal_id"],
            "node_type": signal["signal_type"].value,
            "domain_id": signal["domain_id"],
            "statement": signal["statement"],
        }
        for signal in state["signals"]
    ]
    failure_graph = [
        node for node in signal_nodes if node["node_type"] == "REPEATED_FAILURE"
    ]
    return {
        "artifact_type": "shared_cognitive_world_model",
        "world_model_version": "dopey-cognitive-world-model-v1",
        "knowledge_graph": signal_nodes,
        "unknown_graph": [node for node in signal_nodes if node["node_type"] in {"UNKNOWN", "CAPABILITY_GAP"}],
        "failure_graph": failure_graph,
        "opportunity_graph": [node for node in signal_nodes if node["node_type"] in {"OPPORTUNITY", "BOTTLENECK"}],
        "research_graph": {
            "question_ids": list(question_ids),
            "method_ids": list(method_ids),
            "experiment_ids": list(experiment_ids),
        },
        "theory_graph": [],
        "capability_graph": [{"role_id": role_id, "state": "available"} for role_id in COGNITIVE_ROLES],
        "experimental_domain_ids": list(state["experimental_domain_ids"]),
    }


def run_intelligence_research_cycle(
    state: CognitiveKnowledgeState,
    output_root: Path,
    question_budget: int,
    hypothesis_budget: int,
    cognitive_level: int,
    generation: int,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("intelligence research issued_at must be timezone-aware")
    if generation <= 0:
        raise ValueError(f"intelligence research generation must be positive: generation={generation}")
    questions = discover_research_questions(state["signals"], question_budget)
    hypotheses = generate_cognitive_hypotheses(questions, hypothesis_budget, cognitive_level)
    experiments = design_cognitive_experiments(hypotheses, state["experimental_domain_ids"])
    status = "cognitive_experiments_queued" if experiments else "no_governed_discoveries"
    world_model = _world_model(
        state,
        tuple(record["question_id"] for record in questions),
        tuple(record["method_id"] for record in hypotheses),
        tuple(record["experiment_id"] for record in experiments),
    )
    body: dict[str, Any] = {
        "artifact_type": "autonomous_intelligence_research_cycle",
        "cycle_version": "dopey-intelligence-research-cycle-v1",
        "cycle_status": status,
        "issued_at": issued_at.isoformat(),
        "generation": generation,
        "cognitive_level": cognitive_level,
        "mission": "discover_better_ways_of_discovering",
        "optimization_target": "evidence_validated_cognitive_methods",
        "knowledge_state_id": state["state_id"],
        "discovery_questions": list(questions),
        "cognitive_hypotheses": list(hypotheses),
        "experiments": list(experiments),
        "cognitive_world_model": world_model,
        "cognitive_roles": list(COGNITIVE_ROLES),
        "automatic_cognitive_method_activation_count": 0,
        "human_review_required_for_qualified_activation": False,
        "candidate_self_activation_allowed": False,
        "candidate_self_evaluation_allowed": False,
        "authority_effect": "none",
        "permission_effect": "none",
        "truth_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    _append_ledger(output_root / "intelligence_experiment_ledger.jsonl", output)
    _write_json_atomic(output_root / "latest_cycle.json", output)
    _write_json_atomic(output_root / "cognitive_world_model.json", world_model)
    return output
