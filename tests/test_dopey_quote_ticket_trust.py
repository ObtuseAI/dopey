from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from dopey.ascendancy.contracts import (
    CandidateGenome,
    DummyOpportunity,
    candidate_genome_from_mapping,
    candidate_genome_to_mapping,
    create_candidate_genome,
    create_dummy_opportunity,
)
from dopey.ascendancy.gates import BehavioralState, CandidateExposure, PortfolioState
from dopey.ascendancy.identity import JsonValue, canonical_hash, canonical_json
from dopey.ascendancy.negative_controls import NegativeControlResult
from dopey.ascendancy.policy_ids import V1_REQUIRED_NEGATIVE_CONTROL_IDS
from dopey.ascendancy.pricing import (
    QuoteSnapshot,
    build_price_triple,
    evaluate_quote_gate,
    quote_snapshot_content_hash,
)
from dopey.ascendancy.stress import v1_required_stress_requirements
from dopey.ascendancy.tickets import (
    AbstentionRecord,
    abstention_record_from_mapping,
    abstention_record_to_mapping,
    DecisionControlInputs,
    PaperExecutionTicket,
    PaperFillObservation,
    PaperPriceRequest,
    build_paper_decision,
    build_paper_fill_observation,
    create_decision_market_context,
    create_point_in_time_decision_market_context,
    create_prospective_paper_evidence,
    paper_fill_observation_id,
    paper_fill_observation_from_mapping,
    paper_fill_observation_to_mapping,
    paper_execution_ticket_id,
    paper_execution_ticket_from_mapping,
    paper_execution_ticket_to_mapping,
    require_v1_environment_hash,
    ticket_leg_content_hash,
    validate_paper_fill_observation,
    validate_paper_execution_ticket,
    validate_decision_market_context,
    v1_quote_gate_policy,
    v1_options_mechanics_coverage,
    v1_risk_limits,
    v1_watch_universe,
)


HASH = "a" * 64
ENVIRONMENT_HASH = "811d348d94e151087cd77d496bd1f5135b24dd40ba107b5d860cde34b8475652"
DECISION_TIMESTAMP = "2026-07-17T14:00:10Z"


def _opportunity(synthetic: bool) -> DummyOpportunity:
    return create_dummy_opportunity(
        "2026-07-17T14:00:00Z",
        "SPY",
        "bullish distribution",
        "5d",
        0.6,
        0.01,
        "2026-07-18T14:00:00Z",
        "dummy-v1",
        HASH,
        synthetic,
    )


def _candidate(opportunity: DummyOpportunity) -> CandidateGenome:
    leg = {
        "contract_id": f"{opportunity.underlying}-2026-08-21-call-500",
        "side": "buy",
        "underlying": opportunity.underlying,
        "option_type": "call",
        "expiry": "2026-08-21",
        "strike": 500.0,
        "quantity": 1,
        "multiplier": 100,
        "deliverable": "100 shares",
        "option_style": "american",
        "settlement_type": "physical",
    }
    specification = {
        "dummy_input_contract": {
            "opportunity_id": opportunity.opportunity_id,
            "creation_timestamp": opportunity.creation_timestamp,
            "underlying": opportunity.underlying,
            "forecast": opportunity.forecast,
            "intended_horizon": opportunity.intended_horizon,
            "confidence": opportunity.confidence,
            "maximum_exposure_fraction": opportunity.maximum_exposure_fraction,
            "expiration_timestamp": opportunity.expiration_timestamp,
            "upstream_version": opportunity.upstream_version,
            "provenance_hash": opportunity.provenance_hash,
            "synthetic": opportunity.synthetic,
            "contract_hash": opportunity.contract_hash,
        },
        "market_state": {
            "available_features": ["nbbo_quote"],
            "timestamp_rules": "point_in_time",
            "liquidity_state": "liquid",
            "volatility_state": "unknown",
        },
        "instrument_choice": {
            "use_options": True,
            "underlying_alternative": "risk_matched_SPY",
            "reason": "defined convexity",
        },
        "structure": {
            "type": "long_call",
            "legs": [leg],
            "maximum_loss": 1_000.0,
            "assignment_profile": "explicit_review",
            "exercise_profile": "explicit_review",
        },
        "entry": {
            "earliest_time": "2026-07-17T14:00:11Z",
            "latest_time": "2026-07-17T14:05:00Z",
            "limit_price_rule": "fixed_adverse_side_cap",
            "cancellation_rule": "cancel_after_60_seconds",
            "venue_rule": "paper_nbbo_reference",
            "legging_rule": "package_only",
            "fill_model_version": "paper-witness-v1",
        },
        "sizing": {
            "method": "fixed_maximum_loss",
            "uncertainty_haircut": 0.5,
            "maximum_position_fraction": 0.01,
            "maximum_portfolio_contribution": 0.01,
            "margin_limit": 0.02,
        },
        "management": {
            "monitor_frequency": "event_driven",
            "hold_rule": "frozen_thesis_valid",
            "trim_rule": "none",
            "hedge_rule": "none",
            "roll_rule": "none",
            "exit_rule": "frozen_invalidation",
            "expiration_rule": "close_before_expiration",
        },
        "risk": {
            "delta_limit": 0.10,
            "gamma_limit": 0.02,
            "theta_limit": 0.005,
            "vega_limit": 0.05,
            "vanna_limit": 0.02,
            "charm_limit": 0.02,
            "vomma_limit": 0.02,
            "skew_limit": 0.03,
            "correlation_limit": 0.05,
            "event_limit": 0.05,
            "liquidity_limit": 0.05,
            "gap_limit": 0.03,
            "tail_limit": 0.03,
            "concentration_limit": 0.05,
            "drawdown_limit": 0.10,
            "expected_shortfall_limit": 0.03,
            "ruin_probability_limit": 0.001,
            "kill_conditions": ["stale_quote"],
        },
        "economics": {
            "commission_model": "v1",
            "spread_model": "adverse_side",
            "slippage_model": "25bps",
            "impact_model": "capacity_blocked",
            "funding_model": "zero",
            "borrow_model": "unavailable",
        },
        "evaluation": {
            "benchmarks": ["no_trade"],
            "primary_metrics": ["lower_bound_utility"],
            "secondary_metrics": ["abstention"],
            "negative_controls": sorted(V1_REQUIRED_NEGATIVE_CONTROL_IDS),
            "stress_tests": sorted(
                scenario_id for _, scenario_id in v1_required_stress_requirements()
            ),
        },
        "reproducibility": {
            "data_snapshot_hash": HASH,
            "code_commit": "test",
            "environment_hash": ENVIRONMENT_HASH,
            "evaluator_version": "v1",
            "random_seeds": [1],
        },
    }
    return create_candidate_genome(
        "quote-ticket-trust-candidate",
        (),
        "defined_risk_directional",
        "frozen mechanics hypothesis",
        "fails mechanics validation",
        "options_expression",
        specification,
    )


