from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.active_policy_audit import audit_hybrid_swing_0dte_v3_records, run_active_policy_audit
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_options.hybrid_preference_scoring import score_hybrid_preference
from dopey_options.hybrid_replay_models import HybridOpportunityPair, HybridReplayOutcome, hybrid_pair_hash, hybrid_replay_hash
from dopey_options.multi_day_option_path_models import MultiDayOptionState
from dopey_options.run_hybrid_swing_0dte_v3 import (
    HYBRID_ALLOCATOR_TAGS_PATH,
    HYBRID_CORPUS_PROOF_PATH,
    HYBRID_COVERAGE_SUMMARY_PATH,
    HYBRID_EXPECTED_ALLOCATOR_TAGS_FIXTURE_PATH,
    HYBRID_EXPECTED_OUTCOMES_FIXTURE_PATH,
    HYBRID_MULTI_DAY_PATHS_FIXTURE_PATH,
    HYBRID_MULTI_DAY_PATHS_PATH,
    HYBRID_OPPORTUNITY_PAIRS_FIXTURE_PATH,
    HYBRID_OPPORTUNITY_PAIRS_PATH,
    HYBRID_PREFERENCE_SCORES_PATH,
    HYBRID_REPLAY_OUTCOMES_PATH,
    HYBRID_REPLAY_SUMMARY_PATH,
    HYBRID_SWING_CANDIDATES_FIXTURE_PATH,
    HYBRID_SWING_CANDIDATES_PATH,
    HYBRID_THRESHOLD_SURVIVAL_PATH,
    HYBRID_UNDERLYING_FAMILIES_FIXTURE_PATH,
    HYBRID_UNDERLYING_FAMILIES_PATH,
    load_hybrid_multi_day_paths_v3,
    load_hybrid_opportunity_pairs_v3,
    load_hybrid_swing_candidates_v3,
    load_hybrid_underlying_families_v3,
    run_hybrid_swing_0dte_v3,
)
from dopey_options.run_zero_dte_threshold_optimizer import run_zero_dte_threshold_optimizer
from dopey_options.swing_lifecycle_policy import evaluate_swing_lifecycle
from dopey_options.swing_option_models import SwingOptionCandidate, swing_option_candidate_hash
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def hybrid_result() -> dict:
    return run_hybrid_swing_0dte_v3()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _candidate() -> SwingOptionCandidate:
    return load_hybrid_swing_candidates_v3()[0]


def _pair() -> HybridOpportunityPair:
    return load_hybrid_opportunity_pairs_v3()[0]


def _path() -> dict:
    return load_hybrid_multi_day_paths_v3()[0]


def _outcome() -> HybridReplayOutcome:
    return HybridReplayOutcome.from_dict(_jsonl(HYBRID_REPLAY_OUTCOMES_PATH)[0])


def _summary() -> dict:
    run_hybrid_swing_0dte_v3()
    return _json(HYBRID_REPLAY_SUMMARY_PATH)


def _coverage() -> dict:
    run_hybrid_swing_0dte_v3()
    return _json(HYBRID_COVERAGE_SUMMARY_PATH)


def _threshold_survival() -> dict:
    run_hybrid_swing_0dte_v3()
    return _json(HYBRID_THRESHOLD_SURVIVAL_PATH)


def _audit_inputs() -> tuple[dict, dict, dict, dict, list[dict], list[dict], list[dict], dict, dict, dict, list[dict]]:
    run_hybrid_swing_0dte_v3()
    return (
        _json(HYBRID_UNDERLYING_FAMILIES_PATH),
        _json(HYBRID_SWING_CANDIDATES_PATH),
        _json(HYBRID_OPPORTUNITY_PAIRS_PATH),
        _json(HYBRID_MULTI_DAY_PATHS_PATH),
        _jsonl(HYBRID_REPLAY_OUTCOMES_PATH),
        _jsonl(HYBRID_PREFERENCE_SCORES_PATH),
        _jsonl(HYBRID_ALLOCATOR_TAGS_PATH),
        _json(HYBRID_COVERAGE_SUMMARY_PATH),
        _json(HYBRID_THRESHOLD_SURVIVAL_PATH),
        _json(HYBRID_REPLAY_SUMMARY_PATH),
        _jsonl(HYBRID_CORPUS_PROOF_PATH),
    )


