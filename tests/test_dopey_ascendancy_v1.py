from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from dopey.ascendancy.contracts import (
    candidate_genome_to_mapping,
    create_candidate_genome,
    create_dummy_opportunity,
)
from dopey.ascendancy.gates import (
    BehavioralState,
    CandidateExposure,
    PortfolioState,
    RiskLimits,
    evaluate_behavioral_gate,
    evaluate_risk_gate,
)
from dopey.ascendancy.ledger import (
    append_canonical_ascendancy_record,
    ledger_anchor_path,
    verify_hash_chained_ledger,
)
from dopey.ascendancy.identity import canonical_hash
from dopey.ascendancy.attribution import (
    ClosingLineValueInputs,
    PnLAttribution,
    calculate_closing_line_value,
    reconcile_pnl,
)
from dopey.ascendancy.behavioral_firewall import (
    BehavioralDecisionEvent,
    BehavioralFirewallState,
    advance_behavioral_firewall,
)
from dopey.ascendancy.negative_controls import (
    NegativeControlResult,
    evaluate_negative_controls,
)
from dopey.ascendancy.policy_ids import V1_REQUIRED_NEGATIVE_CONTROL_IDS
from dopey.ascendancy.negative_control_generation import (
    circular_shift,
    deterministic_permutation,
    invert_directional_signal,
)
from dopey.ascendancy.paired_evaluation import (
    MatchedUtilityObservation,
    evaluate_matched_baseline_superiority,
)
from dopey.ascendancy.pricing import (
    QuoteGatePolicy,
    QuoteSnapshot,
    build_price_triple,
    evaluate_quote_gate,
    quote_snapshot_content_hash,
)
from dopey.ascendancy.promotion import (
    PromotionEvidence,
    _evaluate_promotion_for_root,
    canonical_candidate_registration,
    v1_promotion_policy,
)
from dopey.ascendancy.retirement import (
    CandidateMonitoringState,
    RetirementPolicy,
    evaluate_retirement,
)
from dopey.ascendancy.router import RouteCandidate, route_validated_candidate
from dopey.ascendancy.stress import (
    PaperEconomics,
    RequiredStressEvidence,
    evaluate_required_stress_evidence,
    evaluate_stress_matrix,
    v1_required_stress_requirements,
    v1_required_stress_scenarios,
)
from dopey.ascendancy.tickets import (
    AbstentionRecord,
    DecisionControlInputs,
    PaperExecutionTicket,
    PaperPriceRequest,
    build_paper_decision,
    build_paper_fill_observation,
    create_decision_market_context,
    v1_risk_limits,
)
from sealed_evaluator_client.aggregate_contract import (
    SealedAggregateResponse,
    validate_aggregate_response,
)
from sealed_evaluator_client.budget import reserve_sealed_submission
from verifier.path_policy import assert_candidate_write_path_allowed
from verifier.environment_freeze import verify_environment_freeze
from verifier.protected_manifest import (
    build_protected_manifest,
    file_sha256,
    verify_ascendancy_protected_manifest,
    verify_protected_manifest,
)


HASH = "a" * 64
ENVIRONMENT_HASH = "811d348d94e151087cd77d496bd1f5135b24dd40ba107b5d860cde34b8475652"
QUOTE_POLICY = QuoteGatePolicy(15.0, 0.10, 0.05, 5, 25)


def _leg(
    side: str,
    option_type: str,
    strike: float,
    quantity: int,
    expiry: str = "2026-08-21",
    underlying: str = "SPY",
) -> dict:
    return {
        "contract_id": f"{underlying}-{expiry}-{option_type}-{strike:g}",
        "side": side,
        "underlying": underlying,
        "option_type": option_type,
        "expiry": expiry,
        "strike": strike,
        "quantity": quantity,
        "multiplier": 100,
        "deliverable": "100 shares",
        "option_style": "american",
        "settlement_type": "physical",
    }


def _opportunity():
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
        True,
    )


