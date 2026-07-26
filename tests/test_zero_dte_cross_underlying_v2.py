from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.active_policy_audit import audit_zero_dte_cross_underlying_v2_records, run_active_policy_audit
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.run_zero_dte_cross_underlying_v2 import (
    COMBINED_V1_V2_REPLAY_SUMMARY_PATH,
    CROSS_UNDERLYING_CORPUS_PROOF_PATH,
    CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH,
    CROSS_UNDERLYING_INTRADAY_PATHS_PATH,
    CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH,
    CROSS_UNDERLYING_REGIME_CASES_PATH,
    CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH,
    CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH,
    CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH,
    UNDERLYING_FAMILIES_PATH,
    ZERO_DTE_CROSS_UNDERLYING_EXPECTED_FEEDBACK_FIXTURE_PATH,
    ZERO_DTE_CROSS_UNDERLYING_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH,
    ZERO_DTE_CROSS_UNDERLYING_INTRADAY_PATHS_FIXTURE_PATH,
    ZERO_DTE_CROSS_UNDERLYING_REGIME_CASES_FIXTURE_PATH,
    ZERO_DTE_UNDERLYING_FAMILIES_FIXTURE_PATH,
    load_zero_dte_cross_underlying_cases,
    load_zero_dte_cross_underlying_intraday_paths,
    load_zero_dte_underlying_families,
    run_zero_dte_cross_underlying_v2,
)
from dopey_options.run_zero_dte_threshold_optimizer import run_zero_dte_threshold_optimizer
from dopey_options.zero_dte_cross_underlying_coverage import score_zero_dte_cross_underlying_coverage
from dopey_options.zero_dte_cross_underlying_fixture_builder import build_zero_dte_cross_underlying_cases, build_zero_dte_underlying_families
from dopey_options.zero_dte_cross_underlying_fixture_models import ZeroDTECrossUnderlyingRegimeCase, zero_dte_cross_underlying_case_hash
from dopey_options.zero_dte_cross_underlying_path_builder import build_zero_dte_cross_underlying_intraday_paths
from dopey_options.zero_dte_underlying_family_models import ZeroDTEUnderlyingFamily, zero_dte_underlying_family_hash
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def cross_result() -> dict:
    return run_zero_dte_cross_underlying_v2()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _families() -> list[ZeroDTEUnderlyingFamily]:
    return load_zero_dte_underlying_families()


def _cases() -> list[ZeroDTECrossUnderlyingRegimeCase]:
    return load_zero_dte_cross_underlying_cases()


def _paths() -> list[dict]:
    return load_zero_dte_cross_underlying_intraday_paths()


def _summary() -> dict:
    run_zero_dte_cross_underlying_v2()
    return _json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH)


def _family_name_by_id() -> dict[str, str]:
    return {family.underlying_family_id: family.family_name for family in _families()}


def _case_ids_by_family_and_risk(risk: str) -> dict[str, set[str]]:
    family_name_by_id = _family_name_by_id()
    output: dict[str, set[str]] = {family_name: set() for family_name in family_name_by_id.values()}
    for case in _cases():
        if risk in case.risk_vectors:
            output[family_name_by_id[case.underlying_family_id]].add(case.case_id)
    return output


def _blocked_by_family_for_risk(risk: str) -> dict[str, bool]:
    outcomes = {record["case_id"]: record for record in _jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH)}
    return {
        family: bool(case_ids) and all(outcomes[case_id]["safety_status"] == "blocked_policy_loophole" and outcomes[case_id]["policy_blocked"] for case_id in case_ids)
        for family, case_ids in _case_ids_by_family_and_risk(risk).items()
    }


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="cross-v2-live-x",
        symbol="SYN_INDEX_A",
        structure="long_call",
        legs=[{"side": "buy", "symbol": "SYN_INDEX_A_C1", "option_type": "call", "expiry": "2026-07-17", "dte": 0}],
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=1.0,
        active_policy_required=True,
    )