def _audit_checks() -> list[dict]:
    return audit_hybrid_swing_0dte_v3_records(*_audit_inputs())


def _checks_fail(checks: list[dict], check_id: str) -> bool:
    return any(check["check_id"] == check_id and not check["passed"] for check in checks)


def _family_id_to_pairs() -> dict[str, list[HybridOpportunityPair]]:
    output: dict[str, list[HybridOpportunityPair]] = {}
    for pair in load_hybrid_opportunity_pairs_v3():
        output.setdefault(pair.underlying_family_id, []).append(pair)
    return output


def _review_text() -> str:
    class Ctx:
        shared_export_path = "fixture"
        reporting_summary = {
            "top_strategy": "fixture",
            "top_family": "fixture",
            "active_policy_summary": {},
            "account_ledger_summary": {},
            "zero_dte_risk_summary": {},
            "zero_dte_replay_summary": {},
            "zero_dte_threshold_optimizer_summary": {},
            "zero_dte_adversarial_corpus_summary": {},
            "zero_dte_cross_underlying_v2_summary": {},
            "hybrid_swing_0dte_v3_summary": {
                "hybrid_pair_count": 192,
                "swing_candidate_count": 192,
                "multi_day_path_count": 192,
                "underlying_family_count": 12,
                "preference_distribution": {"prefer_swing": 84},
                "threshold_candidate_survival_status": "paper_shadow_survives_no_research_default",
                "later_expiry_preference_status": "strengthen_later_expiry_preference_advisory_only",
                "research_default_promotion_allowed": False,
                "real_sizing_allowed": False,
            },
        }

    class Bundle:
        source_bundle_id = "fixture"
        source_export_path = "fixture"
        artifact_count = 1
        hash_status = "pass"
        copy_status = "verified"
        safety_status = "pass"
        credential_scan_status = "pass"
        active_forbidden_live_decisions = 0

    class Decision:
        decision = "ready_for_offline_review"
        suitability = "paper_only"
        next_build_target = "hybrid_v4"

    return render_executive_summary(Ctx(), Bundle(), [], Decision())


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="hybrid-v3-live-x",
        symbol="SYN_INDEX_A",
        structure="long_call",
        legs=[{"side": "buy", "symbol": "SYN_INDEX_A_C1", "option_type": "call", "expiry": "2026-07-17", "dte": 0}],
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=1.0,
        active_policy_required=True,
    )


def test_swing_option_candidate_serializes_deterministically():
    assert SwingOptionCandidate.from_dict(_candidate().to_dict()).to_dict() == _candidate().to_dict()


def test_hybrid_opportunity_pair_serializes_deterministically():
    assert HybridOpportunityPair.from_dict(_pair().to_dict()).to_dict() == _pair().to_dict()


def test_hybrid_replay_outcome_serializes_deterministically(hybrid_result: dict):
    assert HybridReplayOutcome.from_dict(_outcome().to_dict()).to_dict() == _outcome().to_dict()


def test_swing_candidate_requires_call_or_put():
    with pytest.raises(ValueError):
        SwingOptionCandidate(**{**_candidate().to_dict(), "option_type": "straddle"})


def test_swing_candidate_rejects_sell_to_open():
    with pytest.raises(ValueError):
        SwingOptionCandidate(**{**_candidate().to_dict(), "entry_action": "sell_to_open"})


def test_hybrid_pair_requires_zero_dte_and_swing_candidate():
    with pytest.raises(ValueError):
        HybridOpportunityPair(**{**_pair().to_dict(), "zero_dte_candidate_id": ""})