def _spec(structure_type: str, legs: list[dict], opportunity) -> dict:
    return {
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
            "type": structure_type,
            "legs": legs,
            "maximum_loss": 1000.0,
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
            "drawdown_limit": 0.1,
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


def _candidate(
    structure_type: str = "bull_call_debit_spread",
    legs: list[dict] | None = None,
    opportunity=None,
):
    selected_opportunity = opportunity if opportunity is not None else _opportunity()
    selected = (
        legs
        if legs is not None
        else [_leg("buy", "call", 500.0, 1), _leg("sell", "call", 510.0, 1)]
    )
    return create_candidate_genome(
        "c1",
        (),
        "defined_risk_directional",
        "frozen hypothesis",
        "fails baseline",
        "options_expression",
        _spec(structure_type, selected, selected_opportunity),
    )


def _quote(
    observed: str = "2026-07-17T14:00:00Z",
    tier: str = "nbbo_quote",
    contract_id: str = "SPY-2026-08-21-call-500",
    bid: float = 2.0,
    ask: float = 2.2,
) -> QuoteSnapshot:
    provisional = QuoteSnapshot(
        contract_id,
        "chain-1",
        observed,
        observed,
        bid,
        ask,
        10,
        12,
        2.1,
        100,
        500,
        "fixture://quote",
        HASH,
        "0" * 64,
        "opra_consolidated",
        "regular",
        tier,
        True,
        "american",
        "physical",
        100,
        "100 shares",
        False,
        False,
        "SPY",
        "call",
        "2026-08-21",
        500.0,
    )
    return replace(provisional, content_hash=quote_snapshot_content_hash(provisional))


def _rehash_quote(quote: QuoteSnapshot) -> QuoteSnapshot:
    return replace(quote, content_hash=quote_snapshot_content_hash(quote))


def _controls(
    maximum_loss_fraction: float, days_to_expiration: int
) -> DecisionControlInputs:
    exposure = CandidateExposure(
        True,
        days_to_expiration,
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
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    )
    controls = tuple(
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
        controls,
        V1_REQUIRED_NEGATIVE_CONTROL_IDS,
        "candidate-author",
    )


def _paper_price_request(quote: QuoteSnapshot) -> PaperPriceRequest:
    return PaperPriceRequest(quote, 2.15, "debit", 25.0, 0.65, 100)


def _ledger_payload(experiment_id: str, status: str) -> dict:
    return {
        "event_time": "2026-07-17T02:00:00Z",
        "code_version": "test",
        "data_hash": HASH,
        "experiment_id": experiment_id,
        "candidate_id": "c1",
        "frozen_specification_hash": HASH,
        "result_artifact_hash": HASH,
        "substantive_trial": True,
        "status": status,
    }


def test_dummy_contract_is_content_addressed_and_frozen() -> None:
    opportunity = _opportunity()
    assert opportunity.opportunity_id.startswith("dummy-")
    with pytest.raises(FrozenInstanceError):
        opportunity.underlying = "QQQ"  # type: ignore[misc]
    with pytest.raises(ValueError, match="SHA-256"):
        create_dummy_opportunity(
            "2026-07-17T14:00:00Z",
            "SPY",
            "x",
            "5d",
            0.6,
            0.01,
            "2026-07-18T14:00:00Z",
            "v1",
            "z" * 64,
            False,
        )


def test_candidate_is_deeply_immutable_and_rejects_nonfinite() -> None:
    candidate = _candidate()
    with pytest.raises(TypeError):
        candidate.specification["risk"] = {}  # type: ignore[index]
    bad = _spec("long_call", [_leg("buy", "call", 500.0, 1)], _opportunity())
    bad["risk"]["delta_limit"] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        create_candidate_genome("c2", (), "x", "h", "f", "options_expression", bad)


@pytest.mark.parametrize(
    ("structure_type", "legs"),
    [
        (
            "vertical_spread",
            [_leg("sell", "call", 500.0, 10), _leg("buy", "put", 490.0, 1)],
        ),
        (
            "bear_call_credit_spread",
            [
                _leg("sell", "call", 500.0, 1),
                _leg("buy", "call", 510.0, 1, "2026-09-18"),
            ],
        ),
        (
            "bear_call_credit_spread",
            [_leg("sell", "call", 500.0, 1), _leg("buy", "call", 490.0, 1)],
        ),
        (
            "bear_call_credit_spread",
            [_leg("sell", "call", 500.0, 2), _leg("buy", "call", 510.0, 1)],
        ),
    ],
)
def test_exact_defined_risk_topology_rejects_false_protection(
    structure_type: str, legs: list[dict]
) -> None:
    with pytest.raises(ValueError):
        _candidate(structure_type, legs)


def test_quote_gate_requires_timestamped_complete_sized_nbbo() -> None:
    policy = QuoteGatePolicy(15.0, 0.10, 0.05, 5, 25)
    passed = evaluate_quote_gate(_quote(), "2026-07-17T14:00:10Z", policy)
    assert passed.passed
    public = evaluate_quote_gate(
        _quote(tier="public_snapshot_quote"), "2026-07-17T14:00:10Z", policy
    )
    assert (
        not public.passed
        and "quote_tier_not_paper_executable:public_snapshot_quote"
        in public.reason_codes
    )
    stale = evaluate_quote_gate(_quote(), "2026-07-17T14:01:00Z", policy)
    assert "stale_quote" in stale.reason_codes
    missing_size = evaluate_quote_gate(
        _rehash_quote(replace(_quote(), bid_size=0)), "2026-07-17T14:00:10Z", policy
    )
    assert "quote_size_missing" in missing_size.reason_codes
    mutated = evaluate_quote_gate(
        replace(_quote(), ask=1.0), "2026-07-17T14:00:10Z", policy
    )
    assert "quote_identity_incomplete" in mutated.reason_codes


def test_three_prices_are_separate_and_nbbo_bound() -> None:
    triple = build_price_triple(
        _quote(), "2026-07-17T14:00:10Z", QUOTE_POLICY, 2.15, "debit", 25.0, 0.65, 100
    )
    assert triple.observed_midpoint == 2.1
    assert triple.model_fair_value == 2.15
    assert triple.conservative_paper_executable > 2.2
    assert not triple.profitability_evidence_eligible
    with pytest.raises(ValueError, match="passing quote gate"):
        build_price_triple(
            _quote(tier="public_snapshot_quote"),
            "2026-07-17T14:00:10Z",
            QUOTE_POLICY,
            2.15,
            "debit",
            25.0,
            0.65,
            100,
        )
    with pytest.raises(ValueError, match="multiplier"):
        build_price_triple(
            _quote(),
            "2026-07-17T14:00:10Z",
            QUOTE_POLICY,
            2.15,
            "debit",
            25.0,
            0.65,
            10,
        )


def test_risk_and_behavior_gates_fail_closed() -> None:
    exposure = CandidateExposure(
        defined_risk=True,
        days_to_expiration=0,
        maximum_loss_fraction=0.005,
        margin_fraction=0.01,
        expected_shortfall_fraction=0.01,
        ruin_probability=0.0001,
        delta=float("nan"),
        gamma=0,
        theta=0,
        vega=0,
        vanna=0,
        charm=0,
        vomma=0,
        skew=0,
        correlation=0,
        event=0,
        liquidity=0,
        gap=0,
    )
    portfolio = PortfolioState(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    limits = RiskLimits(
        0.01,
        0.1,
        0.03,
        0.001,
        0.02,
        0.1,
        10,
        10,
        10,
        10,
        10,
        10,
        10,
        10,
        10,
        10,
        10,
        10,
        False,
    )
    risk = evaluate_risk_gate(exposure, portfolio, limits)
    assert not risk.passed
    assert {
        "candidate_exposure_uncomputable",
        "zero_dte_requires_dedicated_intraday_evidence",
    }.issubset(risk.reason_codes)
    behavior = evaluate_behavioral_gate(
        BehavioralState(1.2, 1.1, 1, True, True, True, False)
    )
    assert (
        not behavior.passed
        and behavior.automatic_effect == "forced_cooldown_and_review"
    )


def test_negative_control_positive_anomaly_blocks() -> None:
    result = NegativeControlResult(
        "shifted_features", "reviewer", "e1", 0.2, 0.01, True, None
    )
    gate = evaluate_negative_controls(
        (result,), frozenset({"shifted_features"}), "author"
    )
    assert not gate.passed
    assert "unexplained_negative_control_anomaly:shifted_features" in gate.reason_codes
    invalid = evaluate_negative_controls(
        (replace(result, observed_absolute_effect=float("nan")),),
        frozenset({"shifted_features"}),
        "author",
    )
    assert not invalid.passed
    assert "negative_control_effect_invalid:shifted_features" in invalid.reason_codes


def test_required_stress_registry_covers_all_protocol_families_and_fails_closed() -> (
    None
):
    requirements = v1_required_stress_requirements()
    assert {family for family, _ in requirements} == {
        "cost",
        "timing",
        "liquidity",
        "volatility",
        "price_path",
        "operational",
        "portfolio",
        "statistical",
        "behavioral",
    }
    assert len(requirements) == len({scenario_id for _, scenario_id in requirements})
    completed = tuple(
        RequiredStressEvidence(scenario_id, family, True, True, f"evidence-{index}")
        for index, (family, scenario_id) in enumerate(requirements, start=1)
    )
    assert evaluate_required_stress_evidence(completed).passed is True
    missing = evaluate_required_stress_evidence(completed[:-1])
    assert missing.passed is False
    assert any(
        reason.startswith("missing_required_stress:") for reason in missing.reason_codes
    )
    failed_last = (
        *completed[:-1],
        RequiredStressEvidence(
            completed[-1].scenario_id, completed[-1].family, True, False, "failed-proof"
        ),
    )
    failed = evaluate_required_stress_evidence(failed_last)
    assert failed.passed is False
    assert f"stress_failed:{completed[-1].scenario_id}" in failed.reason_codes


def test_hash_chained_ledger_rejects_duplicate_and_detects_tamper(
    tmp_path: Path,
) -> None:
    path = tmp_path / "EXPERIMENT_REGISTRY.jsonl"
    with pytest.raises(ValueError, match="protected chain fields"):
        append_canonical_ascendancy_record(
            tmp_path,
            "experiment",
            "trusted-id",
            {**_ledger_payload("e0", "completed"), "record_id": "payload-override"},
        )
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r1", _ledger_payload("e1", "completed")
    )
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r2", _ledger_payload("e2", "failed")
    )
    assert len(verify_hash_chained_ledger(path)) == 2
    with pytest.raises(ValueError, match="already exists"):
        append_canonical_ascendancy_record(
            tmp_path, "experiment", "r1", _ledger_payload("e3", "completed")
        )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '"status":"failed"', '"status":"completed"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_hash_chained_ledger(path)