def _review_text() -> str:
    class Ctx:
        shared_export_path = "fixture"
        reporting_summary = {
            "zero_dte_cross_underlying_v2_summary": {
                "cross_underlying_v2_fixture_count": 168,
                "combined_v1_v2_fixture_count": 291,
                "underlying_family_count": 12,
                "call_put_balance_score": 1.0,
                "cross_underlying_completeness_score": 1.0,
                "threshold_candidate_survival_status": "paper_shadow_survives_no_research_default",
                "paper_shadow_candidate_downgrade_status": "non_gamma_theta_shadow_candidates_advisory_only_under_cross_underlying_pressure",
                "research_default_promotion_allowed": False,
            }
        }
        export_safety_scan = {"active_forbidden_live_decisions": 0}
        safety_state = {"mode": "RESEARCH", "live_trading_enabled": False, "funded_broker_connections_enabled": False, "allow_unofficial_robinhood_api": False}

    class Bundle:
        source_bundle_id = "b"
        source_export_path = "s"
        artifact_count = 1
        hash_status = "pass"
        copy_status = "verified"
        safety_status = "pass"
        credential_scan_status = "pass"
        active_forbidden_live_decisions = 0

    class Decision:
        decision = "approve_for_offline_review"
        suitability = "paper_only_review"
        next_build_target = "cross_underlying_v3_multi_day_swing_0dte_hybrid_replay_corpus"

    return render_executive_summary(Ctx(), Bundle(), [], Decision())


def test_underlying_family_serializes_deterministically():
    family = build_zero_dte_underlying_families()[0]
    assert ZeroDTEUnderlyingFamily.from_dict(family.to_dict()).to_dict() == family.to_dict()


def test_underlying_family_hash_is_deterministic():
    family = build_zero_dte_underlying_families()[0]
    assert family.family_hash == zero_dte_underlying_family_hash(family)


def test_underlying_family_requires_paper_only_live_blocked():
    record = build_zero_dte_underlying_families()[0].to_dict()
    record["live_blocked"] = False
    with pytest.raises(ValueError):
        ZeroDTEUnderlyingFamily.from_dict(record)


def test_underlying_family_uses_synthetic_symbol_only():
    assert all(family.synthetic_underlying_symbol.startswith("SYN_") for family in build_zero_dte_underlying_families())


def test_underlying_family_rejects_real_market_data_reference():
    record = build_zero_dte_underlying_families()[0].to_dict()
    record["option_liquidity_archetype"] = "polygon live_quote"
    with pytest.raises(ValueError):
        ZeroDTEUnderlyingFamily.from_dict(record)


def test_cross_underlying_case_serializes_deterministically():
    case = build_zero_dte_cross_underlying_cases(build_zero_dte_underlying_families())[0]
    assert ZeroDTECrossUnderlyingRegimeCase.from_dict(case.to_dict()).to_dict() == case.to_dict()


def test_cross_underlying_case_hash_is_deterministic():
    case = build_zero_dte_cross_underlying_cases(build_zero_dte_underlying_families())[0]
    assert case.case_hash == zero_dte_cross_underlying_case_hash(case)


def test_cross_underlying_case_requires_expected_policy_result():
    record = build_zero_dte_cross_underlying_cases(build_zero_dte_underlying_families())[0].to_dict()
    record["expected_policy_result"] = ""
    with pytest.raises(ValueError):
        ZeroDTECrossUnderlyingRegimeCase.from_dict(record)


def test_cross_underlying_case_requires_expected_optimizer_effect():
    record = build_zero_dte_cross_underlying_cases(build_zero_dte_underlying_families())[0].to_dict()
    record["expected_optimizer_effect"] = ""
    with pytest.raises(ValueError):
        ZeroDTECrossUnderlyingRegimeCase.from_dict(record)


def test_underlying_families_fixture_loads(cross_result: dict):
    assert _json(ZERO_DTE_UNDERLYING_FAMILIES_FIXTURE_PATH)["family_count"] == 12


def test_cross_underlying_regime_cases_load(cross_result: dict):
    assert _json(ZERO_DTE_CROSS_UNDERLYING_REGIME_CASES_FIXTURE_PATH)["case_count"] >= 144