def _quote(observed_at: str) -> QuoteSnapshot:
    provisional = QuoteSnapshot(
        contract_id="SPY-2026-08-21-call-500",
        chain_id="chain-1",
        observed_at=observed_at,
        received_at=observed_at,
        bid=2.0,
        ask=2.2,
        bid_size=10,
        ask_size=12,
        last=2.1,
        volume=100,
        open_interest=500,
        source_uri="fixture://quote",
        source_record_hash=HASH,
        content_hash="0" * 64,
        venue="opra_consolidated",
        quote_condition="regular",
        evidence_tier="nbbo_quote",
        chain_complete=True,
        option_style="american",
        settlement_type="physical",
        contract_multiplier=100,
        deliverable="100 shares",
        adjustment_required=False,
        adjustment_validated=False,
        underlying="SPY",
        option_type="call",
        expiry="2026-08-21",
        strike=500.0,
    )
    return _rehash_quote(provisional)


def _rehash_quote(quote: QuoteSnapshot) -> QuoteSnapshot:
    return replace(quote, content_hash=quote_snapshot_content_hash(quote))


def _controls(maximum_loss_fraction: float) -> DecisionControlInputs:
    exposure = CandidateExposure(
        True,
        35,
        maximum_loss_fraction,
        maximum_loss_fraction,
        maximum_loss_fraction,
        0.0001,
        0.01,
        0.001,
        -0.0001,
        0.01,
        0.001,
        0.001,
        0.001,
        0.001,
        0.001,
        0.001,
        0.001,
        0.001,
    )
    portfolio = PortfolioState(
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    negative_controls = tuple(
        NegativeControlResult(
            control_id,
            "control-reviewer",
            f"negative-control-{control_id}",
            0.0,
            0.01,
            True,
            None,
        )
        for control_id in sorted(V1_REQUIRED_NEGATIVE_CONTROL_IDS)
    )
    return DecisionControlInputs(
        ENVIRONMENT_HASH,
        exposure,
        portfolio,
        v1_risk_limits(),
        BehavioralState(1.0, 1.0, 0, False, False, False, False),
        negative_controls,
        V1_REQUIRED_NEGATIVE_CONTROL_IDS,
        "candidate-author",
    )


def _request(quote: QuoteSnapshot) -> PaperPriceRequest:
    return PaperPriceRequest(
        quote, 2.15, "debit", 25.0, 0.65, quote.contract_multiplier
    )


def _dynamic_market_context(symbols: tuple[str, ...] | None):
    selected_symbols = symbols if symbols is not None else v1_watch_universe()
    return create_point_in_time_decision_market_context(
        "operator-membership-2026-07-17",
        HASH,
        "dopey-point-in-time-universe-v1",
        "2026-07-17T13:59:00Z",
        "2026-07-17T13:59:00Z",
        "2026-07-17T20:00:00Z",
        "artifact://independent-universe/membership.json",
        HASH,
        "independent-membership-attestation-1",
        HASH,
        selected_symbols,
        "2026-07-17",
    )


def _setup(
    synthetic: bool,
) -> tuple[
    DummyOpportunity,
    CandidateGenome,
    QuoteSnapshot,
    DecisionControlInputs,
]:
    opportunity = _opportunity(synthetic)
    candidate = _candidate(opportunity)
    quote = _quote("2026-07-17T14:00:00Z")
    price = build_price_triple(
        quote,
        DECISION_TIMESTAMP,
        v1_quote_gate_policy(),
        2.15,
        "debit",
        25.0,
        0.65,
        100,
    )
    maximum_loss_fraction = price.conservative_paper_executable * 100.0 / 100_000.0
    return opportunity, candidate, quote, _controls(maximum_loss_fraction)


def _decision(
    opportunity: DummyOpportunity,
    candidate: CandidateGenome,
    quote: QuoteSnapshot,
    controls: DecisionControlInputs,
) -> PaperExecutionTicket | AbstentionRecord:
    return build_paper_decision(
        opportunity,
        candidate,
        DECISION_TIMESTAMP,
        (_request(quote),),
        v1_quote_gate_policy(),
        controls,
        (
            create_decision_market_context("2026-07-17", True)
            if opportunity.synthetic
            else None
        ),
        None,
    )


def _rehash_ticket(ticket: PaperExecutionTicket) -> PaperExecutionTicket:
    return replace(ticket, ticket_id=paper_execution_ticket_id(ticket))


def _rehash_fill(observation: PaperFillObservation) -> PaperFillObservation:
    return replace(
        observation,
        observation_id=paper_fill_observation_id(observation),
    )


def _replace_candidate_snapshot(
    ticket: PaperExecutionTicket,
    snapshot: dict[str, JsonValue],
) -> PaperExecutionTicket:
    canonical_snapshot = canonical_json(snapshot)
    forged = replace(
        ticket,
        candidate_snapshot=canonical_snapshot,
        candidate_genome_hash=canonical_hash(snapshot),
    )
    return _rehash_ticket(forged)


def _replace_control_snapshot(
    ticket: PaperExecutionTicket,
    snapshot: dict[str, JsonValue],
) -> PaperExecutionTicket:
    forged = replace(
        ticket,
        control_snapshot=canonical_json(snapshot),
        control_hash=canonical_hash(snapshot),
    )
    return _rehash_ticket(forged)


def test_v1_issues_only_synthetic_mechanics_tickets() -> None:
    real_setup = _setup(False)
    real_decision = _decision(*real_setup)
    assert isinstance(real_decision, AbstentionRecord)
    assert "prospective_paper_evidence_missing" in real_decision.reason_codes

    synthetic_setup = _setup(True)
    synthetic_decision = _decision(*synthetic_setup)
    assert isinstance(synthetic_decision, PaperExecutionTicket)
    assert synthetic_decision.evidence_class == "synthetic_mechanics_only"
    assert synthetic_decision.opportunity_synthetic is True
    assert synthetic_decision.exposure_model_certified is False
    assert synthetic_decision.complete_cost_model_certified is False
    assert synthetic_decision.fair_value_input_stack_certified is False
    assert synthetic_decision.profitability_evidence_eligible is False
    assert synthetic_decision.paper_only and synthetic_decision.live_blocked

    later_quote = _quote("2026-07-17T14:00:20Z")
    fill = build_paper_fill_observation(
        synthetic_decision,
        (later_quote,),
        1.0,
        v1_quote_gate_policy(),
    )
    assert fill.evidence_class == "synthetic_mechanics_only"
    assert fill.profitability_evidence_eligible is False
    assert fill.realized_evidence is False


@pytest.mark.parametrize(
    ("field_name", "altered_value", "reason_code"),
    (
        ("contract_id", "opaque-other-id", "paper_ticket_contract_identity_mismatch"),
        ("underlying", "QQQ", "paper_ticket_contract_underlying_mismatch"),
        ("option_type", "put", "paper_ticket_contract_option_type_mismatch"),
        ("expiry", "2026-08-22", "paper_ticket_contract_expiry_mismatch"),
        ("strike", 501.0, "paper_ticket_contract_strike_mismatch"),
        ("contract_multiplier", 50, "paper_ticket_contract_multiplier_mismatch"),
        ("deliverable", "50 shares", "paper_ticket_contract_deliverable_mismatch"),
        ("option_style", "european", "paper_ticket_contract_option_style_mismatch"),
        ("settlement_type", "cash", "paper_ticket_contract_settlement_type_mismatch"),
    ),
)
def test_rehashed_semantically_different_quote_cannot_bind_to_candidate_leg(
    field_name: str,
    altered_value: object,
    reason_code: str,
) -> None:
    opportunity, candidate, quote, controls = _setup(True)
    altered_quote = _rehash_quote(replace(quote, **{field_name: altered_value}))
    assert evaluate_quote_gate(
        altered_quote,
        DECISION_TIMESTAMP,
        v1_quote_gate_policy(),
    ).passed
    decision = _decision(opportunity, candidate, altered_quote, controls)
    assert isinstance(decision, AbstentionRecord)
    assert reason_code in decision.reason_codes


def test_later_quote_must_preserve_frozen_contract_terms() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)
    altered_quote = _rehash_quote(replace(_quote("2026-07-17T14:00:20Z"), strike=501.0))
    observation = build_paper_fill_observation(
        decision,
        (altered_quote,),
        1.0,
        v1_quote_gate_policy(),
    )
    assert observation.paper_fill_status == "missed"
    assert "witness_contract_terms_mismatch" in observation.reason_codes