def test_hash_chained_ledger_detects_valid_prefix_truncation(tmp_path: Path) -> None:
    path = tmp_path / "EXPERIMENT_REGISTRY.jsonl"
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r1", _ledger_payload("e1", "completed")
    )
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r2", _ledger_payload("e2", "failed")
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(f"{lines[0]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="truncation or replacement"):
        verify_hash_chained_ledger(path)


def test_hash_chained_ledger_recovers_stranded_lock(tmp_path: Path) -> None:
    path = tmp_path / "EXPERIMENT_REGISTRY.jsonl"
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r1", _ledger_payload("e1", "completed")
    )
    lock_path = path.with_suffix(".jsonl.lock")
    lock_path.write_text("", encoding="ascii")  # old-protocol stranded lock
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r2", _ledger_payload("e2", "completed")
    )
    lock_path.write_text("99999999", encoding="ascii")  # dead-pid stranded lock
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r3", _ledger_payload("e3", "failed")
    )
    assert len(verify_hash_chained_ledger(path)) == 3
    assert not lock_path.exists()


def test_hash_chained_ledger_repins_anchor_lagging_after_crash(tmp_path: Path) -> None:
    path = tmp_path / "EXPERIMENT_REGISTRY.jsonl"
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r1", _ledger_payload("e1", "completed")
    )
    append_canonical_ascendancy_record(
        tmp_path, "experiment", "r2", _ledger_payload("e2", "completed")
    )
    records = verify_hash_chained_ledger(path)
    anchor_path = ledger_anchor_path(path)
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    # Simulate a crash between the second record append and the anchor write.
    anchor["record_count"] = 1
    anchor["head_hash"] = records[0]["entry_hash"]
    anchor_body = {key: value for key, value in anchor.items() if key != "anchor_hash"}
    anchor["anchor_hash"] = canonical_hash(anchor_body)
    anchor_path.write_text(json.dumps(anchor), encoding="utf-8")

    assert len(verify_hash_chained_ledger(path)) == 2
    repinned = json.loads(anchor_path.read_text(encoding="utf-8"))
    assert repinned["record_count"] == 2
    assert repinned["head_hash"] == records[-1]["entry_hash"]


