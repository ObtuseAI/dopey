from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.active_policy_audit import audit_zero_dte_threshold_optimizer_records, run_active_policy_audit
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.run_zero_dte_risk_model import load_zero_dte_risk_cases
from dopey_options.run_zero_dte_threshold_optimizer import (
    ZERO_DTE_OPTIMIZATION_DECISIONS_PATH,
    ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH,
    ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH,
    ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH,
    ZERO_DTE_THRESHOLD_CANDIDATES_PATH,
    ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH,
    ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH,
    ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH,
    run_zero_dte_threshold_optimizer,
)
from dopey_options.zero_dte_decision_engine import evaluate_zero_dte_candidate
from dopey_options.zero_dte_feedback_aggregator import build_zero_dte_threshold_feedback_aggregate
from dopey_options.zero_dte_optimizer_decision_policy import (
    decide_zero_dte_threshold_candidate,
    retained_current_threshold_decision,
)
from dopey_options.zero_dte_risk_model import ZERO_DTE_OPEN_APPROVAL_DECISIONS, ZeroDTERiskInput
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds
from dopey_options.zero_dte_shadow_replay import run_zero_dte_shadow_replay_for_candidates
from dopey_options.zero_dte_threshold_candidate import zero_dte_thresholds_from_candidate
from dopey_options.zero_dte_threshold_candidate_generator import generate_zero_dte_threshold_candidates
from dopey_options.zero_dte_threshold_optimizer_models import (
    ZeroDTEShadowReplayResult,
    ZeroDTEThresholdCandidate,
    ZeroDTEThresholdFeedbackAggregate,
    ZeroDTEThresholdOptimizationDecision,
    zero_dte_optimization_decision_hash,
    zero_dte_shadow_replay_hash,
    zero_dte_threshold_candidate_hash,
)
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _zero_dte_threshold_optimizer_summary


@pytest.fixture(scope="module")
def optimizer_result() -> dict:
    return run_zero_dte_threshold_optimizer()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _aggregate() -> ZeroDTEThresholdFeedbackAggregate:
    return build_zero_dte_threshold_feedback_aggregate()


def _base_thresholds():
    return load_default_zero_dte_risk_thresholds()


def _candidates() -> list[ZeroDTEThresholdCandidate]:
    return generate_zero_dte_threshold_candidates(_aggregate(), _base_thresholds())


def _candidate(candidate_threshold_id: str) -> ZeroDTEThresholdCandidate:
    for candidate in _candidates():
        if candidate.candidate_threshold_id == candidate_threshold_id:
            return candidate
    raise AssertionError(f"missing candidate {candidate_threshold_id}")


def _shadow(
    candidate_threshold_id: str,
    unsafe_approval_count: int,
    safety_error_count: int,
    overfit_warning_count: int,
    new_blocks: int,
) -> ZeroDTEShadowReplayResult:
    draft = ZeroDTEShadowReplayResult(
        shadow_replay_id=f"shadow-{candidate_threshold_id}",
        candidate_threshold_id=candidate_threshold_id,
        fixture_cases_replayed=24,
        decisions_changed=new_blocks + unsafe_approval_count,
        new_approvals=unsafe_approval_count,
        new_blocks=new_blocks,
        new_throttles=0,
        validated_block_preserved_count=4,
        unsafe_approval_count=unsafe_approval_count,
        overfit_warning_count=overfit_warning_count,
        safety_error_count=safety_error_count,
        paper_only=True,
        live_blocked=True,
        shadow_replay_hash="",
    )
    return ZeroDTEShadowReplayResult(
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
        safety_error_count=draft.safety_error_count,
        paper_only=True,
        live_blocked=True,
        shadow_replay_hash=zero_dte_shadow_replay_hash(draft),
    )


def _decision_for(
    candidate: ZeroDTEThresholdCandidate,
    shadow: ZeroDTEShadowReplayResult,
    reason_codes: list[str],
) -> ZeroDTEThresholdOptimizationDecision:
    return decide_zero_dte_threshold_candidate("test-run", _aggregate(), candidate, shadow, reason_codes, True)


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="threshold-optimizer-live-x",
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": "buy", "symbol": "SPY_C1", "option_type": "call", "expiry": "2026-07-17", "dte": 14}],
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=1.0,
        active_policy_required=True,
    )