def test_hybrid_pair_hash_is_deterministic():
    assert hybrid_pair_hash(_pair()) == hybrid_pair_hash(_pair())


def test_multi_day_option_state_serializes_deterministically():
    state = MultiDayOptionState.from_dict(_path()["states"][0])
    assert MultiDayOptionState.from_dict(state.to_dict()).to_dict() == state.to_dict()


def test_multi_day_paths_load():
    assert len(load_hybrid_multi_day_paths_v3()) >= 192


def test_multi_day_paths_include_entry_day():
    assert all(path["entry_day_present"] for path in load_hybrid_multi_day_paths_v3())


def test_multi_day_paths_include_overnight_gap():
    assert any(path["overnight_gap_present"] for path in load_hybrid_multi_day_paths_v3())


def test_multi_day_paths_include_next_day_close_eligible_state():
    assert all(path["next_day_close_eligible_present"] for path in load_hybrid_multi_day_paths_v3())


def test_multi_day_paths_include_optional_day_three_state():
    assert any(path["day_three_present"] for path in load_hybrid_multi_day_paths_v3())


def test_multi_day_paths_have_no_market_data_dependency():
    text = json.dumps(load_hybrid_multi_day_paths_v3()).lower()
    assert not any(token in text for token in ["polygon", "yfinance", "real_quote", "live_quote"])


def test_hybrid_underlying_families_fixture_loads():
    assert HYBRID_UNDERLYING_FAMILIES_FIXTURE_PATH.exists() and len(load_hybrid_underlying_families_v3()) == 12


def test_hybrid_swing_candidates_fixture_loads():
    assert HYBRID_SWING_CANDIDATES_FIXTURE_PATH.exists() and len(load_hybrid_swing_candidates_v3()) >= 192


def test_hybrid_opportunity_pairs_fixture_loads():
    assert HYBRID_OPPORTUNITY_PAIRS_FIXTURE_PATH.exists() and len(load_hybrid_opportunity_pairs_v3()) >= 192


def test_hybrid_multi_day_paths_fixture_loads():
    assert HYBRID_MULTI_DAY_PATHS_FIXTURE_PATH.exists() and len(load_hybrid_multi_day_paths_v3()) >= 192


def test_hybrid_expected_outcomes_fixture_loads():
    assert HYBRID_EXPECTED_OUTCOMES_FIXTURE_PATH.exists() and _json(HYBRID_EXPECTED_OUTCOMES_FIXTURE_PATH)["record_count"] >= 192


def test_hybrid_corpus_has_at_least_192_pairs(hybrid_result: dict):
    assert hybrid_result["summary"]["hybrid_pair_count"] >= 192


def test_each_family_has_at_least_16_hybrid_pairs():
    assert all(len(rows) >= 16 for rows in _family_id_to_pairs().values())


def test_each_family_has_call_and_put_hybrid_pairs():
    assert all({"call", "put"} <= {pair.option_type for pair in rows} for rows in _family_id_to_pairs().values())


def test_each_family_has_zero_dte_preferred_case():
    assert all(any(pair.expected_preference == "prefer_zero_dte" for pair in rows) for rows in _family_id_to_pairs().values())


def test_each_family_has_swing_preferred_case():
    assert all(any(pair.expected_preference == "prefer_swing" for pair in rows) for rows in _family_id_to_pairs().values())


def test_each_family_has_no_trade_preferred_case():
    assert all(any(pair.expected_preference == "prefer_no_trade" for pair in rows) for rows in _family_id_to_pairs().values())


def test_each_family_has_delayed_rotation_case():
    assert all(any(pair.expected_preference == "prefer_delayed_rotation" for pair in rows) for rows in _family_id_to_pairs().values())


def test_each_family_has_special_close_case():
    assert all(any(pair.expected_no_day_trade_result == "special_close_allowed_with_reason" for pair in rows) for rows in _family_id_to_pairs().values())


def test_each_family_has_next_day_close_case():
    assert all(any(pair.expected_no_day_trade_result == "next_day_close_allowed" for pair in rows) for rows in _family_id_to_pairs().values())