def test_promotion_uses_registry_accounting_and_stays_l5_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_genome = _candidate()
    frozen_specification = {
        "artifact_type": "frozen_candidate_specification",
        "schema_version": "dopey-frozen-candidate-v1",
        "candidate_id": "c1",
        "candidate_author_id": "author",
        "candidate_mode": "options_expression",
        "candidate_genome_hash": candidate_genome.genome_hash,
        "candidate_genome": candidate_genome_to_mapping(candidate_genome),
        "frozen_at": "2026-07-17T01:00:00Z",
        "paper_only": True,
        "live_blocked": True,
    }
    registration = canonical_candidate_registration(
        "c1",
        "author",
        "2026-07-17T01:00:00Z",
        frozen_specification,
    )
    candidate_hash = str(registration["frozen_specification_hash"])
    (tmp_path / "CANDIDATE_LINEAGE.jsonl").write_text(
        json.dumps(
            {
                "environment_id": "dopey-options-paper-v1",
                "record_type": "registry_initialization",
                "registered_candidates": 0,
                "status": "empty",
            }
        )
        + "\n"
        + json.dumps(registration)
        + "\n",
        encoding="utf-8",
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "r1",
        {
            **_ledger_payload("e1", "completed"),
            "frozen_specification_hash": candidate_hash,
        },
    )
    common = {
        "event_time": "2026-07-17T03:00:00Z",
        "code_version": "test",
        "data_hash": HASH,
        "candidate_id": "c1",
        "frozen_specification_hash": candidate_hash,
        "environment_id": "dopey-options-paper-v1",
        "evaluator_id": "independent-reviewer",
        "substantive_trial": False,
        "status": "completed",
    }
    append_canonical_ascendancy_record(
        tmp_path,
        "proof",
        "proof-development",
        {
            **common,
            "experiment_id": "proof-development",
            "proof_type": "development",
            "evidence_id": "development-e1",
            "passed": True,
        },
    )
    for index, control_id in enumerate(
        sorted(v1_promotion_policy().required_negative_controls), start=1
    ):
        append_canonical_ascendancy_record(
            tmp_path,
            "proof",
            f"proof-control-{index}",
            {
                **common,
                "experiment_id": f"proof-control-{index}",
                "proof_type": "negative_control",
                "evidence_id": f"negative-control-e{index}",
                "passed": True,
                "control_id": control_id,
                "observed_absolute_effect": 0.0,
                "maximum_expected_absolute_effect": 0.01,
                "explanation_evidence_id": None,
            },
        )
    budget_path = tmp_path / "HOLDOUT_BUDGET.json"
    budget_path.write_text("{}\n", encoding="utf-8")
    forward_path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    forward_path.parent.mkdir(parents=True, exist_ok=True)
    forward_path.write_text("", encoding="utf-8")
    source_manifest = tmp_path / "source-manifest.json"
    source_manifest.write_text("{}\n", encoding="utf-8")
    (tmp_path / "DATA_MANIFEST.json").write_text(
        json.dumps({"source_manifest": str(source_manifest.resolve())}),
        encoding="utf-8",
    )

    def dynamic_state(root: Path) -> dict[str, object]:
        return {
            "schema_version": "dopey-dynamic-state-audit-v1",
            "environment_id": "dopey-options-paper-v1",
            "dynamic_state_hash": HASH,
            "files": {
                "CANDIDATE_LINEAGE.jsonl": file_sha256(
                    root / "CANDIDATE_LINEAGE.jsonl"
                ),
                "EXPERIMENT_REGISTRY.jsonl": file_sha256(
                    root / "EXPERIMENT_REGISTRY.jsonl"
                ),
                "PROOF_LEDGER.jsonl": file_sha256(root / "PROOF_LEDGER.jsonl"),
                "HOLDOUT_BUDGET.json": file_sha256(root / "HOLDOUT_BUDGET.json"),
                "shadow_trading/FORWARD_EVIDENCE.jsonl": file_sha256(
                    root / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
                ),
            },
                "external_anchor_verified": False,
                "external_trust_root_pinned_role_identities": {},
                "certification_eligible": False,
        }

    def full_audit(root: Path, observed_source_manifest: Path) -> dict[str, object]:
        assert observed_source_manifest == source_manifest.resolve()
        return {
            "schema_version": "dopey-ascendancy-audit-v1",
            "environment_id": "dopey-options-paper-v1",
            "status": "pass_fail_closed_research_kernel",
            "paper_only": True,
            "live_blocked": True,
            "action_ready": False,
            "profitability_edge_demonstrated": False,
            "protected_manifest_sha256": HASH,
            "source_manifest_sha256": HASH,
            "external_anchor_verified": False,
            "certification_eligible": False,
            "dynamic_state": dynamic_state(root),
        }

    monkeypatch.setattr("verifier.audit.run_ascendancy_audit", full_audit)
    evidence = PromotionEvidence(
        "c1",
        "author",
        "L0",
        "L1",
        "2026-07-17T01:00:00Z",
        candidate_hash,
        "2026-07-17T08:00:00Z",
    )
    decision = _evaluate_promotion_for_root(
        evidence,
        v1_promotion_policy(),
        tmp_path,
    )
    assert not decision.allowed and decision.trial_accounting.registered == 1
    assert "external_dynamic_state_anchor_not_verified" in decision.reason_codes
    assert any(
        reason.startswith("stage_proof_authentication_invalid:")
        for reason in decision.reason_codes
    )
    assert decision.live_blocked and decision.requested_level == "L1"
    with pytest.raises(ValueError, match="canonical lineage registration"):
        _evaluate_promotion_for_root(
            replace(evidence, candidate_id="c2"),
            v1_promotion_policy(),
            tmp_path,
        )


