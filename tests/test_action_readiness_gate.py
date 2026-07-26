from __future__ import annotations

import json

import pytest
from dopey_broker_readiness.action_readiness_gate import (
    MIN_FORWARD_CLOSED_TRADES,
    READINESS_SUMMARY_PATH,
    run_action_readiness_gate,
    stress_book_snapshot_matches_forward_book,
    stress_evidence_integrity_valid,
    stress_valuation_inputs_match_current,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_risk_engine import adversarial_stress_engine as stress_module
from dopey_risk_engine.adversarial_stress_engine import (
    build_current_quote_snapshot_binding,
    build_forward_book_binding,
    build_stress_policy_binding,
)


def test_gate_runs_and_reports_current_honest_state() -> None:
    summary = run_action_readiness_gate()
    assert summary["live_trading_enabled"] is False
    assert summary["paper_only"] is True and summary["live_blocked"] is True
    assert summary["gate_semantics"].startswith("necessary_not_sufficient")
    # today's honest state: forward track is days old, so the gate must be closed
    assert summary["action_ready"] is False
    assert "forward_track_sample_sufficient" in summary["missing_requirements"]
    assert summary["forward_closed_trades_required"] == MIN_FORWARD_CLOSED_TRADES
    on_disk = json.loads(READINESS_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert on_disk["action_ready"] is False


def test_gate_boundary_official_lane_recorded_execution_still_sealed() -> None:
    summary = run_action_readiness_gate()
    boundary = summary["robinhood_mcp_boundary"]
    assert boundary["official_mcp_available"] is True
    assert (
        boundary["official_mcp_endpoint"] == "https://agent.robinhood.com/mcp/trading"
    )
    assert (
        "unofficial_api_or_reverse_auth_or_session_cookies"
        in boundary["blocked_always"]
    )
    assert "credentials_or_env_in_repo" in boundary["blocked_always"]
    assert "read_only_account_snapshot_via_official_mcp" in boundary["allowed_now"]
    execution = boundary["execution_policy"]
    assert (
        execution["status"]
        == "blocked_until_gate_all_green_plus_explicit_human_approval"
    )
    assert "human" in execution["designated_path_if_ever_unlocked"]


def test_gate_checks_cover_every_evidence_dimension() -> None:
    summary = run_action_readiness_gate()
    expected = {
        "forward_track_sample_sufficient",
        "forward_track_net_positive",
        "forward_evidence_integrity_current",
        "validated_multi_cohort_forward_sample",
        "cohort_baseline_policy_current",
        "any_cohort_beats_matched_baseline_familywise",
        "cohort_era_policy_current",
        "any_cohort_regime_robust",
        "statistical_truth_promotion_allowed",
        "stress_evidence_integrity_valid",
        "stress_book_snapshot_current",
        "stress_valuation_inputs_current",
        "stress_book_survives_all_scenarios",
        "no_active_discipline_halt",
        "pricing_model_calibrated",
        "data_freshness_green",
        "open_book_entry_quality_green",
        "open_book_concentration_green",
        "hardened_champion_available",
        "full_nightly_validation_green",
        "paper_twin_broker_reconciliation_green",
    }
    assert set(summary["checks"]) == expected


def test_gate_stress_snapshot_binding_fails_closed_on_any_book_drift() -> None:
    positions = [
        {
            "position_id": "fw-TEST-long_call-2026-07-23-00001",
            "symbol": "TEST",
            "entry_fill": 2.5,
            "last_mark_bid": 2.0,
        }
    ]
    binding = build_forward_book_binding(positions)
    stress = {"scenario_stress_green": True, **binding}
    assert stress_book_snapshot_matches_forward_book(stress, positions) is True

    count_drift = {**stress, "source_forward_book_position_count": 2}
    identity_drift = {
        **stress,
        "source_forward_book_position_ids_hash": "0" * 64,
    }
    snapshot_drift = {
        **stress,
        "source_forward_book_snapshot_hash": "0" * 64,
    }
    assert stress_book_snapshot_matches_forward_book(count_drift, positions) is False
    assert stress_book_snapshot_matches_forward_book(identity_drift, positions) is False
    assert stress_book_snapshot_matches_forward_book(snapshot_drift, positions) is False


def test_gate_rejects_tampered_or_stale_stress_valuation_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positions = [
        {
            "position_id": "fw-TEST-long_call-2026-07-23-00001",
            "symbol": "TEST",
            "expiry": "2026-08-21",
            "option_type": "call",
            "strike": 100.0,
        }
    ]
    snapshot = {
        "chain_snapshot_status": "real_chain_snapshot_validated",
        "snapshot_date": "2026-07-24",
        "files_loaded": 1,
        "row_count": 1,
        "symbols": ["TEST"],
        "reason_codes": [],
        "rows": [
            {
                "symbol": "TEST",
                "expiry": "2026-08-21",
                "option_type": "call",
                "strike": 100.0,
                "implied_vol": 0.4,
                "underlying_spot": 101.0,
            }
        ],
        "quote_derived": True,
        "paper_only": True,
        "live_blocked": True,
    }
    monkeypatch.setattr(
        stress_module,
        "load_latest_chain_snapshot",
        lambda: snapshot,
    )
    stress = {
        "artifact_type": "adversarial_stress_summary",
        "scenario_stress_green": True,
        "paper_only": True,
        "live_blocked": True,
        **build_forward_book_binding(positions),
        **build_current_quote_snapshot_binding(positions),
        **build_stress_policy_binding(),
    }
    stress["reproducibility_hash"] = reproducibility_hash(stress)

    inputs_current, _current_inputs = stress_valuation_inputs_match_current(
        stress,
        positions,
    )
    assert stress_evidence_integrity_valid(stress) is True
    assert inputs_current is True

    tampered = {**stress, "scenario_stress_green": False}
    assert stress_evidence_integrity_valid(tampered) is False

    stale_inputs = {**stress, "source_quote_snapshot_hash": "0" * 64}
    stale_inputs.pop("reproducibility_hash")
    stale_inputs["reproducibility_hash"] = reproducibility_hash(stale_inputs)
    inputs_current, _current_inputs = stress_valuation_inputs_match_current(
        stale_inputs,
        positions,
    )
    assert stress_evidence_integrity_valid(stale_inputs) is True
    assert inputs_current is False