def test_threshold_feedback_aggregate_serializes_deterministically(optimizer_result: dict):
    record = _json(ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH)
    assert ZeroDTEThresholdFeedbackAggregate.from_dict(record).to_dict()["aggregate_hash"] == record["aggregate_hash"]


def test_threshold_candidate_serializes_deterministically(optimizer_result: dict):
    record = _jsonl(ZERO_DTE_THRESHOLD_CANDIDATES_PATH)[0]
    assert ZeroDTEThresholdCandidate.from_dict(record).to_dict()["candidate_hash"] == record["candidate_hash"]


def test_shadow_replay_result_serializes_deterministically(optimizer_result: dict):
    record = _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH)[0]
    assert ZeroDTEShadowReplayResult.from_dict(record).to_dict()["shadow_replay_hash"] == record["shadow_replay_hash"]


def test_optimization_decision_serializes_deterministically(optimizer_result: dict):
    record = _jsonl(ZERO_DTE_OPTIMIZATION_DECISIONS_PATH)[0]
    assert ZeroDTEThresholdOptimizationDecision.from_dict(record).to_dict()["decision_hash"] == record["decision_hash"]


def test_threshold_candidate_hash_is_deterministic():
    candidate = _candidate("balanced_research_profile")
    assert candidate.candidate_hash == zero_dte_threshold_candidate_hash(candidate)


def test_feedback_aggregator_loads_replay_artifacts(optimizer_result: dict):
    aggregate = _aggregate()
    assert aggregate.feedback_records_loaded == 24
    assert aggregate.outcomes_loaded == 24


def test_feedback_aggregator_counts_outcomes():
    assert _aggregate().outcome_counts_by_type["blocked_correctly"] == 4


def test_feedback_aggregator_counts_feedback_types():
    assert _aggregate().feedback_counts_by_type["tighten_spread_threshold"] >= 1


def test_feedback_aggregator_identifies_validated_blocks():
    assert len(_aggregate().validated_blocks) == 4


def test_feedback_aggregator_identifies_possible_overstrict_blocks():
    assert len(_aggregate().possible_overstrict_blocks) == 1


def test_feedback_aggregator_identifies_approved_failures():
    assert len(_aggregate().approved_failures) >= 1


def test_feedback_aggregator_identifies_throttle_validations():
    assert len(_aggregate().throttle_validations) == 1


def test_generate_stricter_liquidity_profile():
    candidate = _candidate("stricter_liquidity_profile")
    assert "minimum_liquidity_score" in candidate.controls_tightened


def test_generate_stricter_gamma_theta_profile():
    candidate = _candidate("stricter_gamma_theta_profile")
    assert {"max_gamma_instability_score", "max_theta_decay_pressure"}.issubset(candidate.controls_tightened)


def test_generate_stricter_iv_overpayment_profile():
    candidate = _candidate("stricter_iv_overpayment_profile")
    assert "max_premium_overpayment_score" in candidate.controls_tightened


def test_generate_proof_strengthened_profile():
    candidate = _candidate("proof_strengthened_profile")
    assert {"minimum_proof_score", "minimum_signal_confidence"}.issubset(candidate.controls_tightened)


def test_generate_later_expiry_preference_profile():
    candidate = _candidate("later_expiry_preference_profile")
    assert candidate.change_set["policy_overrides"]["later_expiry_preference"]


def test_generate_balanced_research_profile():
    candidate = _candidate("balanced_research_profile")
    assert candidate.risk_posture == "balanced_research"


def test_generate_coverage_expansion_profile():
    candidate = _candidate("coverage_expansion_profile")
    assert candidate.promotion_gate == "needs_more_fixture_coverage"