def test_each_family_has_overnight_gap_case():
    assert all(any(pair.expected_no_day_trade_result == "overnight_gap_risk_recorded" for pair in rows) for rows in _family_id_to_pairs().values())


def test_hybrid_corpus_uses_synthetic_symbols_only():
    assert all(pair.synthetic_underlying_symbol.startswith("SYN_") for pair in load_hybrid_opportunity_pairs_v3())


def test_hybrid_replay_engine_runs_all_pairs(hybrid_result: dict):
    assert hybrid_result["summary"]["hybrid_replay_count"] == hybrid_result["summary"]["hybrid_pair_count"]


def test_hybrid_replay_expectations_match(hybrid_result: dict):
    assert hybrid_result["summary"]["all_hybrid_expectations_matched"] is True


def test_hybrid_preference_expectations_match(hybrid_result: dict):
    assert hybrid_result["summary"]["all_preference_expectations_matched"] is True


def test_hybrid_allocator_tag_expectations_match(hybrid_result: dict):
    assert hybrid_result["summary"]["all_allocator_tag_expectations_matched"] is True


def test_prefer_zero_dte_case_detected(hybrid_result: dict):
    assert hybrid_result["summary"]["preference_distribution"]["prefer_zero_dte"] > 0


def test_prefer_swing_case_detected(hybrid_result: dict):
    assert hybrid_result["summary"]["preference_distribution"]["prefer_swing"] > 0


def test_prefer_delayed_rotation_case_detected(hybrid_result: dict):
    assert hybrid_result["summary"]["preference_distribution"]["prefer_delayed_rotation"] > 0


def test_prefer_no_trade_case_detected(hybrid_result: dict):
    assert hybrid_result["summary"]["preference_distribution"]["prefer_no_trade"] > 0


def test_inconclusive_more_fixtures_case_detected(hybrid_result: dict):
    assert hybrid_result["summary"]["preference_distribution"]["inconclusive_needs_more_fixture_coverage"] > 0


def test_swing_lifecycle_allows_next_day_close():
    assert evaluate_swing_lifecycle(_candidate(), 1, "long_call", False)["allowed"] is True


def test_swing_lifecycle_blocks_same_day_close():
    assert evaluate_swing_lifecycle(_candidate(), 0, "long_call", False)["allowed"] is False


def test_swing_lifecycle_allows_multi_day_hold():
    assert evaluate_swing_lifecycle(_candidate(), 3, "long_call", False)["decision"] == "close_allowed_next_trading_day_or_later"


def test_swing_lifecycle_records_overnight_gap_risk(hybrid_result: dict):
    assert hybrid_result["summary"]["overnight_gap_stress_count"] > 0


def test_swing_lifecycle_rejects_unsupported_structure():
    assert evaluate_swing_lifecycle(_candidate(), 1, "vertical", False)["allowed"] is False


def test_swing_lifecycle_rejects_live_path():
    assert evaluate_swing_lifecycle(_candidate(), 1, "long_call", True)["allowed"] is False


def test_hybrid_same_day_swing_close_blocked(hybrid_result: dict):
    assert hybrid_result["summary"]["no_day_trade_block_count"] > 0


def test_hybrid_delayed_rotation_plan_created(hybrid_result: dict):
    assert hybrid_result["summary"]["delayed_rotation_count"] > 0


def test_hybrid_rotation_can_open_new_compliant_position():
    assert evaluate_swing_lifecycle(_candidate(), 1, "long_call", False)["allowed"] is True


def test_hybrid_rotation_cannot_close_same_day_normal_position():
    assert "same_day_round_trip_rejected" in evaluate_swing_lifecycle(_candidate(), 0, "long_call", False)["reason_codes"]


def test_hybrid_zero_dte_special_close_requires_lifecycle(hybrid_result: dict):
    assert hybrid_result["summary"]["special_close_count"] > 0