def test_rehashed_ticket_cannot_weaken_evidence_or_structural_invariants() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)

    profitability_forgery = _rehash_ticket(
        replace(decision, profitability_evidence_eligible=True)
    )
    with pytest.raises(ValueError, match="profitability evidence"):
        validate_paper_execution_ticket(profitability_forgery)

    forged_price = replace(
        decision.price_triples[0],
        paper_executable_is_simulated=False,
        profitability_evidence_eligible=True,
    )
    price_forgery = _rehash_ticket(replace(decision, price_triples=(forged_price,)))
    with pytest.raises(ValueError, match="simulated|profitability evidence"):
        validate_paper_execution_ticket(price_forgery)

    cardinality_forgery = _rehash_ticket(replace(decision, quantities=()))
    with pytest.raises(ValueError, match="equal length"):
        validate_paper_execution_ticket(cardinality_forgery)

    loss_forgery = _rehash_ticket(
        replace(decision, maximum_loss_fraction=decision.maximum_loss_fraction + 0.001)
    )
    with pytest.raises(ValueError, match="maximum-loss fields are inconsistent"):
        validate_paper_execution_ticket(loss_forgery)

    chronology_forgery = _rehash_ticket(
        replace(decision, entry_earliest_time="2026-07-17T14:05:01Z")
    )
    with pytest.raises(ValueError, match="causal order"):
        validate_paper_execution_ticket(chronology_forgery)


