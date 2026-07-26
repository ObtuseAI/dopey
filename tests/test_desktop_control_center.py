from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dopey_dashboard.control_center_state import build_control_center_state_with_runner
from dopey_dashboard.desktop_app import DesktopApi, DesktopHostError, _execution_seal_verified
from dopey_dashboard.desktop_tray import (
    FORWARD_WALK_LEDGER_PATH,
    PROMOTION_CYCLE_PATH,
    notification_source_summary,
)
from dopey_dashboard.scheduler_control import (
    CONTROL_CONFIRMATION,
    ResearchCoreConfirmationError,
    SchedulerCommandError,
    SchedulerRunner,
    SchedulerVerificationError,
    inspect_research_core,
    parse_scheduled_tasks,
    set_research_core_enabled,
    set_research_core_enabled_with_runner,
)


def _prepare_commands(repository_root: Path) -> None:
    tools = repository_root / "operator_tools"
    tools.mkdir(parents=True, exist_ok=True)
    source_tools = Path(__file__).resolve().parents[1] / "operator_tools"
    for filename in (
        "acceleration_cycle.cmd",
        "daily_ritual.cmd",
        "run_scheduled_hidden.vbs",
    ):
        (tools / filename).write_bytes((source_tools / filename).read_bytes())


class FixedSchedulerRunner(SchedulerRunner):
    def __init__(
        self,
        repository_root: Path,
        enabled: bool,
        task_state: str,
        process_present: bool,
        process_command: str | None,
        acceleration_arguments: str,
    ) -> None:
        self.repository_root = repository_root
        self.enabled = enabled
        self.task_state = task_state
        self.process_present = process_present
        self.process_command = process_command
        self.acceleration_arguments = acceleration_arguments
        self.task_enabled = {
            "DOPEY_AccelerationCycle": enabled,
            "DOPEY_DailyRitual": enabled,
        }
        self.mutations: list[str] = []

    def query_tasks(self) -> str:
        launcher = self.repository_root / "operator_tools" / "run_scheduled_hidden.vbs"
        wscript = Path(os.environ["SystemRoot"]) / "System32" / "wscript.exe"
        acceleration_arguments = self.acceleration_arguments or (
            f'//B //NoLogo "{launcher}" acceleration_cycle'
        )
        return json.dumps(
            [
                {
                    "TaskName": "DOPEY_AccelerationCycle",
                    "Present": True,
                    "Enabled": self.task_enabled["DOPEY_AccelerationCycle"],
                    "State": self.task_state,
                    "TaskPath": "\\",
                    "PrincipalUserId": os.environ["USERNAME"],
                    "LogonType": "Interactive",
                    "RunLevel": "Limited",
                    "Actions": [
                        {
                            "Execute": str(wscript),
                            "Arguments": acceleration_arguments,
                            "WorkingDirectory": "",
                        }
                    ],
                    "Triggers": [
                        {
                            "CimClass": "MSFT_TaskTimeTrigger",
                            "Enabled": True,
                            "StartBoundary": "2026-07-17T00:05:00",
                            "RepetitionInterval": "PT15M",
                        },
                        {
                            "CimClass": "MSFT_TaskLogonTrigger",
                            "Enabled": True,
                            "StartBoundary": "",
                            "RepetitionInterval": "",
                        }
                    ],
                },
                {
                    "TaskName": "DOPEY_DailyRitual",
                    "Present": True,
                    "Enabled": self.task_enabled["DOPEY_DailyRitual"],
                    "State": "Ready",
                    "TaskPath": "\\",
                    "PrincipalUserId": os.environ["USERNAME"],
                    "LogonType": "Interactive",
                    "RunLevel": "Limited",
                    "Actions": [
                        {
                            "Execute": str(wscript),
                            "Arguments": f'//B //NoLogo "{launcher}" daily_ritual',
                            "WorkingDirectory": "",
                        }
                    ],
                    "Triggers": [
                        {
                            "CimClass": "MSFT_TaskWeeklyTrigger",
                            "Enabled": True,
                            "StartBoundary": "2026-07-09T16:45:00",
                            "RepetitionInterval": "",
                        }
                    ],
                },
            ]
        )

    def query_process(self, pid: int) -> str:
        command = self.process_command
        if command is None:
            command = (
                f'"{self.repository_root / ".venv" / "Scripts" / "python.exe"}" '
                "-m dopey_acceleration.run_acceleration_cycle --mode execute"
            )
        return json.dumps(
            {
                "Present": self.process_present,
                "Pid": pid,
                "Name": "python.exe" if self.process_present else "",
                "ExecutablePath": (
                    str(self.repository_root / ".venv" / "Scripts" / "python.exe")
                    if self.process_present
                    else ""
                ),
                "CommandLine": command if self.process_present else "",
            }
        )

    def enable_task(self, task_name: str) -> None:
        self.mutations.append(f"enable:{task_name}")
        self.task_enabled[task_name] = True
        self.enabled = all(self.task_enabled.values())

    def disable_task(self, task_name: str) -> None:
        self.mutations.append(f"disable:{task_name}")
        self.task_enabled[task_name] = False
        self.enabled = all(self.task_enabled.values())


