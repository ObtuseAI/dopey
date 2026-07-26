"""Diagnostic runner for inconclusive full pytest runs."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR


FULL_SUITE_STABILIZER_VERSION = "dopey-full-suite-stabilizer-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "validation"
SUMMARY_PATH = ARTIFACT_DIR / "full_suite_stabilizer_summary.json"
TEST_SHARD_PLAN_PATH = ARTIFACT_DIR / "test_shard_plan.json"
TEST_SHARD_PLAN_MD = REPORTS_DIR / "DOPEY_TEST_SHARD_PLAN.md"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    status: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool
    windows_flush_oserror_seen: bool
    stdout_tail: str
    stderr_tail: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_command(command: list[str], timeout_seconds: int, cwd: Path | str = REPO_ROOT) -> CommandResult:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        duration = round(time.monotonic() - start, 6)
        combined = f"{completed.stdout}\n{completed.stderr}"
        status = "pass" if completed.returncode == 0 else "fail"
        return CommandResult(
            command=command,
            status=status,
            exit_code=completed.returncode,
            duration_seconds=duration,
            timed_out=False,
            windows_flush_oserror_seen=detect_windows_flush_oserror(combined),
            stdout_tail=_tail(completed.stdout),
            stderr_tail=_tail(completed.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - start, 6)
        stdout = _decode_timeout_stream(exc.stdout)
        stderr = _decode_timeout_stream(exc.stderr)
        combined = f"{stdout}\n{stderr}"
        return CommandResult(
            command=command,
            status="inconclusive_timeout",
            exit_code=None,
            duration_seconds=duration,
            timed_out=True,
            windows_flush_oserror_seen=detect_windows_flush_oserror(combined),
            stdout_tail=_tail(stdout),
            stderr_tail=_tail(stderr),
        )


def collect_test_files(cwd: Path | str = REPO_ROOT) -> list[str]:
    tests_dir = Path(cwd) / "tests"
    if not tests_dir.exists():
        return []
    return sorted(str(path.relative_to(cwd)).replace("\\", "/") for path in tests_dir.glob("test_*.py"))


def identify_slow_groups(results: list[CommandResult], threshold_seconds: float) -> list[dict]:
    return [
        {
            "command": " ".join(result.command),
            "duration_seconds": result.duration_seconds,
            "status": result.status,
        }
        for result in results
        if result.duration_seconds >= threshold_seconds or result.timed_out
    ]


def run_full_suite_stabilizer(
    cwd: Path | str = REPO_ROOT,
    per_file_timeout_seconds: int = 20,
    max_files: int = 12,
    full_timeout_seconds: int = 120,
    write_summary: bool = True,
) -> dict:
    root = Path(cwd)
    collection = run_command([sys.executable, "-m", "pytest", "--collect-only", "-q"], full_timeout_seconds, root)
    files = collect_test_files(root)
    file_results: list[CommandResult] = []
    for file_name in files[:max_files]:
        file_results.append(run_command([sys.executable, "-m", "pytest", file_name, "-q"], per_file_timeout_seconds, root))
    full = run_command([sys.executable, "-m", "pytest", "-q"], full_timeout_seconds, root)
    results = [collection, *file_results, full]
    summary = {
        "full_suite_stabilizer_version": FULL_SUITE_STABILIZER_VERSION,
        "collection": collection.to_dict(),
        "test_files_detected": files,
        "file_results": [result.to_dict() for result in file_results],
        "full_suite": full.to_dict(),
        "slow_or_inconclusive_groups": identify_slow_groups(results, per_file_timeout_seconds),
        "timeout_recorded_as_pass": False,
        "windows_flush_oserror_seen": any(result.windows_flush_oserror_seen for result in results),
        "diagnostic_status": "full_pass" if full.status == "pass" else "full_inconclusive_or_failed",
        "recommended_targeted_fixes": _recommendations(results),
    }
    summary["test_shard_plan_path"] = str(TEST_SHARD_PLAN_PATH)
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    if write_summary:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        write_test_shard_plan(files, file_results, summary)
    return summary


def write_test_shard_plan(
    test_files: list[str],
    file_results: list[CommandResult],
    stabilizer_summary: dict,
) -> dict:
    duration_by_file = {
        _file_from_command(result.command): result.duration_seconds
        for result in file_results
    }
    slow_allowlist = [
        "tests/test_artifact_compaction_export_verifier.py",
        "tests/test_export_bundle_review_assistant.py",
    ]
    shards = [
        {
            "shard_id": f"pytest-file-{index + 1:03d}",
            "command": [sys.executable, "-m", "pytest", file_name, "-q"],
            "test_file": file_name,
            "observed_duration_seconds": duration_by_file.get(file_name),
            "slow_allowlisted": file_name in slow_allowlist,
        }
        for index, file_name in enumerate(test_files)
    ]
    plan = {
        "test_shard_plan_version": "dopey-test-shard-plan-v1",
        "collection_status": stabilizer_summary["collection"]["status"],
        "tests_collected_tail": stabilizer_summary["collection"]["stdout_tail"],
        "full_suite_status": stabilizer_summary["full_suite"]["status"],
        "timeout_recorded_as_pass": False,
        "slow_test_allowlist": slow_allowlist,
        "zero_dte_risk_test_files": [
            file_name for file_name in test_files
            if file_name in {
                "tests/test_zero_dte_risk_model.py",
                "tests/test_zero_dte_account_lifecycle.py",
                "tests/test_zero_dte_outcome_replay.py",
                "tests/test_zero_dte_threshold_optimizer.py",
                "tests/test_zero_dte_adversarial_corpus.py",
                "tests/test_zero_dte_cross_underlying_v2.py",
                "tests/test_hybrid_swing_0dte_v3.py",
                "tests/test_proof_weighted_allocator.py",
                "tests/test_portfolio_replay.py",
                "tests/test_portfolio_stress_ladder.py",
                "tests/test_incident_response.py",
                "tests/test_active_option_lifecycle_simulator.py",
                "tests/test_broker_readiness_preflight.py",
                "tests/test_read_only_detector_manual_approval_packet.py",
                "tests/test_read_only_detector_dry_run_validator.py",
                "tests/test_read_only_detector_approval_intake_validator.py",
                "tests/test_read_only_detector_approval_to_run_handoff_gate.py",
                "tests/test_read_only_detector_pre_run_safety_scanner.py",
                "tests/test_human_approved_read_only_broker_capability_detector.py",
                "tests/test_read_only_detector_post_run_evidence_contract.py",
                "tests/test_real_data_backtest_spine.py",
                "tests/test_model_repricer.py",
                "tests/test_real_signal_engines.py",
                "tests/test_honest_backtester.py",
                "tests/test_statistical_truth_layer.py",
                "tests/test_fitness_function_replacement.py",
                "tests/test_real_data_ingestion_plan.py",
                "tests/test_real_data_validation_stack.py",
                "tests/test_open_source_quant_stack_and_free_data_path.py",
                "tests/test_local_free_ohlcv_import_validator_and_history_activation.py",
                "tests/test_manual_free_ohlcv_staging_or_local_import_fix.py",
                "tests/test_operator_stage_max_progress.py",
                "tests/test_operator_reviewed_ohlcv_stage_rerun.py",
                "tests/test_open_source_autonomous_options_trader_max_completion.py",
                "tests/test_open_data_breakthrough_and_options_evidence_completion.py",
                "tests/test_finish_everything_openbb_model_priced_s_tier_completion.py",
                "tests/test_wealth_engine_market_vision_paper_tournament_completion.py",
                "tests/test_market_data_provider_install_and_fallback_expansion_v2.py",
                "tests/test_public_market_paper_champion_evolution_v1.py",
                "tests/test_public_market_signal_mutation_deepening_v2.py",
                "tests/test_public_paper_champion_hardening_and_deep_stress_v1.py",
                "tests/test_public_champion_repair_and_retune_v1.py",
                "tests/test_public_signal_research_breakthrough_v1.py",
                "tests/test_public_signal_research_breakthrough_v2.py",
                "tests/test_public_signal_research_breakthrough_v3.py",
                "tests/test_public_signal_research_breakthrough_v4.py",
                "tests/test_public_signal_research_breakthrough_v5.py",
                "tests/test_public_signal_research_breakthrough_v6.py",
                "tests/test_public_signal_research_breakthrough_v7.py",
            }
        ],
        "public_signal_research_breakthrough_v7_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v7.py"
        ],
        "public_signal_research_breakthrough_v6_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v6.py"
        ],
        "public_signal_research_breakthrough_v5_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v5.py"
        ],
        "public_signal_research_breakthrough_v4_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v4.py"
        ],
        "public_signal_research_breakthrough_v3_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v3.py"
        ],
        "public_signal_research_breakthrough_v2_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v2.py"
        ],
        "public_signal_research_breakthrough_v1_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_signal_research_breakthrough_v1.py"
        ],
        "public_champion_repair_v1_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_champion_repair_and_retune_v1.py"
        ],
        "public_paper_champion_hardening_v1_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_paper_champion_hardening_and_deep_stress_v1.py"
        ],
        "wealth_engine_test_files": [
            file_name for file_name in test_files
            if file_name in {
                "tests/test_wealth_engine_market_vision_paper_tournament_completion.py",
                "tests/test_market_data_provider_install_and_fallback_expansion_v2.py",
                "tests/test_public_market_paper_champion_evolution_v1.py",
            }
        ],
        "public_signal_mutation_deepening_v2_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_public_market_signal_mutation_deepening_v2.py"
        ],
        "open_source_autonomous_options_trader_tests": [
            file_name for file_name in test_files
            if file_name == "tests/test_open_source_autonomous_options_trader_max_completion.py"
        ],
        "open_data_breakthrough_tests": [
            file_name for file_name in test_files
            if file_name == "tests/test_open_data_breakthrough_and_options_evidence_completion.py"
        ],
        "finish_everything_openbb_tests": [
            file_name for file_name in test_files
            if file_name == "tests/test_finish_everything_openbb_model_priced_s_tier_completion.py"
        ],
        "local_free_ohlcv_stack_test_files": [
            file_name for file_name in test_files
            if file_name in {
                "tests/test_local_free_ohlcv_import_validator_and_history_activation.py",
                "tests/test_manual_free_ohlcv_staging_or_local_import_fix.py",
                "tests/test_operator_stage_max_progress.py",
                "tests/test_operator_reviewed_ohlcv_stage_rerun.py",
                "tests/test_public_market_paper_champion_evolution_v1.py",
            }
        ],
        "real_data_validation_stack_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_real_data_validation_stack.py"
        ],
        "open_source_free_data_path_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_open_source_quant_stack_and_free_data_path.py"
        ],
        "real_data_ingestion_plan_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_real_data_ingestion_plan.py"
        ],
        "fitness_function_replacement_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_fitness_function_replacement.py"
        ],
        "statistical_truth_layer_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_statistical_truth_layer.py"
        ],
        "honest_backtester_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_honest_backtester.py"
        ],
        "real_signal_engine_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_real_signal_engines.py"
        ],
        "approval_intake_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_read_only_detector_approval_intake_validator.py"
        ],
        "approval_to_run_handoff_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_read_only_detector_approval_to_run_handoff_gate.py"
        ],
        "pre_run_safety_scanner_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_read_only_detector_pre_run_safety_scanner.py"
        ],
        "proof_weighted_allocation_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_proof_weighted_allocator.py"
        ],
        "portfolio_replay_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_portfolio_replay.py"
        ],
        "portfolio_stress_ladder_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_portfolio_stress_ladder.py"
        ],
        "incident_response_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_incident_response.py"
        ],
        "active_lifecycle_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_active_option_lifecycle_simulator.py"
        ],
        "broker_readiness_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_broker_readiness_preflight.py"
        ],
        "adversarial_corpus_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_zero_dte_adversarial_corpus.py"
        ],
        "cross_underlying_v2_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_zero_dte_cross_underlying_v2.py"
        ],
        "hybrid_swing_0dte_v3_test_files": [
            file_name for file_name in test_files
            if file_name == "tests/test_hybrid_swing_0dte_v3.py"
        ],
        "artifact_writing_tests_sequential": [
            file_name for file_name in test_files
            if file_name in {
                "tests/test_real_data_backtest_spine.py",
                "tests/test_zero_dte_adversarial_corpus.py",
                "tests/test_zero_dte_cross_underlying_v2.py",
                "tests/test_hybrid_swing_0dte_v3.py",
                "tests/test_zero_dte_threshold_optimizer.py",
                "tests/test_active_policy_integration.py",
                "tests/test_proof_weighted_allocator.py",
                "tests/test_portfolio_replay.py",
                "tests/test_portfolio_stress_ladder.py",
                "tests/test_incident_response.py",
                "tests/test_active_option_lifecycle_simulator.py",
                "tests/test_broker_readiness_preflight.py",
                "tests/test_read_only_detector_manual_approval_packet.py",
                "tests/test_read_only_detector_dry_run_validator.py",
                "tests/test_read_only_detector_approval_intake_validator.py",
                "tests/test_read_only_detector_approval_to_run_handoff_gate.py",
                "tests/test_read_only_detector_pre_run_safety_scanner.py",
                "tests/test_human_approved_read_only_broker_capability_detector.py",
                "tests/test_read_only_detector_post_run_evidence_contract.py",
                "tests/test_reporting_dashboard_artifacts.py",
                "tests/test_artifact_compaction_export_verifier.py",
                "tests/test_export_bundle_review_assistant.py",
                "tests/test_model_repricer.py",
                "tests/test_real_signal_engines.py",
                "tests/test_honest_backtester.py",
                "tests/test_statistical_truth_layer.py",
                "tests/test_fitness_function_replacement.py",
                "tests/test_real_data_ingestion_plan.py",
                "tests/test_real_data_validation_stack.py",
                "tests/test_open_source_quant_stack_and_free_data_path.py",
                "tests/test_local_free_ohlcv_import_validator_and_history_activation.py",
                "tests/test_operator_reviewed_ohlcv_stage_rerun.py",
            }
        ],
        "export_review_slow_test_files": [
            file_name for file_name in test_files
            if file_name in {"tests/test_export_bundle_review_assistant.py", "tests/test_artifact_compaction_export_verifier.py"}
        ],
        "split_suite_lanes": {
            "core_policy_tests": [
                file_name for file_name in test_files
                if file_name in {"tests/test_active_policy_integration.py", "tests/test_active_trading_policy.py"}
            ],
            "zero_dte_risk_replay_optimizer_tests": [
                file_name for file_name in test_files
                if file_name in {"tests/test_zero_dte_risk_model.py", "tests/test_zero_dte_outcome_replay.py", "tests/test_zero_dte_threshold_optimizer.py"}
            ],
            "adversarial_corpus_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_zero_dte_adversarial_corpus.py"
            ],
            "cross_underlying_v2_corpus_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_zero_dte_cross_underlying_v2.py"
            ],
            "hybrid_swing_0dte_v3_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_hybrid_swing_0dte_v3.py"
            ],
            "proof_weighted_allocation_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_proof_weighted_allocator.py"
            ],
            "portfolio_replay_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_portfolio_replay.py"
            ],
            "portfolio_stress_ladder_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_portfolio_stress_ladder.py"
            ],
            "incident_response_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_incident_response.py"
            ],
            "active_lifecycle_simulator_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_active_option_lifecycle_simulator.py"
            ],
            "broker_readiness_preflight_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_broker_readiness_preflight.py"
            ],
            "manual_approval_packet_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_read_only_detector_manual_approval_packet.py"
            ],
            "read_only_detector_dry_run_validator_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_read_only_detector_dry_run_validator.py"
            ],
            "approval_intake_validator_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_read_only_detector_approval_intake_validator.py"
            ],
            "approval_to_run_handoff_gate_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_read_only_detector_approval_to_run_handoff_gate.py"
            ],
            "pre_run_safety_scanner_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_read_only_detector_pre_run_safety_scanner.py"
            ],
            "human_approved_read_only_detector_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_human_approved_read_only_broker_capability_detector.py"
            ],
            "read_only_detector_post_run_evidence_contract_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_read_only_detector_post_run_evidence_contract.py"
            ],
            "real_data_backtest_spine_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_real_data_backtest_spine.py"
            ],
            "model_repricer_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_model_repricer.py"
            ],
            "real_signal_engine_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_real_signal_engines.py"
            ],
            "honest_backtester_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_honest_backtester.py"
            ],
            "statistical_truth_layer_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_statistical_truth_layer.py"
            ],
            "fitness_function_replacement_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_fitness_function_replacement.py"
            ],
            "real_data_ingestion_plan_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_real_data_ingestion_plan.py"
            ],
            "real_data_validation_stack_tests": [
                file_name for file_name in test_files
                if file_name == "tests/test_real_data_validation_stack.py"
            ],
            "local_free_ohlcv_stack_tests": [
                file_name for file_name in test_files
                if file_name in {
                    "tests/test_local_free_ohlcv_import_validator_and_history_activation.py",
                    "tests/test_manual_free_ohlcv_staging_or_local_import_fix.py",
                    "tests/test_operator_reviewed_ohlcv_stage_rerun.py",
                }
            ],
            "reporting_export_review_tests": [
                file_name for file_name in test_files
                if file_name in {"tests/test_reporting_dashboard_artifacts.py", "tests/test_artifact_compaction_export_verifier.py", "tests/test_export_bundle_review_assistant.py"}
            ],
            "full_audit_tests": [
                file_name for file_name in test_files
                if file_name in {"tests/test_offline_evidence_replay_audit.py", "tests/test_full_validation_stabilizer.py"}
            ],
        },
        "recommended_export_review_slow_shard_command": [sys.executable, "-m", "pytest", "tests/test_export_bundle_review_assistant.py", "-q"],
        "recommended_split_suite_sequence": [
            "core active policy",
            "account ledger / rotation / PaperBroker",
            "0DTE risk/replay",
            "threshold optimizer",
            "adversarial v1 corpus",
            "cross-underlying v2 corpus",
            "hybrid swing/0DTE v3 corpus",
            "proof-weighted allocation",
            "portfolio replay",
            "stress ladder / crisis throttles",
            "kill-switch rehearsal / incident response",
            "active lifecycle simulator",
            "broker-readiness preflight / read-only boundary simulator",
            "manual approval packet",
            "read-only detector dry-run fixture validator",
            "approval-intake validator",
            "approval-to-run handoff gate",
            "pre-run safety scanner",
            "human-approved read-only detector",
            "read-only detector post-run evidence contract",
            "real-data backtest spine",
            "model repricer",
            "real signal engines",
            "honest backtester",
            "statistical truth layer",
            "fitness function replacement",
            "real data ingestion plan",
            "real data validation stack",
            "open-source quant stack and free-data path",
            "open-source autonomous options trader max completion",
            "wealth-engine market vision and paper tournament completion",
            "audit/report/export/review",
        ],
        "recommended_long_timeout_command": [sys.executable, "-m", "pytest", "-q"],
        "recommended_long_timeout_seconds": 900,
        "split_suite_command_plan": shards,
        "paper_only": True,
        "live_blocked": True,
    }
    plan["reproducibility_hash"] = reproducibility_hash(plan)
    TEST_SHARD_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_SHARD_PLAN_PATH.write_text(json.dumps(plan, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    TEST_SHARD_PLAN_MD.write_text(_render_shard_plan_markdown(plan), encoding="utf-8")
    return plan


def detect_windows_flush_oserror(output: str) -> bool:
    return "OSError: [Errno 22] Invalid argument" in output and "flush" in output.lower()


def timeout_result(command: list[str], timeout_seconds: int) -> dict:
    return {
        "command": command,
        "status": "inconclusive_timeout",
        "timed_out": True,
        "timeout_seconds": timeout_seconds,
        "timeout_recorded_as_pass": False,
    }


def _file_from_command(command: list[str]) -> str:
    for value in command:
        if value.startswith("tests/") or value.startswith("tests\\"):
            return value.replace("\\", "/")
    return ""


def _render_shard_plan_markdown(plan: dict) -> str:
    lines = ["# DOPEY Test Shard Plan", ""]
    lines.append("- fixture_only: `true`")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append(f"- full_suite_status: `{plan['full_suite_status']}`")
    lines.append(f"- timeout_recorded_as_pass: `{str(plan['timeout_recorded_as_pass']).lower()}`")
    lines.append(f"- recommended_long_timeout_seconds: `{plan['recommended_long_timeout_seconds']}`")
    lines.append("")
    lines.append("## Slow-Test Allowlist")
    for file_name in plan["slow_test_allowlist"]:
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## 0DTE Risk And Replay Test Shards")
    for file_name in plan.get("zero_dte_risk_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Adversarial Corpus Test Shards")
    for file_name in plan.get("adversarial_corpus_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Cross-Underlying V2 Corpus Test Shards")
    for file_name in plan.get("cross_underlying_v2_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Hybrid Swing 0DTE V3 Test Shards")
    for file_name in plan.get("hybrid_swing_0dte_v3_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Proof-Weighted Allocation Test Shards")
    for file_name in plan.get("proof_weighted_allocation_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Portfolio Replay Test Shards")
    for file_name in plan.get("portfolio_replay_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Portfolio Stress Ladder Test Shards")
    for file_name in plan.get("portfolio_stress_ladder_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Kill-Switch Incident Response Test Shards")
    for file_name in plan.get("incident_response_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Manual Approval Packet Test Shards")
    for file_name in plan.get("manual_approval_packet_tests", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Read-Only Detector Dry-Run Validator Test Shards")
    for file_name in plan.get("read_only_detector_dry_run_validator_tests", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Approval Intake Validator Test Shards")
    for file_name in plan.get("approval_intake_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Approval-To-Run Handoff Gate Test Shards")
    for file_name in plan.get("approval_to_run_handoff_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Pre-Run Safety Scanner Test Shards")
    for file_name in plan.get("pre_run_safety_scanner_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Real-Data Backtest Spine Test Shards")
    for file_name in plan.get("split_suite_lanes", {}).get("real_data_backtest_spine_tests", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Model Repricer Test Shards")
    for file_name in plan.get("split_suite_lanes", {}).get("model_repricer_tests", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Real Data Ingestion Plan Test Shards")
    for file_name in plan.get("real_data_ingestion_plan_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Real Data Validation Stack Test Shards")
    for file_name in plan.get("real_data_validation_stack_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Local Free OHLCV Stack Test Shards")
    for file_name in plan.get("local_free_ohlcv_stack_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Open-Source Free-Data Path Test Shards")
    for file_name in plan.get("open_source_free_data_path_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Wealth Engine Test Shards")
    for file_name in plan.get("wealth_engine_test_files", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Artifact-Writing Tests Run Sequentially")
    for file_name in plan.get("artifact_writing_tests_sequential", []):
        lines.append(f"- `{file_name}`")
    lines.append("")
    lines.append("## Export Review Slow Shard")
    lines.append(f"- `{' '.join(plan['recommended_export_review_slow_shard_command'])}`")
    lines.append("")
    lines.append("## Split Suite Commands")
    for shard in plan["split_suite_command_plan"]:
        command = " ".join(shard["command"])
        marker = " slow_allowlisted" if shard["slow_allowlisted"] else ""
        lines.append(f"- `{shard['shard_id']}`{marker}: `{command}`")
    return "\n".join(lines) + "\n"


def _recommendations(results: list[CommandResult]) -> list[str]:
    recommendations: list[str] = []
    if any(result.timed_out for result in results):
        recommendations.append("split full pytest by file and isolate timed-out group before claiming full validation")
    if any(result.windows_flush_oserror_seen for result in results):
        recommendations.append("capture pytest output to files on Windows to avoid terminal flush OSError masking final status")
    if not recommendations:
        recommendations.append("keep targeted active policy, audit, reporting, and export smokes in the validation ladder")
    return recommendations


def _decode_timeout_stream(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _tail(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def main() -> int:
    summary = run_full_suite_stabilizer(
        per_file_timeout_seconds=6,
        max_files=6,
        full_timeout_seconds=30,
    )
    print(json.dumps({
        "diagnostic_status": summary["diagnostic_status"],
        "collection_status": summary["collection"]["status"],
        "full_suite_status": summary["full_suite"]["status"],
        "summary_path": str(SUMMARY_PATH),
        "timeout_recorded_as_pass": summary["timeout_recorded_as_pass"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