def test_ticket_reconstructs_and_enforces_complete_control_snapshot() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)

    arbitrary_hash = _rehash_ticket(replace(decision, control_hash="b" * 64))
    with pytest.raises(ValueError, match="control snapshot hash mismatch"):
        validate_paper_execution_ticket(arbitrary_hash)

    understated_exposure = cast(
        dict[str, JsonValue],
        json.loads(decision.control_snapshot),
    )
    exposure = cast(dict[str, JsonValue], understated_exposure["candidate_exposure"])
    exposure["maximum_loss_fraction"] = 0.0001
    exposure_forgery = _replace_control_snapshot(decision, understated_exposure)
    with pytest.raises(ValueError, match="not derived from its maximum loss"):
        validate_paper_execution_ticket(exposure_forgery)

    weakened_limits = cast(
        dict[str, JsonValue],
        json.loads(decision.control_snapshot),
    )
    risk_limits = cast(dict[str, JsonValue], weakened_limits["risk_limits"])
    risk_limits["maximum_position_loss_fraction"] = 1.0
    limits_forgery = _replace_control_snapshot(decision, weakened_limits)
    with pytest.raises(ValueError, match="weakened environment-v1 limits"):
        validate_paper_execution_ticket(limits_forgery)

    weakened_firewall = cast(
        dict[str, JsonValue],
        json.loads(decision.control_snapshot),
    )
    behavioral_state = cast(dict[str, JsonValue], weakened_firewall["behavioral_state"])
    behavioral_state["fomo_entry"] = True
    firewall_forgery = _replace_control_snapshot(decision, weakened_firewall)
    with pytest.raises(ValueError, match="behavioral firewall"):
        validate_paper_execution_ticket(firewall_forgery)

    self_reviewed_control = cast(
        dict[str, JsonValue],
        json.loads(decision.control_snapshot),
    )
    negative_controls = cast(
        list[JsonValue],
        self_reviewed_control["negative_control_results"],
    )
    first_control = cast(dict[str, JsonValue], negative_controls[0])
    first_control["evaluator_id"] = "candidate-author"
    control_forgery = _replace_control_snapshot(decision, self_reviewed_control)
    with pytest.raises(ValueError, match="failed negative controls"):
        validate_paper_execution_ticket(control_forgery)