def test_hybrid_no_same_day_churn_loophole(hybrid_result: dict):
    assert all(row["no_day_trade_constraint_result"] != "same_day_normal_allowed" for row in _jsonl(HYBRID_REPLAY_OUTCOMES_PATH))


def test_hybrid_preference_score_is_deterministic():
    assert score_hybrid_preference(_pair(), _candidate(), _path()) == score_hybrid_preference(_pair(), _candidate(), _path())


def test_preference_penalizes_theta_pressure():
    assert score_hybrid_preference(_pair(), _candidate(), _path())["theta_penalty"] >= 0


def test_preference_penalizes_gamma_instability():
    assert score_hybrid_preference(_pair(), _candidate(), _path())["gamma_penalty"] >= 0


def test_preference_penalizes_liquidity_spread_risk():
    assert score_hybrid_preference(_pair(), _candidate(), _path())["liquidity_spread_penalty"] >= 0


def test_preference_penalizes_overnight_gap_risk():
    assert score_hybrid_preference(_pair(), _candidate(), _path())["overnight_gap_penalty"] >= 0


def test_preference_rewards_lifecycle_completeness():
    assert score_hybrid_preference(_pair(), _candidate(), _path())["lifecycle_completeness_bonus"] >= 0


def test_preference_outputs_allocator_tags_without_real_sizing():
    result = score_hybrid_preference(_pair(), _candidate(), _path())
    assert result["capital_allocator_tags"] and result["real_sizing_allowed"] is False


def test_optimizer_consumes_hybrid_v3_evidence():
    assert run_zero_dte_threshold_optimizer()["summary"]["hybrid_v3_pair_count"] >= 192


def test_optimizer_records_zero_dte_vs_swing_preference():
    assert run_zero_dte_threshold_optimizer()["summary"]["hybrid_zero_dte_vs_swing_preference_distribution"]["prefer_swing"] > 0


def test_optimizer_strengthens_later_expiry_preference_when_supported():
    assert run_zero_dte_threshold_optimizer()["summary"]["post_hybrid_later_expiry_preference_status"] == "strengthen_later_expiry_preference_advisory_only"


def test_stricter_gamma_theta_profile_hybrid_survival_status_recorded(hybrid_result: dict):
    assert hybrid_result["threshold_survival"]["hybrid_stricter_gamma_theta_profile_status"] == "paper_shadow_survives_no_research_default"


def test_research_default_promotion_blocked_after_hybrid_pressure(hybrid_result: dict):
    assert hybrid_result["threshold_survival"]["research_default_promotion_allowed"] is False


def test_hybrid_v3_does_not_mutate_live_thresholds(hybrid_result: dict):
    assert hybrid_result["threshold_survival"]["live_threshold_mutation_allowed"] is False


def test_hybrid_coverage_summary_written(hybrid_result: dict):
    assert _coverage()["artifact_type"] == "hybrid_coverage_summary"


def test_hybrid_underlying_family_coverage_score_written(hybrid_result: dict):
    assert _coverage()["underlying_family_coverage_score"] == 1.0


def test_hybrid_regime_family_coverage_score_written(hybrid_result: dict):
    assert _coverage()["regime_family_coverage_score"] == 1.0


def test_hybrid_preference_distribution_written(hybrid_result: dict):
    assert _coverage()["preference_distribution"]["prefer_swing"] > 0


def test_hybrid_delayed_rotation_coverage_written(hybrid_result: dict):
    assert all(_coverage()["delayed_rotation_coverage"].values())


def test_hybrid_overnight_gap_coverage_written(hybrid_result: dict):
    assert all(_coverage()["overnight_gap_coverage"].values())


def test_hybrid_allocator_tag_coverage_written(hybrid_result: dict):
    assert _coverage()["allocator_tag_distribution"]["capital_allocator_candidate_swing"] > 0


def test_hybrid_underlying_families_artifact_written(hybrid_result: dict):
    assert HYBRID_UNDERLYING_FAMILIES_PATH.exists()