class NavigatedWindow:
    def __init__(self, current_url: str) -> None:
        self.current_url = current_url
        self.destroyed = False
        self.hidden = False

    def minimize(self) -> None:
        raise AssertionError("navigation validation must run before minimize")

    def maximize(self) -> None:
        raise AssertionError("navigation validation must run before maximize")

    def hide(self) -> None:
        self.hidden = True

    def restore(self) -> None:
        raise AssertionError("navigation validation must run before restore")

    def show(self) -> None:
        raise AssertionError("show is owned by the native tray connector")

    def destroy(self) -> None:
        self.destroyed = True

    def get_current_url(self) -> str:
        return self.current_url

def _runner(
    repository_root: Path,
    enabled: bool,
    task_state: str,
    process_present: bool,
) -> FixedSchedulerRunner:
    return FixedSchedulerRunner(
        repository_root,
        enabled,
        task_state,
        process_present,
        None,
        "",
    )


def test_privileged_bridge_rejects_a_navigated_renderer(tmp_path: Path) -> None:
    expected_url = (tmp_path / "desktop" / "dist" / "index.html").as_uri()
    window = NavigatedWindow("https://example.invalid/")
    api = DesktopApi(tmp_path, expected_url)
    api._bind_window(window)

    with pytest.raises(DesktopHostError, match="Blocked renderer navigation"):
        api.get_state()

    assert window.destroyed is True


def test_close_control_hides_the_local_window_to_the_tray(tmp_path: Path) -> None:
    expected_url = (tmp_path / "desktop" / "dist" / "index.html").as_uri()
    window = NavigatedWindow(expected_url)
    api = DesktopApi(tmp_path, expected_url)
    api._bind_window(window)

    result = api.close_window()

    assert result == {"status": "ok", "window": "hidden_to_tray"}
    assert window.hidden is True
    assert window.destroyed is False


def test_notification_summary_reports_missing_clean_checkout_sources(tmp_path: Path) -> None:
    summary = notification_source_summary(tmp_path)

    assert summary["status"] == "pass"
    assert summary["source_status"] == "unavailable_missing_artifacts"
    assert summary["current_event_counts"] is None
    assert summary["missing_source_paths"] == [
        str(FORWARD_WALK_LEDGER_PATH),
        str(PROMOTION_CYCLE_PATH),
    ]
    assert summary["paper_only"] is False
    assert summary["live_blocked"] is False
    assert summary["live_execution_enabled"] is True


def test_scheduler_state_machine_maps_verified_idle_and_running_states(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)
    on = inspect_research_core(tmp_path, _runner(tmp_path, True, "Ready", False))
    off = inspect_research_core(tmp_path, _runner(tmp_path, False, "Disabled", False))
    assert on["state"] == "ON"
    assert off["state"] == "OFF"

    lock_path = tmp_path / "artifacts" / "dopey" / "acceleration" / "acceleration_cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("4211", encoding="ascii")
    running = inspect_research_core(tmp_path, _runner(tmp_path, True, "Running", True))
    draining = inspect_research_core(tmp_path, _runner(tmp_path, False, "Running", True))
    assert running["state"] == "RUNNING"
    assert draining["state"] == "DRAINING"
    assert running["active_cycle_verified"] is True


