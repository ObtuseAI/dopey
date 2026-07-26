"""Tiered operational-readiness frontier for research and paper shadowing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

from dopey.protocols.identity import canonical_hash


GateStatus = Literal["pass", "blocked", "unknown"]


@dataclass(frozen=True, slots=True)
class ReadinessGate:
    gate_id: str
    status: GateStatus
    evidence_class: str
    source: str
    detail: str
    autonomous_next_action: str


def _boundary_valid(record: Mapping[str, object]) -> bool:
    return record.get("paper_only") is True and record.get("live_blocked") is True


def _gate(
    gate_id: str,
    passed: bool | None,
    evidence_class: str,
    source: str,
    detail: str,
    autonomous_next_action: str,
) -> ReadinessGate:
    status: GateStatus = "unknown" if passed is None else "pass" if passed else "blocked"
    return ReadinessGate(
        gate_id=gate_id,
        status=status,
        evidence_class=evidence_class,
        source=source,
        detail=detail,
        autonomous_next_action=autonomous_next_action,
    )


def _all_pass(gates: tuple[ReadinessGate, ...], required_ids: tuple[str, ...]) -> bool:
    by_id = {gate.gate_id: gate for gate in gates}
    return all(by_id[gate_id].status == "pass" for gate_id in required_ids)


def build_trade_readiness_frontier(
    action_gate: Mapping[str, object],
    nightly: Mapping[str, object],
    options_contract: Mapping[str, object],
    history_manifest: Mapping[str, object],
    stress_summary: Mapping[str, object],
    incident_summary: Mapping[str, object],
    lifecycle_summary: Mapping[str, object],
) -> dict[str, object]:
    """Distinguish operational mechanics from strategy and live authority."""

    sources = {
        "action_gate": action_gate,
        "nightly": nightly,
        "options_contract": options_contract,
        "history_manifest": history_manifest,
        "stress_summary": stress_summary,
        "incident_summary": incident_summary,
        "lifecycle_summary": lifecycle_summary,
    }
    boundary_failures = sorted(name for name, record in sources.items() if not _boundary_valid(record))
    action_checks = action_gate.get("checks")
    normalized_action_checks = action_checks if isinstance(action_checks, Mapping) else {}
    suite = nightly.get("suite")
    normalized_suite = suite if isinstance(suite, Mapping) else {}
    suite_status = normalized_suite.get("suite_status", normalized_suite.get("status", "unknown"))
    file_records = history_manifest.get("data_files")
    history_file_count = len(file_records) if isinstance(file_records, list) else 0

    gates = (
        _gate(
            "constitutional_boundary",
            not boundary_failures,
            "constitutional_control",
            "all readiness inputs",
            "all inputs assert paper_only=true and live_blocked=true"
            if not boundary_failures
            else f"invalid source boundaries: {boundary_failures}",
            "quarantine any source that weakens the constitutional boundary",
        ),
        _gate(
            "governed_stock_history_200",
            history_manifest.get("dataset_status") == "operator_staged_real_dataset"
            and history_file_count >= 200,
            "observed_public_history",
            "history_dataset_manifest.json",
            f"governed stock files={history_file_count}; required>=200",
            "refresh, hash, validate, and promote public OHLCV through the governed lake",
        ),
        _gate(
            "nightly_validation_green",
            nightly.get("suite_green") is True
            and suite_status in {"passed", "complete_green"}
            and int(normalized_suite.get("failed", 0)) == 0
            and int(normalized_suite.get("errors", 0)) == 0,
            "mechanical_validation",
            "nightly_latest.json",
            f"status={suite_status}; failed={normalized_suite.get('failed', 'unknown')}; errors={normalized_suite.get('errors', 'unknown')}",
            "run the resumable isolated nightly suite and publish a fresh green checkpoint",
        ),
        _gate(
            "stress_mechanics_complete",
            int(stress_summary.get("stress_case_count", 0)) >= 120
            and stress_summary.get("paper_shadow_contained") is True
            and stress_summary.get("same_day_churn_allowed") is False,
            "deterministic_fixture_mechanics",
            "stress_ladder_summary.json",
            f"stress_cases={stress_summary.get('stress_case_count', 0)}; paper_shadow_contained={stress_summary.get('paper_shadow_contained')}",
            "expand stressed quote, liquidity, correlation, and outage fixtures when coverage regresses",
        ),
        _gate(
            "incident_kill_switch_complete",
            int(incident_summary.get("incident_case_count", 0)) >= 144
            and incident_summary.get("terminal_block_auto_recovery_allowed") is False,
            "deterministic_fixture_mechanics",
            "incident_rehearsal_summary.json",
            f"incident_cases={incident_summary.get('incident_case_count', 0)}; terminal_auto_recovery={incident_summary.get('terminal_block_auto_recovery_allowed')}",
            "rehearse new incident families and preserve terminal fail-closed behavior",
        ),
        _gate(
            "option_lifecycle_mechanics_complete",
            lifecycle_summary.get("proof_completeness") is True
            and int(lifecycle_summary.get("lifecycle_case_count", 0)) >= 136
            and lifecycle_summary.get("paperbroker_override_allowed") is False,
            "deterministic_fixture_mechanics",
            "lifecycle_summary.json",
            f"lifecycle_cases={lifecycle_summary.get('lifecycle_case_count', 0)}; proof_complete={lifecycle_summary.get('proof_completeness')}",
            "extend assignment, exercise, expiration, partial-fill, and outage fixture families",
        ),
        _gate(
            "observed_options_quotes_validated",
            options_contract.get("options_data_validated") is True
            and options_contract.get("quote_priced_backtest_allowed") is True,
            "observed_options_market_data",
            "options_data_contract_summary.json",
            f"options_data_validated={options_contract.get('options_data_validated')}; quote_priced_backtest_allowed={options_contract.get('quote_priced_backtest_allowed')}",
            "ingest timestamped licensed option chains and pass all quote-quality gates",
        ),
        _gate(
            "forward_sample_sufficient",
            normalized_action_checks.get("forward_track_sample_sufficient") is True,
            "prospective_forward_evidence",
            "action_readiness_gate.json",
            f"closed={action_gate.get('forward_closed_trades', 0)}; required={action_gate.get('forward_closed_trades_required', 0)}",
            "continue immutable forward settlement; never synthesize or backfill outcomes",
        ),
        _gate(
            "forward_track_net_positive",
            normalized_action_checks.get("forward_track_net_positive") is True,
            "prospective_forward_evidence",
            "action_readiness_gate.json",
            f"gate={normalized_action_checks.get('forward_track_net_positive')}",
            "continue settlement and retire or retune only through held-out challenger evidence",
        ),
        _gate(
            "regime_robust_and_statistically_promotable",
            normalized_action_checks.get("any_cohort_regime_robust") is True
            and normalized_action_checks.get("statistical_truth_promotion_allowed") is True,
            "held_out_selection_adjusted_evidence",
            "action_readiness_gate.json",
            "requires regime robustness and statistical-truth promotion together",
            "run held-out, multiple-testing-adjusted cohort evaluation without changing the judge",
        ),
    )

    research_ids = (
        "constitutional_boundary",
        "governed_stock_history_200",
        "stress_mechanics_complete",
        "incident_kill_switch_complete",
        "option_lifecycle_mechanics_complete",
    )
    stock_shadow_ids = (*research_ids, "nightly_validation_green")
    option_shadow_ids = (*stock_shadow_ids, "observed_options_quotes_validated")
    promotion_ids = (
        *option_shadow_ids,
        "forward_sample_sufficient",
        "forward_track_net_positive",
        "regime_robust_and_statistically_promotable",
    )
    research_ready = _all_pass(gates, research_ids)
    stock_shadow_ready = _all_pass(gates, stock_shadow_ids)
    option_shadow_ready = _all_pass(gates, option_shadow_ids)
    strategy_promotion_ready = _all_pass(gates, promotion_ids) and action_gate.get("action_ready") is True
    blocked_gates = [asdict(gate) for gate in gates if gate.status != "pass"]
    autonomous_queue = list(
        dict.fromkeys(
            gate.autonomous_next_action
            for gate in gates
            if gate.status != "pass"
        )
    )
    frontier = {
        "artifact_type": "dopey_trade_readiness_frontier",
        "schema_version": "dopey-trade-readiness-frontier-v1",
        "frontier_status": (
            "strategy_promotion_ready_paper_only"
            if strategy_promotion_ready
            else "option_shadow_ready_strategy_evidence_pending"
            if option_shadow_ready
            else "stock_shadow_ready_options_evidence_pending"
            if stock_shadow_ready
            else "research_mechanics_ready_full_validation_pending"
            if research_ready
            else "research_mechanics_blocked"
        ),
        "highest_operational_level": (
            "strategy_promotion_ready_paper_only"
            if strategy_promotion_ready
            else "option_shadow"
            if option_shadow_ready
            else "stock_shadow"
            if stock_shadow_ready
            else "research_mechanics"
            if research_ready
            else "constitutional_diagnostics"
        ),
        "levels": {
            "research_mechanics": {"ready": research_ready, "required_gate_ids": list(research_ids)},
            "stock_shadow": {"ready": stock_shadow_ready, "required_gate_ids": list(stock_shadow_ids)},
            "option_shadow": {"ready": option_shadow_ready, "required_gate_ids": list(option_shadow_ids)},
            "strategy_promotion": {"ready": strategy_promotion_ready, "required_gate_ids": list(promotion_ids)},
            "live_execution": {
                "ready": False,
                "status": "constitutionally_unavailable",
                "reason": "DOPEY has no order authority, credential authority, or live execution capability",
            },
        },
        "gates": [asdict(gate) for gate in gates],
        "blocked_gates": blocked_gates,
        "autonomous_next_action_queue": autonomous_queue,
        "research_basis": [
            {"topic": "execution_quality", "source": "SEC Rule 605 execution-quality statistics"},
            {"topic": "options_mechanics", "source": "OCC Characteristics and Risks of Standardized Options"},
            {"topic": "options_market_data", "source": "Cboe US Options technical and market-data specifications"},
            {"topic": "selection_bias", "source": "Bailey and Lopez de Prado, Deflated Sharpe Ratio"},
            {"topic": "volatility_surface", "source": "Gatheral and Jacquier, Arbitrage-free SVI volatility surfaces"},
            {"topic": "execution_cost_risk", "source": "Almgren and Chriss, Optimal execution of portfolio transactions"},
        ],
        "thresholds_weakened": False,
        "simulation_counted_as_realized_evidence": False,
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": strategy_promotion_ready,
        "live_trading_enabled": False,
    }
    frontier["reproducibility_hash"] = canonical_hash(frontier)
    return frontier