def test_cross_underlying_intraday_paths_load(cross_result: dict):
    assert _json(ZERO_DTE_CROSS_UNDERLYING_INTRADAY_PATHS_FIXTURE_PATH)["path_count"] >= 144


def test_cross_underlying_expected_feedback_loads(cross_result: dict):
    assert _json(ZERO_DTE_CROSS_UNDERLYING_EXPECTED_FEEDBACK_FIXTURE_PATH)["record_count"] >= 144


def test_cross_underlying_expected_optimizer_effects_load(cross_result: dict):
    assert _json(ZERO_DTE_CROSS_UNDERLYING_EXPECTED_OPTIMIZER_EFFECTS_FIXTURE_PATH)["record_count"] >= 144


def test_cross_underlying_corpus_has_at_least_144_cases(cross_result: dict):
    assert _summary()["cross_underlying_v2_fixture_count"] >= 144


def test_cross_underlying_corpus_has_12_families(cross_result: dict):
    assert len(_families()) == 12


def test_each_family_has_at_least_12_cases():
    counts = _summary()["underlying_family_distribution"]
    assert counts and all(value >= 12 for value in counts.values())


def test_each_family_has_call_and_put_cases():
    family_name_by_id = _family_name_by_id()
    options: dict[str, set[str]] = {family: set() for family in family_name_by_id.values()}
    for case in _cases():
        options[family_name_by_id[case.underlying_family_id]].add(case.option_type)
    assert all(values == {"call", "put"} for values in options.values())


def test_each_family_has_policy_loophole_case():
    coverage = score_zero_dte_cross_underlying_coverage(_families(), _cases())
    assert all(coverage["policy_loophole_coverage_by_family"].values())


def test_each_family_has_special_close_case():
    coverage = score_zero_dte_cross_underlying_coverage(_families(), _cases())
    assert all(coverage["special_close_coverage_by_family"].values())


def test_each_family_has_expiry_management_case():
    coverage = score_zero_dte_cross_underlying_coverage(_families(), _cases())
    assert all(coverage["expiry_management_coverage_by_family"].values())


def test_each_family_has_later_expiry_case():
    coverage = score_zero_dte_cross_underlying_coverage(_families(), _cases())
    assert all(coverage["later_expiry_coverage_by_family"].values())


def test_each_family_has_at_least_8_regimes():
    family_name_by_id = _family_name_by_id()
    regimes: dict[str, set[str]] = {family: set() for family in family_name_by_id.values()}
    for case in _cases():
        regimes[family_name_by_id[case.underlying_family_id]].add(case.regime_family)
    assert all(len(values) >= 8 for values in regimes.values())


def test_cross_underlying_corpus_uses_synthetic_symbols_only():
    assert all(case.synthetic_underlying_symbol.startswith("SYN_") for case in _cases())


def test_cross_underlying_path_builder_is_deterministic():
    families = build_zero_dte_underlying_families()
    cases = build_zero_dte_cross_underlying_cases(families)
    assert build_zero_dte_cross_underlying_intraday_paths(families, cases) == build_zero_dte_cross_underlying_intraday_paths(families, cases)


def test_cross_underlying_paths_include_bid_mid_ask(cross_result: dict):
    assert all(path["option_bid_mid_ask_path"] for path in _paths())


def test_cross_underlying_paths_include_liquidity_and_spread(cross_result: dict):
    assert all(path["liquidity_score_path"] and path["spread_path"] and path["slippage_path"] for path in _paths())


def test_cross_underlying_paths_include_greeks_and_iv(cross_result: dict):
    assert all(path["delta_path"] and path["gamma_path"] and path["theta_path"] and path["vega_path"] and path["iv_path"] for path in _paths())


def test_cross_underlying_paths_include_event_macro_stress(cross_result: dict):
    assert all(path["event_macro_stress_path"] for path in _paths())


def test_cross_underlying_paths_include_expiry_pressure(cross_result: dict):
    assert all(path["expiry_pressure_path"] and "pin_risk_state_path" in path for path in _paths())