def test_paper_ticket_requires_later_quote_cross_for_fill() -> None:
    opportunity = _opportunity()
    leg = _leg("buy", "call", 500.0, 1)
    candidate = _candidate("long_call", [leg], opportunity)
    quote = _quote(contract_id=leg["contract_id"])
    price = build_price_triple(
        quote, "2026-07-17T14:00:10Z", QUOTE_POLICY, 2.15, "debit", 25.0, 0.65, 100
    )
    maximum_loss_fraction = price.conservative_paper_executable * 100.0 / 100_000.0
    decision = build_paper_decision(
        opportunity,
        candidate,
        "2026-07-17T14:00:10Z",
        (_paper_price_request(quote),),
        QUOTE_POLICY,
        _controls(maximum_loss_fraction, 35),
        create_decision_market_context("2026-07-17", True),
        None,
    )
    assert isinstance(decision, PaperExecutionTicket)
    alternate = build_paper_decision(
        opportunity,
        candidate,
        "2026-07-17T14:00:10Z",
        (_paper_price_request(quote),),
        QUOTE_POLICY,
        _controls(maximum_loss_fraction, 35),
        create_decision_market_context("2026-07-17", True),
        None,
    )
    assert isinstance(alternate, PaperExecutionTicket)
    assert alternate.ticket_id == decision.ticket_id
    early = build_paper_fill_observation(decision, (quote,), 1.0, QUOTE_POLICY)
    assert early.paper_fill_status == "missed"
    assert "witness_not_after_decision" in early.reason_codes
    missed_quote = _quote(
        "2026-07-17T14:00:20Z", contract_id=leg["contract_id"], bid=2.5, ask=2.6
    )
    missed = build_paper_fill_observation(decision, (missed_quote,), 1.0, QUOTE_POLICY)
    assert missed.paper_fill_status == "missed" and missed.conservative_prices == ()
    filled_quote = _quote("2026-07-17T14:00:20Z", contract_id=leg["contract_id"])
    filled = build_paper_fill_observation(decision, (filled_quote,), 1.0, QUOTE_POLICY)
    assert filled.paper_fill_status == "filled" and not filled.realized_evidence
    with pytest.raises(ValueError, match="lifecycle differs"):
        build_paper_fill_observation(
            replace(decision, management_rule="tampered"),
            (filled_quote,),
            1.0,
            QUOTE_POLICY,
        )
    with pytest.raises(ValueError, match="content hash"):
        build_paper_fill_observation(
            decision,
            (replace(filled_quote, bid=-2.0, ask=0.0),),
            1.0,
            QUOTE_POLICY,
        )


