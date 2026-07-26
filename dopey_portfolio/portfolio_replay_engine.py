"""Deterministic offline portfolio-level replay engine."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_allocation.run_proof_weighted_allocator import (
    PAPER_ALLOCATION_DECISIONS_PATH,
    PAPER_ALLOCATION_PLAN_PATH,
    PROOF_WEIGHTED_OPPORTUNITIES_PATH,
    run_proof_weighted_allocator,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .portfolio_exposure_models import PortfolioExposureSnapshot, portfolio_exposure_hash
from .portfolio_exposure_policy import PortfolioReplayPolicy, default_portfolio_replay_policy, portfolio_policy_status
from .portfolio_position_models import PaperPortfolioPosition, portfolio_position_hash
from .portfolio_replay_models import PaperPortfolioState, portfolio_state_hash
from .portfolio_rotation_models import PortfolioRotationDecision, portfolio_rotation_decision_hash


PORTFOLIO_REPLAY_VERSION = "dopey-portfolio-rotation-exposure-replay-v1"
PORTFOLIO_ID = "dopey-paper-portfolio-replay-v1"


def build_portfolio_replay_bundle() -> dict[str, Any]:
    run_proof_weighted_allocator()
    policy = default_portfolio_replay_policy()
    plan = _load_json(PAPER_ALLOCATION_PLAN_PATH)
    opportunities = _load_jsonl(PROOF_WEIGHTED_OPPORTUNITIES_PATH)
    decisions = _load_jsonl(PAPER_ALLOCATION_DECISIONS_PATH)
    cases = build_portfolio_replay_cases(opportunities, decisions)
    replay = replay_portfolio_cases(cases, opportunities, decisions, plan, policy)
    return {
        "policy": policy,
        "plan": plan,
        "allocation_opportunities": opportunities,
        "allocation_decisions": decisions,
        "portfolio_opportunities": cases,
        **replay,
    }


def build_portfolio_replay_cases(
    opportunities: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sources = _source_catalog(opportunities, decisions)
    cases: list[dict[str, Any]] = []

    def add_case(
        case_family: str,
        required_case: str,
        source_key: str,
        decision_type: str,
        action: str,
        reason_codes: list[str],
        exposure_before: dict[str, Any],
        risk_tags: list[str],
    ) -> None:
        source = _select_source(sources, source_key, len(cases))
        case_index = len(cases) + 1
        units = _case_units(source, case_family)
        case = {
            "artifact_type": "portfolio_replay_case",
            "case_id": f"portfolio-case-{case_index:03d}-{required_case}",
            "case_family": case_family,
            "required_case": required_case,
            "source_allocation_id": source["decision"]["allocation_id"],
            "opportunity_id": source["opportunity"]["opportunity_id"],
            "underlying_family_id": source["opportunity"]["underlying_family_id"],
            "synthetic_underlying_symbol": source["opportunity"]["synthetic_underlying_symbol"],
            "regime_family": source["opportunity"]["regime_family"],
            "option_type": _safe_option_type(source["opportunity"]),
            "strategy_type": _safe_strategy_type(source["opportunity"]),
            "lifecycle": _case_lifecycle(source["opportunity"], case_family),
            "trading_day_index": case_index,
            "attempted_action": action,
            "expected_decision_type": decision_type,
            "expected_allowed": decision_type in {"open_position", "close_position_allowed", "rotate_allowed"},
            "expected_exit_allowed": decision_type in {"close_position_allowed", "rotate_allowed"},
            "expected_entry_allowed": decision_type in {"open_position", "rotate_allowed"},
            "same_day_close_attempted": "same_day" in action,
            "zero_dte_special_lifecycle_proof": required_case == "zero_dte_special_close_allowed_only_with_lifecycle_proof",
            "candidate_paper_attention_weight": round(float(source["decision"].get("paper_attention_weight", 0.0)), 6),
            "candidate_paper_premium_risk_units": units,
            "candidate_contract_units": int(source["decision"].get("max_paper_contract_units", 0)),
            "exposure_before": _normalized_exposure_before(exposure_before),
            "risk_tags": sorted(set(risk_tags)),
            "expected_reason_codes": sorted(set(reason_codes)),
            "allocator_feedback_expected": _allocator_feedback_for_case(case_family, risk_tags),
            "threshold_feedback_expected": _threshold_feedback_for_case(case_family, risk_tags),
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
        }
        case["case_hash"] = reproducibility_hash(case)
        cases.append(case)

    _add_required_cases(add_case)
    _fill_case_family(cases, add_case, "clean_swing_allocation", 12, "swing", "open_position", "open_and_close_next_day", ["swing_next_day_close_allowed"], [], {})
    _fill_case_family(cases, add_case, "clean_zero_dte_capped_allocation", 12, "zero_dte", "open_position", "open_0dte_under_cap", ["zero_dte_special_lifecycle_cap_respected"], [], {})
    _fill_case_family(cases, add_case, "delayed_rotation_case", 10, "delayed", "rotate_delayed", "reserve_delayed_rotation", ["delayed_rotation_advisory_reserve"], [], {})
    _fill_case_family(cases, add_case, "same_day_close_blocked_case", 10, "swing", "close_delayed_same_day_block", "attempt_same_day_close", ["same_day_round_trip_rejected"], [], {})
    _fill_case_family(cases, add_case, "paper_shadow_containment_case", 8, "shadow", "paper_shadow_only", "shadow_candidate_attempt", ["paper_shadow_contained"], [], {})
    _fill_case_family(cases, add_case, "watchlist_only_case", 8, "watchlist", "watchlist_only", "watchlist_review", ["watchlist_only_no_entry"], [], {})
    _fill_case_family(cases, add_case, "no_trade_rejection_case", 8, "rejected", "reject_policy", "rejected_candidate_attempt", ["rejected_candidate_no_entry"], [], {})
    _fill_case_family(cases, add_case, "underlying_family_concentration_case", 8, "swing", "reject_exposure", "attempt_family_concentration_entry", ["underlying_family_cap"], ["family_concentration"], _family_cap_before())
    _fill_case_family(cases, add_case, "regime_family_concentration_case", 8, "swing", "reject_exposure", "attempt_regime_concentration_entry", ["regime_family_cap"], ["regime_concentration"], _regime_cap_before())
    _fill_case_family(cases, add_case, "high_gamma_theta_throttle_case", 6, "zero_dte", "reject_exposure", "attempt_gamma_theta_entry", ["high_gamma_or_theta_cap"], ["high_gamma", "high_theta"], _gamma_theta_before())
    _fill_case_family(cases, add_case, "iv_event_macro_throttle_case", 6, "zero_dte", "reject_exposure", "attempt_iv_event_macro_entry", ["iv_event_macro_cap"], ["iv_crush", "event_macro"], _iv_event_before())
    if len(cases) != 96:
        raise ValueError(f"portfolio replay case count must be 96, got {len(cases)}")
    return cases


def replay_portfolio_cases(
    cases: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    plan: dict[str, Any],
    policy: PortfolioReplayPolicy,
) -> dict[str, Any]:
    source_plan_hash = str(plan.get("plan_hash", ""))
    states: list[PaperPortfolioState] = []
    positions: list[PaperPortfolioPosition] = []
    rotation_decisions: list[PortfolioRotationDecision] = []
    exposure_snapshots: list[PortfolioExposureSnapshot] = []
    allocator_feedback: list[dict[str, Any]] = []
    threshold_feedback: list[dict[str, Any]] = []
    proof_records: list[dict[str, Any]] = []
    for case in cases:
        snapshot = _build_exposure_snapshot(case, policy)
        decision = _build_rotation_decision(case, snapshot)
        position = _build_position(case, decision)
        state = _build_state(case, snapshot, decision, position)
        exposure_snapshots.append(snapshot)
        rotation_decisions.append(decision)
        if position is not None:
            positions.append(position)
        allocator_feedback.append(_allocator_feedback_record(case, snapshot, decision))
        threshold_feedback.append(_threshold_feedback_record(case, snapshot, decision))
        proof_records.append(_proof_record(case, source_plan_hash, state, decision, snapshot))
        states.append(state)
    summary = _summary_record(
        plan,
        cases,
        states,
        positions,
        rotation_decisions,
        exposure_snapshots,
        allocator_feedback,
        threshold_feedback,
        proof_records,
    )
    return {
        "states": states,
        "positions": positions,
        "rotation_decisions": rotation_decisions,
        "exposure_snapshots": exposure_snapshots,
        "allocator_feedback": allocator_feedback,
        "threshold_feedback": threshold_feedback,
        "proof_records": proof_records,
        "summary": summary,
    }


def _add_required_cases(add_case) -> None:
    add_case("clean_swing_allocation", "swing_call_opens_and_closes_next_day", "swing_call", "close_position_allowed", "open_and_close_next_day", ["next_day_close_allowed"], {}, [])
    add_case("clean_swing_allocation", "swing_put_opens_and_closes_next_day", "swing_put", "close_position_allowed", "open_and_close_next_day", ["next_day_close_allowed"], {}, [])
    add_case("clean_zero_dte_capped_allocation", "zero_dte_call_opens_under_capped_exposure", "zero_call", "open_position", "open_0dte_under_cap", ["zero_dte_special_lifecycle_cap_respected"], {}, [])
    add_case("clean_zero_dte_capped_allocation", "zero_dte_put_opens_under_capped_exposure", "zero_put", "open_position", "open_0dte_under_cap", ["zero_dte_special_lifecycle_cap_respected"], {}, [])
    add_case("clean_zero_dte_capped_allocation", "zero_dte_exposure_cap_blocks_extra_entry", "zero_call", "reject_exposure", "attempt_0dte_cap_breach", ["zero_dte_portfolio_exposure_cap"], _zero_dte_cap_before(), ["zero_dte_concentration"])
    add_case("same_day_close_blocked_case", "same_day_swing_close_is_blocked", "swing_call", "close_delayed_same_day_block", "attempt_same_day_close", ["same_day_round_trip_rejected"], {}, [])
    add_case("same_day_close_blocked_case", "same_day_normal_0dte_churn_attempt_is_blocked", "zero_call", "close_delayed_same_day_block", "attempt_same_day_0dte_churn", ["same_day_round_trip_rejected"], {}, [])
    add_case("clean_zero_dte_capped_allocation", "zero_dte_special_close_allowed_only_with_lifecycle_proof", "zero_put", "close_position_allowed", "zero_dte_special_lifecycle_close", ["zero_dte_special_lifecycle_proof"], {}, [])
    add_case("delayed_rotation_case", "delayed_rotation_reserve_created", "delayed", "rotate_delayed", "reserve_delayed_rotation", ["delayed_rotation_advisory_reserve"], {}, [])
    add_case("delayed_rotation_case", "delayed_rotation_executes_next_day", "delayed", "rotate_allowed", "execute_delayed_rotation_next_day", ["next_day_rotation_allowed"], {}, [])
    add_case("delayed_rotation_case", "delayed_rotation_does_not_force_same_day_close", "delayed", "rotate_delayed", "attempt_same_day_delayed_rotation", ["delayed_rotation_cannot_force_same_day_close"], {}, [])
    add_case("paper_shadow_containment_case", "paper_shadow_candidate_remains_shadow_only", "shadow", "paper_shadow_only", "shadow_candidate_attempt", ["paper_shadow_contained"], {}, [])
    add_case("watchlist_only_case", "watchlist_candidate_remains_watchlist_only", "watchlist", "watchlist_only", "watchlist_review", ["watchlist_only_no_entry"], {}, [])
    add_case("no_trade_rejection_case", "no_trade_candidate_remains_zero_allocation", "no_trade", "reject_policy", "no_trade_candidate_attempt", ["no_trade_zero_allocation"], {}, [])
    add_case("no_trade_rejection_case", "rejected_candidate_cannot_enter_portfolio", "rejected", "reject_policy", "rejected_candidate_attempt", ["rejected_candidate_no_entry"], {}, [])
    add_case("underlying_family_concentration_case", "low_liquidity_family_cap_starves_additional_entry", "swing", "reject_exposure", "attempt_low_liquidity_family_entry", ["low_liquidity_family_starved", "underlying_family_cap"], _low_liquidity_before(), ["family_concentration"])
    add_case("iv_event_macro_throttle_case", "event_sensitive_family_cap_throttles_entry", "zero_dte", "reject_exposure", "attempt_event_sensitive_entry", ["event_macro_exposure_cap"], _iv_event_before(), ["event_macro"])
    add_case("iv_event_macro_throttle_case", "macro_sensitive_family_cap_throttles_entry", "delayed", "reject_exposure", "attempt_macro_sensitive_entry", ["event_macro_exposure_cap"], _iv_event_before(), ["event_macro"])
    add_case("high_gamma_theta_throttle_case", "high_gamma_exposure_cap_blocks_entry", "zero_dte", "reject_exposure", "attempt_high_gamma_entry", ["high_gamma_exposure_cap"], _gamma_before(), ["high_gamma"])
    add_case("high_gamma_theta_throttle_case", "high_theta_exposure_cap_blocks_entry", "zero_dte", "reject_exposure", "attempt_high_theta_entry", ["high_theta_exposure_cap"], _theta_before(), ["high_theta"])
    add_case("high_gamma_theta_throttle_case", "call_put_imbalance_triggers_throttle", "swing_call", "reject_exposure", "attempt_call_heavy_entry", ["call_put_imbalance_cap"], _call_heavy_before(), ["call_heavy"])
    add_case("high_gamma_theta_throttle_case", "swing_0dte_imbalance_triggers_throttle", "zero_dte", "reject_exposure", "attempt_swing_0dte_imbalance_entry", ["zero_dte_portfolio_exposure_cap"], _zero_dte_cap_before(), ["zero_dte_concentration"])
    add_case("clean_swing_allocation", "multiple_strong_swing_opportunities_allowed_within_cap", "swing", "open_position", "open_swing_within_cap", ["swing_within_portfolio_cap"], {}, [])
    add_case("clean_zero_dte_capped_allocation", "multiple_strong_0dte_opportunities_are_capped", "zero_dte", "open_position", "open_0dte_under_cap", ["zero_dte_special_lifecycle_cap_respected"], {}, [])
    add_case("underlying_family_concentration_case", "synthetic_underlying_concentration_cap_blocks_entry", "swing", "reject_exposure", "attempt_synthetic_underlying_concentration", ["synthetic_underlying_concentration_cap"], _family_cap_before(), ["family_concentration"])
    add_case("regime_family_concentration_case", "same_regime_concentration_cap_blocks_entry", "swing", "reject_exposure", "attempt_same_regime_concentration", ["regime_family_cap"], _regime_cap_before(), ["regime_concentration"])
    add_case("underlying_family_concentration_case", "portfolio_holds_call_and_put_different_thesis_families_when_allowed", "swing_put", "open_position", "open_balanced_cross_family", ["call_put_balance_within_cap"], {}, ["put_heavy"])
    add_case("no_trade_rejection_case", "live_path_negative_control_rejected", "live", "reject_live_path", "attempt_live_path_negative_control", ["live_path_rejected"], {}, ["live_path_injection"])
    add_case("no_trade_rejection_case", "real_capital_sizing_negative_control_rejected", "swing", "reject_policy", "attempt_real_capital_sizing_negative_control", ["real_capital_sizing_rejected"], {}, ["real_sizing_injection"])
    add_case("no_trade_rejection_case", "broker_boundary_negative_control_rejected", "swing", "reject_policy", "attempt_broker_boundary_negative_control", ["broker_boundary_rejected"], {}, ["broker_boundary_injection"])


def _fill_case_family(cases: list[dict[str, Any]], add_case, case_family: str, target_count: int, source_key: str, decision_type: str, action: str, reason_codes: list[str], risk_tags: list[str], exposure_before: dict[str, Any]) -> None:
    existing_count = sum(1 for case in cases if case["case_family"] == case_family)
    while existing_count < target_count:
        add_case(case_family, f"{case_family}_{existing_count + 1:02d}", source_key, decision_type, action, reason_codes, exposure_before, risk_tags)
        existing_count += 1


def _source_catalog(opportunities: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> dict[str, list[dict[str, dict[str, Any]]]]:
    opportunities_by_id = {record["opportunity_id"]: record for record in opportunities}
    sources: dict[str, list[dict[str, dict[str, Any]]]] = {
        "swing": [],
        "swing_call": [],
        "swing_put": [],
        "zero_dte": [],
        "zero_call": [],
        "zero_put": [],
        "delayed": [],
        "shadow": [],
        "watchlist": [],
        "no_trade": [],
        "rejected": [],
        "live": [],
    }
    for decision in decisions:
        opportunity = opportunities_by_id[decision["opportunity_id"]]
        source = {"opportunity": opportunity, "decision": decision}
        strategy = str(opportunity.get("strategy_type", ""))
        option_type = str(opportunity.get("option_type", ""))
        decision_type = str(decision.get("decision", ""))
        if strategy.startswith("swing"):
            sources["swing"].append(source)
            if option_type == "call":
                sources["swing_call"].append(source)
            if option_type == "put":
                sources["swing_put"].append(source)
        if strategy.startswith("zero_dte"):
            sources["zero_dte"].append(source)
            if option_type == "call":
                sources["zero_call"].append(source)
            if option_type == "put":
                sources["zero_put"].append(source)
        if decision_type == "reserve_for_delayed_rotation" or strategy.startswith("delayed_rotation"):
            sources["delayed"].append(source)
        if decision_type == "allocate_paper_shadow_only":
            sources["shadow"].append(source)
        if decision_type in {"watchlist_only", "needs_more_fixture_coverage"}:
            sources["watchlist"].append(source)
        if decision_type == "reject_no_trade":
            sources["no_trade"].append(source)
        if decision_type.startswith("reject_"):
            sources["rejected"].append(source)
        if decision_type == "reject_live_path":
            sources["live"].append(source)
    for key, records in list(sources.items()):
        if not records:
            sources[key] = sources["swing"] or sources["zero_dte"] or sources["rejected"]
    return sources


def _select_source(sources: dict[str, list[dict[str, dict[str, Any]]]], key: str, index: int) -> dict[str, dict[str, Any]]:
    records = sources[key]
    if not records:
        raise ValueError(f"missing portfolio replay source records for {key}")
    return records[index % len(records)]


def _case_units(source: dict[str, dict[str, Any]], case_family: str) -> float:
    decision = source["decision"]
    units = float(decision.get("paper_premium_risk_units", 0.0))
    if case_family == "paper_shadow_containment_case":
        return 0.35
    if case_family == "delayed_rotation_case":
        return 0.25
    if units <= 0.0:
        return 0.75
    return round(min(units, 2.4), 6)


def _safe_option_type(opportunity: dict[str, Any]) -> str:
    value = str(opportunity.get("option_type", "call"))
    return value if value in {"call", "put"} else "call"


def _safe_strategy_type(opportunity: dict[str, Any]) -> str:
    strategy = str(opportunity.get("strategy_type", "swing_long_call"))
    if strategy == "no_trade":
        return "swing_long_call"
    if strategy in {
        "zero_dte_long_call",
        "zero_dte_long_put",
        "swing_long_call",
        "swing_long_put",
        "delayed_rotation_long_call",
        "delayed_rotation_long_put",
    }:
        return strategy
    return "swing_long_call"


def _case_lifecycle(opportunity: dict[str, Any], case_family: str) -> str:
    if case_family == "delayed_rotation_case":
        return "delayed_rotation"
    if case_family == "paper_shadow_containment_case":
        return "paper_shadow"
    if str(opportunity.get("strategy_type", "")).startswith("zero_dte"):
        return "zero_dte_special_lifecycle"
    return "swing_multi_day"


def _build_exposure_snapshot(case: dict[str, Any], policy: PortfolioReplayPolicy) -> PortfolioExposureSnapshot:
    before = _normalized_exposure_before(case["exposure_before"])
    units = float(case["candidate_paper_premium_risk_units"])
    allowed = bool(case["expected_allowed"])
    decision_type = str(case["expected_decision_type"])
    if case["strategy_type"].startswith("zero_dte") and allowed and before["total_paper_premium_risk_units"] == 0.0:
        before = _clean_zero_dte_before()
    added_units = units if allowed or decision_type in {"paper_shadow_only", "rotate_delayed"} else 0.0
    shadow_units = units if decision_type == "paper_shadow_only" else 0.0
    delayed_units = units if decision_type == "rotate_delayed" else 0.0
    zero_units = units if case["strategy_type"].startswith("zero_dte") and allowed else 0.0
    swing_units = units if case["strategy_type"].startswith("swing") and allowed else 0.0
    call_units = units if case["option_type"] == "call" and allowed else 0.0
    put_units = units if case["option_type"] == "put" and allowed else 0.0
    high_gamma_units = units if "high_gamma" in case["risk_tags"] and decision_type == "reject_exposure" else 0.0
    high_theta_units = units if "high_theta" in case["risk_tags"] and decision_type == "reject_exposure" else 0.0
    iv_units = units if "iv_crush" in case["risk_tags"] and decision_type == "reject_exposure" else 0.0
    event_units = units if "event_macro" in case["risk_tags"] and decision_type == "reject_exposure" else 0.0
    underlying = dict(before["underlying_family_exposure"])
    regime = dict(before["regime_family_exposure"])
    strategy = dict(before["strategy_type_exposure"])
    if allowed:
        _add_map_value(underlying, case["underlying_family_id"], units)
        _add_map_value(regime, case["regime_family"], units)
        _add_map_value(strategy, case["strategy_type"], units)
    snapshot_seed = {
        "snapshot_id": f"portfolio-exposure-{case['case_id']}",
        "portfolio_id": PORTFOLIO_ID,
        "trading_day_index": int(case["trading_day_index"]),
        "total_paper_attention_weight": round(before["total_paper_attention_weight"] + (float(case["candidate_paper_attention_weight"]) if allowed else 0.0), 6),
        "total_paper_premium_risk_units": round(before["total_paper_premium_risk_units"] + added_units, 6),
        "zero_dte_paper_units": round(before["zero_dte_paper_units"] + zero_units, 6),
        "swing_paper_units": round(before["swing_paper_units"] + swing_units, 6),
        "paper_shadow_units": round(before["paper_shadow_units"] + shadow_units, 6),
        "delayed_rotation_reserved_units": round(before["delayed_rotation_reserved_units"] + delayed_units, 6),
        "call_units": round(before["call_units"] + call_units, 6),
        "put_units": round(before["put_units"] + put_units, 6),
        "high_gamma_units": round(before["high_gamma_units"] + high_gamma_units, 6),
        "high_theta_units": round(before["high_theta_units"] + high_theta_units, 6),
        "iv_crush_exposed_units": round(before["iv_crush_exposed_units"] + iv_units, 6),
        "event_macro_exposed_units": round(before["event_macro_exposed_units"] + event_units, 6),
        "underlying_family_exposure": {key: round(value, 6) for key, value in sorted(underlying.items())},
        "regime_family_exposure": {key: round(value, 6) for key, value in sorted(regime.items())},
        "strategy_type_exposure": {key: round(value, 6) for key, value in sorted(strategy.items())},
        "constraint_status": {},
        "paper_only": True,
        "live_blocked": True,
        "exposure_hash": "",
    }
    status = portfolio_policy_status(snapshot_seed, policy)
    status["action_result"] = "allowed" if allowed else "blocked"
    status["attempt_reason_codes"] = list(case["expected_reason_codes"])
    status["exposure_constraint_result"] = "blocked" if decision_type == "reject_exposure" else status["status"]
    snapshot_seed["constraint_status"] = status
    snapshot = PortfolioExposureSnapshot.from_dict(snapshot_seed)
    return PortfolioExposureSnapshot(**{**snapshot.to_dict(), "exposure_hash": portfolio_exposure_hash(snapshot)})


def _build_rotation_decision(case: dict[str, Any], snapshot: PortfolioExposureSnapshot) -> PortfolioRotationDecision:
    decision_type = str(case["expected_decision_type"])
    delayed_until = int(case["trading_day_index"]) + 1 if decision_type in {"close_delayed_same_day_block", "rotate_delayed"} else 0
    decision_seed = PortfolioRotationDecision(
        rotation_decision_id=f"portfolio-rotation-{case['case_id']}",
        source_allocation_id=str(case["source_allocation_id"]),
        decision_type=decision_type,
        from_position_id=f"portfolio-position-{case['case_id']}" if "close" in decision_type or "rotate" in decision_type else "",
        to_opportunity_id=str(case["opportunity_id"]),
        trading_day_index=int(case["trading_day_index"]),
        entry_allowed=bool(case["expected_entry_allowed"]),
        exit_allowed=bool(case["expected_exit_allowed"]),
        same_day_close_blocked=decision_type == "close_delayed_same_day_block" or any("same_day" in reason for reason in case["expected_reason_codes"]),
        delayed_until_day_index=delayed_until,
        reason_codes=list(case["expected_reason_codes"]),
        exposure_effect={
            "snapshot_id": snapshot.snapshot_id,
            "total_paper_premium_risk_units": snapshot.total_paper_premium_risk_units,
            "zero_dte_exposure_share": snapshot.constraint_status["zero_dte_exposure_share"],
            "policy_status": snapshot.constraint_status["exposure_constraint_result"],
        },
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return PortfolioRotationDecision(**{**decision_seed.to_dict(), "decision_hash": portfolio_rotation_decision_hash(decision_seed)})


def _build_position(case: dict[str, Any], decision: PortfolioRotationDecision) -> PaperPortfolioPosition | None:
    if decision.decision_type in {"watchlist_only", "reject_policy", "reject_exposure", "reject_live_path"}:
        return None
    current_state = {
        "open_position": "open",
        "close_position_allowed": "closed_allowed",
        "rotate_allowed": "rotated_next_day",
        "rotate_delayed": "reserved_delayed_rotation",
        "close_delayed_same_day_block": "blocked_same_day_close",
        "paper_shadow_only": "shadow_only",
        "hold_position": "held",
    }[decision.decision_type]
    close_eligible = int(case["trading_day_index"]) if case["zero_dte_special_lifecycle_proof"] else int(case["trading_day_index"]) + 1
    planned_close = close_eligible if decision.decision_type != "rotate_delayed" else int(case["trading_day_index"]) + 1
    position_seed = PaperPortfolioPosition(
        portfolio_position_id=f"portfolio-position-{case['case_id']}",
        source_allocation_id=str(case["source_allocation_id"]),
        opportunity_id=str(case["opportunity_id"]),
        underlying_family_id=str(case["underlying_family_id"]),
        synthetic_underlying_symbol=str(case["synthetic_underlying_symbol"]),
        regime_family=str(case["regime_family"]),
        option_type=str(case["option_type"]),
        strategy_type=str(case["strategy_type"]),
        lifecycle=str(case["lifecycle"]),
        open_day_index=int(case["trading_day_index"]),
        close_eligible_day_index=close_eligible,
        planned_close_day_index=planned_close,
        paper_attention_weight=float(case["candidate_paper_attention_weight"]),
        paper_premium_risk_units=float(case["candidate_paper_premium_risk_units"]),
        max_paper_contract_units=int(case["candidate_contract_units"]),
        current_paper_state=current_state,
        same_day_close_blocked=decision.same_day_close_blocked,
        zero_dte_special_lifecycle=bool(case["strategy_type"].startswith("zero_dte")),
        delayed_rotation_flag=decision.decision_type in {"rotate_allowed", "rotate_delayed"},
        paper_shadow_flag=decision.decision_type == "paper_shadow_only",
        paper_only=True,
        live_blocked=True,
    )
    hashed = portfolio_position_hash(position_seed)
    return PaperPortfolioPosition.from_dict({**position_seed.to_dict(), "position_hash": hashed})


def _build_state(
    case: dict[str, Any],
    snapshot: PortfolioExposureSnapshot,
    decision: PortfolioRotationDecision,
    position: PaperPortfolioPosition | None,
) -> PaperPortfolioState:
    position_record = position.to_dict() if position is not None else None
    state_seed = PaperPortfolioState(
        state_id=f"portfolio-state-{case['case_id']}",
        portfolio_id=PORTFOLIO_ID,
        trading_day_index=int(case["trading_day_index"]),
        timestamp_label=f"fixture-day-{int(case['trading_day_index']):03d}",
        open_positions=[position_record] if position_record and decision.decision_type in {"open_position", "hold_position"} else [],
        pending_entries=[decision.to_dict()] if decision.decision_type == "open_position" else [],
        pending_exits=[decision.to_dict()] if decision.decision_type in {"close_position_allowed", "close_delayed_same_day_block"} else [],
        delayed_rotations=[decision.to_dict()] if decision.decision_type in {"rotate_allowed", "rotate_delayed"} else [],
        paper_shadow_positions=[position_record] if position_record and decision.decision_type == "paper_shadow_only" else [],
        watchlist_items=[case] if decision.decision_type == "watchlist_only" else [],
        rejected_items=[case] if decision.decision_type in {"reject_policy", "reject_exposure", "reject_live_path"} else [],
        exposure_snapshot=snapshot.to_dict(),
        constraint_snapshot=snapshot.constraint_status,
        paper_only=True,
        live_blocked=True,
        state_hash="",
    )
    return PaperPortfolioState(**{**state_seed.to_dict(), "state_hash": portfolio_state_hash(state_seed)})


def _summary_record(
    plan: dict[str, Any],
    cases: list[dict[str, Any]],
    states: list[PaperPortfolioState],
    positions: list[PaperPortfolioPosition],
    decisions: list[PortfolioRotationDecision],
    snapshots: list[PortfolioExposureSnapshot],
    allocator_feedback: list[dict[str, Any]],
    threshold_feedback: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_counts = Counter(decision.decision_type for decision in decisions)
    family_counts = Counter(case["case_family"] for case in cases)
    blocked = [decision for decision in decisions if not decision.entry_allowed and not decision.exit_allowed and decision.decision_type != "paper_shadow_only"]
    latest_snapshot = snapshots[-1].to_dict() if snapshots else {}
    max_zero_share = max((snapshot.constraint_status["zero_dte_exposure_share"] for snapshot in snapshots), default=0.0)
    summary = {
        "artifact_type": "portfolio_replay_summary",
        "portfolio_replay_version": PORTFOLIO_REPLAY_VERSION,
        "portfolio_id": PORTFOLIO_ID,
        "source_allocation_plan_id": plan.get("plan_id", ""),
        "source_allocation_plan_hash": plan.get("plan_hash", ""),
        "replay_case_count": len(cases),
        "stress_case_count": sum(1 for case in cases if case["risk_tags"]),
        "state_count": len(states),
        "position_count": len(positions),
        "rotation_decision_count": len(decisions),
        "exposure_snapshot_count": len(snapshots),
        "proof_record_count": len(proof_records),
        "allocator_feedback_count": len(allocator_feedback),
        "threshold_feedback_count": len(threshold_feedback),
        "decision_distribution": dict(sorted(decision_counts.items())),
        "case_family_distribution": dict(sorted(family_counts.items())),
        "blocked_action_count": len(blocked),
        "same_day_close_blocked_count": sum(1 for decision in decisions if decision.same_day_close_blocked),
        "paper_shadow_containment_count": decision_counts.get("paper_shadow_only", 0),
        "delayed_rotation_decision_count": decision_counts.get("rotate_delayed", 0) + decision_counts.get("rotate_allowed", 0),
        "zero_dte_exposure_share_max": round(max_zero_share, 6),
        "zero_dte_exposure_status": "within_cap" if max_zero_share <= 0.35 else "blocked",
        "latest_exposure_snapshot": latest_snapshot,
        "allocator_feedback_actions": _feedback_action_counts(allocator_feedback),
        "threshold_feedback_actions": _feedback_action_counts(threshold_feedback),
        "portfolio_feedback_advisory_only": True,
        "same_day_churn_allowed": False,
        "paper_shadow_contained": True,
        "delayed_rotation_advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _allocator_feedback_record(case: dict[str, Any], snapshot: PortfolioExposureSnapshot, decision: PortfolioRotationDecision) -> dict[str, Any]:
    feedback_type = case["allocator_feedback_expected"]
    record = {
        "artifact_type": "portfolio_allocator_feedback",
        "feedback_id": f"portfolio-allocator-feedback-{case['case_id']}",
        "case_id": case["case_id"],
        "source_allocation_id": case["source_allocation_id"],
        "feedback_type": feedback_type,
        "feedback_action": feedback_type,
        "portfolio_pressure_reason_codes": list(decision.reason_codes),
        "zero_dte_exposure_share": snapshot.constraint_status["zero_dte_exposure_share"],
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _threshold_feedback_record(case: dict[str, Any], snapshot: PortfolioExposureSnapshot, decision: PortfolioRotationDecision) -> dict[str, Any]:
    feedback_type = case["threshold_feedback_expected"]
    record = {
        "artifact_type": "portfolio_threshold_feedback",
        "feedback_id": f"portfolio-threshold-feedback-{case['case_id']}",
        "case_id": case["case_id"],
        "source_allocation_id": case["source_allocation_id"],
        "feedback_type": feedback_type,
        "feedback_action": feedback_type,
        "threshold_profile_effect": "paper_shadow_only_or_advisory_strengthening",
        "same_day_churn_pressure": decision.same_day_close_blocked,
        "zero_dte_exposure_share": snapshot.constraint_status["zero_dte_exposure_share"],
        "live_threshold_mutation_allowed": False,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _proof_record(
    case: dict[str, Any],
    source_plan_hash: str,
    state: PaperPortfolioState,
    decision: PortfolioRotationDecision,
    snapshot: PortfolioExposureSnapshot,
) -> dict[str, Any]:
    record = {
        "artifact_type": "portfolio_replay_proof",
        "replay_id": case["case_id"],
        "source_allocation_plan_hash": source_plan_hash,
        "state_id": state.state_id,
        "decision_id": decision.rotation_decision_id,
        "exposure_snapshot_id": snapshot.snapshot_id,
        "action_attempted": case["attempted_action"],
        "action_result": "allowed" if decision.entry_allowed or decision.exit_allowed else "blocked",
        "exposure_constraint_result": snapshot.constraint_status["exposure_constraint_result"],
        "no_day_trade_result": "blocked" if decision.same_day_close_blocked else "allowed_or_not_applicable",
        "allocator_feedback": case["allocator_feedback_expected"],
        "threshold_feedback": case["threshold_feedback_expected"],
        "reason_codes": list(decision.reason_codes),
        "safety_status": "paper_only_live_blocked",
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _allocator_feedback_for_case(case_family: str, risk_tags: list[str]) -> str:
    if "zero_dte_concentration" in risk_tags:
        return "reduce_0dte_exposure_cap"
    if "high_gamma" in risk_tags:
        return "reduce_high_gamma_exposure"
    if "high_theta" in risk_tags:
        return "reduce_high_theta_exposure"
    if "family_concentration" in risk_tags:
        return "reduce_family_concentration"
    if "regime_concentration" in risk_tags:
        return "reduce_regime_concentration"
    if case_family == "delayed_rotation_case":
        return "reserve_delayed_rotation_capacity"
    if case_family == "clean_swing_allocation":
        return "keep_allocation_unchanged"
    if case_family == "clean_zero_dte_capped_allocation":
        return "keep_allocation_unchanged"
    if case_family == "no_trade_rejection_case":
        return "prefer_no_trade_due_to_concentration"
    if case_family == "watchlist_only_case":
        return "increase_fixture_coverage"
    if case_family == "paper_shadow_containment_case":
        return "reject_unsafe_allocation_profile"
    return "prefer_swing_due_to_exposure_pressure"


def _threshold_feedback_for_case(case_family: str, risk_tags: list[str]) -> str:
    if "high_gamma" in risk_tags or "high_theta" in risk_tags:
        return "keep_profile_paper_shadow_due_to_gamma_theta_pressure"
    if "zero_dte_concentration" in risk_tags:
        return "preserve_strict_0dte_threshold_profile"
    if "event_macro" in risk_tags or "iv_crush" in risk_tags:
        return "recommend_advisory_later_expiry_strengthening"
    if case_family == "same_day_close_blocked_case":
        return "reject_profile_that_increases_same_day_churn_pressure"
    if "live_path_injection" in risk_tags or "real_sizing_injection" in risk_tags or "broker_boundary_injection" in risk_tags:
        return "reject_profile_with_safety_boundary_pressure"
    return "keep_threshold_profile_unchanged"


def _feedback_action_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(record["feedback_action"]) for record in records).items()))


def _normalized_exposure_before(record: dict[str, Any]) -> dict[str, Any]:
    base = {
        "total_paper_attention_weight": 0.0,
        "total_paper_premium_risk_units": 0.0,
        "zero_dte_paper_units": 0.0,
        "swing_paper_units": 0.0,
        "paper_shadow_units": 0.0,
        "delayed_rotation_reserved_units": 0.0,
        "call_units": 0.0,
        "put_units": 0.0,
        "high_gamma_units": 0.0,
        "high_theta_units": 0.0,
        "iv_crush_exposed_units": 0.0,
        "event_macro_exposed_units": 0.0,
        "underlying_family_exposure": {},
        "regime_family_exposure": {},
        "strategy_type_exposure": {},
    }
    output = {**base, **record}
    for key in ["underlying_family_exposure", "regime_family_exposure", "strategy_type_exposure"]:
        output[key] = {str(k): float(v) for k, v in output.get(key, {}).items()}
    for key, value in list(output.items()):
        if key not in {"underlying_family_exposure", "regime_family_exposure", "strategy_type_exposure"}:
            output[key] = float(value)
    return output


def _zero_dte_cap_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 50.0, "zero_dte_paper_units": 17.5, "swing_paper_units": 32.5, "call_units": 25.0, "put_units": 25.0, "strategy_type_exposure": {"zero_dte_long_call": 17.5}}


def _family_cap_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 12.0, "swing_paper_units": 12.0, "call_units": 6.0, "put_units": 6.0, "underlying_family_exposure": {"underlying-family-09": 12.0}}


def _low_liquidity_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 1.0, "swing_paper_units": 1.0, "underlying_family_exposure": {"underlying-family-05": 1.0}}


def _regime_cap_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 18.0, "swing_paper_units": 18.0, "regime_family_exposure": {"trend_persistence": 18.0}}


def _gamma_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 8.0, "zero_dte_paper_units": 2.8, "swing_paper_units": 5.2, "high_gamma_units": 8.0}


def _theta_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 8.0, "zero_dte_paper_units": 2.8, "swing_paper_units": 5.2, "high_theta_units": 8.0}


def _gamma_theta_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 8.0, "zero_dte_paper_units": 2.8, "swing_paper_units": 5.2, "high_gamma_units": 8.0, "high_theta_units": 8.0}


def _iv_event_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 7.0, "zero_dte_paper_units": 2.45, "swing_paper_units": 4.55, "iv_crush_exposed_units": 7.0, "event_macro_exposed_units": 6.0}


def _call_heavy_before() -> dict[str, Any]:
    return {"total_paper_premium_risk_units": 20.0, "swing_paper_units": 20.0, "call_units": 13.6, "put_units": 6.4}


def _clean_zero_dte_before() -> dict[str, Any]:
    return _normalized_exposure_before({
        "total_paper_attention_weight": 6.0,
        "total_paper_premium_risk_units": 24.0,
        "swing_paper_units": 24.0,
        "call_units": 12.0,
        "put_units": 12.0,
        "strategy_type_exposure": {"swing_long_call": 12.0, "swing_long_put": 12.0},
    })


def _add_map_value(record: dict[str, float], key: str, value: float) -> None:
    record[key] = round(float(record.get(key, 0.0)) + value, 6)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