def test_scheduler_faults_when_aggregate_task_enablement_diverges(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)
    runner = _runner(tmp_path, True, "Ready", False)
    runner.task_enabled["DOPEY_DailyRitual"] = False

    state = inspect_research_core(tmp_path, runner)

    assert state["state"] == "FAULT"
    assert "inconsistent enabled states" in " ".join(state["issues"])


def test_scheduler_faults_on_unverified_task_or_lock_command(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)
    wrong_arguments = FixedSchedulerRunner(
        tmp_path,
        True,
        "Ready",
        False,
        None,
        "--unexpected",
    )
    task_state = inspect_research_core(tmp_path, wrong_arguments)
    assert task_state["state"] == "FAULT"
    assert "hidden arguments mismatch" in " ".join(task_state["issues"])

    lock_path = tmp_path / "artifacts" / "dopey" / "acceleration" / "acceleration_cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("4211", encoding="ascii")
    wrong_process = FixedSchedulerRunner(
        tmp_path,
        True,
        "Running",
        True,
        "python.exe -m unrelated.module --mode execute",
        "",
    )
    lock_state = inspect_research_core(tmp_path, wrong_process)
    assert lock_state["state"] == "FAULT"
    assert "lock command mismatch" in " ".join(lock_state["issues"])


def test_daily_ritual_is_verified_as_part_of_aggregate_control(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)
    tasks = parse_scheduled_tasks(
        _runner(tmp_path, True, "Ready", False).query_tasks(),
        tmp_path,
    )
    daily = next(task for task in tasks if task["task_name"] == "DOPEY_DailyRitual")
    assert daily["read_only"] is False
    assert daily["action_verified"] is True
    assert daily["identity_verified"] is True


def test_disable_prevents_future_starts_without_killing_running_cycle(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)
    lock_path = tmp_path / "artifacts" / "dopey" / "acceleration" / "acceleration_cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("4211", encoding="ascii")
    runner = _runner(tmp_path, True, "Running", True)
    audit_path = tmp_path / "audit" / "control.jsonl"

    result = set_research_core_enabled_with_runner(
        tmp_path,
        False,
        CONTROL_CONFIRMATION,
        runner,
        audit_path,
        "2026-07-18T12:00:00+00:00",
    )

    after = result["after"]
    assert isinstance(after, dict)
    assert after["state"] == "DRAINING"
    assert runner.mutations == [
        "disable:DOPEY_AccelerationCycle",
        "disable:DOPEY_DailyRitual",
    ]
    audit_records = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert audit_records[0]["outcome"] == "mutation_intent_fsynced"
    audit = audit_records[-1]
    assert audit["active_process_terminated"] is False
    assert audit["action"] == "disable_all_future_paper_automation_starts"
    assert audit["paper_only"] is True and audit["live_blocked"] is True


def test_failed_enable_is_forced_back_to_verified_aggregate_off(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)

    class FailingEnableRunner(FixedSchedulerRunner):
        def enable_task(self, task_name: str) -> None:
            self.mutations.append(f"enable:{task_name}")
            if task_name == "DOPEY_AccelerationCycle":
                raise SchedulerCommandError("injected enable failure")
            self.task_enabled[task_name] = True

    runner = FailingEnableRunner(tmp_path, False, "Disabled", False, None, "")
    audit_path = tmp_path / "audit" / "control.jsonl"

    with pytest.raises(SchedulerVerificationError, match="injected enable failure"):
        set_research_core_enabled_with_runner(
            tmp_path,
            True,
            CONTROL_CONFIRMATION,
            runner,
            audit_path,
            "2026-07-18T12:00:00+00:00",
        )

    assert runner.task_enabled == {
        "DOPEY_AccelerationCycle": False,
        "DOPEY_DailyRitual": False,
    }
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["outcome"] == "mutation_intent_fsynced"
    assert records[-1]["outcome"] == "failed_mutation_rolled_back_off"
    assert records[-1]["rollback_verified"] is True


