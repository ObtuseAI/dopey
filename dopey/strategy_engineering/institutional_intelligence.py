"""Pure institutional-research synthesis and dependency-aware gap allocation."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Final

from dopey.protocols.identity import canonical_hash

from .institutional_registry import (
    INSTITUTIONAL_DOCTRINES,
    SUPPORTED_INSTRUMENTS,
    doctrine_by_id,
    doctrine_ids,
    institutional_source_ids,
)
from .schema import CouncilObservation, ResearchGap, ThesisEscrow


COUNCIL_VERSION: Final[str] = "dopey-institutional-council-v1"
RESEARCH_PORTFOLIO_VERSION: Final[str] = "dopey-research-portfolio-v1"
MINIMUM_RELIABLE_GROUP_SCORE: Final[float] = 0.25
MINIMUM_INDEPENDENT_GROUPS: Final[int] = 3
MAXIMUM_CONTRADICTION_INDEX: Final[float] = 0.45
MINIMUM_NET_SUPPORT: Final[float] = 0.10
REQUIRED_BASE_LENSES: Final[frozenset[str]] = frozenset({"implementation", "risk"})
ALLOWED_GAP_STATUSES: Final[frozenset[str]] = frozenset(
    {"open", "blocked_missing_evidence", "closed"}
)
INSTRUMENT_DOCTRINE_REQUIREMENTS: Final[dict[str, frozenset[str]]] = {
    "equity": frozenset(),
    "leveraged_etf": frozenset({"leveraged_product_path_authority"}),
    "leaps": frozenset({"option_quote_lifecycle", "long_horizon_option_state"}),
    "short_term_option": frozenset(
        {"option_quote_lifecycle", "volatility_forecast_risk_premium"}
    ),
    "zero_dte_option": frozenset(
        {"option_quote_lifecycle", "same_day_expiry_lifecycle"}
    ),
}
SOURCE_CLAIM_EVIDENCE_PREFIXES: Final[tuple[str, ...]] = (
    "institutional-source:",
    "primary-source:",
    "source-claim:",
)


def _validated_unit_interval(value: float, field: str, identity: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(
            "institutional intelligence requires finite unit-interval values: "
            f"identity={identity}, field={field}, value={value}"
        )
    return number


def _validated_direction(value: float, identity: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        raise ValueError(
            "institutional council direction must be finite and within [-1, 1]: "
            f"observation_id={identity}, value={value}"
        )
    return number


def _validate_nonempty_identity(value: str, field: str, identity: str) -> None:
    if not value.strip():
        raise ValueError(
            "institutional intelligence requires a non-empty identity: "
            f"identity={identity}, field={field}"
        )


def _is_source_claim_identity(value: str) -> bool:
    return value in institutional_source_ids() or value.startswith(
        SOURCE_CLAIM_EVIDENCE_PREFIXES
    )


def _validate_thesis(thesis: ThesisEscrow) -> None:
    candidate_id = thesis["candidate_id"]
    _validate_nonempty_identity(candidate_id, "candidate_id", candidate_id)
    if thesis["instrument_class"] not in SUPPORTED_INSTRUMENTS:
        raise ValueError(
            "institutional thesis has an unsupported instrument class: "
            f"candidate_id={candidate_id}, instrument_class={thesis['instrument_class']}"
        )
    for field in (
        "economic_mechanism",
        "base_rate_evidence_id",
        "opposed_thesis_id",
        "cost_model_id",
        "capacity_model_id",
        "forward_plan_id",
    ):
        value = thesis[field]
        if not isinstance(value, str):
            raise TypeError(
                "institutional thesis scalar identity must be text: "
                f"candidate_id={candidate_id}, field={field}, value_type={type(value).__name__}"
            )
    if _is_source_claim_identity(thesis["base_rate_evidence_id"]):
        raise ValueError(
            "institutional thesis cannot use a source claim as DOPEY base-rate evidence: "
            f"candidate_id={candidate_id}, evidence_id={thesis['base_rate_evidence_id']}"
        )
    tuple_fields = (
        "kill_condition_ids",
        "counterfactual_ids",
        "required_lens_ids",
        "required_doctrine_ids",
    )
    for field in tuple_fields:
        values = thesis[field]
        if len(set(values)) != len(values):
            raise ValueError(
                "institutional thesis tuple identities must be unique: "
                f"candidate_id={candidate_id}, field={field}"
            )
    unknown_doctrines = sorted(set(thesis["required_doctrine_ids"]) - doctrine_ids())
    incompatible_doctrines = sorted(
        doctrine_id
        for doctrine_id in thesis["required_doctrine_ids"]
        if thesis["instrument_class"]
        not in doctrine_by_id(doctrine_id)["applicable_instruments"]
    )
    if unknown_doctrines:
        raise ValueError(
            "institutional thesis references unknown doctrines: "
            f"candidate_id={candidate_id}, doctrine_ids={unknown_doctrines}"
        )
    if incompatible_doctrines:
        raise ValueError(
            "institutional thesis references instrument-incompatible doctrines: "
            f"candidate_id={candidate_id}, doctrine_ids={incompatible_doctrines}"
        )


def _validate_observations(observations: Sequence[CouncilObservation]) -> None:
    identities: set[str] = set()
    known_doctrines = doctrine_ids()
    for observation in observations:
        observation_id = observation["observation_id"]
        _validate_nonempty_identity(observation_id, "observation_id", observation_id)
        if observation_id in identities:
            raise ValueError(
                "institutional council observations require unique identities: "
                f"observation_id={observation_id}"
            )
        identities.add(observation_id)
        for field in (
            "lens_id",
            "evidence_family",
            "independence_group",
            "falsifier_id",
        ):
            _validate_nonempty_identity(observation[field], field, observation_id)
        if not observation["evidence_ids"]:
            raise ValueError(
                "institutional council observation requires evidence identities: "
                f"observation_id={observation_id}"
            )
        if len(set(observation["evidence_ids"])) != len(observation["evidence_ids"]):
            raise ValueError(
                "institutional council observation evidence identities must be unique: "
                f"observation_id={observation_id}"
            )
        for evidence_id in observation["evidence_ids"]:
            _validate_nonempty_identity(evidence_id, "evidence_id", observation_id)
            if _is_source_claim_identity(evidence_id):
                raise ValueError(
                    "institutional council cannot count a source claim as DOPEY evidence: "
                    f"observation_id={observation_id}, evidence_id={evidence_id}"
                )
        if not observation["doctrine_ids"]:
            raise ValueError(
                "institutional council observation requires doctrine identities: "
                f"observation_id={observation_id}"
            )
        unknown = sorted(set(observation["doctrine_ids"]) - known_doctrines)
        if unknown:
            raise ValueError(
                "institutional council observation references unknown doctrines: "
                f"observation_id={observation_id}, doctrine_ids={unknown}"
            )
        mismatched_lenses = sorted(
            doctrine_id
            for doctrine_id in observation["doctrine_ids"]
            if doctrine_by_id(doctrine_id)["lens_id"] != observation["lens_id"]
        )
        if mismatched_lenses:
            raise ValueError(
                "institutional council observation doctrine lens mismatch: "
                f"observation_id={observation_id}, doctrine_ids={mismatched_lenses}"
            )
        _validated_direction(observation["direction"], observation_id)
        for field in (
            "data_quality",
            "calibration_quality",
            "uncertainty",
            "implementation_relevance",
        ):
            _validated_unit_interval(observation[field], field, observation_id)


def _observation_reliability(observation: CouncilObservation) -> float:
    terms = (
        float(observation["data_quality"]),
        float(observation["calibration_quality"]),
        1.0 - float(observation["uncertainty"]),
        float(observation["implementation_relevance"]),
    )
    return math.prod(terms) ** (1.0 / len(terms))


def _group_observations(
    observations: Sequence[CouncilObservation],
) -> tuple[dict[str, Any], ...]:
    grouped: dict[str, list[CouncilObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation["independence_group"]].append(observation)
    records: list[dict[str, Any]] = []
    for independence_group, members in sorted(grouped.items()):
        reliabilities = tuple(_observation_reliability(member) for member in members)
        reliability_total = sum(reliabilities)
        direction = (
            sum(
                float(member["direction"]) * reliability
                for member, reliability in zip(members, reliabilities, strict=True)
            )
            / reliability_total
            if reliability_total > 0.0
            else 0.0
        )
        group_reliability = max(reliabilities, default=0.0)
        group_score = direction * group_reliability
        records.append(
            {
                "independence_group": independence_group,
                "observation_ids": tuple(
                    sorted(member["observation_id"] for member in members)
                ),
                "evidence_families": tuple(
                    sorted({member["evidence_family"] for member in members})
                ),
                "lens_ids": tuple(sorted({member["lens_id"] for member in members})),
                "group_direction": round(direction, 10),
                "group_reliability": round(group_reliability, 10),
                "group_score": round(group_score, 10),
                "duplicate_vote_inflation_allowed": False,
            }
        )
    return tuple(records)


def _escrow_failures(
    thesis: ThesisEscrow,
    observations: Sequence[CouncilObservation],
) -> tuple[str, ...]:
    failures: list[str] = []
    scalar_requirements = (
        ("economic_mechanism", thesis["economic_mechanism"]),
        ("base_rate_evidence_id", thesis["base_rate_evidence_id"]),
        ("opposed_thesis_id", thesis["opposed_thesis_id"]),
        ("cost_model_id", thesis["cost_model_id"]),
        ("capacity_model_id", thesis["capacity_model_id"]),
        ("forward_plan_id", thesis["forward_plan_id"]),
    )
    failures.extend(field for field, value in scalar_requirements if not value.strip())
    if not thesis["kill_condition_ids"]:
        failures.append("kill_condition_ids")
    if "no_trade" not in thesis["counterfactual_ids"]:
        failures.append("no_trade_counterfactual")
    if thesis["opposed_thesis_id"] not in thesis["counterfactual_ids"]:
        failures.append("opposed_thesis_counterfactual")
    required_lenses = set(thesis["required_lens_ids"]) | REQUIRED_BASE_LENSES
    reliable_observations = tuple(
        observation
        for observation in observations
        if _observation_reliability(observation) >= MINIMUM_RELIABLE_GROUP_SCORE
    )
    observed_lenses = {observation["lens_id"] for observation in reliable_observations}
    failures.extend(
        f"missing_lens:{lens_id}"
        for lens_id in sorted(required_lenses - observed_lenses)
    )
    required_doctrines = set(thesis["required_doctrine_ids"]) | set(
        INSTRUMENT_DOCTRINE_REQUIREMENTS[thesis["instrument_class"]]
    )
    observed_doctrines = {
        doctrine_id
        for observation in reliable_observations
        for doctrine_id in observation["doctrine_ids"]
    }
    failures.extend(
        f"missing_doctrine:{doctrine_id}"
        for doctrine_id in sorted(required_doctrines - observed_doctrines)
    )
    observations_without_falsifiers = sorted(
        observation["observation_id"]
        for observation in observations
        if not observation["falsifier_id"].strip()
    )
    failures.extend(
        f"missing_observation_falsifier:{observation_id}"
        for observation_id in observations_without_falsifiers
    )
    return tuple(sorted(set(failures)))


def _next_falsification_target(
    observations: Sequence[CouncilObservation],
) -> dict[str, str | float] | None:
    if not observations:
        return None
    selected = sorted(
        observations,
        key=lambda observation: (
            -float(observation["uncertainty"])
            * float(observation["implementation_relevance"]),
            observation["observation_id"],
        ),
    )[0]
    return {
        "observation_id": selected["observation_id"],
        "lens_id": selected["lens_id"],
        "falsifier_id": selected["falsifier_id"],
        "uncertainty_relevance": round(
            float(selected["uncertainty"])
            * float(selected["implementation_relevance"]),
            10,
        ),
    }


def synthesize_institutional_council(
    thesis: ThesisEscrow,
    observations: Sequence[CouncilObservation],
) -> dict[str, Any]:
    """Synthesize independent research lenses without treating the result as edge."""

    _validate_thesis(thesis)
    _validate_observations(observations)
    incompatible_observation_doctrines = sorted(
        {
            doctrine_id
            for observation in observations
            for doctrine_id in observation["doctrine_ids"]
            if thesis["instrument_class"]
            not in doctrine_by_id(doctrine_id)["applicable_instruments"]
        }
    )
    if incompatible_observation_doctrines:
        raise ValueError(
            "institutional council observations contain instrument-incompatible doctrines: "
            f"candidate_id={thesis['candidate_id']}, doctrine_ids={incompatible_observation_doctrines}"
        )
    group_records = _group_observations(observations)
    active_groups = tuple(
        record
        for record in group_records
        if float(record["group_reliability"]) >= MINIMUM_RELIABLE_GROUP_SCORE
    )
    support_mass = sum(
        max(0.0, float(record["group_score"])) for record in active_groups
    )
    opposition_mass = sum(
        max(0.0, -float(record["group_score"])) for record in active_groups
    )
    total_directional_mass = support_mass + opposition_mass
    contradiction_index = (
        2.0 * min(support_mass, opposition_mass) / total_directional_mass
        if total_directional_mass > 0.0
        else 0.0
    )
    net_support = (
        sum(float(record["group_score"]) for record in active_groups)
        / len(active_groups)
        if active_groups
        else 0.0
    )
    mean_reliability = (
        sum(float(record["group_reliability"]) for record in active_groups)
        / len(active_groups)
        if active_groups
        else 0.0
    )
    group_sufficiency = min(1.0, len(active_groups) / MINIMUM_INDEPENDENT_GROUPS)
    epistemic_strength = (
        abs(net_support)
        * mean_reliability
        * (1.0 - contradiction_index)
        * group_sufficiency
    )
    failures = _escrow_failures(thesis, observations)
    if failures:
        status = "abstain_incomplete_thesis_escrow"
    elif len(active_groups) < MINIMUM_INDEPENDENT_GROUPS:
        status = "abstain_insufficient_independent_evidence"
    elif contradiction_index > MAXIMUM_CONTRADICTION_INDEX:
        status = "quarantined_unresolved_contradiction"
    elif net_support <= MINIMUM_NET_SUPPORT:
        status = "abstain_weak_or_nonpositive_net_support"
    else:
        status = "research_candidate_requires_protected_evaluation"
    body: dict[str, Any] = {
        "artifact_type": "institutional_research_council_synthesis",
        "council_version": COUNCIL_VERSION,
        "candidate_id": thesis["candidate_id"],
        "instrument_class": thesis["instrument_class"],
        "council_status": status,
        "escrow_failures": failures,
        "raw_observation_count": len(observations),
        "distinct_lens_count": len(
            {observation["lens_id"] for observation in observations}
        ),
        "distinct_evidence_family_count": len(
            {observation["evidence_family"] for observation in observations}
        ),
        "independence_group_count": len(group_records),
        "effective_independent_group_count": len(active_groups),
        "minimum_independent_group_count": MINIMUM_INDEPENDENT_GROUPS,
        "redundancy_discount": round(
            1.0 - len(group_records) / len(observations) if observations else 0.0,
            10,
        ),
        "support_mass": round(support_mass, 10),
        "opposition_mass": round(opposition_mass, 10),
        "net_support": round(net_support, 10),
        "contradiction_index": round(contradiction_index, 10),
        "epistemic_strength": round(epistemic_strength, 10),
        "group_records": group_records,
        "next_falsification_target": _next_falsification_target(observations),
        "not_a_probability": True,
        "not_edge_evidence": True,
        "candidate_self_grading_allowed": False,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "council_hash": canonical_hash(body)}


def _validate_gap_registry(gaps: Sequence[ResearchGap]) -> None:
    gap_by_id: dict[str, ResearchGap] = {}
    for gap in gaps:
        gap_id = gap["gap_id"]
        _validate_nonempty_identity(gap_id, "gap_id", gap_id)
        if gap_id in gap_by_id:
            raise ValueError(
                f"research gap registry requires unique identities: gap_id={gap_id}"
            )
        gap_by_id[gap_id] = gap
        for field in ("domain_id", "statement", "current_status"):
            _validate_nonempty_identity(gap[field], field, gap_id)
        if gap["current_status"] not in ALLOWED_GAP_STATUSES:
            raise ValueError(
                "research gap has unsupported status: "
                f"gap_id={gap_id}, current_status={gap['current_status']}"
            )
        if not gap["evidence_ids"]:
            raise ValueError(
                f"research gap requires evidence identities: gap_id={gap_id}"
            )
        for field in (
            "information_gain",
            "falsifiability",
            "uncertainty_reduction",
            "orthogonality",
            "implementation_readiness",
            "edge_relevance",
            "safety_relevance",
            "reuse_potential",
            "selection_risk",
        ):
            _validated_unit_interval(gap[field], field, gap_id)
        evaluation_cost = float(gap["evaluation_cost"])
        if not math.isfinite(evaluation_cost) or not 0.0 < evaluation_cost <= 1.0:
            raise ValueError(
                "research gap evaluation cost must be finite within (0, 1]: "
                f"gap_id={gap_id}, evaluation_cost={gap['evaluation_cost']}"
            )
        if gap["max_budget_units"] <= 0:
            raise ValueError(
                "research gap maximum budget must be positive: "
                f"gap_id={gap_id}, max_budget_units={gap['max_budget_units']}"
            )
    known_ids = set(gap_by_id)
    for gap in gaps:
        unknown_dependencies = sorted(set(gap["dependency_ids"]) - known_ids)
        if unknown_dependencies:
            raise ValueError(
                "research gap references unknown dependencies: "
                f"gap_id={gap['gap_id']}, dependency_ids={unknown_dependencies}"
            )
        if gap["gap_id"] in gap["dependency_ids"]:
            raise ValueError(
                f"research gap cannot depend on itself: gap_id={gap['gap_id']}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(gap_id: str) -> None:
        if gap_id in visiting:
            raise ValueError(
                f"research gap dependency graph contains a cycle: gap_id={gap_id}"
            )
        if gap_id in visited:
            return
        visiting.add(gap_id)
        for dependency_id in gap_by_id[gap_id]["dependency_ids"]:
            visit(dependency_id)
        visiting.remove(gap_id)
        visited.add(gap_id)

    for gap_id in sorted(gap_by_id):
        visit(gap_id)


def _gap_base_score(gap: ResearchGap) -> float:
    dimensions = (
        float(gap["information_gain"]),
        float(gap["falsifiability"]),
        float(gap["uncertainty_reduction"]),
        float(gap["orthogonality"]),
        float(gap["implementation_readiness"]),
        max(float(gap["edge_relevance"]), float(gap["safety_relevance"])),
        float(gap["reuse_potential"]),
        1.0 - float(gap["selection_risk"]),
    )
    if any(value == 0.0 for value in dimensions):
        return 0.0
    geometric_benefit = math.prod(dimensions) ** (1.0 / len(dimensions))
    safety_multiplier = 1.0 + 0.5 * float(gap["safety_relevance"])
    return geometric_benefit * safety_multiplier / float(gap["evaluation_cost"])


def allocate_research_gap_portfolio(
    gaps: Sequence[ResearchGap],
    total_budget_units: int,
) -> dict[str, Any]:
    """Allocate research units to evidence-ready gaps, never to trading capital."""

    if total_budget_units <= 0:
        raise ValueError(
            "research portfolio budget must be positive: "
            f"total_budget_units={total_budget_units}"
        )
    _validate_gap_registry(gaps)
    gap_by_id = {gap["gap_id"]: gap for gap in gaps}
    base_scores = {gap["gap_id"]: _gap_base_score(gap) for gap in gaps}
    blocking_dependencies = {
        gap["gap_id"]: tuple(
            sorted(
                dependency_id
                for dependency_id in gap["dependency_ids"]
                if gap_by_id[dependency_id]["current_status"] != "closed"
            )
        )
        for gap in gaps
    }
    allocations = {gap["gap_id"]: 0 for gap in gaps}
    domain_allocations: dict[str, int] = defaultdict(int)
    allocation_trace: list[dict[str, Any]] = []
    for unit_index in range(total_budget_units):
        eligible = tuple(
            gap
            for gap in gaps
            if gap["current_status"] == "open"
            and not blocking_dependencies[gap["gap_id"]]
            and allocations[gap["gap_id"]] < gap["max_budget_units"]
            and base_scores[gap["gap_id"]] > 0.0
        )
        if not eligible:
            break
        marginal_scores = {
            gap["gap_id"]: base_scores[gap["gap_id"]]
            / (1.0 + allocations[gap["gap_id"]])
            / (1.0 + 0.35 * domain_allocations[gap["domain_id"]])
            for gap in eligible
        }
        selected = sorted(
            eligible,
            key=lambda gap: (-marginal_scores[gap["gap_id"]], gap["gap_id"]),
        )[0]
        allocations[selected["gap_id"]] += 1
        domain_allocations[selected["domain_id"]] += 1
        allocation_trace.append(
            {
                "unit_index": unit_index + 1,
                "gap_id": selected["gap_id"],
                "domain_id": selected["domain_id"],
                "marginal_score": round(marginal_scores[selected["gap_id"]], 10),
            }
        )
    ranked_ids = sorted(
        (gap["gap_id"] for gap in gaps),
        key=lambda gap_id: (-allocations[gap_id], -base_scores[gap_id], gap_id),
    )
    rank_by_id = {gap_id: index + 1 for index, gap_id in enumerate(ranked_ids)}
    records = tuple(
        {
            "gap_id": gap["gap_id"],
            "domain_id": gap["domain_id"],
            "statement": gap["statement"],
            "current_status": gap["current_status"],
            "dependency_ids": gap["dependency_ids"],
            "blocking_dependency_ids": blocking_dependencies[gap["gap_id"]],
            "base_priority_score": round(base_scores[gap["gap_id"]], 10),
            "allocated_research_units": allocations[gap["gap_id"]],
            "priority_rank": rank_by_id[gap["gap_id"]],
            "evidence_ids": gap["evidence_ids"],
            "capital_allocation_allowed": False,
        }
        for gap in sorted(gaps, key=lambda record: rank_by_id[record["gap_id"]])
    )
    allocated_units = sum(allocations.values())
    body: dict[str, Any] = {
        "artifact_type": "dependency_aware_research_gap_portfolio",
        "portfolio_version": RESEARCH_PORTFOLIO_VERSION,
        "gap_count": len(gaps),
        "total_budget_units": total_budget_units,
        "allocated_budget_units": allocated_units,
        "unallocated_budget_units": total_budget_units - allocated_units,
        "budget_fully_allocated": allocated_units == total_budget_units,
        "domain_allocations": dict(sorted(domain_allocations.items())),
        "gap_records": records,
        "allocation_trace": tuple(allocation_trace),
        "allocation_target": "research_attention_only",
        "capital_allocation_allowed": False,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "portfolio_hash": canonical_hash(body)}


def institutional_evaluation_contract() -> dict[str, Any]:
    """Return the invariant contract shared by all strategy candidates."""

    return {
        "contract_version": "dopey-institutional-evaluation-contract-v1",
        "minimum_independent_evidence_groups": MINIMUM_INDEPENDENT_GROUPS,
        "required_base_lenses": tuple(sorted(REQUIRED_BASE_LENSES)),
        "required_counterfactuals": (
            "no_trade",
            "simplest_plausible_baseline",
            "opposed_thesis",
        ),
        "required_candidate_fields": (
            "economic_mechanism",
            "base_rate_evidence_id",
            "opposed_thesis_id",
            "kill_condition_ids",
            "cost_model_id",
            "capacity_model_id",
            "forward_plan_id",
        ),
        "doctrine_count": len(INSTITUTIONAL_DOCTRINES),
        "duplicate_vote_inflation_allowed": False,
        "source_claims_count_as_edge_evidence": False,
        "council_score_is_probability": False,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