def test_candidate_cannot_be_rebound_to_another_dummy_opportunity() -> None:
    opportunity = _opportunity()
    leg = _leg("buy", "call", 500.0, 1)
    candidate = _candidate("long_call", [leg], opportunity)
    other = create_dummy_opportunity(
        opportunity.creation_timestamp,
        "QQQ",
        opportunity.forecast,
        opportunity.intended_horizon,
        opportunity.confidence,
        opportunity.maximum_exposure_fraction,
        opportunity.expiration_timestamp,
        opportunity.upstream_version,
        opportunity.provenance_hash,
        opportunity.synthetic,
    )
    quote = _quote(contract_id=leg["contract_id"])
    price = build_price_triple(
        quote, "2026-07-17T14:00:10Z", QUOTE_POLICY, 2.15, "debit", 25.0, 0.65, 100
    )
    with pytest.raises(ValueError, match="not bound"):
        build_paper_decision(
            other,
            candidate,
            "2026-07-17T14:00:10Z",
            (_paper_price_request(quote),),
            QUOTE_POLICY,
            _controls(price.conservative_paper_executable * 100.0 / 100_000.0, 35),
            create_decision_market_context("2026-07-17", True),
            None,
        )


def test_forged_dummy_and_internal_control_gate_fail_closed() -> None:
    opportunity = _opportunity()
    leg = _leg("buy", "call", 500.0, 1)
    candidate = _candidate("long_call", [leg], opportunity)
    quote = _quote(contract_id=leg["contract_id"])
    price = build_price_triple(
        quote, "2026-07-17T14:00:10Z", QUOTE_POLICY, 2.15, "debit", 25.0, 0.65, 100
    )
    controls = _controls(price.conservative_paper_executable * 100.0 / 100_000.0, 35)
    with pytest.raises(ValueError, match="contract hash"):
        build_paper_decision(
            replace(opportunity, forecast="tampered"),
            candidate,
            "2026-07-17T14:00:10Z",
            (_paper_price_request(quote),),
            QUOTE_POLICY,
            controls,
            create_decision_market_context("2026-07-17", True),
            None,
        )
    invalid_exposure = replace(controls.candidate_exposure, delta=float("nan"))
    with pytest.raises(ValueError, match="non-finite|Out of range"):
        build_paper_decision(
            opportunity,
            candidate,
            "2026-07-17T14:00:10Z",
            (_paper_price_request(quote),),
            QUOTE_POLICY,
            replace(controls, candidate_exposure=invalid_exposure),
            create_decision_market_context("2026-07-17", True),
            None,
        )