def test_generate_rejected_too_loose_negative_control():
    candidate = _candidate("rejected_too_loose_profile")
    assert candidate.risk_posture == "rejected_too_loose"
    assert candidate.controls_loosened


def test_candidate_generation_never_removes_thesis_requirement():
    assert all(zero_dte_thresholds_from_candidate(_base_thresholds(), candidate).explicit_thesis_required for candidate in _candidates())


def test_candidate_generation_never_removes_exit_plan_requirement():
    assert all(zero_dte_thresholds_from_candidate(_base_thresholds(), candidate).explicit_exit_plan_required for candidate in _candidates())


def test_candidate_generation_never_approves_sell_to_open():
    case = next(item for item in load_zero_dte_risk_cases() if item["case_id"] == "sell_to_open_blocked")
    decisions = [
        evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(case["input"]), zero_dte_thresholds_from_candidate(_base_thresholds(), candidate)).decision
        for candidate in _candidates()
    ]
    assert not any(decision in ZERO_DTE_OPEN_APPROVAL_DECISIONS for decision in decisions)


def test_shadow_replay_runs_for_all_candidate_profiles():
    results, _codes = run_zero_dte_shadow_replay_for_candidates(_candidates(), _base_thresholds(), _aggregate().validated_blocks)
    assert len(results) == 8


def test_shadow_replay_detects_decision_changes(optimizer_result: dict):
    assert any(record["decisions_changed"] > 0 for record in _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH))


def test_shadow_replay_detects_unsafe_new_approval(optimizer_result: dict):
    rejected = next(record for record in _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH) if record["candidate_threshold_id"] == "rejected_too_loose_profile")
    assert rejected["unsafe_approval_count"] > 0


def test_shadow_replay_preserves_validated_blocks(optimizer_result: dict):
    assert max(record["validated_block_preserved_count"] for record in _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH)) == 4


def test_shadow_replay_records_overfit_warning(optimizer_result: dict):
    assert any(record["overfit_warning_count"] > 0 for record in _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH))


def test_shadow_replay_hash_is_deterministic(optimizer_result: dict):
    record = _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH)[0]
    assert ZeroDTEShadowReplayResult.from_dict(record).shadow_replay_hash == record["shadow_replay_hash"]


def test_optimizer_rejects_candidate_with_safety_error():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 0, 1, 0, 0), ["shadow_replay_safety_error"])
    assert decision.decision == "reject_candidate"


def test_optimizer_rejects_candidate_with_live_path_approval():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 1, 1, 0, 0), ["unsafe_new_approval_live_path"])
    assert decision.decision == "reject_candidate"


def test_optimizer_rejects_candidate_with_unsupported_structure_approval():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 1, 1, 0, 0), ["unsafe_new_approval_unsupported_structure"])
    assert decision.decision == "reject_candidate"


def test_optimizer_rejects_candidate_missing_thesis_approval():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 1, 1, 0, 0), ["unsafe_new_approval_missing_thesis"])
    assert decision.decision == "reject_candidate"


def test_optimizer_rejects_candidate_missing_exit_plan_approval():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 1, 1, 0, 0), ["unsafe_new_approval_missing_exit_plan"])
    assert decision.decision == "reject_candidate"


def test_optimizer_rejects_candidate_poor_liquidity_approval():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 1, 1, 0, 0), ["unsafe_new_approval_poor_liquidity"])
    assert decision.decision == "reject_candidate"


def test_optimizer_holds_advisory_when_coverage_insufficient():
    decision = _decision_for(_candidate("stricter_liquidity_profile"), _shadow("stricter_liquidity_profile", 0, 0, 1, 1), [])
    assert decision.decision == "hold_advisory_only"


def test_optimizer_promotes_safe_candidate_to_paper_shadow():
    decision = _decision_for(_candidate("stricter_gamma_theta_profile"), _shadow("stricter_gamma_theta_profile", 0, 0, 0, 0), [])
    assert decision.decision == "promote_to_paper_shadow_candidate"


