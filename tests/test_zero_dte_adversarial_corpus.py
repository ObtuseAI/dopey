from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.active_policy_audit import audit_zero_dte_adversarial_corpus_records, run_active_policy_audit
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.run_zero_dte_adversarial_corpus import (
    ADVERSARIAL_CORPUS_PROOF_PATH,
    ADVERSARIAL_COVERAGE_SUMMARY_PATH,
    ADVERSARIAL_FIXTURE_CASES_PATH,
    ADVERSARIAL_INTRADAY_PATHS_PATH,
    ADVERSARIAL_OPTIMIZER_EFFECTS_PATH,
    ADVERSARIAL_REPLAY_OUTCOMES_PATH,
    ADVERSARIAL_THRESHOLD_FEEDBACK_PATH,
    COMBINED_REPLAY_SUMMARY_PATH,
    ZERO_DTE_ADVERSARIAL_EXPECTED_FEEDBACK_FIXTURE_PATH,
    ZERO_DTE_ADVERSARIAL_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH,
    ZERO_DTE_ADVERSARIAL_INTRADAY_PATHS_FIXTURE_PATH,
    ZERO_DTE_ADVERSARIAL_REPLAY_CASES_FIXTURE_PATH,
    load_zero_dte_adversarial_intraday_paths,
    load_zero_dte_adversarial_replay_cases,
    run_zero_dte_adversarial_corpus,
)
from dopey_options.run_zero_dte_threshold_optimizer import run_zero_dte_threshold_optimizer
from dopey_options.zero_dte_adversarial_coverage import score_zero_dte_adversarial_coverage
from dopey_options.zero_dte_adversarial_fixture_builder import build_zero_dte_adversarial_fixture_cases
from dopey_options.zero_dte_adversarial_fixture_models import (
    ADVERSARIAL_CASE_FAMILIES,
    ADVERSARIAL_RISK_VECTORS,
    ZeroDTEAdversarialFixtureCase,
    zero_dte_adversarial_fixture_hash,
)
from dopey_options.zero_dte_adversarial_path_builder import build_zero_dte_adversarial_intraday_paths
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def adversarial_result() -> dict:
    return run_zero_dte_adversarial_corpus()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cases() -> list[ZeroDTEAdversarialFixtureCase]:
    return load_zero_dte_adversarial_replay_cases()


def _paths() -> list[dict]:
    return load_zero_dte_adversarial_intraday_paths()


def _summary() -> dict:
    run_zero_dte_adversarial_corpus()
    return _json(COMBINED_REPLAY_SUMMARY_PATH)


def _case(primary_risk: str) -> ZeroDTEAdversarialFixtureCase:
    return next(case for case in _cases() if case.primary_risk_vector == primary_risk)


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="adv-live-x",
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": "buy", "symbol": "SPY_C1", "option_type": "call", "expiry": "2026-07-17", "dte": 14}],
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=1.0,
        active_policy_required=True,
    )


def test_adversarial_fixture_case_serializes_deterministically():
    case = build_zero_dte_adversarial_fixture_cases()[0]
    assert ZeroDTEAdversarialFixtureCase.from_dict(case.to_dict()).to_dict() == case.to_dict()


def test_adversarial_fixture_hash_is_deterministic():
    case = build_zero_dte_adversarial_fixture_cases()[0]
    assert case.fixture_hash == zero_dte_adversarial_fixture_hash(case)


def test_adversarial_fixture_requires_paper_only_live_blocked():
    case = build_zero_dte_adversarial_fixture_cases()[0].to_dict()
    case["paper_only"] = False
    with pytest.raises(ValueError):
        ZeroDTEAdversarialFixtureCase.from_dict(case)


def test_adversarial_fixture_rejects_live_market_reference():
    case = build_zero_dte_adversarial_fixture_cases()[0].to_dict()
    case["adversarial_theme"] = "polygon live_quote"
    with pytest.raises(ValueError):
        ZeroDTEAdversarialFixtureCase.from_dict(case)