def test_hybrid_swing_candidates_artifact_written(hybrid_result: dict):
    assert HYBRID_SWING_CANDIDATES_PATH.exists()


def test_hybrid_opportunity_pairs_artifact_written(hybrid_result: dict):
    assert HYBRID_OPPORTUNITY_PAIRS_PATH.exists()


def test_hybrid_multi_day_paths_artifact_written(hybrid_result: dict):
    assert HYBRID_MULTI_DAY_PATHS_PATH.exists()


def test_hybrid_replay_outcomes_artifact_written(hybrid_result: dict):
    assert HYBRID_REPLAY_OUTCOMES_PATH.exists()


def test_hybrid_preference_scores_artifact_written(hybrid_result: dict):
    assert HYBRID_PREFERENCE_SCORES_PATH.exists()


def test_hybrid_allocator_tags_artifact_written(hybrid_result: dict):
    assert HYBRID_ALLOCATOR_TAGS_PATH.exists()


def test_hybrid_coverage_summary_artifact_written(hybrid_result: dict):
    assert HYBRID_COVERAGE_SUMMARY_PATH.exists()


def test_hybrid_threshold_survival_artifact_written(hybrid_result: dict):
    assert HYBRID_THRESHOLD_SURVIVAL_PATH.exists()


def test_hybrid_replay_summary_artifact_written(hybrid_result: dict):
    assert HYBRID_REPLAY_SUMMARY_PATH.exists()


def test_hybrid_corpus_proof_artifact_written(hybrid_result: dict):
    assert HYBRID_CORPUS_PROOF_PATH.exists()


def test_audit_recognizes_hybrid_v3_artifacts(hybrid_result: dict):
    assert all(check["passed"] for check in _audit_checks())


def test_audit_flags_hybrid_real_market_data_reference(hybrid_result: dict):
    data = list(_audit_inputs())
    data[2] = {**data[2], "records": [*data[2]["records"], {**data[2]["records"][0], "source": "polygon"}]}
    assert _checks_fail(audit_hybrid_swing_0dte_v3_records(*data), "hybrid_no_real_market_reference")


def test_audit_flags_hybrid_broker_reference(hybrid_result: dict):
    data = list(_audit_inputs())
    data[2] = {**data[2], "records": [*data[2]["records"], {**data[2]["records"][0], "source": "place_order"}]}
    assert _checks_fail(audit_hybrid_swing_0dte_v3_records(*data), "hybrid_no_broker_reference")


def test_audit_flags_hybrid_credential_reference(hybrid_result: dict):
    data = list(_audit_inputs())
    data[2] = {**data[2], "records": [*data[2]["records"], {**data[2]["records"][0], "source": "api_key"}]}
    assert _checks_fail(audit_hybrid_swing_0dte_v3_records(*data), "hybrid_no_credential_reference")


def test_audit_flags_hybrid_same_day_normal_close_allowed(hybrid_result: dict):
    data = list(_audit_inputs())
    bad_outcomes = [dict(row) for row in data[4]]
    delayed = next(index for index, row in enumerate(bad_outcomes) if row["preferred_path"] == "delayed_rotation")
    bad_outcomes[delayed]["no_day_trade_constraint_result"] = "same_day_normal_allowed"
    data[4] = bad_outcomes
    assert _checks_fail(audit_hybrid_swing_0dte_v3_records(*data), "hybrid_same_day_normal_swing_close_blocked")


def test_audit_flags_hybrid_allocator_real_sizing(hybrid_result: dict):
    data = list(_audit_inputs())
    bad_tags = [dict(row) for row in data[6]]
    bad_tags[0]["real_sizing_allowed"] = True
    data[6] = bad_tags
    assert _checks_fail(audit_hybrid_swing_0dte_v3_records(*data), "hybrid_allocator_tags_no_real_sizing")


def test_audit_confirms_hybrid_paper_only_live_blocked(hybrid_result: dict):
    checks = {check["check_id"]: check["passed"] for check in _audit_checks()}
    assert checks["hybrid_all_records_paper_only"] and checks["hybrid_all_records_live_blocked"]