def test_ticket_reconstructs_price_leg_and_bounded_loss_economics() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)

    altered_price = replace(
        decision.price_triples[0],
        conservative_paper_executable=(
            decision.price_triples[0].conservative_paper_executable + 1.0
        ),
    )
    manipulated_loss = altered_price.conservative_paper_executable * 100.0
    price_and_loss_forgery = _rehash_ticket(
        replace(
            decision,
            price_triples=(altered_price,),
            maximum_loss_usd=manipulated_loss,
            maximum_loss_fraction=round(manipulated_loss / 100_000.0, 12),
        )
    )
    with pytest.raises(
        ValueError, match="price triple is not mechanically reproducible"
    ):
        validate_paper_execution_ticket(price_and_loss_forgery)

    altered_leg = replace(decision.leg_terms[0], quantity=2)
    altered_leg = replace(
        altered_leg, content_hash=ticket_leg_content_hash(altered_leg)
    )
    coherent_quantity_forgery = _rehash_ticket(
        replace(
            decision,
            leg_terms=(altered_leg,),
            quantities=(2,),
            maximum_loss_usd=decision.maximum_loss_usd * 2.0,
            maximum_loss_fraction=round(decision.maximum_loss_fraction * 2.0, 12),
        )
    )
    with pytest.raises(ValueError, match="legs differ from its candidate snapshot"):
        validate_paper_execution_ticket(coherent_quantity_forgery)

    cardinality_forgery = _rehash_ticket(
        replace(
            decision,
            contract_ids=decision.contract_ids + decision.contract_ids,
            quantities=decision.quantities + decision.quantities,
            price_triples=decision.price_triples + decision.price_triples,
        )
    )
    with pytest.raises(ValueError, match="equal length"):
        validate_paper_execution_ticket(cardinality_forgery)


def test_fill_observation_has_public_content_and_evidence_validation() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)
    observation = build_paper_fill_observation(
        decision,
        (_quote("2026-07-17T14:00:20Z"),),
        1.0,
        v1_quote_gate_policy(),
    )
    validate_paper_fill_observation(observation, decision)

    realized_forgery = _rehash_fill(replace(observation, realized_evidence=True))
    with pytest.raises(ValueError, match="realized evidence"):
        validate_paper_fill_observation(realized_forgery, decision)

    profitability_forgery = _rehash_fill(
        replace(observation, profitability_evidence_eligible=True)
    )
    with pytest.raises(ValueError, match="profitability eligibility"):
        validate_paper_fill_observation(profitability_forgery, decision)

    price_forgery = _rehash_fill(
        replace(
            observation,
            conservative_prices=(observation.conservative_prices[0] + 1.0,),
        )
    )
    with pytest.raises(ValueError, match="prices differ"):
        validate_paper_fill_observation(price_forgery, decision)

    content_forgery = replace(observation, witnessed_at="2026-07-17T14:00:21Z")
    with pytest.raises(ValueError, match="time differs from its latest witness"):
        validate_paper_fill_observation(content_forgery, decision)


def test_ticket_reconstructs_candidate_dummy_and_both_loss_caps() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)

    lowered_candidate_cap = cast(
        dict[str, JsonValue], json.loads(decision.candidate_snapshot)
    )
    candidate_specification = cast(
        dict[str, JsonValue],
        lowered_candidate_cap["specification"],
    )
    candidate_structure = cast(
        dict[str, JsonValue], candidate_specification["structure"]
    )
    candidate_structure["maximum_loss"] = 100.0
    candidate_cap_forgery = _replace_candidate_snapshot(decision, lowered_candidate_cap)
    with pytest.raises(ValueError, match="exceeds its candidate cap"):
        validate_paper_execution_ticket(candidate_cap_forgery)

    lowered_dummy_cap = cast(
        dict[str, JsonValue], json.loads(decision.candidate_snapshot)
    )
    dummy_specification = cast(dict[str, JsonValue], lowered_dummy_cap["specification"])
    dummy_contract = cast(
        dict[str, JsonValue],
        dummy_specification["dummy_input_contract"],
    )
    dummy_contract["maximum_exposure_fraction"] = 0.001
    dummy_cap_forgery = _replace_candidate_snapshot(decision, lowered_dummy_cap)
    with pytest.raises(ValueError):
        validate_paper_execution_ticket(dummy_cap_forgery)

    invalid_dummy_hash = cast(
        dict[str, JsonValue], json.loads(decision.candidate_snapshot)
    )
    invalid_specification = cast(
        dict[str, JsonValue],
        invalid_dummy_hash["specification"],
    )
    invalid_contract = cast(
        dict[str, JsonValue],
        invalid_specification["dummy_input_contract"],
    )
    invalid_contract["contract_hash"] = HASH
    dummy_hash_forgery = _replace_candidate_snapshot(decision, invalid_dummy_hash)
    with pytest.raises(ValueError, match="Dummy contract hash"):
        validate_paper_execution_ticket(dummy_hash_forgery)