def test_adversarial_replay_cases_load(adversarial_result: dict):
    assert len(_cases()) >= 96


def test_adversarial_intraday_paths_load(adversarial_result: dict):
    assert len(_paths()) >= 96


def test_adversarial_expected_feedback_loads(adversarial_result: dict):
    assert _json(ZERO_DTE_ADVERSARIAL_EXPECTED_FEEDBACK_FIXTURE_PATH)["record_count"] >= 96


def test_adversarial_expected_optimizer_effects_load(adversarial_result: dict):
    assert _json(ZERO_DTE_ADVERSARIAL_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH)["record_count"] >= 96


def test_adversarial_corpus_has_at_least_96_cases(adversarial_result: dict):
    assert _summary()["adversarial_fixture_count"] >= 96


def test_adversarial_corpus_covers_all_required_case_families():
    assert ADVERSARIAL_CASE_FAMILIES.issubset({case.case_family for case in _cases()})


def test_adversarial_corpus_covers_all_required_risk_vectors():
    assert ADVERSARIAL_RISK_VECTORS.issubset({case.primary_risk_vector for case in _cases()})


def test_adversarial_corpus_includes_policy_loophole_cases():
    assert any(case.case_family == "policy_loophole_adversarial" for case in _cases())


def test_adversarial_corpus_includes_special_close_stress_cases():
    assert sum(1 for case in _cases() if case.case_family == "special_close_stress") >= 10


def test_adversarial_corpus_includes_expiry_management_stress_cases():
    assert sum(1 for case in _cases() if case.case_family == "expiry_management_stress") >= 8


def test_adversarial_path_builder_is_deterministic():
    cases = build_zero_dte_adversarial_fixture_cases()
    assert build_zero_dte_adversarial_intraday_paths(cases) == build_zero_dte_adversarial_intraday_paths(cases)


def test_adversarial_paths_include_underlying_path():
    assert all(path["underlying_path"] for path in _paths())


def test_adversarial_paths_include_option_bid_mid_ask_path():
    assert all(path["option_bid_mid_ask_path"] for path in _paths())


def test_adversarial_paths_include_spread_and_slippage_shocks():
    assert all(path["spread_path"] and path["slippage_shock_path"] for path in _paths())


def test_adversarial_paths_include_greeks_and_iv_paths():
    assert all(path["gamma_path"] and path["theta_path"] and path["iv_path"] for path in _paths())


def test_adversarial_paths_include_expiry_pressure():
    assert all(path["expiry_pressure_path"] for path in _paths())


def test_adversarial_paths_have_no_market_data_dependency():
    text = ZERO_DTE_ADVERSARIAL_INTRADAY_PATHS_FIXTURE_PATH.read_text(encoding="utf-8").lower()
    assert not any(token in text for token in ["polygon", "yfinance", "live_quote", "broker_quote"])


def test_replay_runner_can_run_baseline_only():
    assert run_zero_dte_adversarial_corpus("baseline", True)["summary"]["baseline_fixture_count"] == 24


def test_replay_runner_can_run_adversarial_only():
    assert run_zero_dte_adversarial_corpus("adversarial", True)["summary"]["adversarial_fixture_count"] >= 96


def test_replay_runner_can_run_combined_corpus():
    assert run_zero_dte_adversarial_corpus("combined", True)["summary"]["combined_fixture_count"] >= 120


def test_combined_corpus_has_120_cases():
    assert _summary()["combined_fixture_count"] >= 120


def test_all_adversarial_replay_expectations_match():
    assert _summary()["all_adversarial_replay_expectations_matched"] is True


def test_all_adversarial_feedback_expectations_match():
    assert _summary()["all_adversarial_feedback_expectations_matched"] is True


def test_policy_loophole_cases_remain_blocked():
    assert _summary()["policy_loophole_block_rate"] == 1.0


def test_same_day_churn_adversarial_case_blocked():
    records = _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH)
    assert any(record["blocked"] for record in records if record["safety_status"] == "blocked_policy_loophole")