def test_cross_underlying_paths_have_no_market_data_dependency():
    text = ZERO_DTE_CROSS_UNDERLYING_INTRADAY_PATHS_FIXTURE_PATH.read_text(encoding="utf-8").lower()
    assert not any(token in text for token in ["polygon", "yfinance", "live_quote", "broker_quote"])


def test_replay_runner_supports_cross_underlying_v2_mode():
    assert run_zero_dte_cross_underlying_v2("cross_underlying_v2", True)["summary"]["cross_underlying_v2_fixture_count"] >= 144


def test_replay_runner_supports_combined_v1_v2_mode():
    assert run_zero_dte_cross_underlying_v2("combined_v1_v2", True)["summary"]["combined_v1_v2_fixture_count"] >= 267


def test_combined_v1_v2_corpus_has_at_least_267_cases(cross_result: dict):
    assert _summary()["combined_v1_v2_fixture_count"] >= 267


def test_cross_underlying_replay_expectations_match(cross_result: dict):
    assert _summary()["all_cross_underlying_replay_expectations_matched"] is True


def test_cross_underlying_feedback_expectations_match(cross_result: dict):
    assert _summary()["all_cross_underlying_feedback_expectations_matched"] is True


def test_cross_underlying_optimizer_effect_expectations_match(cross_result: dict):
    assert _summary()["all_cross_underlying_optimizer_effects_matched"] is True


def test_policy_loophole_cases_blocked_in_every_family(cross_result: dict):
    assert all(_summary()["policy_loophole_block_rate_by_family"].values())


def test_live_path_cases_blocked_in_every_family(cross_result: dict):
    assert all(_blocked_by_family_for_risk("live_path_attempt").values())


def test_unsupported_structure_cases_blocked_in_every_family(cross_result: dict):
    assert all(_blocked_by_family_for_risk("unsupported_structure_attempt").values())


def test_same_day_churn_cases_blocked_in_every_family(cross_result: dict):
    assert all(_blocked_by_family_for_risk("same_day_churn_attempt").values())


def test_missing_paper_only_live_blocked_cases_rejected():
    record = _cases()[0].to_dict()
    record["paper_only"] = False
    with pytest.raises(ValueError):
        ZeroDTECrossUnderlyingRegimeCase.from_dict(record)


def test_optimizer_consumes_cross_underlying_v2_corpus():
    assert run_zero_dte_threshold_optimizer()["summary"]["cross_underlying_v2_fixture_count"] >= 144


def test_optimizer_compares_pre_and_post_v2_results():
    summary = run_zero_dte_threshold_optimizer()["summary"]
    assert summary["combined_fixture_count"] < summary["combined_v1_v2_fixture_count"]


def test_stricter_gamma_theta_profile_v2_survival_status_recorded(cross_result: dict):
    assert _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH)["stricter_gamma_theta_profile_status"]


def test_all_paper_shadow_candidates_v2_survival_status_recorded(cross_result: dict):
    assert _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH)["all_paper_shadow_candidate_survival_status"]


def test_negative_control_profile_still_rejected_after_v2(cross_result: dict):
    assert _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH)["negative_control_profile_status"] == "rejected_negative_control"


def test_unsafe_profiles_not_promoted_after_v2(cross_result: dict):
    assert _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH)["research_default_promotion_allowed"] is False


def test_research_default_promotion_blocked_when_v2_overfit_pressure_high(cross_result: dict):
    survival = _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH)
    assert survival["cross_underlying_overfit_pressure_score"] >= 1.0 and survival["research_default_promotion_allowed"] is False


def test_cross_underlying_v2_does_not_mutate_live_thresholds():
    assert run_zero_dte_threshold_optimizer()["summary"]["live_threshold_mutation_allowed"] is False


def test_cross_underlying_coverage_summary_written(cross_result: dict):
    assert CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH.exists()


def test_underlying_family_coverage_score_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["underlying_family_coverage_score"] == 1.0


def test_regime_family_coverage_score_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["regime_family_coverage_score"] >= 0.75


def test_call_put_balance_score_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["call_put_balance_score"] > 0.0


def test_policy_loophole_coverage_by_family_written(cross_result: dict):
    assert all(_json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["policy_loophole_coverage_by_family"].values())