def test_control_requires_exact_confirmation_without_task_mutation(tmp_path: Path) -> None:
    _prepare_commands(tmp_path)
    runner = _runner(tmp_path, False, "Disabled", False)
    audit_path = tmp_path / "audit.jsonl"
    with pytest.raises(ResearchCoreConfirmationError, match="paper_research_only"):
        set_research_core_enabled_with_runner(
            tmp_path,
            True,
            "paper-only",
            runner,
            audit_path,
            "2026-07-18T12:00:00+00:00",
        )
    assert runner.mutations == []
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["outcome"] == "rejected_invalid_confirmation"
    assert audit["confirmation_valid"] is False


def test_production_control_rechecks_constitution_before_scheduler_access(tmp_path: Path) -> None:
    _write_json(
        tmp_path,
        "artifacts/dopey/vnext/operational/constitution_state.json",
        {
            "paper_only": True,
            "live_blocked": False,
            "broker_authority": False,
            "order_authority": False,
            "order_construction_authority": False,
            "credential_access": False,
            "self_unlock_available": False,
        },
    )

    with pytest.raises(SchedulerVerificationError, match="execution seal assertions failed"):
        set_research_core_enabled(tmp_path, True, CONTROL_CONFIRMATION)

    audit_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "desktop"
        / "research_core_control_audit.jsonl"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["outcome"] == "rejected_unverified_execution_seal"
    assert audit["schedule_mutated"] is False