def test_fill_rejects_substituted_witness_hash_and_quote() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)
    observation = build_paper_fill_observation(
        decision,
        (_quote("2026-07-17T14:00:20Z"),),
        1.0,
        v1_quote_gate_policy(),
    )

    substituted_hash = _rehash_fill(replace(observation, witness_hashes=("b" * 64,)))
    with pytest.raises(ValueError, match="witness hashes are not quote-derived"):
        validate_paper_fill_observation(substituted_hash, decision)

    substituted_quote = _rehash_quote(
        replace(observation.witness_quotes[0], strike=501.0)
    )
    substituted_observation = build_paper_fill_observation(
        decision,
        (substituted_quote,),
        1.0,
        v1_quote_gate_policy(),
    )
    assert substituted_observation.paper_fill_status == "missed"
    assert "witness_contract_terms_mismatch" in substituted_observation.reason_codes


@pytest.mark.parametrize(
    "witness_time",
    (
        "2026-07-17T14:00:10.500000Z",
        "2026-07-17T14:01:12Z",
    ),
)
def test_pre_entry_and_post_cancel_witnesses_cannot_be_fills(
    witness_time: str,
) -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)
    observation = build_paper_fill_observation(
        decision,
        (_quote(witness_time),),
        1.0,
        v1_quote_gate_policy(),
    )
    assert observation.paper_fill_status == "missed"
    assert "witness_outside_entry_or_cancel_window" in observation.reason_codes


def test_public_decision_mapping_parsers_require_complete_exact_artifacts() -> None:
    ticket = _decision(*_setup(True))
    assert isinstance(ticket, PaperExecutionTicket)
    ticket_mapping = paper_execution_ticket_to_mapping(ticket)
    assert paper_execution_ticket_from_mapping(ticket_mapping) == ticket
    incomplete_ticket = dict(ticket_mapping)
    del incomplete_ticket["control_hash"]
    with pytest.raises(ValueError, match="canonical schema"):
        paper_execution_ticket_from_mapping(incomplete_ticket)
    missing_control_snapshot = dict(ticket_mapping)
    del missing_control_snapshot["control_snapshot"]
    with pytest.raises(ValueError, match="canonical schema"):
        paper_execution_ticket_from_mapping(missing_control_snapshot)

    abstention = _decision(*_setup(False))
    assert isinstance(abstention, AbstentionRecord)
    abstention_mapping = abstention_record_to_mapping(abstention)
    assert abstention_record_from_mapping(abstention_mapping) == abstention
    expanded_abstention = {**abstention_mapping, "unexpected": True}
    with pytest.raises(ValueError, match="canonical schema"):
        abstention_record_from_mapping(expanded_abstention)


def test_candidate_mapping_is_full_exact_and_reconstructed() -> None:
    candidate = _candidate(_opportunity(True))
    mapping = candidate_genome_to_mapping(candidate)
    assert candidate_genome_from_mapping(mapping) == candidate
    assert mapping["genome_hash"] == candidate.genome_hash

    with pytest.raises(ValueError, match="exact canonical schema"):
        candidate_genome_from_mapping({})
    tampered = dict(mapping)
    tampered["genome_hash"] = "b" * 64
    with pytest.raises(ValueError, match="hash does not match"):
        candidate_genome_from_mapping(tampered)


def test_candidate_rejects_nested_secrets_extras_and_semantic_nonsense() -> None:
    opportunity = _opportunity(True)
    source = _candidate(opportunity)
    mapping = candidate_genome_to_mapping(source)
    specification = cast(dict[str, JsonValue], mapping["specification"])
    economics = cast(dict[str, JsonValue], specification["economics"])
    economics["api_key"] = "forbidden"
    with pytest.raises(PermissionError, match="forbidden nested key"):
        create_candidate_genome(
            "secret",
            (),
            "family",
            "hypothesis",
            "fails",
            "options_expression",
            specification,
        )

    mapping = candidate_genome_to_mapping(source)
    specification = cast(dict[str, JsonValue], mapping["specification"])
    market_state = cast(dict[str, JsonValue], specification["market_state"])
    market_state["unexpected_but_benign"] = "x"
    with pytest.raises(ValueError, match="unsupported fields"):
        create_candidate_genome(
            "extra",
            (),
            "family",
            "hypothesis",
            "fails",
            "options_expression",
            specification,
        )

    mapping = candidate_genome_to_mapping(source)
    specification = cast(dict[str, JsonValue], mapping["specification"])
    management = cast(dict[str, JsonValue], specification["management"])
    management["exit_rule"] = ""
    with pytest.raises(ValueError, match="non-empty string"):
        create_candidate_genome(
            "empty",
            (),
            "family",
            "hypothesis",
            "fails",
            "options_expression",
            specification,
        )

    mapping = candidate_genome_to_mapping(source)
    specification = cast(dict[str, JsonValue], mapping["specification"])
    evaluation = cast(dict[str, JsonValue], specification["evaluation"])
    evaluation["negative_controls"] = ["shifted_features"]
    with pytest.raises(ValueError, match="canonical v1 required set"):
        create_candidate_genome(
            "weak-plan",
            (),
            "family",
            "hypothesis",
            "fails",
            "options_expression",
            specification,
        )


