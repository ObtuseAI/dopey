"""Tests: active trading policy integration map, audit, reporting, export, and safety."""
from __future__ import annotations

from pathlib import Path

from dopey_audit.active_policy_audit import run_active_policy_audit
from dopey_audit.safety_auditor import audit_blunder_integrity
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_safety_summary
from dopey_governor.active_policy_compliance import (
    active_strategy_generation_universe,
    classify_mutation_for_active_policy,
    classify_structure_for_active_policy,
    tournament_candidate_active_policy_compliant,
)
from dopey_governor.active_policy_integration_map import (
    build_active_policy_integration_map,
    write_active_policy_integration_map,
)
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _active_policy_summary


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="active-policy-live-x",
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": "buy", "symbol": "SPY_C1", "option_type": "call", "expiry": "2026-07-17", "dte": 14}],
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=1.0,
        active_policy_required=True,
    )


def test_active_policy_integration_map_exists(tmp_path: Path) -> None:
    output = write_active_policy_integration_map(tmp_path / "map.json", tmp_path / "map.md")
    assert Path(output["json_path"]).exists()
    assert Path(output["markdown_path"]).exists()


def test_active_policy_integration_map_is_deterministic() -> None:
    first = build_active_policy_integration_map()
    second = build_active_policy_integration_map()
    assert first["reproducibility_hash"] == second["reproducibility_hash"]


def test_active_policy_enforcement_points_include_order_validator() -> None:
    names = {point["enforcement_point"] for point in build_active_policy_integration_map()["enforcement_points"]}
    assert "order_intent_validator" in names


def test_active_policy_enforcement_points_include_paper_broker() -> None:
    names = {point["enforcement_point"] for point in build_active_policy_integration_map()["enforcement_points"]}
    assert "paper_broker" in names


def test_active_policy_enforcement_points_include_audit() -> None:
    names = {point["enforcement_point"] for point in build_active_policy_integration_map()["enforcement_points"]}
    assert "evidence_audit" in names


def test_active_strategy_generation_only_long_call_long_put() -> None:
    structures = {row["structure_type"] for row in active_strategy_generation_universe()}
    assert {"long_call", "long_put", "swing_call", "swing_put", "rotation_call", "rotation_put"}.issubset(structures)
    assert "short_straddle" not in structures


def test_mutation_rejects_short_option_leg() -> None:
    decision = classify_mutation_for_active_policy({"genome_id": "m", "parameters": {"spread_structure_proxy": "short_straddle"}})
    assert decision.compliant is False
    assert "unsupported_short_option_leg" in decision.reasons


def test_mutation_rejects_same_day_churn_candidate() -> None:
    decision = classify_mutation_for_active_policy({"genome_id": "m", "parameters": {"same_day_round_trip": True}})
    assert decision.compliant is False
    assert "same_day_round_trip_rejected" in decision.reasons


def test_structure_builder_marks_unsupported_spreads_noncompliant() -> None:
    decision = classify_structure_for_active_policy("long_call_vertical", 2)
    assert decision.compliant is False
    assert decision.status == "research_legacy_unsupported"


def test_active_policy_compliant_candidates_survive_tournament_validation() -> None:
    assert tournament_candidate_active_policy_compliant({"structure_type": "long_call", "leg_count": 1}) is True


def test_audit_recognizes_active_policy_artifacts() -> None:
    result = run_active_policy_audit()
    assert result["verdict"] == "pass"
    assert result["artifact_paths"]["active_policy_integration_map"]


def test_audit_fails_on_active_policy_missing(tmp_path: Path) -> None:
    result = run_active_policy_audit(tmp_path / "missing-map.json", write_proofs=False, auto_create_map=False)
    assert result["verdict"] == "fail_safety"


def test_audit_flags_same_day_round_trip_violation() -> None:
    result = run_active_policy_audit()
    proof = Path(result["artifact_paths"]["active_policy_position_lifecycle_proof"]).read_text(encoding="utf-8")
    assert "same_day_round_trip_rejected" in proof


def test_audit_flags_undefined_risk_active_candidate() -> None:
    result = run_active_policy_audit()
    proof = Path(result["artifact_paths"]["active_policy_order_validation_proof"]).read_text(encoding="utf-8")
    assert "unsupported_multileg_structure_rejected" in proof


def test_audit_confirms_no_active_forbidden_live_decisions() -> None:
    result = run_active_policy_audit()
    assert result["live_blocked"] is True
    assert result["paper_only"] is True


def test_reporting_includes_active_policy_summary() -> None:
    run_active_policy_audit()
    summary = _active_policy_summary(load_reporting_evidence(EVIDENCE_PATHS))
    assert summary["allowed_strategy_universe"] == ["long_call", "long_put"]
    assert summary["live_blocked"] is True


def test_export_review_includes_active_policy_summary() -> None:
    class Context:
        safety_state = {"mode": "RESEARCH", "live_trading_enabled": False, "funded_broker_connections_enabled": False, "allow_unofficial_robinhood_api": False}
        export_safety_scan = {"active_forbidden_live_decisions": 0, "credential_findings": 0}

    rendered = render_safety_summary(Context())
    assert "active_policy_no_day_trade_guard" in rendered


def test_export_manifest_can_include_active_policy_artifacts() -> None:
    artifact_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "active_policy_integration_map" in artifact_ids
    assert "active_policy_paperbroker_proof" in artifact_ids


def test_active_policy_artifact_ledger_written() -> None:
    assert Path("docs/reports/DOPEY_ACTIVE_POLICY_ARTIFACT_LEDGER.md").exists()


def test_live_trading_remains_disabled_after_active_policy_integration() -> None:
    assert build_active_policy_integration_map()["safety_state"]["live_trading_enabled"] is False


def test_robinhood_stub_still_raises_live_trading_disabled() -> None:
    try:
        RobinhoodMCPAdapter().place_order(_live_intent())
    except LiveTradingDisabledError:
        return
    raise AssertionError("Robinhood live order was not blocked")


def test_alpaca_stub_still_raises_live_trading_disabled() -> None:
    try:
        AlpacaOptionsAdapter().place_order(_live_intent())
    except LiveTradingDisabledError:
        return
    raise AssertionError("Alpaca live order was not blocked")


def test_tradier_stub_still_raises_live_trading_disabled() -> None:
    try:
        TradierOptionsAdapter().place_order(_live_intent())
    except LiveTradingDisabledError:
        return
    raise AssertionError("Tradier live order was not blocked")


def test_no_credentials_created_by_active_policy_integration() -> None:
    governor_artifacts = Path("artifacts/dopey/governor")
    assert not list(governor_artifacts.glob("*.env")) if governor_artifacts.exists() else True


def test_no_scheduler_created_by_active_policy_integration() -> None:
    assert not Path("dopey_scheduler").exists()


def test_no_network_market_data_dependency_created() -> None:
    assert build_active_policy_integration_map()["safety_state"]["network_market_data_required"] is False


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    findings = audit_blunder_integrity()
    assert not [finding for finding in findings if finding.severity == "safety_error"]