def _write_json(repository_root: Path, relative_path: str, value: dict[str, object]) -> None:
    path = repository_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _state_artifacts(repository_root: Path, include_world_model: bool) -> None:
    sealed = {"paper_only": True, "live_blocked": True}
    _write_json(
        repository_root,
        "artifacts/dopey/acceleration/readiness_acceleration_plan.json",
        {
            **sealed,
            "readiness_status": "not_action_ready",
            "active_symbol_count": 200,
            "starting_active_universe_target": 200,
            "bottlenecks": [
                {
                    "bottleneck_id": "forward_closed_trade_sample",
                    "priority": 1,
                    "current": 21,
                    "required": 100,
                    "remaining": 79,
                    "threshold_unchanged": True,
                    "acceleration": "settle forward evidence",
                }
            ],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/acceleration/schedule_plan.json",
        {
            **sealed,
            "due_lane_ids": ["nightly_validation"],
            "broker_lanes_present": False,
            "lanes": [
                {
                    "lane_id": "nightly_validation",
                    "due": True,
                    "last_run_status": "completed",
                }
            ],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/acceleration/universe_expansion_plan.json",
        {
            **sealed,
            "active_symbol_count": 200,
            "starting_active_universe_target": 200,
            "maximum_active_universe_size": 250,
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/universe/evolving_universe_summary.json",
        {
            **sealed,
            "artifact_type": "evolving_symbol_universe",
            "status": "evolved",
            "capacity_policy": "evolving_ranked_cap",
            "maximum_active_universe_size": 500,
            "active_after": 200,
            "available_active_slots": 300,
            "promoted_symbols": [],
            "demoted_symbols": [],
            "ranked_members": [
                {
                    "symbol": f"S{index:03d}",
                    "resulting_tier": "probation",
                }
                for index in range(200)
            ],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/llm_research/latest_cycle.json",
        {
            **sealed,
            "cycle_status": "complete_analysis_current",
            "analysis_action": "generated_initial_analysis",
            "issued_at": "2026-07-18T11:30:00+00:00",
            "provider_models": ["minimax/minimax-m3", "z-ai/glm-5.2", "gpt-5.6-sol"],
            "reported_openrouter_cost_usd": 0.02,
            "llm_output_evidence_class": "unverified_research_hypothesis",
            "synthesis_council": {
                "results": [
                    {
                        "structured_analysis": {
                            "summary": "Evidence supports more paper research, not promotion.",
                            "recommended_experiments": [{"title": "cost stress"}],
                            "abstain": False,
                        }
                    }
                ]
            },
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/runs/latest_dossier.json",
        {
            **sealed,
            "dossier_status": "complete_no_eligible_candidates",
            "run_id": "dossier-test",
            "headline": "No cohort survived every hard gate.",
            "run_directory": str(repository_root / "artifacts/dopey/runs/dossier-test"),
            "candidate_count": 12,
            "eligible_candidate_count": 0,
            "diagnostic_frontier_count": 3,
            "frontier_status": "diagnostic_only_no_eligible_candidates",
            "frontier_candidate_ids": ["breakout|long_call"],
            "trade_count": 285301,
            "gross_model_unit_pnl": -100.0,
            "net_model_unit_pnl": -200.0,
            "total_cost_model_units": 100.0,
            "selection_risk": {"effective_trials": 12, "mutation_attempts_recorded": 2988},
            "truth_state": {
                "real_history_used": True,
                "real_option_chain_used": False,
                "truth_decision": "insufficient_real_evidence",
                "fitness_decision": "hold_no_promotion",
            },
            "promotion_allowed": False,
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/evolution/mutation_genealogy.json",
        {
            **sealed,
            "explorer_status": "complete",
            "search_method": "deterministic_bounded_mutation_graph_not_a_star",
            "search_method_reason": "no admissible heuristic",
            "registry_record_count": 88,
            "node_count": 2,
            "edge_count": 1,
            "pruned_branch_count": 1,
            "duplicate_candidate_count": 0,
            "mutation_pareto_frontier_ids": ["child"],
            "historical_search_budget": {"mutation_attempt_count": 2988},
            "champion_dynamics": {"unique_champion_count": 3, "champion_change_count": 4, "longest_champion_streak": 10},
            "nodes": [
                {"node_id": "parent", "parent_id": "", "family": "test", "mutation_type": "root_parent", "status": "parent", "score": None, "score_delta": 0.0, "reasons": ["root"]},
                {"node_id": "child", "parent_id": "parent", "family": "test", "mutation_type": "threshold", "status": "degraded", "score": 0.5, "score_delta": -0.1, "reasons": ["degraded"]},
            ],
            "edges": [{"edge_id": "edge", "parent_id": "parent", "child_id": "child", "mutation_type": "threshold", "status": "degraded"}],
            "family_budgets": [{"family": "test", "attempt_count": 1, "allocation_share": 1.0, "frontier_candidate_count": 0, "rejected_count": 0, "degraded_count": 1, "concentration_alert": True}],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/options_oracle/binomial_oracle_validation.json",
        {
            **sealed,
            "validation_status": "complete",
            "passed_test_count": 10,
            "failed_test_count": 0,
            "test_count": 10,
            "pricing_source_tier": "model_priced_oracle",
            "real_option_chain_absent": True,
            "promotion_allowed": False,
            "convergence": [{"option_type": "call", "steps": 400, "absolute_error": 0.005}],
            "convergence_diagnostics": {"odd_even_price_gap": 0.004},
            "sensitivity_grid": [{"axis": "spot", "axis_value": 100.0}],
            "fixtures": {
                "american_put": {"early_exercise_node_count": 150},
                "discrete_dividend_american_call": {"early_exercise_node_count": 8},
            },
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/equity_swing/latest_context_settlement.json",
        {
            **sealed,
            "operation_status": "complete",
            "outcome_status": "no_matured_decisions",
            "decision_count": 4,
            "selected_decision_count": 4,
            "newly_resolved_count": 0,
            "resolved_count_after": 0,
            "unresolved_count_after": 4,
            "resolution_as_of": "2026-07-17",
            "decision_ledger_immutable": True,
            "history_evidence": {"loaded_row_count": 18000, "selective_hash_validation": True},
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/runs/latest_capital_exposure.json",
        {
            **sealed,
            "normalization_status": "complete_model_premium_diagnostic",
            "complete_candidate_count": 12,
            "candidate_count": 12,
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/contracts/latest_bundle_audit.json",
        {
            **sealed,
            "audit_status": "complete",
            "cross_artifact_issue_count": 0,
            "artifact_count": 5,
            "contract_registry_hash": "contract-registry-test",
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/evidence_intelligence/latest_cycle.json",
        {**sealed, "cycle_status": "complete"},
    )
    _write_json(
        repository_root,
        "dopey_data/history/history_dataset_manifest.json",
        {
            **sealed,
            "dataset_status": "valid_real_dataset",
            "data_files": [
                {"path": f"raw/S{index:03d}.csv", "symbols": [f"S{index:03d}"]}
                for index in range(200)
            ],
        },
    )
    if include_world_model:
        _write_json(
            repository_root,
            "artifacts/dopey/vnext/operational/world_model.json",
            {**sealed, "regimes": {"volatility": {"state": "neutral", "probability": 0.6}}},
        )
    _write_json(
        repository_root,
        "artifacts/dopey/vnext/operational/metacognition.json",
        {**sealed, "knowledge_boundary": "PARTIALLY_KNOWN", "primary_control": "CONTINUE"},
    )
    _write_json(
        repository_root,
        "artifacts/dopey/vnext/operational/homeostasis.json",
        {**sealed, "health_status": "stable", "variables": {"data_freshness": 0.9}},
    )
    _write_json(
        repository_root,
        "artifacts/dopey/vnext/operational/observatory_artifact.json",
        {
            "surface": "dashboard",
            "snapshot": {
                "accessIssues": [],
                "datasets": {
                    "hero_metrics": [{"action_ready": 0}],
                    "source_health": [
                        {
                            "source": "world",
                            "path": "artifacts/dopey/vnext/operational/world_model.json",
                            "status": "available",
                        }
                    ],
                },
            },
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/forward_walk/forward_walk_summary.json",
        {
            **sealed,
            "forward_walk_status": "forward_walk_marked",
            "closed_trade_count": 21,
            "open_position_count": 8,
            "not_live_ready": True,
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/forward_walk/forward_walk_ledger.json",
        {
            "open_positions": [
                {
                    **sealed,
                    "position_id": "fw-SPY-long_call-1",
                    "symbol": "SPY",
                    "candidate_strategy": "long_call",
                    "entry_date": "2026-07-17",
                }
            ],
            "closed_trades": [],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/playbook/option_extremes_report.json",
        {
            **sealed,
            "status": "complete",
            "top_winners": [
                {
                    "symbol": "SPY",
                    "contract_key": "SPY|2026-08-21|call|600",
                    "tail": "winner",
                    "roi_pct": 84.0,
                    "entry_date": "2026-07-16",
                    "exit_date": "2026-07-17",
                }
            ],
            "top_losers": [
                {
                    "symbol": "QQQ",
                    "contract_key": "QQQ|2026-08-21|put|500",
                    "tail": "loser",
                    "roi_pct": -62.0,
                    "entry_date": "2026-07-16",
                    "exit_date": "2026-07-17",
                }
            ],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/playbook/market_extremes_report.json",
        {
            **sealed,
            "status": "complete",
            "top_gainers": [
                {
                    "symbol": "SPY",
                    "direction": "up",
                    "direction_rank": 1,
                    "latest_return_pct": 4.2,
                    "rsi_14": 71.0,
                }
            ],
            "top_decliners": [
                {
                    "symbol": "QQQ",
                    "direction": "down",
                    "direction_rank": 1,
                    "latest_return_pct": -5.1,
                    "rsi_14": 28.0,
                }
            ],
        },
    )
    _write_json(
        repository_root,
        "artifacts/dopey/vnext/operational/constitution_state.json",
        {
            **sealed,
            "broker_authority": False,
            "order_authority": False,
            "order_construction_authority": False,
            "credential_access": False,
            "self_unlock_available": False,
        },
    )


def test_control_center_state_exposes_evolving_universe_under_500_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOPEY_PROVIDER_CONTROL_ROOT", str(tmp_path / "provider-control"))
    _prepare_commands(tmp_path)
    _state_artifacts(tmp_path, True)
    state = build_control_center_state_with_runner(
        tmp_path,
        _runner(tmp_path, True, "Ready", False),
        "2026-07-18T12:00:00+00:00",
    )
    universe = state["universe"]
    constitution = state["constitution"]
    analytics = state["analytics"]
    assert isinstance(universe, dict) and universe["active_symbol_count"] == 200
    assert len(universe["symbols"]) == 200
    assert universe["maximum_count"] == 500
    assert universe["capacity_policy"] == "evolving_ranked_cap"
    assert state["schedule_lanes"][0]["lane_id"] == "nightly_validation"
    assert state["observatory_datasets"]["hero_metrics"][0]["action_ready"] == 0
    assert state["world_model"] is not None
    assert state["metacognition"] is not None
    assert state["homeostasis"] is not None
    assert state["paper_record"] is not None
    assert state["paper_record"]["open_positions"][0]["symbol"] == "SPY"
    assert state["option_extremes"]["top_losers"][0]["symbol"] == "QQQ"
    assert state["market_extremes"]["top_gainers"][0]["symbol"] == "SPY"
    assert state["llm_research"]["cycle_status"] == "complete_analysis_current"
    assert state["strategy_dossier"]["eligible_candidate_count"] == 0
    assert state["mutation_genealogy"]["historical_search_budget"]["mutation_attempt_count"] == 2988
    assert state["binomial_oracle"]["passed_test_count"] == 10
    assert state["context_settlement"]["decision_ledger_immutable"] is True
    assert state["capital_exposure"]["complete_candidate_count"] == 12
    assert state["evidence_contract_audit"]["audit_status"] == "complete"
    assert state["llm_provider_control"]["instrument_mode"] == "both"
    assert state["llm_provider_control"]["providers"]["openrouter_hybrid"] is True
    assert state["llm_provider_control"]["api_key_value_exposed"] is False
    assert isinstance(constitution, dict) and constitution["execution_seal_state"] == "SEALED"
    assert isinstance(analytics, dict)
    assert analytics["paper_only"] is True and analytics["live_blocked"] is True
    assert analytics["telemetry"]["status"] == "unavailable_declared_topology_only"
    assert analytics["machine_learning"]["conformal"]["status"].startswith("unavailable_")
    assert state["headline"] == (
        "Paper research scheduler armed; execution sealed; nightly validation due; "
        "not action ready."
    )
    assert state["paper_only"] is False and state["live_blocked"] is False
    assert state["research_branch_paper_only"] is True


def test_control_center_reports_missing_sources_instead_of_silent_empty_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOPEY_PROVIDER_CONTROL_ROOT", str(tmp_path / "provider-control"))
    _prepare_commands(tmp_path)
    _state_artifacts(tmp_path, False)
    state = build_control_center_state_with_runner(
        tmp_path,
        _runner(tmp_path, False, "Disabled", False),
        "2026-07-18T12:00:00+00:00",
    )
    assert state["world_model"] is None
    issues = state["issues"]
    assert isinstance(issues, list)
    assert any(
        isinstance(issue, dict) and issue.get("issue_id") == "source_missing:world_model"
        for issue in issues
    )
    source_health = state["source_health"]
    assert isinstance(source_health, list)
    assert any(
        isinstance(source, dict)
        and source.get("source_id") == "world_model"
        and source.get("status") == "missing"
        for source in source_health
    )


def test_boundary_invalid_sources_are_quarantined_and_seal_faults_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOPEY_PROVIDER_CONTROL_ROOT", str(tmp_path / "provider-control"))
    _prepare_commands(tmp_path)
    _state_artifacts(tmp_path, True)
    _write_json(
        tmp_path,
        "artifacts/dopey/vnext/operational/world_model.json",
        {"paper_only": True, "live_blocked": False, "regimes": {"trend": "bullish"}},
    )
    _write_json(
        tmp_path,
        "artifacts/dopey/vnext/operational/constitution_state.json",
        {
            "paper_only": True,
            "live_blocked": False,
            "broker_authority": False,
            "order_authority": False,
            "order_construction_authority": False,
            "credential_access": False,
            "self_unlock_available": False,
        },
    )

    state = build_control_center_state_with_runner(
        tmp_path,
        _runner(tmp_path, True, "Ready", False),
        "2026-07-18T12:00:00+00:00",
    )

    assert state["world_model"] is None
    assert state["constitution"]["execution_seal_state"] == "FAULT"
    assert state["paper_only"] is False and state["live_blocked"] is False
    assert state["research_branch_paper_only"] is None
    assert _execution_seal_verified(state) is False
    assert any(
        issue.get("issue_id") == "source_boundary_invalid:world_model"
        for issue in state["issues"]
        if isinstance(issue, dict)
    )