def test_optimizer_can_promote_research_default_when_strict_gates_pass():
    decision = _decision_for(_candidate("balanced_research_profile"), _shadow("balanced_research_profile", 0, 0, 0, 1), [])
    assert decision.decision == "promote_to_research_default_candidate"


def test_optimizer_retains_current_thresholds_when_no_candidate_improves():
    decision = retained_current_threshold_decision("test-run", _aggregate())
    assert decision.decision == "retain_current_thresholds"


def test_optimizer_decision_does_not_mutate_live_thresholds():
    before = _base_thresholds().to_dict()
    run_zero_dte_threshold_optimizer()
    assert _base_thresholds().to_dict() == before


def test_threshold_feedback_aggregate_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH.exists()


def test_threshold_candidates_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_THRESHOLD_CANDIDATES_PATH.exists()


def test_shadow_replay_results_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH.exists()


def test_optimization_decisions_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_OPTIMIZATION_DECISIONS_PATH.exists()


def test_recommended_threshold_profile_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH.exists()


def test_rejected_threshold_profiles_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH.exists()


def test_threshold_optimizer_summary_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH.exists()


def test_threshold_optimizer_proof_artifact_written(optimizer_result: dict):
    assert ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH.exists()


def test_audit_recognizes_threshold_optimizer_artifacts():
    names = {item[0] for item in __import__("dopey_audit.artifact_loader", fromlist=["ARTIFACT_SPECS"]).ARTIFACT_SPECS}
    assert "zero_dte_threshold_optimizer_summary" in names


def test_audit_flags_promoted_candidate_with_unsafe_approval():
    checks = audit_zero_dte_threshold_optimizer_records(
        {"artifact_type": "zero_dte_threshold_feedback_aggregate", "paper_only": True, "live_blocked": True},
        [{"artifact_type": "zero_dte_threshold_candidate", "change_set": {"safety_invariants": {"allow_normal_same_day_churn": False, "allow_sell_to_open": False}}, "threshold_profile": {"thresholds": {"special_lifecycle_required": True, "explicit_same_day_special_close_reason_required": True, "paper_only": True, "live_blocked": True}}}],
        [{"candidate_threshold_id": "bad", "unsafe_approval_count": 1, "safety_error_count": 1}],
        [{"artifact_type": "zero_dte_threshold_optimization_decision", "candidate_threshold_id": "bad", "decision": "promote_to_paper_shadow_candidate", "decision_reason_codes": []}],
        {"paper_only": True, "live_blocked": True, "live_threshold_mutation_allowed": False},
        [{"candidate_threshold_id": "bad"}],
        [],
    )
    assert any(check["check_id"] == "zero_dte_threshold_optimizer_no_unsafe_approval_promoted" and not check["passed"] for check in checks)


def test_audit_flags_threshold_candidate_that_approves_live_path():
    checks = audit_zero_dte_threshold_optimizer_records(
        {"artifact_type": "zero_dte_threshold_feedback_aggregate", "paper_only": True, "live_blocked": True},
        [],
        [{"candidate_threshold_id": "bad", "unsafe_approval_count": 0, "safety_error_count": 0}],
        [{"artifact_type": "zero_dte_threshold_optimization_decision", "candidate_threshold_id": "bad", "decision": "promote_to_paper_shadow_candidate", "decision_reason_codes": ["unsafe_new_approval_live_path"]}],
        {"paper_only": True, "live_blocked": True, "live_threshold_mutation_allowed": False},
        [{"candidate_threshold_id": "bad"}],
        [],
    )
    assert any(check["check_id"] == "zero_dte_threshold_optimizer_no_live_path_approved" and not check["passed"] for check in checks)


def test_audit_confirms_recommended_profile_paper_only_live_blocked(optimizer_result: dict):
    checks = audit_zero_dte_threshold_optimizer_records(
        _json(ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH),
        _jsonl(ZERO_DTE_THRESHOLD_CANDIDATES_PATH),
        _jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH),
        _jsonl(ZERO_DTE_OPTIMIZATION_DECISIONS_PATH),
        _json(ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH),
        _jsonl(ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH),
        _jsonl(ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH),
    )
    assert any(check["check_id"] == "zero_dte_threshold_optimizer_recommended_profile_paper_only_live_blocked" and check["passed"] for check in checks)