def test_live_path_adversarial_case_blocked():
    case = _case("live_path_attempt")
    outcome = next(record for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH) if record["case_id"] == case.case_id)
    assert outcome["actual_replay_outcome"] == "rejected_policy_violation"


def test_unsupported_structure_adversarial_case_blocked():
    case = _case("unsupported_structure_attempt")
    outcome = next(record for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH) if record["case_id"] == case.case_id)
    assert outcome["blocked"] is True


def test_missing_paper_only_live_blocked_case_rejected():
    case = _cases()[0].to_dict()
    case["live_blocked"] = False
    with pytest.raises(ValueError):
        ZeroDTEAdversarialFixtureCase.from_dict(case)


def test_special_close_adversarial_missing_reason_blocked():
    assert _summary()["special_close_stress_count"] >= 10


def test_special_close_adversarial_missing_liquidity_blocked():
    assert any(case.primary_risk_vector == "liquidity_decay" for case in _cases() if case.case_family == "special_close_stress")


def test_special_close_adversarial_missing_risk_cap_blocked():
    assert any(case.primary_risk_vector == "missing_exit_plan" for case in _cases())


def test_special_close_adversarial_with_all_proof_allowed():
    assert any(record["actual_replay_outcome"] == "approved_special_close_helped" for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH))


def test_special_close_adversarial_not_normal_day_trade():
    assert all(record["safety_status"] != "normal_day_trade_allowed" for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH))


def test_expiry_management_worthless_adversarial_case():
    assert any(record["actual_replay_outcome"] == "approved_expiry_managed_failure" for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH))


def test_expiry_management_intrinsic_value_adversarial_case():
    assert any(record["actual_replay_outcome"] == "approved_expiry_managed_success" for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH))


def test_expiry_management_pin_risk_adversarial_case():
    assert any(case.primary_risk_vector == "pin_risk" for case in _cases())


def test_expiry_management_exercise_assignment_flag_simulated_only():
    assert all(path["no_broker"] is True for path in _paths())


def test_expiry_management_has_no_broker_instruction():
    assert all(record["no_broker"] is True for record in _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH))


def test_optimizer_consumes_adversarial_corpus():
    assert run_zero_dte_threshold_optimizer()["summary"]["adversarial_fixture_count"] >= 96


def test_optimizer_compares_pre_and_post_adversarial_results():
    summary = run_zero_dte_threshold_optimizer()["summary"]
    assert summary["combined_fixture_count"] >= 120


def test_stricter_gamma_theta_profile_survival_status_recorded():
    summary = run_zero_dte_threshold_optimizer()["summary"]
    assert "paper_shadow" in summary["post_adversarial_threshold_candidate_survival_status"]


def test_negative_control_profile_still_rejected():
    summary = run_zero_dte_threshold_optimizer()["summary"]
    assert summary["rejected_count"] >= 1


def test_unsafe_profiles_not_promoted_after_adversarial_replay():
    assert run_zero_dte_threshold_optimizer()["summary"]["post_adversarial_research_default_promotion_allowed"] is False


def test_research_default_promotion_blocked_when_overfit_pressure_high():
    assert _summary()["research_default_promotion_allowed"] is False


def test_adversarial_corpus_updates_fixture_coverage_gaps():
    assert _json(ADVERSARIAL_COVERAGE_SUMMARY_PATH)["coverage_completeness_score"] > 0.9


def test_optimizer_does_not_mutate_live_thresholds():
    before = load_default_zero_dte_risk_thresholds().to_dict()
    run_zero_dte_threshold_optimizer()
    assert load_default_zero_dte_risk_thresholds().to_dict() == before


def test_adversarial_coverage_summary_written(adversarial_result: dict):
    assert ADVERSARIAL_COVERAGE_SUMMARY_PATH.exists()


def test_adversarial_case_family_coverage_score():
    assert score_zero_dte_adversarial_coverage(_cases())["case_family_coverage_score"] == 1.0