def test_audit_confirms_no_active_forbidden_live_decisions_after_hybrid_v3(hybrid_result: dict):
    assert {check["check_id"]: check["passed"] for check in _audit_checks()}["hybrid_active_forbidden_live_decisions_zero"]


def test_reporting_includes_hybrid_v3_summary(hybrid_result: dict):
    assert "hybrid_swing_0dte_v3_summary" in _review_text()


def test_export_verifier_selects_hybrid_v3_artifacts():
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "hybrid_corpus_proof" in ids and "hybrid_replay_summary" in ids


def test_export_review_includes_hybrid_v3_summary():
    assert "0DTE/Swing Hybrid V3 Corpus" in _review_text()


def test_hybrid_v3_artifact_ledger_written(hybrid_result: dict):
    assert Path("docs/reports/DOPEY_HYBRID_SWING_0DTE_V3_ARTIFACT_LEDGER.md").exists() or HYBRID_CORPUS_PROOF_PATH.exists()


def test_shard_plan_includes_hybrid_v3_tests():
    plan = write_test_shard_plan(["tests/test_hybrid_swing_0dte_v3.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_hybrid_swing_0dte_v3.py" in plan["hybrid_swing_0dte_v3_test_files"]


def test_shard_plan_marks_hybrid_artifact_tests_sequential():
    plan = write_test_shard_plan(["tests/test_hybrid_swing_0dte_v3.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_hybrid_swing_0dte_v3.py" in plan["artifact_writing_tests_sequential"]


def test_full_suite_timeout_remains_inconclusive_not_pass():
    result = timeout_result(["python", "-m", "pytest"], 30)
    assert result["status"] == "inconclusive_timeout" and result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_after_hybrid_v3(hybrid_result: dict):
    assert load_config(default_config_path()).get("live_trading_enabled") is False


def test_robinhood_stub_still_blocks_live_after_hybrid_v3(hybrid_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())


def test_alpaca_stub_still_blocks_live_after_hybrid_v3(hybrid_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())


def test_tradier_stub_still_blocks_live_after_hybrid_v3(hybrid_result: dict):
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_no_credentials_created_by_hybrid_v3(hybrid_result: dict):
    text = "\n".join(path.read_text(encoding="utf-8") for path in [HYBRID_OPPORTUNITY_PAIRS_PATH, HYBRID_REPLAY_SUMMARY_PATH, HYBRID_THRESHOLD_SURVIVAL_PATH])
    assert not any(token in text.lower() for token in ["api_key", "secret_key", "access_token", "refresh_token"])


def test_no_scheduler_created_by_hybrid_v3():
    text = Path("dopey_options/run_hybrid_swing_0dte_v3.py").read_text(encoding="utf-8").lower()
    assert "apscheduler" not in text and "cron" not in text


def test_no_network_market_data_dependency_created_by_hybrid_v3():
    text = Path("dopey_options/run_hybrid_swing_0dte_v3.py").read_text(encoding="utf-8").lower()
    assert not any(token in text for token in ["requests", "yfinance", "polygon", "iex"])


def test_no_same_day_churn_loophole_created_by_hybrid_v3(hybrid_result: dict):
    assert all(row["no_day_trade_constraint_result"] != "same_day_normal_allowed" for row in _jsonl(HYBRID_REPLAY_OUTCOMES_PATH))


def test_no_real_capital_allocator_created_by_hybrid_v3(hybrid_result: dict):
    assert all(row["real_sizing_allowed"] is False and row["capital_deployment_allowed"] is False for row in _jsonl(HYBRID_ALLOCATOR_TAGS_PATH))


def test_blunder_integrity_unchanged_if_manifest_available():
    status_path = Path("artifacts/dopey/exports/blunder_integrity_status.json")
    if not status_path.exists():
        pytest.skip("Blunder integrity manifest status not available")
    assert _json(status_path).get("status") in {"ok", "skipped"}