def test_candidate_leg_binding_and_cardinality_fail_closed() -> None:
    opportunity = _opportunity()
    with pytest.raises(ValueError, match="underlying"):
        _candidate(
            "long_call", [_leg("buy", "call", 500.0, 1, underlying="QQQ")], opportunity
        )
    leg = _leg("buy", "call", 500.0, 1)
    candidate = _candidate("long_call", [leg], opportunity)
    blocked = build_paper_decision(
        opportunity,
        candidate,
        "2026-07-17T14:00:10Z",
        (),
        QUOTE_POLICY,
        _controls(0.001, 35),
        create_decision_market_context("2026-07-17", True),
        None,
    )
    assert isinstance(blocked, AbstentionRecord)
    assert "paper_ticket_leg_cardinality_mismatch" in blocked.reason_codes


def test_candidate_paths_and_sealed_response_are_isolated(tmp_path: Path) -> None:
    (tmp_path / "candidates").mkdir()
    assert_candidate_write_path_allowed(tmp_path, tmp_path / "candidates" / "c1.json")
    with pytest.raises(PermissionError, match="protected"):
        assert_candidate_write_path_allowed(
            tmp_path, tmp_path / "verifier" / "policy.py"
        )
    request_id = "sealed-request-1234567890abcdef12345678"
    response = SealedAggregateResponse(
        request_id,
        "c1",
        HASH,
        1,
        (("lower_bound_utility", 0.0),),
        (),
        "sealed-v1",
        True,
        "2026-07-17T03:00:00Z",
    )
    validation_args = (
        frozenset({"lower_bound_utility"}),
        request_id,
        "c1",
        HASH,
        "sealed-v1",
    )
    validate_aggregate_response(response, *validation_args)
    with pytest.raises(ValueError, match="canonical UTC ISO-8601"):
        validate_aggregate_response(
            replace(response, evaluator_issued_at="2026-07-16T22:00:00-05:00"),
            *validation_args,
        )
    with pytest.raises(ValueError, match="passed verdict must be boolean"):
        validate_aggregate_response(replace(response, passed=1), *validation_args)
    with pytest.raises(
        ValueError, match="requires aggregate metrics and no failure codes"
    ):
        validate_aggregate_response(
            replace(response, failure_codes=("candidate_failed_metric_floor",)),
            *validation_args,
        )
    validate_aggregate_response(
        replace(
            response,
            passed=False,
            aggregate_metrics=(),
            failure_codes=("candidate_failed_metric_floor",),
        ),
        *validation_args,
    )
    with pytest.raises(ValueError, match="one-shot"):
        validate_aggregate_response(
            replace(response, submission_number=2), *validation_args
        )
    with pytest.raises(ValueError, match="undeclared"):
        validate_aggregate_response(
            replace(response, aggregate_metrics=(("raw_return", 1.0),)),
            *validation_args,
        )
    with pytest.raises(ValueError, match="finite"):
        validate_aggregate_response(
            replace(
                response, aggregate_metrics=(("lower_bound_utility", float("nan")),)
            ),
            *validation_args,
        )
    with pytest.raises(ValueError, match="failure codes"):
        validate_aggregate_response(
            replace(response, failure_codes=("SPY_2026-07-17_2.15",)),
            *validation_args,
        )


def test_sealed_budget_is_atomic_one_shot_and_aggregate_only(tmp_path: Path) -> None:
    budget_path = tmp_path / "HOLDOUT_BUDGET.json"
    budget_path.write_text(
        json.dumps(
            {
                "schema_version": "dopey-sealed-budget-v1",
                "aggregate_feedback_only": True,
                "raw_holdout_access": False,
                "maximum_submissions_per_frozen_candidate": 1,
                "maximum_total_submissions": 2,
                "allowed_aggregate_metric_ids": ["lower_bound_utility"],
                "submissions_used": 0,
                "candidate_submissions": {},
                "frozen_hash_submissions": {},
                "status": "configured_external_evaluator",
                "environment_id": "dopey-options-paper-v1",
                "evaluator_id": "independent-sealed-evaluator",
                "evaluator_version": "sealed-v1",
            }
        ),
        encoding="utf-8",
    )
    request = reserve_sealed_submission(
        budget_path,
        "c1",
        HASH,
        ("lower_bound_utility",),
        "sealed-v1",
        "2026-07-17T14:00:00Z",
    )
    assert request.submission_number == 1 and not request.raw_holdout_access
    with pytest.raises(PermissionError, match="already consumed"):
        reserve_sealed_submission(
            budget_path,
            "c1",
            HASH,
            ("lower_bound_utility",),
            "sealed-v1",
            "2026-07-17T14:00:01Z",
        )
    with pytest.raises(PermissionError, match="specification hash"):
        reserve_sealed_submission(
            budget_path,
            "renamed-candidate",
            HASH,
            ("lower_bound_utility",),
            "sealed-v1",
            "2026-07-17T14:00:02Z",
        )


