from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dopey_evolution import exit_policy_walkforward_search as exit_policy_module
from dopey_evolution import sharpness_tuning as sharpness_module
from dopey_evolution.exit_policy_walkforward_search import _promotion_assessment
from dopey_evolution.sharpness_tuning import (
    COHORT_EXIT_DECISIONS_PATH,
    FILTER_EXPERIMENTS_PATH,
    PORTFOLIO_AGGRESSION_GATE_PATH,
    SHARPNESS_SUMMARY_PATH,
    build_cohort_starvation_decisions,
    build_evidence_gated_allocation_decisions,
    build_portfolio_aggression_gate,
    run_sharpness_tuning,
)
from dopey_backtest.baseline_arbitration import BASELINE_POLICY_VERSION
from dopey_backtest.era_walk_forward import ERA_POLICY_VERSION
from dopey_backtest.forward_evidence_integrity import (
    QUARANTINED_OUTCOME,
    VALIDATED_OUTCOME,
)


def _exit_cell(train: float, validation: float, validation_ci_low: float) -> dict[str, Any]:
    return {
        "train_net_pnl": train * 100.0,
        "validation_net_pnl": validation * 100.0,
        "train_mean_pnl": train,
        "validation_mean_pnl": validation,
        "validation_mean_ci_low": validation_ci_low,
        "train_trades": 100,
        "validation_trades": 100,
    }


def _classified_forward_trade(position_id: str, path_pnl: float, outcome_class: str) -> dict[str, Any]:
    return {
        "position_id": position_id,
        "path_pnl": path_pnl,
        "outcome_integrity_class": outcome_class,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(value, sort_keys=True) + "\n" for value in values)
    path.write_text(payload, encoding="utf-8")


