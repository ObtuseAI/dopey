"""Deterministic active long-call/long-put lifecycle simulator."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_execution.paper_broker import PaperBroker
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .account_ledger_lifecycle_adapter import AccountLedgerLifecycleAdapter, evaluate_no_day_trade_result
from .lifecycle_models import (
    ActiveOptionLifecycle,
    active_lifecycle_hash,
    make_proof,
    make_state,
    make_transition,
)
from .lifecycle_policy import default_lifecycle_policy, evaluate_lifecycle_case
from .paperbroker_lifecycle_adapter import PaperBrokerLifecycleAdapter


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "lifecycle"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "lifecycle"

LIFECYCLE_POLICY_FIXTURE_PATH = FIXTURE_DIR / "lifecycle_policy.json"
LIFECYCLE_CASES_FIXTURE_PATH = FIXTURE_DIR / "lifecycle_cases.json"
LIFECYCLE_EXPECTED_STATES_FIXTURE_PATH = FIXTURE_DIR / "lifecycle_expected_states.json"
LIFECYCLE_EXPECTED_TRANSITIONS_FIXTURE_PATH = FIXTURE_DIR / "lifecycle_expected_transitions.json"
LIFECYCLE_EXPECTED_PROOFS_FIXTURE_PATH = FIXTURE_DIR / "lifecycle_expected_proofs.json"
LIFECYCLE_EXPECTED_SUMMARY_FIXTURE_PATH = FIXTURE_DIR / "lifecycle_expected_summary.json"

LIFECYCLE_POLICY_PATH = ARTIFACT_DIR / "lifecycle_policy.json"
LIFECYCLE_CASES_PATH = ARTIFACT_DIR / "lifecycle_cases.json"
LIFECYCLE_STATES_PATH = ARTIFACT_DIR / "lifecycle_states.jsonl"
LIFECYCLE_TRANSITIONS_PATH = ARTIFACT_DIR / "lifecycle_transitions.jsonl"
LIFECYCLE_PROOF_PATH = ARTIFACT_DIR / "lifecycle_proof.jsonl"
LIFECYCLE_PAPERBROKER_RESULTS_PATH = ARTIFACT_DIR / "lifecycle_paperbroker_results.jsonl"
LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH = ARTIFACT_DIR / "lifecycle_account_ledger_results.jsonl"
LIFECYCLE_FEEDBACK_ALLOCATOR_PATH = ARTIFACT_DIR / "lifecycle_feedback_allocator.jsonl"
LIFECYCLE_FEEDBACK_PORTFOLIO_PATH = ARTIFACT_DIR / "lifecycle_feedback_portfolio.jsonl"
LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH = ARTIFACT_DIR / "lifecycle_feedback_stress_ladder.jsonl"
LIFECYCLE_FEEDBACK_INCIDENT_PATH = ARTIFACT_DIR / "lifecycle_feedback_incident.jsonl"
LIFECYCLE_SUMMARY_PATH = ARTIFACT_DIR / "lifecycle_summary.json"


def build_lifecycle_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    groups = [
        ("swing_call_ok", 16, "call", "swing_long_call"),
        ("swing_put_ok", 16, "put", "swing_long_put"),
        ("zero_dte_call_expiry", 16, "call", "zero_dte_long_call"),
        ("zero_dte_put_special_close", 16, "put", "zero_dte_long_put"),
        ("delayed_rotation", 12, "call", "delayed_rotation_long_call"),
        ("no_day_trade_block", 12, "put", "swing_long_put"),
        ("incident_interruption", 8, "call", "swing_long_call"),
        ("stress_interruption", 8, "put", "zero_dte_long_put"),
        ("paperbroker_rejection", 8, "call", "swing_long_call"),
    ]
    index = 1
    for group, count, option_type, strategy_type in groups:
        for offset in range(count):
            case = _base_case(index, group, option_type, strategy_type)
            if group == "zero_dte_call_expiry":
                case["days_to_expiry"] = 0
                case["expiry"] = case["trade_date"]
                case["close_behavior"] = "expiry_simulated"
            if group == "zero_dte_put_special_close":
                case["days_to_expiry"] = 0
                case["expiry"] = case["trade_date"]
                case["close_behavior"] = "zero_dte_special_close"
            if group == "delayed_rotation":
                case["close_behavior"] = "delayed_rotation"
                case["strategy_type"] = "delayed_rotation_long_call" if offset % 2 == 0 else "delayed_rotation_long_put"
                case["option_type"] = "call" if offset % 2 == 0 else "put"
            if group == "no_day_trade_block":
                case["close_behavior"] = "same_day_close_attempt"
            if group == "incident_interruption":
                case["incident_status"] = "terminal_block"
            if group == "stress_interruption":
                case["days_to_expiry"] = 0
                case["expiry"] = case["trade_date"]
                case["stress_status"] = "severe" if offset % 2 == 0 else "crisis_lockdown"
            if group == "paperbroker_rejection":
                case["paperbroker_reject"] = True
                case["open_action"] = "sell_to_open" if offset % 2 == 0 else "buy_to_open"
                if offset % 2 == 1:
                    case["close_without_open"] = True
            cases.append(case)
            index += 1
    negative_controls = [
        ("zero_dte_missing_reason", {"days_to_expiry": 0, "close_behavior": "zero_dte_special_close", "special_close_reason": ""}),
        ("zero_dte_missing_liquidity", {"days_to_expiry": 0, "close_behavior": "zero_dte_special_close", "liquidity_approved": False}),
        ("zero_dte_missing_risk_cap", {"days_to_expiry": 0, "close_behavior": "zero_dte_special_close", "risk_cap_approved": False}),
        ("paper_shadow_full_open", {"allocation_status": "paper_shadow"}),
        ("watchlist_open", {"allocation_status": "watchlist"}),
        ("no_trade_open", {"allocation_status": "no_trade"}),
        ("rejected_candidate_open", {"allocation_status": "rejected"}),
        ("portfolio_cap_block", {"portfolio_status": "exposure_cap_block"}),
        ("policy_violation", {"unsupported_spread_attempt": True}),
        ("sell_to_open_rejected", {"open_action": "sell_to_open", "sell_to_open_attempt": True}),
        ("unsupported_spread_rejected", {"structure": "vertical_spread", "unsupported_spread_attempt": True}),
        ("naked_terminal_block", {"naked_option_attempt": True}),
        ("live_flag_terminal_block", {"live_flag_injection": True}),
        ("broker_path_terminal_block", {"broker_path_injection": True}),
        ("credential_terminal_block", {"credential_reference": True}),
        ("scheduler_terminal_block", {"scheduler_emergence": True}),
        ("real_sizing_terminal_block", {"real_sizing_reference": True}),
        ("close_without_open_rejected", {"close_without_open": True}),
        ("ledger_mismatch_audit_only", {"ledger_mismatch": True}),
        ("audit_proof_missing_audit_only", {"audit_proof_missing": True}),
        ("full_suite_timeout_terminal_block", {"full_suite_timeout_misclassified_as_pass": True}),
        ("terminal_recovery_rejected", {"terminal_block_auto_recovery_attempt": True}),
        ("paperbroker_override_terminal_block", {"paperbroker_override_attempt": True}),
        ("no_day_trade_dominant", {"close_behavior": "same_day_close_attempt"}),
    ]
    for label, overrides in negative_controls:
        case = _base_case(index, label, "call" if index % 2 == 0 else "put", "swing_long_call" if index % 2 == 0 else "swing_long_put")
        case.update(overrides)
        if int(case["days_to_expiry"]) == 0:
            case["expiry"] = case["trade_date"]
            case["strategy_type"] = "zero_dte_long_call" if case["option_type"] == "call" else "zero_dte_long_put"
        cases.append(case)
        index += 1
    return cases


def simulate_lifecycle_cases(policy: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    states: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    proofs: list[dict[str, Any]] = []
    lifecycles: list[dict[str, Any]] = []
    paperbroker_results: list[dict[str, Any]] = []
    account_ledger_results: list[dict[str, Any]] = []
    feedback_allocator: list[dict[str, Any]] = []
    feedback_portfolio: list[dict[str, Any]] = []
    feedback_stress: list[dict[str, Any]] = []
    feedback_incident: list[dict[str, Any]] = []
    for case in cases:
        result = _simulate_case(policy, case)
        states.extend(result["states"])
        transitions.extend(result["transitions"])
        proofs.extend(result["proofs"])
        lifecycles.append(result["lifecycle"])
        paperbroker_results.extend(result["paperbroker_results"])
        account_ledger_results.extend(result["account_ledger_results"])
        feedback_allocator.append(result["feedback_allocator"])
        feedback_portfolio.append(result["feedback_portfolio"])
        feedback_stress.append(result["feedback_stress"])
        feedback_incident.append(result["feedback_incident"])
    summary = _summary(cases, states, transitions, proofs, lifecycles, paperbroker_results, account_ledger_results)
    return {
        "cases": cases,
        "states": states,
        "transitions": transitions,
        "proofs": proofs,
        "lifecycles": lifecycles,
        "paperbroker_results": paperbroker_results,
        "account_ledger_results": account_ledger_results,
        "feedback_allocator": feedback_allocator,
        "feedback_portfolio": feedback_portfolio,
        "feedback_stress": feedback_stress,
        "feedback_incident": feedback_incident,
        "summary": summary,
    }


def _simulate_case(policy: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    lifecycle_id = str(case["lifecycle_id"])
    policy_result = evaluate_lifecycle_case(case, policy)
    state_names = ["signal_detected", "candidate_built"]
    blocked_codes: list[str] = []
    paperbroker_results: list[dict[str, Any]] = []
    account_ledger_results: list[dict[str, Any]] = []
    current_state = "candidate_built"
    policy_status = str(policy_result["status"])
    allocation_status = str(case.get("allocation_status", "allocate_paper"))
    portfolio_status = str(case.get("portfolio_status", "within_cap"))
    stress_status = str(case.get("stress_status", "normal"))
    incident_status = str(case.get("incident_status", "clear"))
    paperbroker_status = "not_requested"
    account_ledger_status = "not_requested"

    if policy_result["status"] == "terminal_block":
        blocked_codes = list(policy_result["reason_codes"])
        state_names.append("terminal_block")
        current_state = "terminal_block"
    elif policy_result["status"] == "rejected":
        blocked_codes = list(policy_result["reason_codes"])
        state_names.append("rejected")
        current_state = "rejected"
    elif allocation_status in {"paper_shadow", "watchlist", "no_trade", "rejected"}:
        blocked_codes = [f"allocation_{allocation_status}_cannot_open"]
        state_names.extend(["policy_validated", "risk_validated", "blocked"])
        current_state = "blocked"
    elif portfolio_status == "exposure_cap_block":
        blocked_codes = ["portfolio_exposure_cap_blocks_open"]
        state_names.extend(["policy_validated", "risk_validated", "allocated_paper", "portfolio_checked", "blocked"])
        current_state = "blocked"
    elif stress_status in {"severe", "crisis_lockdown"}:
        blocked_codes = ["stress_severe_blocks_zero_dte_open" if stress_status == "severe" else "crisis_lockdown_blocks_new_entries"]
        state_names.extend(["policy_validated", "risk_validated", "allocated_paper", "portfolio_checked", "stress_checked", "blocked"])
        current_state = "blocked"
    elif incident_status == "terminal_block":
        blocked_codes = ["incident_terminal_block_prevents_lifecycle_progress"]
        state_names.extend(["policy_validated", "risk_validated", "allocated_paper", "portfolio_checked", "stress_checked", "incident_checked", "terminal_block"])
        current_state = "terminal_block"
    else:
        broker = PaperBroker()
        broker_adapter = PaperBrokerLifecycleAdapter(broker)
        ledger_adapter = AccountLedgerLifecycleAdapter()
        state_names.extend(["policy_validated", "risk_validated", "allocated_paper", "portfolio_checked", "stress_checked", "incident_checked", "paper_open_requested"])
        if bool(case.get("close_without_open", False)):
            broker_result = broker_adapter.close_lifecycle_position(case, str(case["trade_date"]), "normal_hold", "")
            ledger_result = ledger_adapter.reject_close_without_open(case)
            paperbroker_results.append(_paperbroker_record(case, broker_result, "close_without_open"))
            account_ledger_results.append(_ledger_record(case, ledger_result, "close_without_open"))
            blocked_codes = ["close_without_open_position_rejected"]
            state_names.append("rejected")
            current_state = "rejected"
            paperbroker_status = "rejected"
            account_ledger_status = "rejected"
        else:
            broker_result = broker_adapter.open_lifecycle_position(case)
            ledger_result = ledger_adapter.record_open(case)
            paperbroker_results.append(_paperbroker_record(case, broker_result, "open"))
            account_ledger_results.append(_ledger_record(case, ledger_result, "open"))
            paperbroker_status = "opened" if broker_result["ok"] else "rejected"
            account_ledger_status = "recorded" if ledger_result["accepted"] else "rejected"
            if not broker_result["ok"] or not ledger_result["accepted"] or bool(case.get("paperbroker_reject", False)):
                blocked_codes = broker_result["errors"] or ledger_result["reason_codes"] or ["paperbroker_rejection"]
                state_names.append("rejected")
                current_state = "rejected"
            elif bool(case.get("ledger_mismatch", False)) or bool(case.get("audit_proof_missing", False)):
                blocked_codes = ["account_ledger_mismatch_manual_review" if case.get("ledger_mismatch") else "audit_proof_missing_manual_review"]
                state_names.extend(["paper_opened", "ledger_recorded", "audit_only"])
                current_state = "audit_only"
            else:
                close_result = _close_case(case, broker_adapter, ledger_adapter)
                state_names.extend(close_result["states"])
                paperbroker_results.extend(close_result["paperbroker_results"])
                account_ledger_results.extend(close_result["account_ledger_results"])
                blocked_codes = close_result["reason_codes"]
                current_state = close_result["current_state"]
                paperbroker_status = close_result["paperbroker_status"]
                account_ledger_status = close_result["account_ledger_status"]

    state_records = [_state_record(lifecycle_id, state_name, index, blocked_codes) for index, state_name in enumerate(state_names, start=1)]
    transition_records = _transition_records(lifecycle_id, state_records, blocked_codes, policy_status, allocation_status, portfolio_status, stress_status, incident_status, paperbroker_results, account_ledger_results)
    proof_records = _proof_records(case, state_records, transition_records, blocked_codes)
    lifecycle_seed = ActiveOptionLifecycle(
        lifecycle_id=lifecycle_id,
        candidate_id=str(case["candidate_id"]),
        underlying_family_id=str(case["underlying_family_id"]),
        synthetic_underlying_symbol=str(case["synthetic_underlying_symbol"]),
        option_type=str(case["option_type"]),
        strategy_type=str(case["strategy_type"]),
        trade_date=str(case["trade_date"]),
        expiry=str(case["expiry"]),
        days_to_expiry=int(case["days_to_expiry"]),
        policy_status=policy_status,
        allocation_status=allocation_status,
        portfolio_status=portfolio_status,
        stress_status=stress_status,
        incident_status=incident_status,
        paperbroker_status=paperbroker_status,
        account_ledger_status=account_ledger_status,
        current_state=current_state,
        transitions=[record["transition_id"] for record in transition_records],
        proof_record_ids=[record["proof_id"] for record in proof_records],
        paper_only=True,
        live_blocked=True,
        lifecycle_hash="",
    )
    lifecycle = ActiveOptionLifecycle(**{**lifecycle_seed.to_dict(), "lifecycle_hash": active_lifecycle_hash(lifecycle_seed)}).to_dict()
    return {
        "states": state_records,
        "transitions": transition_records,
        "proofs": proof_records,
        "lifecycle": lifecycle,
        "paperbroker_results": paperbroker_results,
        "account_ledger_results": account_ledger_results,
        "feedback_allocator": _feedback_record(case, "allocator", current_state, blocked_codes),
        "feedback_portfolio": _feedback_record(case, "portfolio", current_state, blocked_codes),
        "feedback_stress": _feedback_record(case, "stress_ladder", current_state, blocked_codes),
        "feedback_incident": _feedback_record(case, "incident", current_state, blocked_codes),
    }


def _close_case(case: dict[str, Any], broker_adapter: PaperBrokerLifecycleAdapter, ledger_adapter: AccountLedgerLifecycleAdapter) -> dict[str, Any]:
    behavior = str(case.get("close_behavior", "next_day_close"))
    if int(case["days_to_expiry"]) == 0:
        if behavior == "expiry_simulated":
            return {
                "states": ["paper_opened", "ledger_recorded", "holding", "zero_dte_special_lifecycle", "zero_dte_expiry_managed", "expired_simulated"],
                "reason_codes": [],
                "paperbroker_results": [],
                "account_ledger_results": [],
                "current_state": "expired_simulated",
                "paperbroker_status": "opened",
                "account_ledger_status": "recorded",
            }
        reason_code = str(case.get("special_close_reason", "expiry_window"))
        broker_result = broker_adapter.close_lifecycle_position(case, str(case["trade_date"]), "zero_dte_expiry_managed", reason_code)
        ledger_result = ledger_adapter.record_close(case, str(case["trade_date"]), "zero_dte_expiry_managed", reason_code)
        reason_codes = broker_result["errors"] or ledger_result["reason_codes"]
        return {
            "states": ["paper_opened", "ledger_recorded", "holding", "zero_dte_special_lifecycle", "zero_dte_special_close_requested", "zero_dte_special_closed" if not reason_codes else "rejected"],
            "reason_codes": reason_codes,
            "paperbroker_results": [_paperbroker_record(case, broker_result, "zero_dte_special_close")],
            "account_ledger_results": [_ledger_record(case, ledger_result, "zero_dte_special_close")],
            "current_state": "zero_dte_special_closed" if not reason_codes else "rejected",
            "paperbroker_status": "closed" if broker_result["ok"] else "rejected",
            "account_ledger_status": "closed" if ledger_result["accepted"] else "rejected",
        }
    if behavior == "same_day_close_attempt":
        broker_result = broker_adapter.close_lifecycle_position(case, str(case["trade_date"]), "normal_hold", "")
        ledger_result = ledger_adapter.record_close(case, str(case["trade_date"]), "normal_hold", "")
        reason_codes = broker_result["errors"] or ledger_result["reason_codes"] or ["same_day_round_trip_rejected"]
        return {
            "states": ["paper_opened", "ledger_recorded", "holding", "paper_close_requested", "blocked"],
            "reason_codes": reason_codes,
            "paperbroker_results": [_paperbroker_record(case, broker_result, "same_day_close_attempt")],
            "account_ledger_results": [_ledger_record(case, ledger_result, "same_day_close_attempt")],
            "current_state": "blocked",
            "paperbroker_status": "rejected",
            "account_ledger_status": "blocked_same_day",
        }
    if behavior == "delayed_rotation":
        next_day = str(case["next_trade_date"])
        broker_result = broker_adapter.close_lifecycle_position(case, next_day, "normal_hold", "delayed_rotation_next_day")
        ledger_result = ledger_adapter.record_close(case, next_day, "normal_hold", "delayed_rotation_next_day")
        reason_codes = broker_result["errors"] or ledger_result["reason_codes"]
        return {
            "states": ["paper_opened", "ledger_recorded", "holding", "rotation_delayed", "next_day_close_eligible", "paper_close_requested", "paper_closed" if not reason_codes else "blocked"],
            "reason_codes": reason_codes,
            "paperbroker_results": [_paperbroker_record(case, broker_result, "delayed_rotation_next_day_close")],
            "account_ledger_results": [_ledger_record(case, ledger_result, "delayed_rotation_next_day_close")],
            "current_state": "paper_closed" if not reason_codes else "blocked",
            "paperbroker_status": "closed" if broker_result["ok"] else "rejected",
            "account_ledger_status": "closed" if ledger_result["accepted"] else "rejected",
        }
    next_day = str(case["next_trade_date"])
    broker_result = broker_adapter.close_lifecycle_position(case, next_day, "normal_hold", "next_day_exit")
    ledger_result = ledger_adapter.record_close(case, next_day, "normal_hold", "next_day_exit")
    reason_codes = broker_result["errors"] or ledger_result["reason_codes"]
    return {
        "states": ["paper_opened", "ledger_recorded", "holding", "swing_overnight_hold", "next_day_close_eligible", "paper_close_requested", "paper_closed" if not reason_codes else "blocked"],
        "reason_codes": reason_codes,
        "paperbroker_results": [_paperbroker_record(case, broker_result, "next_day_close")],
        "account_ledger_results": [_ledger_record(case, ledger_result, "next_day_close")],
        "current_state": "paper_closed" if not reason_codes else "blocked",
        "paperbroker_status": "closed" if broker_result["ok"] else "rejected",
        "account_ledger_status": "closed" if ledger_result["accepted"] else "rejected",
    }


def _state_record(lifecycle_id: str, state_name: str, index: int, reason_codes: list[str]) -> dict[str, Any]:
    trading_day = 1 if state_name in {"next_day_close_eligible", "paper_closed"} else 0
    state = make_state(f"{lifecycle_id}-state-{index:02d}", lifecycle_id, state_name, index, trading_day, reason_codes if state_name in {"blocked", "rejected", "audit_only", "terminal_block"} else [])
    return state.to_dict()


def _transition_records(
    lifecycle_id: str,
    states: list[dict[str, Any]],
    blocked_codes: list[str],
    policy_status: str,
    allocation_status: str,
    portfolio_status: str,
    stress_status: str,
    incident_status: str,
    paperbroker_results: list[dict[str, Any]],
    account_ledger_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    final_state = states[-1]["state_name"]
    for index in range(1, len(states)):
        from_state = states[index - 1]["state_name"]
        to_state = states[index]["state_name"]
        allowed = to_state not in {"blocked", "rejected", "audit_only", "terminal_block"}
        transition = make_transition(
            f"{lifecycle_id}-transition-{index:02d}",
            lifecycle_id,
            from_state,
            to_state,
            int(states[index]["trading_day_index"]),
            allowed,
            blocked_codes if not allowed or final_state in {"blocked", "rejected", "audit_only", "terminal_block"} else [],
            {
                "policy": policy_status,
                "allocation": allocation_status,
                "portfolio": portfolio_status,
                "stress": stress_status,
                "incident": incident_status,
            },
            paperbroker_results[-1] if paperbroker_results else {},
            account_ledger_results[-1] if account_ledger_results else {},
            {"decision": "blocked" if "same_day_round_trip_rejected" in blocked_codes else "allowed", "reason_codes": blocked_codes},
            {"status": stress_status},
            {"status": incident_status},
        )
        records.append(transition.to_dict())
    return records


def _proof_records(case: dict[str, Any], states: list[dict[str, Any]], transitions: list[dict[str, Any]], reason_codes: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        transition_id = transitions[index - 1]["transition_id"] if index > 0 and transitions else ""
        proof = make_proof(
            f"{case['lifecycle_id']}-proof-{index + 1:02d}",
            str(case["lifecycle_id"]),
            transition_id,
            str(state["state_id"]),
            "active_option_lifecycle_simulator",
            "lifecycle_state_transition",
            "blocked" if state["state_name"] in {"blocked", "rejected", "audit_only", "terminal_block"} else "accepted",
            [str(LIFECYCLE_POLICY_PATH), str(LIFECYCLE_CASES_PATH)],
            reason_codes if state["state_name"] in {"blocked", "rejected", "audit_only", "terminal_block"} else [],
        ).to_dict()
        proof.update({
            "artifact_type": "lifecycle_proof",
            "candidate_id": str(case["candidate_id"]),
            "option_type": str(case["option_type"]),
            "strategy_type": str(case["strategy_type"]),
            "action_attempted": state["state_name"],
            "action_allowed": state["state_name"] not in {"blocked", "rejected", "audit_only", "terminal_block"},
            "policy_result": str(case.get("policy_status", "approved")),
            "allocation_result": str(case.get("allocation_status", "allocate_paper")),
            "portfolio_result": str(case.get("portfolio_status", "within_cap")),
            "stress_result": str(case.get("stress_status", "normal")),
            "incident_result": str(case.get("incident_status", "clear")),
            "paperbroker_result": "paper_only_authority_gate",
            "account_ledger_result": "paper_only_no_day_trade_gate",
            "no_day_trade_result": "same_day_blocked" if "same_day_round_trip_rejected" in reason_codes else "allowed",
            "safety_status": "paper_only_live_blocked_fixture_only",
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
            "no_scheduler": True,
            "no_credentials": True,
            "same_day_churn_allowed": False,
            "paperbroker_override_allowed": False,
        })
        records.append(proof)
    return records


def _summary(
    cases: list[dict[str, Any]],
    states: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    proofs: list[dict[str, Any]],
    lifecycles: list[dict[str, Any]],
    paperbroker_results: list[dict[str, Any]],
    account_ledger_results: list[dict[str, Any]],
) -> dict[str, Any]:
    state_distribution = dict(sorted(Counter(str(record["state_name"]) for record in states).items()))
    transition_distribution = dict(sorted(Counter(str(record["to_state"]) for record in transitions).items()))
    current_distribution = dict(sorted(Counter(str(record["current_state"]) for record in lifecycles).items()))
    blocked_transitions = [record for record in transitions if record["transition_allowed"] is False or record["to_state"] in {"blocked", "rejected", "audit_only", "terminal_block"}]
    summary = {
        "artifact_type": "active_option_lifecycle_summary",
        "lifecycle_simulator_version": "dopey-active-option-lifecycle-simulator-v1",
        "lifecycle_case_count": len(cases),
        "state_count": len(states),
        "transition_count": len(transitions),
        "proof_record_count": len(proofs),
        "paperbroker_result_count": len(paperbroker_results),
        "account_ledger_result_count": len(account_ledger_results),
        "state_distribution": state_distribution,
        "transition_distribution": transition_distribution,
        "current_state_distribution": current_distribution,
        "paper_open_count": sum(1 for record in paperbroker_results if record["action"] == "open" and record["ok"]),
        "paper_close_count": sum(1 for record in paperbroker_results if "close" in record["action"] and record["ok"]),
        "blocked_transition_count": len(blocked_transitions),
        "no_day_trade_block_count": sum(1 for record in transitions if "same_day_round_trip_rejected" in record["blocked_reason_codes"]),
        "delayed_rotation_count": state_distribution.get("rotation_delayed", 0),
        "zero_dte_special_lifecycle_count": state_distribution.get("zero_dte_special_lifecycle", 0),
        "zero_dte_expiry_managed_count": state_distribution.get("zero_dte_expiry_managed", 0),
        "zero_dte_special_close_success_count": state_distribution.get("zero_dte_special_closed", 0),
        "swing_next_day_close_count": sum(1 for record in lifecycles if record["current_state"] == "paper_closed" and record["strategy_type"] in {"swing_long_call", "swing_long_put"}),
        "paperbroker_rejection_count": sum(1 for record in paperbroker_results if not record["ok"]),
        "account_ledger_mismatch_count": sum(1 for record in lifecycles if record["current_state"] == "audit_only"),
        "incident_interruption_count": sum(1 for record in lifecycles if record["incident_status"] == "terminal_block"),
        "stress_interruption_count": sum(1 for record in lifecycles if record["stress_status"] in {"severe", "crisis_lockdown"}),
        "terminal_block_count": current_distribution.get("terminal_block", 0),
        "proof_completeness": len(proofs) >= len(states),
        "same_day_churn_allowed": False,
        "paperbroker_override_allowed": False,
        "terminal_block_auto_recovery_allowed": False,
        "full_suite_timeout_recorded_as_pass": False,
        "feedback_advisory_only": True,
        "live_allocation_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credentials": True,
    }
    summary["strict_hashes"] = {
        "lifecycle_policy": _file_hash(LIFECYCLE_POLICY_PATH),
        "lifecycle_cases": _file_hash(LIFECYCLE_CASES_PATH),
        "lifecycle_states": _file_hash(LIFECYCLE_STATES_PATH),
        "lifecycle_transitions": _file_hash(LIFECYCLE_TRANSITIONS_PATH),
        "lifecycle_proof": _file_hash(LIFECYCLE_PROOF_PATH),
    }
    summary["reproducibility_hash"] = reproducibility_hash({key: value for key, value in summary.items() if key != "reproducibility_hash"})
    return summary


def _feedback_record(case: dict[str, Any], target: str, current_state: str, reason_codes: list[str]) -> dict[str, Any]:
    feedback_type = _feedback_type(current_state, reason_codes)
    return {
        "artifact_type": f"lifecycle_feedback_{target}",
        "feedback_id": f"{case['lifecycle_id']}-{target}-feedback",
        "lifecycle_id": str(case["lifecycle_id"]),
        "candidate_id": str(case["candidate_id"]),
        "feedback_type": feedback_type,
        "feedback_action": feedback_type,
        "feedback_actions": [feedback_type],
        "reason_codes": reason_codes,
        "advisory_only": True,
        "paper_only": True,
        "live_blocked": True,
        "live_allocation_mutation_allowed": False,
        "live_portfolio_mutation_allowed": False,
        "live_stress_ladder_mutation_allowed": False,
        "live_incident_mutation_allowed": False,
        "real_allocation_mutation_allowed": False,
    }


def _feedback_type(current_state: str, reason_codes: list[str]) -> str:
    if current_state == "paper_closed":
        return "lifecycle_close_success"
    if current_state == "zero_dte_special_closed":
        return "lifecycle_zero_dte_special_close_success"
    if current_state == "expired_simulated":
        return "lifecycle_zero_dte_expiry_managed"
    if "same_day_round_trip_rejected" in reason_codes:
        return "lifecycle_blocked_same_day_close"
    if "incident_terminal_block_prevents_lifecycle_progress" in reason_codes:
        return "lifecycle_incident_terminal_block"
    if any("stress" in code or "crisis" in code for code in reason_codes):
        return "lifecycle_stress_throttle"
    if any("account_ledger_mismatch" in code for code in reason_codes):
        return "lifecycle_account_ledger_mismatch"
    if current_state == "rejected":
        return "lifecycle_paperbroker_rejection"
    if current_state == "blocked":
        return "lifecycle_requires_more_fixture_coverage"
    return "lifecycle_open_success"


def write_lifecycle_outputs(policy: dict[str, Any], bundle: dict[str, Any]) -> dict[str, str]:
    cases = bundle["cases"]
    states = bundle["states"]
    transitions = bundle["transitions"]
    proofs = bundle["proofs"]
    summary = bundle["summary"]
    fixture_payloads = {
        LIFECYCLE_POLICY_FIXTURE_PATH: policy,
        LIFECYCLE_CASES_FIXTURE_PATH: {"fixture_version": "dopey-lifecycle-cases-v1", "records": cases, "lifecycle_case_count": len(cases), "paper_only": True, "live_blocked": True},
        LIFECYCLE_EXPECTED_STATES_FIXTURE_PATH: {"fixture_version": "dopey-lifecycle-expected-states-v1", "records": states, "state_count": len(states), "paper_only": True, "live_blocked": True},
        LIFECYCLE_EXPECTED_TRANSITIONS_FIXTURE_PATH: {"fixture_version": "dopey-lifecycle-expected-transitions-v1", "records": transitions, "transition_count": len(transitions), "paper_only": True, "live_blocked": True},
        LIFECYCLE_EXPECTED_PROOFS_FIXTURE_PATH: {"fixture_version": "dopey-lifecycle-expected-proofs-v1", "records": proofs, "proof_record_count": len(proofs), "paper_only": True, "live_blocked": True},
        LIFECYCLE_EXPECTED_SUMMARY_FIXTURE_PATH: {"fixture_version": "dopey-lifecycle-expected-summary-v1", "summary": summary, "paper_only": True, "live_blocked": True},
    }
    artifact_payloads = {
        LIFECYCLE_POLICY_PATH: policy,
        LIFECYCLE_CASES_PATH: {"artifact_type": "lifecycle_cases", "records": cases, "lifecycle_case_count": len(cases), "paper_only": True, "live_blocked": True},
        LIFECYCLE_SUMMARY_PATH: summary,
    }
    for path, payload in fixture_payloads.items():
        _write_json(path, payload)
    for path, payload in artifact_payloads.items():
        _write_json(path, payload)
    _write_jsonl(LIFECYCLE_STATES_PATH, states)
    _write_jsonl(LIFECYCLE_TRANSITIONS_PATH, transitions)
    _write_jsonl(LIFECYCLE_PROOF_PATH, proofs)
    _write_jsonl(LIFECYCLE_PAPERBROKER_RESULTS_PATH, bundle["paperbroker_results"])
    _write_jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH, bundle["account_ledger_results"])
    _write_jsonl(LIFECYCLE_FEEDBACK_ALLOCATOR_PATH, bundle["feedback_allocator"])
    _write_jsonl(LIFECYCLE_FEEDBACK_PORTFOLIO_PATH, bundle["feedback_portfolio"])
    _write_jsonl(LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH, bundle["feedback_stress"])
    _write_jsonl(LIFECYCLE_FEEDBACK_INCIDENT_PATH, bundle["feedback_incident"])
    refreshed_summary = dict(summary)
    refreshed_summary["strict_hashes"] = {
        "lifecycle_policy": _file_hash(LIFECYCLE_POLICY_PATH),
        "lifecycle_cases": _file_hash(LIFECYCLE_CASES_PATH),
        "lifecycle_states": _file_hash(LIFECYCLE_STATES_PATH),
        "lifecycle_transitions": _file_hash(LIFECYCLE_TRANSITIONS_PATH),
        "lifecycle_proof": _file_hash(LIFECYCLE_PROOF_PATH),
        "lifecycle_summary": _file_hash(LIFECYCLE_SUMMARY_PATH),
    }
    _write_json(LIFECYCLE_SUMMARY_PATH, refreshed_summary)
    _write_json(LIFECYCLE_EXPECTED_SUMMARY_FIXTURE_PATH, {"fixture_version": "dopey-lifecycle-expected-summary-v1", "summary": refreshed_summary, "paper_only": True, "live_blocked": True})
    return lifecycle_artifact_paths()


def lifecycle_artifact_paths() -> dict[str, str]:
    return {
        "lifecycle_policy": str(LIFECYCLE_POLICY_PATH),
        "lifecycle_cases": str(LIFECYCLE_CASES_PATH),
        "lifecycle_states": str(LIFECYCLE_STATES_PATH),
        "lifecycle_transitions": str(LIFECYCLE_TRANSITIONS_PATH),
        "lifecycle_proof": str(LIFECYCLE_PROOF_PATH),
        "lifecycle_paperbroker_results": str(LIFECYCLE_PAPERBROKER_RESULTS_PATH),
        "lifecycle_account_ledger_results": str(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH),
        "lifecycle_feedback_allocator": str(LIFECYCLE_FEEDBACK_ALLOCATOR_PATH),
        "lifecycle_feedback_portfolio": str(LIFECYCLE_FEEDBACK_PORTFOLIO_PATH),
        "lifecycle_feedback_stress_ladder": str(LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH),
        "lifecycle_feedback_incident": str(LIFECYCLE_FEEDBACK_INCIDENT_PATH),
        "lifecycle_summary": str(LIFECYCLE_SUMMARY_PATH),
    }


def _base_case(index: int, group: str, option_type: str, strategy_type: str) -> dict[str, Any]:
    date = "2026-07-06"
    expiry = "2026-07-17"
    return {
        "case_id": f"lifecycle-case-{index:03d}",
        "lifecycle_id": f"lifecycle-{index:03d}",
        "candidate_id": f"lifecycle-candidate-{index:03d}",
        "case_group": group,
        "underlying_family_id": f"synthetic-family-{(index % 6) + 1}",
        "synthetic_underlying_symbol": f"DLP{(index % 9) + 1}",
        "option_type": option_type,
        "strategy_type": strategy_type,
        "structure": "long_call" if option_type == "call" else "long_put",
        "trade_date": date,
        "next_trade_date": "2026-07-07",
        "expiry": expiry,
        "days_to_expiry": 5,
        "policy_status": "approved",
        "allocation_status": "allocate_paper",
        "portfolio_status": "within_cap",
        "stress_status": "normal",
        "incident_status": "clear",
        "open_action": "buy_to_open",
        "defined_risk": True,
        "liquidity_approved": True,
        "risk_cap_approved": True,
        "special_close_allowed": True,
        "special_close_reason": "expiry_window",
        "close_behavior": "next_day_close",
        "paper_only": True,
        "live_blocked": True,
    }


def _paperbroker_record(case: dict[str, Any], result: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "artifact_type": "lifecycle_paperbroker_result",
        "result_id": f"{case['lifecycle_id']}-{action}-paperbroker",
        "lifecycle_id": str(case["lifecycle_id"]),
        "candidate_id": str(case["candidate_id"]),
        "action": action,
        "ok": bool(result.get("ok", False)),
        "status": str(result.get("status", "")),
        "reason_codes": result.get("errors", []),
        "paperbroker_override_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _ledger_record(case: dict[str, Any], result: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        "artifact_type": "lifecycle_account_ledger_result",
        "result_id": f"{case['lifecycle_id']}-{action}-ledger",
        "lifecycle_id": str(case["lifecycle_id"]),
        "candidate_id": str(case["candidate_id"]),
        "action": action,
        "accepted": bool(result.get("accepted", False)),
        "decision": str(result.get("decision", "")),
        "reason_codes": result.get("reason_codes", []),
        "close_eligible_date": str(result.get("close_eligible_date", "")),
        "paper_only": True,
        "live_blocked": True,
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    output: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash({key: value for key, value in payload.items() if key != "reproducibility_hash"})
        output.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output) + ("\n" if output else ""), encoding="utf-8")


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()
