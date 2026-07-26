"""Shadow replay 0DTE risk fixtures under candidate threshold profiles."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .run_zero_dte_outcome_replay import (
    ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH,
    ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH,
)
from .run_zero_dte_risk_model import evaluate_zero_dte_fixture_cases, load_zero_dte_risk_cases
from .zero_dte_replay_engine import (
    evaluate_zero_dte_replay_fixture_cases,
    load_zero_dte_intraday_paths,
    load_zero_dte_outcome_replay_cases,
)
from .zero_dte_risk_model import ZERO_DTE_OPEN_APPROVAL_DECISIONS
from .zero_dte_risk_thresholds import ZeroDTERiskThresholds
from .zero_dte_threshold_candidate import zero_dte_thresholds_from_candidate
from .zero_dte_threshold_optimizer_models import (
    ZeroDTEShadowReplayResult,
    ZeroDTEThresholdCandidate,
    zero_dte_shadow_replay_hash,
)


def run_zero_dte_shadow_replay_for_candidates(
    candidates: list[ZeroDTEThresholdCandidate],
    base_thresholds: ZeroDTERiskThresholds,
    validated_blocks: list[dict[str, Any]],
) -> tuple[list[ZeroDTEShadowReplayResult], dict[str, list[str]]]:
    return run_zero_dte_shadow_replay_for_cases(
        candidates,
        base_thresholds,
        load_zero_dte_risk_cases(),
        load_zero_dte_outcome_replay_cases(ZERO_DTE_OUTCOME_REPLAY_CASES_FIXTURE_PATH),
        load_zero_dte_intraday_paths(ZERO_DTE_INTRADAY_PATHS_FIXTURE_PATH),
        validated_blocks,
    )


def run_zero_dte_shadow_replay_for_cases(
    candidates: list[ZeroDTEThresholdCandidate],
    base_thresholds: ZeroDTERiskThresholds,
    risk_cases: list[dict[str, Any]],
    replay_cases: list[dict[str, Any]],
    intraday_paths: dict[str, dict[str, Any]],
    validated_blocks: list[dict[str, Any]],
) -> tuple[list[ZeroDTEShadowReplayResult], dict[str, list[str]]]:
    baseline_records = evaluate_zero_dte_fixture_cases(risk_cases, base_thresholds)
    baseline_by_case = {str(record["case_id"]): record for record in baseline_records}
    results: list[ZeroDTEShadowReplayResult] = []
    safety_reason_codes_by_candidate: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_thresholds = zero_dte_thresholds_from_candidate(base_thresholds, candidate)
        candidate_records = evaluate_zero_dte_fixture_cases(risk_cases, candidate_thresholds)
        replay_evaluation = evaluate_zero_dte_replay_fixture_cases(replay_cases, intraday_paths, candidate_thresholds)
        candidate_by_case = {str(record["case_id"]): record for record in candidate_records}
        safety_codes = _safety_reason_codes(baseline_by_case, candidate_by_case)
        replay_mismatches = sum(1 for record in replay_evaluation["replay_details"] if not record["expectation_matched"])
        feedback_mismatches = sum(1 for record in replay_evaluation["replay_details"] if not record["feedback_expectation_matched"])
        draft = ZeroDTEShadowReplayResult(
            shadow_replay_id=f"zero-dte-shadow-replay-{candidate.candidate_threshold_id}",
            candidate_threshold_id=candidate.candidate_threshold_id,
            fixture_cases_replayed=len(risk_cases),
            decisions_changed=_decisions_changed(baseline_by_case, candidate_by_case),
            new_approvals=_new_approval_count(baseline_by_case, candidate_by_case),
            new_blocks=_new_block_count(baseline_by_case, candidate_by_case),
            new_throttles=_new_throttle_count(baseline_by_case, candidate_by_case),
            validated_block_preserved_count=_validated_block_preserved_count(candidate_records, validated_blocks),
            unsafe_approval_count=len([code for code in safety_codes if code.startswith("unsafe_new_approval")]),
            overfit_warning_count=_overfit_warning_count(candidate, replay_mismatches, feedback_mismatches),
            safety_error_count=0,
            paper_only=True,
            live_blocked=True,
            shadow_replay_hash="",
        )
        final_draft = ZeroDTEShadowReplayResult(
            shadow_replay_id=draft.shadow_replay_id,
            candidate_threshold_id=draft.candidate_threshold_id,
            fixture_cases_replayed=draft.fixture_cases_replayed,
            decisions_changed=draft.decisions_changed,
            new_approvals=draft.new_approvals,
            new_blocks=draft.new_blocks,
            new_throttles=draft.new_throttles,
            validated_block_preserved_count=draft.validated_block_preserved_count,
            unsafe_approval_count=draft.unsafe_approval_count,
            overfit_warning_count=draft.overfit_warning_count,
            safety_error_count=draft.unsafe_approval_count + _candidate_safety_error_count(candidate),
            paper_only=True,
            live_blocked=True,
            shadow_replay_hash="",
        )
        result = ZeroDTEShadowReplayResult(
            shadow_replay_id=final_draft.shadow_replay_id,
            candidate_threshold_id=final_draft.candidate_threshold_id,
            fixture_cases_replayed=final_draft.fixture_cases_replayed,
            decisions_changed=final_draft.decisions_changed,
            new_approvals=final_draft.new_approvals,
            new_blocks=final_draft.new_blocks,
            new_throttles=final_draft.new_throttles,
            validated_block_preserved_count=final_draft.validated_block_preserved_count,
            unsafe_approval_count=final_draft.unsafe_approval_count,
            overfit_warning_count=final_draft.overfit_warning_count,
            safety_error_count=final_draft.safety_error_count,
            paper_only=True,
            live_blocked=True,
            shadow_replay_hash=zero_dte_shadow_replay_hash(final_draft),
        )
        results.append(result)
        safety_reason_codes_by_candidate[candidate.candidate_threshold_id] = sorted(set(safety_codes))
    return results, safety_reason_codes_by_candidate


def _decisions_changed(baseline_by_case: dict[str, dict], candidate_by_case: dict[str, dict]) -> int:
    return sum(
        1 for case_id, baseline in baseline_by_case.items()
        if baseline["decision"]["decision"] != candidate_by_case[case_id]["decision"]["decision"]
    )


def _new_approval_count(baseline_by_case: dict[str, dict], candidate_by_case: dict[str, dict]) -> int:
    return sum(
        1 for case_id, baseline in baseline_by_case.items()
        if not _approved(baseline["decision"]) and _approved(candidate_by_case[case_id]["decision"])
    )


def _new_block_count(baseline_by_case: dict[str, dict], candidate_by_case: dict[str, dict]) -> int:
    return sum(
        1 for case_id, baseline in baseline_by_case.items()
        if _approved(baseline["decision"]) and not _approved(candidate_by_case[case_id]["decision"])
    )


def _new_throttle_count(baseline_by_case: dict[str, dict], candidate_by_case: dict[str, dict]) -> int:
    return sum(
        1 for case_id, baseline in baseline_by_case.items()
        if baseline["decision"]["decision"] == "approved_for_paper_open"
        and candidate_by_case[case_id]["decision"]["decision"] == "approved_with_throttle"
    )


def _validated_block_preserved_count(candidate_records: list[dict[str, Any]], validated_blocks: list[dict[str, Any]]) -> int:
    candidate_by_id = {record["decision"]["candidate_id"]: record["decision"] for record in candidate_records}
    count = 0
    for block in validated_blocks:
        candidate_id = str(block.get("candidate_id", ""))
        decision = candidate_by_id.get(candidate_id)
        if decision is not None and not _approved(decision):
            count += 1
    return count


def _safety_reason_codes(
    baseline_by_case: dict[str, dict],
    candidate_by_case: dict[str, dict],
) -> list[str]:
    codes: list[str] = []
    for case_id, baseline in baseline_by_case.items():
        candidate_record = candidate_by_case[case_id]
        baseline_decision = baseline["decision"]
        candidate_decision = candidate_record["decision"]
        if _approved(baseline_decision) or not _approved(candidate_decision):
            continue
        codes.extend(_unsafe_approval_codes(baseline_decision, candidate_decision))
    return _dedupe(codes)


def _unsafe_approval_codes(baseline_decision: dict[str, Any], candidate_decision: dict[str, Any]) -> list[str]:
    candidate_input = candidate_decision.get("candidate_input", {})
    failed_controls = [str(item) for item in baseline_decision.get("failed_controls", [])]
    reason_codes = [str(item) for item in baseline_decision.get("reason_codes", [])]
    codes: list[str] = []
    if isinstance(candidate_input, dict) and candidate_input.get("live_blocked") is not True:
        codes.append("unsafe_new_approval_live_path")
    if isinstance(candidate_input, dict) and candidate_input.get("order_action") != "buy_to_open":
        codes.append("unsafe_new_approval_sell_to_open_or_non_open")
    if isinstance(candidate_input, dict) and candidate_input.get("option_type") not in {"call", "put"}:
        codes.append("unsafe_new_approval_unsupported_option_type")
    if isinstance(candidate_input, dict) and candidate_input.get("structure_type") not in {"long_call", "long_put", "single"}:
        codes.append("unsafe_new_approval_unsupported_structure")
    if isinstance(candidate_input, dict) and candidate_input.get("defined_risk") is not True:
        codes.append("unsafe_new_approval_undefined_risk")
    if isinstance(candidate_input, dict) and not str(candidate_input.get("explicit_thesis", "")).strip():
        codes.append("unsafe_new_approval_missing_thesis")
    if isinstance(candidate_input, dict) and not str(candidate_input.get("explicit_exit_or_expiry_plan", "")).strip():
        codes.append("unsafe_new_approval_missing_exit_plan")
    if "strict_liquidity" in failed_controls or "liquidity_below_zero_dte_floor" in reason_codes:
        codes.append("unsafe_new_approval_poor_liquidity")
    if "strict_spread" in failed_controls or "spread_pct_exceeds_zero_dte_limit" in reason_codes:
        codes.append("unsafe_new_approval_wide_spread")
    if "strict_slippage" in failed_controls:
        codes.append("unsafe_new_approval_high_slippage")
    if "greeks_stable_enough" in failed_controls:
        codes.append("unsafe_new_approval_greeks_instability")
    if "iv_not_overpaid" in failed_controls:
        codes.append("unsafe_new_approval_iv_or_premium_overpayment")
    if "proof_and_signal_present" in failed_controls:
        codes.append("unsafe_new_approval_weak_proof")
    if "event_macro_regime_acceptable" in failed_controls:
        codes.append("unsafe_new_approval_event_or_macro_risk")
    if not codes:
        codes.append("unsafe_new_approval_from_blocked_baseline")
    return codes


def _overfit_warning_count(
    candidate: ZeroDTEThresholdCandidate,
    replay_mismatches: int,
    feedback_mismatches: int,
) -> int:
    warnings = replay_mismatches + feedback_mismatches
    if candidate.risk_posture in {"coverage_expansion_only", "rejected_too_loose", "rejected_overfit"}:
        warnings += 1
    if len(candidate.controls_tightened) >= 7 and candidate.candidate_threshold_id != "balanced_research_profile":
        warnings += 1
    return warnings


def _candidate_safety_error_count(candidate: ZeroDTEThresholdCandidate) -> int:
    invariants = candidate.change_set.get("safety_invariants", {})
    if not isinstance(invariants, dict):
        return 1
    checks = [
        invariants.get("paper_only") is True,
        invariants.get("live_blocked") is True,
        invariants.get("allow_live_threshold_mutation") is False,
        invariants.get("allow_sell_to_open") is False,
        invariants.get("allow_normal_same_day_churn") is False,
        candidate.paper_only is True,
        candidate.live_blocked is True,
    ]
    return 0 if all(checks) else 1


def _approved(decision: dict[str, Any]) -> bool:
    return str(decision.get("decision", "")) in ZERO_DTE_OPEN_APPROVAL_DECISIONS


def shadow_replay_summary(results: list[ZeroDTEShadowReplayResult]) -> dict[str, Any]:
    decisions = Counter(result.candidate_threshold_id for result in results)
    return {
        "candidate_count": len(results),
        "shadow_replay_ids": sorted(decisions),
        "total_decisions_changed": sum(result.decisions_changed for result in results),
        "total_new_approvals": sum(result.new_approvals for result in results),
        "total_new_blocks": sum(result.new_blocks for result in results),
        "total_new_throttles": sum(result.new_throttles for result in results),
        "unsafe_approval_count": sum(result.unsafe_approval_count for result in results),
        "overfit_warning_count": sum(result.overfit_warning_count for result in results),
        "safety_error_count": sum(result.safety_error_count for result in results),
        "paper_only": True,
        "live_blocked": True,
    }


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