def _write_starved_sharpness_inputs() -> None:
    _write_jsonl(sharpness_module.BASELINE_VERDICTS_PATH, [])
    _write_json(
        sharpness_module.BASELINE_SUMMARY_PATH,
        {
            "baseline_policy_version": BASELINE_POLICY_VERSION,
            "cohorts_beating_baseline": 0,
            "paper_only": True,
            "live_blocked": True,
            "not_readiness_evidence": True,
        },
    )
    _write_jsonl(sharpness_module.ERA_STATS_PATH, [])
    _write_json(
        sharpness_module.ERA_SUMMARY_PATH,
        {
            "era_policy_version": ERA_POLICY_VERSION,
            "regime_robust_cohorts": [],
            "regime_robust_count": 0,
            "paper_only": True,
            "live_blocked": True,
            "not_readiness_evidence": True,
        },
    )
    _write_jsonl(sharpness_module.TRADE_RECORDS_PATH, [])
    _write_json(sharpness_module.FORWARD_SUMMARY_PATH, {"paper_only": True, "live_blocked": True})
    _write_json(
        sharpness_module.FORWARD_LEDGER_PATH,
        {
            "closed_trades": [],
            "last_discipline_halt": {"cooldown_sessions_remaining": 1},
            "paper_only": True,
            "live_blocked": True,
            "not_readiness_evidence": True,
        },
    )
    _write_json(
        sharpness_module.READINESS_GATE_PATH,
        {
            "evidence_eta": {"closed_required": 100},
            "action_ready": False,
            "paper_only": True,
            "live_blocked": True,
            "not_readiness_evidence": True,
        },
    )
    _write_json(
        sharpness_module.FOUNDRY_SUMMARY_PATH,
        {"promoted_count": 0, "paper_only": True, "live_blocked": True},
    )
    _write_jsonl(
        sharpness_module.COHORT_EXIT_SHADOW_SOURCE_PATH,
        [{"cohort_id": "fixture|fixture", "local_exit_promotion_eligible": False}],
    )
    _write_json(
        sharpness_module.RAW_ALLOCATION_PLAN_PATH,
        {
            "plan_id": "non-readiness-fixture",
            "plan_hash": "non-readiness-fixture",
            "total_paper_premium_risk_units": 1.0,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    _write_jsonl(sharpness_module.RAW_ALLOCATION_DECISIONS_PATH, [])


def test_exit_policy_relative_improvement_is_not_promotion() -> None:
    current = _exit_cell(-0.20, -0.30, -0.40)
    challenger = _exit_cell(-0.10, -0.15, -0.20)
    promoted, status, checks = _promotion_assessment(challenger, current)
    assert promoted is False
    assert status == "relative_improvement_only"
    assert checks["beats_current_train_net"] is True
    assert checks["validation_mean_ci_low_positive"] is False


def test_exit_policy_requires_positive_validation_lower_bound() -> None:
    current = _exit_cell(-0.20, -0.30, -0.40)
    challenger = _exit_cell(0.10, 0.15, 0.05)
    promoted, status, checks = _promotion_assessment(challenger, current)
    assert promoted is True
    assert status == "promotion_eligible"
    assert all(checks.values())


def test_exit_policy_grid_checkpoint_resumes_by_input_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exit_policy_module, "SEARCH_GRID_PATH", tmp_path / "exit_policy_search_grid.jsonl")
    monkeypatch.setattr(exit_policy_module, "SEARCH_SUMMARY_PATH", tmp_path / "exit_policy_search_summary.json")
    monkeypatch.setattr(exit_policy_module, "SEARCH_CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(exit_policy_module, "SEARCH_QUARANTINE_DIR", tmp_path / "quarantine")
    calls: list[tuple[float, float, int]] = []

    def fake_evaluate(
        prepared: list[tuple[dict[str, Any], list[float], list[str], str]],
        stop: float,
        target: float,
        hold: int,
    ) -> dict[str, Any]:
        calls.append((stop, target, hold))
        metrics = {
            "net_pnl": round(stop + target + hold, 6),
            "trade_count": len(prepared),
            "mean_pnl": 0.01,
            "mean_ci_low": -0.01,
            "mean_ci_high": 0.03,
        }
        return {"train": metrics, "validation": metrics, "cohorts": {}}

    monkeypatch.setattr(exit_policy_module, "_evaluate", fake_evaluate)
    prepared = [
        (
            {"symbol": "SPY", "signal_id": "signal-1"},
            [1.0, 1.1],
            ["2026-01-01"],
            "path-1",
        )
    ]
    fingerprint = exit_policy_module._prepared_input_fingerprint(prepared)

    first, first_source = exit_policy_module._load_or_build_grid(prepared, fingerprint)
    second, second_source = exit_policy_module._load_or_build_grid(prepared, fingerprint)

    assert len(first) == 27
    assert len(second) == 27
    assert len(calls) == 27
    assert first_source == "content_addressed_grid_rebuilt_or_resumed_from_checkpoint"
    assert second_source == "content_addressed_grid_rebuilt_or_resumed_from_checkpoint"


def test_cohort_starvation_is_fail_closed() -> None:
    verdicts = [
        {"cohort_id": "bad|long_call", "signal_family": "bad", "candidate_strategy": "long_call", "mean_difference": -0.2, "difference_ci_low": -0.3, "difference_ci_high": -0.1, "worse_than_baseline_ci": True, "beats_baseline_ci": False},
        {"cohort_id": "unclear|long_call", "signal_family": "unclear", "candidate_strategy": "long_call", "mean_difference": 0.1, "difference_ci_low": -0.1, "difference_ci_high": 0.3, "worse_than_baseline_ci": False, "beats_baseline_ci": False},
        {"cohort_id": "good|long_call", "signal_family": "good", "candidate_strategy": "long_call", "mean_difference": 0.2, "difference_ci_low": 0.1, "difference_ci_high": 0.3, "worse_than_baseline_ci": False, "beats_baseline_ci": True},
    ]
    decisions = build_cohort_starvation_decisions(verdicts, {"regime_robust_cohorts": ["good|long_call"]})
    by_id = {record["cohort_id"]: record["decision"] for record in decisions}
    assert by_id == {"bad|long_call": "starve", "good|long_call": "survivor", "unclear|long_call": "shadow_only"}


def test_portfolio_aggression_gate_stops_new_risk_during_discipline_halt() -> None:
    gate = build_portfolio_aggression_gate(
        {"cohorts_beating_baseline": 1, "baseline_policy_version": BASELINE_POLICY_VERSION},
        {"regime_robust_count": 1, "era_policy_version": ERA_POLICY_VERSION},
        {},
        {
            "closed_trades": [
                _classified_forward_trade(f"halt-{index}", 1.0, VALIDATED_OUTCOME)
                for index in range(100)
            ],
            "last_discipline_halt": {"cooldown_sessions_remaining": 2},
        },
        {},
        {"evidence_eta": {"closed_required": 100}},
    )
    assert gate["aggression_state"] == "discipline_halt_starvation_only"
    assert gate["new_paper_risk_multiplier"] == 0.0
    assert gate["increased_paper_sizing_allowed"] is False


def test_portfolio_aggression_is_earned_only_after_every_gate() -> None:
    gate = build_portfolio_aggression_gate(
        {"cohorts_beating_baseline": 1, "baseline_policy_version": BASELINE_POLICY_VERSION},
        {"regime_robust_count": 1, "era_policy_version": ERA_POLICY_VERSION},
        {},
        {
            "closed_trades": [
                _classified_forward_trade(f"validated-{index}", 1.0, VALIDATED_OUTCOME)
                for index in range(100)
            ]
        },
        {},
        {"evidence_eta": {"closed_required": 100}},
    )
    assert gate["aggression_state"] == "aggressive_paper_earned"
    assert gate["new_paper_risk_multiplier"] == 1.25
    assert gate["increased_paper_sizing_allowed"] is True


def test_portfolio_aggression_rejects_stale_cohort_policy_artifacts() -> None:
    gate = build_portfolio_aggression_gate(
        {"cohorts_beating_baseline": 1},
        {"regime_robust_count": 1},
        {},
        {
            "closed_trades": [
                _classified_forward_trade(f"stale-policy-{index}", 1.0, VALIDATED_OUTCOME)
                for index in range(100)
            ]
        },
        {},
        {"evidence_eta": {"closed_required": 100}},
    )

    assert gate["aggression_state"] == "shadow_only_minimum_sizing"
    assert gate["checks"]["cohort_baseline_policy_current"] is False
    assert gate["checks"]["cohort_era_policy_current"] is False
    assert gate["increased_paper_sizing_allowed"] is False


def test_portfolio_aggression_counts_only_integrity_validated_outcomes() -> None:
    closed_trades = [
        _classified_forward_trade("validated-loss", -2.0, VALIDATED_OUTCOME),
        *[
            _classified_forward_trade(f"quarantined-win-{index}", 100.0, QUARANTINED_OUTCOME)
            for index in range(99)
        ],
    ]
    gate = build_portfolio_aggression_gate(
        {"cohorts_beating_baseline": 1, "baseline_policy_version": BASELINE_POLICY_VERSION},
        {"regime_robust_count": 1, "era_policy_version": ERA_POLICY_VERSION},
        {},
        {"closed_trades": closed_trades},
        {},
        {"evidence_eta": {"closed_required": 100}},
    )

    assert gate["aggression_state"] == "normal_paper_capped_forward_evidence_accruing"
    assert gate["increased_paper_sizing_allowed"] is False
    assert gate["forward_evidence"] == {
        "raw_closed_record_count": 100,
        "closed_trade_count": 1,
        "closed_trade_count_required": 100,
        "censored_outcome_count": 0,
        "quarantined_outcome_count": 99,
        "statistics_exclude_censored_and_quarantined_outcomes": True,
        "mean_pnl": -2.0,
        "mean_pnl_ci_low_95": -2.0,
        "mean_pnl_ci_high_95": -2.0,
    }


def test_portfolio_aggression_quarantines_unclassified_outcomes_without_policy_proof() -> None:
    gate = build_portfolio_aggression_gate(
        {"cohorts_beating_baseline": 1, "baseline_policy_version": BASELINE_POLICY_VERSION},
        {"regime_robust_count": 1, "era_policy_version": ERA_POLICY_VERSION},
        {},
        {
            "closed_trades": [
                {"position_id": f"unclassified-{index}", "path_pnl": 100.0}
                for index in range(100)
            ]
        },
        {},
        {"evidence_eta": {"closed_required": 100}},
    )

    assert gate["checks"]["forward_sample_sufficient"] is False
    assert gate["checks"]["forward_mean_positive"] is False
    assert gate["checks"]["forward_95ci_low_positive"] is False
    assert gate["increased_paper_sizing_allowed"] is False
    assert gate["forward_evidence"]["raw_closed_record_count"] == 100
    assert gate["forward_evidence"]["closed_trade_count"] == 0
    assert gate["forward_evidence"]["quarantined_outcome_count"] == 100


def test_zero_multiplier_starves_new_allocation_risk() -> None:
    decisions = build_evidence_gated_allocation_decisions(
        [{"allocation_id": "a", "opportunity_id": "o", "decision": "allocate_paper", "paper_premium_risk_units": 2.0, "max_paper_contract_units": 2, "paper_attention_weight": 0.8}],
        {"new_paper_risk_multiplier": 0.0, "aggression_state": "discipline_halt_starvation_only"},
    )
    assert decisions[0]["evidence_gated_decision"] == "evidence_starved_no_new_paper_risk"
    assert decisions[0]["evidence_gated_paper_premium_risk_units"] == 0.0
    assert decisions[0]["evidence_gated_max_paper_contract_units"] == 0


def test_starved_sharpness_bundle_is_complete_and_fail_closed() -> None:
    _write_starved_sharpness_inputs()
    summary = run_sharpness_tuning()
    assert summary["sharpness_status"] == "complete_paper_only"
    assert summary["live_blocked"] is True
    assert summary["increased_paper_sizing_allowed"] is False
    assert _read_json(SHARPNESS_SUMMARY_PATH)["reproducibility_hash"]
    assert _read_json(PORTFOLIO_AGGRESSION_GATE_PATH)["new_paper_risk_multiplier"] == 0.0
    exits = _read_jsonl(COHORT_EXIT_DECISIONS_PATH)
    assert any(record["sharpness_decision"] == "blocked_missing_baseline_verdict" for record in exits)
    filters = _read_jsonl(FILTER_EXPERIMENTS_PATH)
    assert all(
        record["cohort_evidence_status"] != "starve"
        for record in filters
        if record["eligible_for_continued_shadow"]
    )
