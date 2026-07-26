"""Tests: DOPEY active long-premium options policy kernel.

All cases are deterministic, offline, paper-only, and live-blocked.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_governor.active_trading_policy import (
    HARD_SAFETY_RULES,
    active_trading_candidate_from_dict,
    active_trading_canon_record,
    default_active_trading_thresholds,
    evaluate_active_trading_policy,
    evaluate_lifecycle_rules,
    evaluate_recursive_improvement,
    policy_improvement_proposal_from_dict,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "dopey_data"
    / "fixtures"
    / "active_trading_policy"
    / "long_premium_policy_cases.json"
)


def _fixture_packet() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_active_trading_canon_records_hard_safety_rules() -> None:
    canon = active_trading_canon_record()
    hard_rules = set(canon["hard_safety_rules"])
    assert "no_uncovered_or_undefined_risk_options" in hard_rules
    assert "long_premium_or_net_debit_only" in hard_rules
    assert "recursive_improvement_cannot_weaken_safety_layer" in hard_rules
    assert set(HARD_SAFETY_RULES).issubset(hard_rules)
    assert "short_straddle" in canon["forbidden_structures"]


def test_fixture_candidates_match_expected_policy_verdicts() -> None:
    packet = _fixture_packet()
    thresholds = default_active_trading_thresholds()
    for row in packet["candidates"]:
        candidate = active_trading_candidate_from_dict(row["candidate"])
        decision = evaluate_active_trading_policy(candidate, thresholds)
        assert decision.allowed is row["expected_allowed"], row["case_id"]
        assert decision.verdict == row["expected_verdict"], row["case_id"]
        assert decision.policy_version == packet["policy_version"]
        if "expected_reason_contains" in row:
            reason_text = " ".join(decision.reasons)
            assert row["expected_reason_contains"] in reason_text, row["case_id"]


def test_0dte_approved_fixture_is_tightly_budgeted() -> None:
    packet = _fixture_packet()
    thresholds = default_active_trading_thresholds()
    row = next(item for item in packet["candidates"] if item["case_id"] == "event_0dte_hold_to_expiration_approved")
    candidate = active_trading_candidate_from_dict(row["candidate"])
    decision = evaluate_active_trading_policy(candidate, thresholds)
    lifecycle_decision = evaluate_lifecycle_rules(candidate, thresholds)
    assert decision.allowed is True
    assert lifecycle_decision.allowed is True
    assert candidate.dte == 0
    assert candidate.lifecycle_state == "hold_to_expiration_worthless_tolerant"
    assert decision.max_position_fraction <= thresholds.max_0dte_position_fraction
    assert candidate.live_allowed is False
    assert candidate.paper_only is True


def test_recursive_improvement_allows_alpha_layer_not_safety_layer() -> None:
    packet = _fixture_packet()
    thresholds = default_active_trading_thresholds()
    for row in packet["recursive_improvement_proposals"]:
        proposal = policy_improvement_proposal_from_dict(row["proposal"])
        decision = evaluate_recursive_improvement(proposal, thresholds)
        assert decision.allowed is row["expected_allowed"], row["case_id"]
        assert decision.verdict == row["expected_verdict"], row["case_id"]
        if "expected_reason_contains" in row:
            reason_text = " ".join(decision.reasons)
            assert row["expected_reason_contains"] in reason_text, row["case_id"]


def test_active_policy_serialization_is_deterministic() -> None:
    packet = _fixture_packet()
    thresholds = default_active_trading_thresholds()
    row = packet["candidates"][0]
    candidate = active_trading_candidate_from_dict(row["candidate"])
    first = evaluate_active_trading_policy(candidate, thresholds).to_dict()
    second = evaluate_active_trading_policy(candidate, thresholds).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