def test_abstention_candidate_is_an_exact_zero_exposure_no_position() -> None:
    opportunity = _opportunity(True)
    source = _candidate(opportunity)
    mapping = candidate_genome_to_mapping(source)
    specification = cast(dict[str, JsonValue], mapping["specification"])
    instrument_choice = cast(dict[str, JsonValue], specification["instrument_choice"])
    instrument_choice.update(
        {
            "use_options": False,
            "underlying_alternative": "none",
            "reason": "formal abstention",
        }
    )
    structure = cast(dict[str, JsonValue], specification["structure"])
    structure.update(
        {
            "type": "no_position",
            "legs": [],
            "maximum_loss": 0.0,
            "assignment_profile": "no_assignment",
            "exercise_profile": "no_exercise",
        }
    )
    sizing = cast(dict[str, JsonValue], specification["sizing"])
    sizing.update(
        {
            "method": "no_position",
            "uncertainty_haircut": 0.0,
            "maximum_position_fraction": 0.0,
            "maximum_portfolio_contribution": 0.0,
            "margin_limit": 0.0,
        }
    )
    risk = cast(dict[str, JsonValue], specification["risk"])
    for field_name in tuple(key for key in risk if key != "kill_conditions"):
        risk[field_name] = 0.0
    candidate = create_candidate_genome(
        "formal-abstention",
        (),
        "no_trade_policy",
        "uncertainty exceeds the action threshold",
        "new independently verified evidence arrives",
        "abstention_policy",
        specification,
    )
    assert (
        candidate_genome_from_mapping(candidate_genome_to_mapping(candidate))
        == candidate
    )
    decision = build_paper_decision(
        opportunity,
        candidate,
        DECISION_TIMESTAMP,
        (),
        v1_quote_gate_policy(),
        _controls(0.0),
        create_decision_market_context("2026-07-17", True),
        None,
    )
    assert isinstance(decision, AbstentionRecord)
    assert decision.reason_codes == tuple(sorted(decision.reason_codes))
    assert "candidate_mode_abstention_policy" in decision.reason_codes


def test_dynamic_membership_is_forward_only_typed_and_symbol_bounded() -> None:
    context = _dynamic_market_context(None)
    validate_decision_market_context(context)
    assert context.membership_mode == "independent_point_in_time"
    assert len(context.symbols) == 200

    with pytest.raises(ValueError, match="interval"):
        create_point_in_time_decision_market_context(
            "backdated",
            HASH,
            "dopey-point-in-time-universe-v1",
            "2026-07-17T14:00:00Z",
            "2026-07-17T13:59:00Z",
            "2026-07-17T20:00:00Z",
            "artifact://independent-universe/backdated.json",
            HASH,
            "attestation-backdated",
            HASH,
            ("SPY",),
            "2026-07-17",
        )
    with pytest.raises(ValueError, match="schema version"):
        create_point_in_time_decision_market_context(
            "wrong-schema",
            HASH,
            "arbitrary-v99",
            "2026-07-17T13:59:00Z",
            "2026-07-17T13:59:00Z",
            "2026-07-17T20:00:00Z",
            "artifact://independent-universe/wrong-schema.json",
            HASH,
            "attestation-wrong-schema",
            HASH,
            ("SPY",),
            "2026-07-17",
        )
    with pytest.raises(ValueError, match="market symbol"):
        _dynamic_market_context(("SPY/../../CONTROL",))
    with pytest.raises(ValueError, match="independent point-in-time"):
        create_decision_market_context("2026-07-17", False)


def test_initial_universe_preserves_200_watch_199_mechanics_and_vix_abstention() -> (
    None
):
    watch = v1_watch_universe()
    options = v1_options_mechanics_coverage()
    assert len(watch) == 200
    assert len(options) == 199
    assert set(watch).difference(options) == {"VIX"}
    early_close = create_decision_market_context("2026-11-27", True)
    assert early_close.session_close == "2026-11-27T18:00:00Z"

    opportunity = create_dummy_opportunity(
        "2026-07-17T14:00:00Z",
        "VIX",
        "volatility distribution",
        "5d",
        0.5,
        0.01,
        "2026-07-18T14:00:00Z",
        "dummy-v1",
        HASH,
        True,
    )
    candidate = _candidate(opportunity)
    quote = _rehash_quote(
        replace(
            _quote("2026-07-17T14:00:00Z"),
            contract_id="VIX-2026-08-21-call-500",
            underlying="VIX",
        )
    )
    price = build_price_triple(
        quote,
        DECISION_TIMESTAMP,
        v1_quote_gate_policy(),
        2.15,
        "debit",
        25.0,
        0.65,
        100,
    )
    decision = build_paper_decision(
        opportunity,
        candidate,
        DECISION_TIMESTAMP,
        (_request(quote),),
        v1_quote_gate_policy(),
        _controls(price.conservative_paper_executable * 100.0 / 100_000.0),
        create_decision_market_context("2026-07-17", True),
        None,
    )
    assert isinstance(decision, AbstentionRecord)
    assert "missing_option_chain_coverage" in decision.reason_codes