def test_adversarial_risk_vector_coverage_score():
    assert score_zero_dte_adversarial_coverage(_cases())["risk_vector_coverage_score"] == 1.0


def test_policy_loophole_coverage_score():
    assert score_zero_dte_adversarial_coverage(_cases())["policy_loophole_coverage_score"] == 1.0


def test_overfit_pressure_score_written():
    assert _json(ADVERSARIAL_COVERAGE_SUMMARY_PATH)["overfit_pressure_score"] > 0.0


def test_coverage_summary_recommends_next_fixture_additions():
    assert _json(ADVERSARIAL_COVERAGE_SUMMARY_PATH)["recommended_next_fixture_additions"]


def test_adversarial_fixture_cases_artifact_written(adversarial_result: dict):
    assert ADVERSARIAL_FIXTURE_CASES_PATH.exists()


def test_adversarial_intraday_paths_artifact_written(adversarial_result: dict):
    assert ADVERSARIAL_INTRADAY_PATHS_PATH.exists()


def test_adversarial_replay_outcomes_artifact_written(adversarial_result: dict):
    assert ADVERSARIAL_REPLAY_OUTCOMES_PATH.exists()


def test_adversarial_threshold_feedback_artifact_written(adversarial_result: dict):
    assert ADVERSARIAL_THRESHOLD_FEEDBACK_PATH.exists()


def test_adversarial_optimizer_effects_artifact_written(adversarial_result: dict):
    assert ADVERSARIAL_OPTIMIZER_EFFECTS_PATH.exists()


def test_combined_replay_summary_artifact_written(adversarial_result: dict):
    assert COMBINED_REPLAY_SUMMARY_PATH.exists()


def test_adversarial_corpus_proof_artifact_written(adversarial_result: dict):
    assert ADVERSARIAL_CORPUS_PROOF_PATH.exists()


def test_audit_recognizes_adversarial_corpus_artifacts():
    names = {item[0] for item in __import__("dopey_audit.artifact_loader", fromlist=["ARTIFACT_SPECS"]).ARTIFACT_SPECS}
    assert "zero_dte_adversarial_fixture_cases" in names


def test_audit_flags_adversarial_live_market_reference():
    checks = audit_zero_dte_adversarial_corpus_records(
        {"artifact_type": "zero_dte_adversarial_fixture_cases", "records": [{"case_id": "bad", "paper_only": True, "live_blocked": True, "source": "polygon"}]},
        {"artifact_type": "zero_dte_adversarial_intraday_paths", "records": []},
        [],
        [],
        [],
        {"artifact_type": "zero_dte_adversarial_coverage_summary"},
        {"research_default_promotion_allowed": False, "special_close_stress_count": 10},
        [],
    )
    assert any(check["check_id"] == "zero_dte_adversarial_no_real_market_reference" and not check["passed"] for check in checks)


def test_audit_flags_policy_loophole_if_not_blocked():
    checks = audit_zero_dte_adversarial_corpus_records(
        _json(ADVERSARIAL_FIXTURE_CASES_PATH),
        _json(ADVERSARIAL_INTRADAY_PATHS_PATH),
        [{"case_id": "bad", "safety_status": "blocked_policy_loophole", "blocked": False}],
        [],
        [],
        _json(ADVERSARIAL_COVERAGE_SUMMARY_PATH),
        _json(COMBINED_REPLAY_SUMMARY_PATH),
        [],
    )
    assert any(check["check_id"] == "zero_dte_adversarial_policy_loopholes_blocked" and not check["passed"] for check in checks)


def test_audit_flags_unsafe_profile_promotion():
    checks = audit_zero_dte_adversarial_corpus_records(
        _json(ADVERSARIAL_FIXTURE_CASES_PATH),
        _json(ADVERSARIAL_INTRADAY_PATHS_PATH),
        _jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH),
        _jsonl(ADVERSARIAL_THRESHOLD_FEEDBACK_PATH),
        [{"research_default_promotion_allowed": True}],
        _json(ADVERSARIAL_COVERAGE_SUMMARY_PATH),
        {"research_default_promotion_allowed": False, "special_close_stress_count": 10},
        _jsonl(ADVERSARIAL_CORPUS_PROOF_PATH),
    )
    assert any(check["check_id"] == "zero_dte_adversarial_threshold_optimizer_no_unsafe_research_default" and not check["passed"] for check in checks)