def test_protected_manifest_detects_mutation(tmp_path: Path) -> None:
    protected = tmp_path / "constitution.md"
    protected.write_text("paper-only\n", encoding="utf-8")
    manifest = build_protected_manifest(tmp_path, ("constitution.md",))
    manifest_path = tmp_path / "PROTECTED_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    verify_protected_manifest(tmp_path, manifest_path)
    protected.write_text("live-enabled\n", encoding="utf-8")
    with pytest.raises(ValueError, match="protected manifest mismatch"):
        verify_protected_manifest(tmp_path, manifest_path)


def test_repository_environment_v1_is_complete_and_frozen() -> None:
    root = Path(__file__).resolve().parents[1]
    verify_environment_freeze(
        root / "environments" / "environment_v1.json",
        root / "ENVIRONMENT_V1_FREEZE.json",
    )
    verify_ascendancy_protected_manifest(root, root / "PROTECTED_MANIFEST.json")


def test_mechanics_evaluators_are_matched_selective_and_fail_closed() -> None:
    observations = tuple(
        MatchedUtilityObservation(
            f"o{index}", "c1", "no_trade", 0.02 + index / 1000.0, 0.0, True, True
        )
        for index in range(1, 5)
    )
    superiority = evaluate_matched_baseline_superiority(
        observations,
        frozenset({"no_trade"}),
        4,
        1.645,
    )
    assert superiority.passed_all_required_baselines
    values = (1.0, 2.0, 3.0, 4.0)
    assert circular_shift(values, 1) == (4.0, 1.0, 2.0, 3.0)
    assert deterministic_permutation(values, 7) != values
    assert invert_directional_signal(values) == (-1.0, -2.0, -3.0, -4.0)

    attribution = PnLAttribution(
        10.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
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
        1.0,
    )
    assert reconcile_pnl(attribution, 1e-9).reconciled
    closing_line = calculate_closing_line_value(
        ClosingLineValueInputs(
            "debit", 2.0, 2.5, 0.1, -0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.05
        )
    )
    assert closing_line.favorable

    route = route_validated_candidate(
        "liquid_non_event",
        (
            RouteCandidate(
                "l3",
                HASH,
                "promotion-l3",
                "routing-l3",
                "retirement-l3",
                "L3",
                frozenset({"liquid_non_event"}),
                0.5,
                True,
                True,
                False,
            ),
            RouteCandidate(
                "l4",
                HASH,
                "promotion-l4",
                "routing-l4",
                "retirement-l4",
                "L4",
                frozenset({"liquid_non_event"}),
                0.1,
                True,
                True,
                False,
            ),
        ),
        "L4",
        "2026-07-17T08:00:00Z",
    )
    assert route.selected_candidate_id is None and route.live_blocked
    assert route.action == "abstain"
    assert set(route.reason_codes).intersection(
        {
            "canonical_audit_unavailable_or_invalid",
            "canonical_audit_certification_ineligible",
            "external_dynamic_state_anchor_unverified",
        }
    )
    retirement = evaluate_retirement(
        CandidateMonitoringState(0.01, 0.01, 0.11, 0, 0.0, True, True, True),
        RetirementPolicy(0.05, 0.05, 0.10, 0, 0.10),
    )
    assert retirement.state == "RETIRED"

    stressed = evaluate_stress_matrix(
        PaperEconomics(0.20, 0.01, 0.01, 0.01, 0.01, 0.0, 0.0, 0.0),
        v1_required_stress_scenarios(),
        0.0,
    )
    assert {result.scenario_id for result in stressed} == {
        scenario.scenario_id for scenario in v1_required_stress_scenarios()
    }
    transition = advance_behavioral_firewall(
        BehavioralFirewallState(
            "2026-07-17T13:00:00Z", 0.01, 1, None, False, ("previous",)
        ),
        BehavioralDecisionEvent(
            "next", "2026-07-17T14:00:00Z", True, 0.02, 2, False, False, False, False
        ),
        24.0,
    )
    assert not transition.gate.passed
    assert "post_loss_size_escalation" in transition.gate.reason_codes