def test_real_prospective_ticket_binds_dynamic_context_but_cannot_self_certify() -> (
    None
):
    opportunity, candidate, quote, controls = _setup(False)
    context = _dynamic_market_context(None)
    evidence = create_prospective_paper_evidence(
        opportunity,
        candidate,
        context,
        "2026-07-17T14:00:05Z",
        {
            "dummy_source_artifact_hash": HASH,
            "quote_source_artifact_hash": HASH,
            "exposure_model_artifact_hash": HASH,
            "complete_cost_model_artifact_hash": HASH,
            "fair_value_input_stack_artifact_hash": HASH,
            "corporate_actions_artifact_hash": HASH,
            "dividends_artifact_hash": HASH,
            "rates_artifact_hash": HASH,
            "borrow_artifact_hash": HASH,
        },
    )
    decision = build_paper_decision(
        opportunity,
        candidate,
        DECISION_TIMESTAMP,
        (_request(quote),),
        v1_quote_gate_policy(),
        controls,
        context,
        evidence,
    )
    assert isinstance(decision, PaperExecutionTicket)
    assert decision.evidence_class == "prospective_market_evidence"
    assert decision.market_context_hash == evidence.market_context_hash
    assert decision.prospective_evidence_hash != HASH
    assert not decision.exposure_model_certified
    assert not decision.complete_cost_model_certified
    assert not decision.fair_value_input_stack_certified
    assert not decision.profitability_evidence_eligible

    forged = _rehash_ticket(
        replace(
            decision,
            exposure_model_certified=True,
            complete_cost_model_certified=True,
            fair_value_input_stack_certified=True,
            profitability_evidence_eligible=True,
        )
    )
    with pytest.raises(ValueError, match="cannot self-certify"):
        validate_paper_execution_ticket(forged)

    with pytest.raises(ValueError, match="causal window"):
        create_prospective_paper_evidence(
            opportunity,
            candidate,
            context,
            "2026-07-19T14:00:00Z",
            {
                "dummy_source_artifact_hash": HASH,
                "quote_source_artifact_hash": HASH,
                "exposure_model_artifact_hash": HASH,
                "complete_cost_model_artifact_hash": HASH,
                "fair_value_input_stack_artifact_hash": HASH,
                "corporate_actions_artifact_hash": HASH,
                "dividends_artifact_hash": HASH,
                "rates_artifact_hash": HASH,
                "borrow_artifact_hash": HASH,
            },
        )


def test_fill_outcomes_are_canonical_including_no_quote_and_nonfirm() -> None:
    decision = _decision(*_setup(True))
    assert isinstance(decision, PaperExecutionTicket)
    no_quote = build_paper_fill_observation(
        decision,
        (),
        1.0,
        v1_quote_gate_policy(),
    )
    assert no_quote.paper_fill_status == "missed"
    assert no_quote.witnessed_at == decision.cancellation_deadline
    assert no_quote.reason_codes == ("no_quote_witness_before_deadline",)
    mapping = paper_fill_observation_to_mapping(no_quote, decision)
    assert paper_fill_observation_from_mapping(mapping, decision) == no_quote
    with pytest.raises(ValueError, match="canonical schema"):
        paper_fill_observation_from_mapping({**mapping, "unexpected": True}, decision)

    nonfirm_quote = _rehash_quote(
        replace(_quote("2026-07-17T14:00:20Z"), quote_condition="nonfirm")
    )
    nonfirm = build_paper_fill_observation(
        decision,
        (nonfirm_quote,),
        1.0,
        v1_quote_gate_policy(),
    )
    assert nonfirm.paper_fill_status == "missed"
    assert any("nonfirm" in reason for reason in nonfirm.reason_codes)


def test_linked_worktree_missing_protected_resources_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".git").write_text(
        "gitdir: C:/example/worktrees/dopey\n", encoding="utf-8"
    )
    monkeypatch.setattr("dopey.ascendancy.tickets._repository_root", lambda: tmp_path)

    with pytest.raises(ValueError, match="missing protected universe_v1"):
        v1_watch_universe()
    with pytest.raises(ValueError, match="missing canonical environment_v1 artifacts"):
        require_v1_environment_hash(ENVIRONMENT_HASH)