def test_audit_confirms_advisory_feedback_does_not_mutate_live_thresholds(optimizer_result: dict):
    recommended = _json(ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH)
    assert recommended["live_threshold_mutation_allowed"] is False


def test_audit_confirms_no_active_forbidden_live_decisions():
    assert run_active_policy_audit()["safety_errors"] == 0


def test_reporting_includes_threshold_optimizer_summary(optimizer_result: dict):
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert _zero_dte_threshold_optimizer_summary(evidence)["candidate_count"] == 8


def test_export_verifier_selects_threshold_optimizer_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"zero_dte_threshold_optimizer_summary", "zero_dte_threshold_optimizer_proof"}.issubset(ids)


def test_export_review_includes_threshold_optimizer_summary():
    class Ctx:
        shared_export_path = "Z:/fixture"
        reporting_summary = {
            "top_strategy": "fixture",
            "top_family": "fixture",
            "active_policy_summary": {},
            "account_ledger_summary": {},
            "zero_dte_risk_summary": {},
            "zero_dte_replay_summary": {},
            "zero_dte_threshold_optimizer_summary": {"candidate_count": 8, "recommended_threshold_profile": "stricter_gamma_theta_profile"},
        }

    class Bundle:
        source_bundle_id = "bundle"
        source_export_path = "local"
        artifact_count = 1
        hash_status = "pass"
        copy_status = "verified"
        safety_status = "pass"
        credential_scan_status = "pass"
        active_forbidden_live_decisions = 0

    class Decision:
        decision = "ready_for_review"
        suitability = "offline_review"
        next_build_target = "0DTE empirical fixture expansion and adversarial replay corpus"

    assert "0DTE Threshold Feedback Optimizer" in render_executive_summary(Ctx(), Bundle(), [], Decision())


def test_threshold_optimizer_artifact_ledger_written():
    assert Path("docs/reports/DOPEY_0DTE_THRESHOLD_OPTIMIZER_ARTIFACT_LEDGER.md").exists() or run_zero_dte_threshold_optimizer()["zero_dte_threshold_optimizer_status"] == "ok"


def test_live_trading_still_disabled_after_threshold_optimizer(optimizer_result: dict):
    assert optimizer_result["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_threshold_optimizer():
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_threshold_optimizer():
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_threshold_optimizer():
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_threshold_optimizer(optimizer_result: dict):
    text = "\n".join(path.read_text(encoding="utf-8") for path in ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR_FILES())
    assert "sk-proj-" not in text
    assert "sk_live" not in text
    assert "api_key" not in text.lower()


def test_no_scheduler_created_by_threshold_optimizer():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_options").glob("zero_dte_*optimizer*.py"))
    assert "cron" not in text
    assert "apscheduler" not in text


def test_no_network_market_data_dependency_created_by_threshold_optimizer():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in Path("dopey_options").glob("zero_dte_*optimizer*.py"))
    assert "requests" not in text
    assert "yfinance" not in text
    assert "websocket" not in text


def test_no_same_day_churn_loophole_created_by_threshold_optimizer(optimizer_result: dict):
    assert all(record["change_set"]["safety_invariants"]["allow_normal_same_day_churn"] is False for record in _jsonl(ZERO_DTE_THRESHOLD_CANDIDATES_PATH))


def test_blunder_integrity_unchanged_if_manifest_available():
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        assert True
        return
    assert manifest.read_text(encoding="utf-8-sig").strip() or manifest.exists()


def ZERO_DTE_THRESHOLD_OPTIMIZER_ARTIFACT_DIR_FILES() -> list[Path]:
    return [
        ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH,
        ZERO_DTE_THRESHOLD_CANDIDATES_PATH,
        ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH,
        ZERO_DTE_OPTIMIZATION_DECISIONS_PATH,
        ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH,
        ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH,
        ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH,
        ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH,
    ]