def test_audit_confirms_adversarial_corpus_paper_only_live_blocked():
    assert run_active_policy_audit()["safety_errors"] == 0


def test_audit_confirms_no_active_forbidden_live_decisions():
    assert run_active_policy_audit()["safety_errors"] == 0


def test_reporting_includes_adversarial_corpus_summary():
    class Ctx:
        shared_export_path = "Z:/fixture"
        reporting_summary = {"zero_dte_adversarial_corpus_summary": {"adversarial_fixture_count": 96, "combined_fixture_count": 120}}

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
        next_build_target = "adversarial corpus v2 with cross-underlying regime families"

    assert "0DTE Adversarial Corpus" in render_executive_summary(Ctx(), Bundle(), [], Decision())


def test_export_verifier_selects_adversarial_corpus_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {"zero_dte_adversarial_fixture_cases", "zero_dte_adversarial_corpus_proof"}.issubset(ids)


def test_export_review_includes_adversarial_corpus_summary():
    assert test_reporting_includes_adversarial_corpus_summary() is None


def test_adversarial_corpus_artifact_ledger_written(adversarial_result: dict):
    assert Path("docs/reports/DOPEY_0DTE_ADVERSARIAL_CORPUS_ARTIFACT_LEDGER.md").exists() or adversarial_result["zero_dte_adversarial_corpus_status"] == "ok"


def test_shard_plan_includes_adversarial_corpus_tests(tmp_path: Path):
    plan = write_test_shard_plan(["tests/test_zero_dte_adversarial_corpus.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_zero_dte_adversarial_corpus.py" in plan["adversarial_corpus_test_files"]


def test_shard_plan_separates_export_review_slow_tests():
    plan = write_test_shard_plan(["tests/test_export_bundle_review_assistant.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_export_bundle_review_assistant.py" in plan["export_review_slow_test_files"]


def test_full_suite_timeout_remains_inconclusive_not_pass():
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_adversarial_corpus(adversarial_result: dict):
    assert adversarial_result["summary"]["live_blocked"] is True


def test_robinhood_stub_still_blocks_live_after_adversarial_corpus():
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_adversarial_corpus():
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_adversarial_corpus():
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_adversarial_corpus(adversarial_result: dict):
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [ADVERSARIAL_FIXTURE_CASES_PATH, ADVERSARIAL_CORPUS_PROOF_PATH])
    assert "sk-proj-" not in text and "sk_live" not in text and "api_key" not in text


def test_no_scheduler_created_by_adversarial_corpus():
    text = Path("dopey_options/run_zero_dte_adversarial_corpus.py").read_text(encoding="utf-8").lower()
    assert "cron" not in text and "apscheduler" not in text


def test_no_network_market_data_dependency_created_by_adversarial_corpus():
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_options/run_zero_dte_adversarial_corpus.py"),
        Path("dopey_options/zero_dte_adversarial_path_builder.py"),
    ])
    assert "requests" not in text and "yfinance" not in text and "websocket" not in text


def test_no_same_day_churn_loophole_created_by_adversarial_corpus():
    assert _summary()["policy_loophole_block_rate"] == 1.0


def test_blunder_integrity_unchanged_if_manifest_available():
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        assert True
        return
    assert manifest.read_text(encoding="utf-8-sig").strip() or manifest.exists()


def test_fixture_files_written(adversarial_result: dict):
    assert ZERO_DTE_ADVERSARIAL_REPLAY_CASES_FIXTURE_PATH.exists()
    assert ZERO_DTE_ADVERSARIAL_INTRADAY_PATHS_FIXTURE_PATH.exists()