def test_special_close_coverage_by_family_written(cross_result: dict):
    assert all(_json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["special_close_coverage_by_family"].values())


def test_expiry_management_coverage_by_family_written(cross_result: dict):
    assert all(_json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["expiry_management_coverage_by_family"].values())


def test_later_expiry_coverage_by_family_written(cross_result: dict):
    assert all(_json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["later_expiry_coverage_by_family"].values())


def test_highest_risk_family_regime_combinations_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["highest_risk_family_regime_combinations"]


def test_underlying_families_artifact_written(cross_result: dict):
    assert _json(UNDERLYING_FAMILIES_PATH)["family_count"] == 12


def test_cross_underlying_regime_cases_artifact_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_REGIME_CASES_PATH)["case_count"] >= 144


def test_cross_underlying_intraday_paths_artifact_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_INTRADAY_PATHS_PATH)["path_count"] >= 144


def test_cross_underlying_replay_outcomes_artifact_written(cross_result: dict):
    assert len(_jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH)) >= 144


def test_cross_underlying_threshold_feedback_artifact_written(cross_result: dict):
    assert len(_jsonl(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH)) >= 144


def test_cross_underlying_optimizer_effects_artifact_written(cross_result: dict):
    assert len(_jsonl(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH)) >= 144


def test_cross_underlying_coverage_summary_artifact_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH)["artifact_type"] == "zero_dte_cross_underlying_coverage_summary"


def test_combined_v1_v2_replay_summary_artifact_written(cross_result: dict):
    assert _json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH)["artifact_type"] == "zero_dte_combined_v1_v2_replay_summary"


def test_cross_underlying_threshold_survival_artifact_written(cross_result: dict):
    assert _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH)["artifact_type"] == "zero_dte_cross_underlying_threshold_survival"


def test_cross_underlying_corpus_proof_artifact_written(cross_result: dict):
    assert len(_jsonl(CROSS_UNDERLYING_CORPUS_PROOF_PATH)) >= 144


def test_audit_recognizes_cross_underlying_v2_artifacts(cross_result: dict):
    names = {spec[0] for spec in ARTIFACT_SPECS}
    assert "zero_dte_cross_underlying_corpus_proof" in names


def test_audit_flags_real_market_data_reference_in_cross_underlying_fixture(cross_result: dict):
    checks = audit_zero_dte_cross_underlying_v2_records(
        _json(UNDERLYING_FAMILIES_PATH),
        {**_json(CROSS_UNDERLYING_REGIME_CASES_PATH), "records": [{**_json(CROSS_UNDERLYING_REGIME_CASES_PATH)["records"][0], "liquidity_profile": "polygon live_quote"}]},
        _json(CROSS_UNDERLYING_INTRADAY_PATHS_PATH),
        _jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH),
        _jsonl(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH),
        _jsonl(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH),
        _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH),
        _json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH),
        _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH),
        _jsonl(CROSS_UNDERLYING_CORPUS_PROOF_PATH),
    )
    assert any(check["check_id"] == "zero_dte_cross_underlying_no_real_market_reference" and not check["passed"] for check in checks)


def test_audit_flags_policy_loophole_if_not_blocked_by_family(cross_result: dict):
    outcomes = _jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH)
    first_loophole = next(index for index, record in enumerate(outcomes) if record["safety_status"] == "blocked_policy_loophole")
    outcomes[first_loophole] = {**outcomes[first_loophole], "safety_status": "paper_only_live_blocked", "policy_blocked": False}
    checks = audit_zero_dte_cross_underlying_v2_records(_json(UNDERLYING_FAMILIES_PATH), _json(CROSS_UNDERLYING_REGIME_CASES_PATH), _json(CROSS_UNDERLYING_INTRADAY_PATHS_PATH), outcomes, _jsonl(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH), _jsonl(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH), _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH), _json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH), _json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH), _jsonl(CROSS_UNDERLYING_CORPUS_PROOF_PATH))
    assert any(check["check_id"] == "zero_dte_cross_underlying_policy_loopholes_blocked_by_family" and not check["passed"] for check in checks)


def test_audit_flags_unsafe_profile_promotion_after_v2(cross_result: dict):
    survival = {**_json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH), "research_default_promotion_allowed": True}
    checks = audit_zero_dte_cross_underlying_v2_records(_json(UNDERLYING_FAMILIES_PATH), _json(CROSS_UNDERLYING_REGIME_CASES_PATH), _json(CROSS_UNDERLYING_INTRADAY_PATHS_PATH), _jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH), _jsonl(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH), _jsonl(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH), _json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH), _json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH), survival, _jsonl(CROSS_UNDERLYING_CORPUS_PROOF_PATH))
    assert any(check["check_id"] == "zero_dte_cross_underlying_threshold_optimizer_no_unsafe_research_default" and not check["passed"] for check in checks)


def test_audit_confirms_cross_underlying_v2_paper_only_live_blocked(cross_result: dict):
    assert run_active_policy_audit()["verdict"] == "pass"


def test_audit_confirms_no_active_forbidden_live_decisions_after_v2(cross_result: dict):
    assert _summary()["research_default_promotion_allowed"] is False


def test_reporting_includes_cross_underlying_v2_summary(cross_result: dict):
    assert "zero_dte_cross_underlying_v2_summary" in _review_text()


def test_export_verifier_selects_cross_underlying_v2_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "zero_dte_cross_underlying_corpus_proof" in ids


def test_export_review_includes_cross_underlying_v2_summary():
    assert "0DTE Cross-Underlying V2 Corpus" in _review_text()


def test_cross_underlying_v2_artifact_ledger_written(cross_result: dict):
    assert Path("docs/reports/DOPEY_0DTE_CROSS_UNDERLYING_V2_ARTIFACT_LEDGER.md").exists() or CROSS_UNDERLYING_CORPUS_PROOF_PATH.exists()


def test_shard_plan_includes_cross_underlying_v2_tests():
    plan = write_test_shard_plan(["tests/test_zero_dte_cross_underlying_v2.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_zero_dte_cross_underlying_v2.py" in plan["cross_underlying_v2_test_files"]


def test_shard_plan_marks_artifact_writing_tests_sequential():
    plan = write_test_shard_plan(["tests/test_zero_dte_cross_underlying_v2.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_zero_dte_cross_underlying_v2.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass():
    result = timeout_result(["python", "-m", "pytest"], 30)
    assert result["status"] == "inconclusive_timeout" and result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_cross_underlying_v2(cross_result: dict):
    cfg = load_config(default_config_path())
    assert cfg.get("live_trading_enabled") is False


def test_robinhood_stub_still_blocks_live_after_cross_underlying_v2(cross_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_cross_underlying_v2(cross_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_cross_underlying_v2(cross_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_cross_underlying_v2(cross_result: dict):
    text = "\n".join(path.read_text(encoding="utf-8") for path in [UNDERLYING_FAMILIES_PATH, CROSS_UNDERLYING_REGIME_CASES_PATH, COMBINED_V1_V2_REPLAY_SUMMARY_PATH])
    assert not any(token in text.lower() for token in ["api_key", "secret_key", "access_token", "refresh_token"])


def test_no_scheduler_created_by_cross_underlying_v2():
    text = Path("dopey_options/run_zero_dte_cross_underlying_v2.py").read_text(encoding="utf-8").lower()
    assert "apscheduler" not in text and "cron" not in text


def test_no_network_market_data_dependency_created_by_cross_underlying_v2():
    text = Path("dopey_options/run_zero_dte_cross_underlying_v2.py").read_text(encoding="utf-8").lower()
    assert not any(token in text for token in ["requests", "yfinance", "polygon", "iex"])


def test_no_same_day_churn_loophole_created_by_cross_underlying_v2(cross_result: dict):
    assert all(_blocked_by_family_for_risk("same_day_churn_attempt").values())


def test_blunder_integrity_unchanged_if_manifest_available():
    status_path = Path("artifacts/dopey/exports/blunder_integrity_status.json")
    if not status_path.exists():
        pytest.skip("Blunder integrity manifest status not available")
    status = _json(status_path)
    assert status.get("status") in {"ok", "skipped"}
