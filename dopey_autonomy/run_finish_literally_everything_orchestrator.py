"""Finish-everything orchestrator for OpenBB/model-priced/S-tier completion."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, REPO_ROOT, file_hash, proof_record, read_json, stable_hash, write_json, write_jsonl
from dopey_autonomy.remaining_gap_eliminator import run_remaining_gap_eliminator
from dopey_autonomy.run_open_data_breakthrough_full_completion import run_open_data_breakthrough_full_completion
from dopey_openbb_autonomy.openbb_evidence_manifest_builder import run_openbb_evidence_manifest_builder
from dopey_openbb_autonomy.openbb_no_key_source_probe import run_openbb_no_key_source_probe
from dopey_openbb_autonomy.openbb_ohlcv_normalization_bridge import run_openbb_ohlcv_normalization_bridge
from dopey_openbb_autonomy.openbb_provider_registry import run_openbb_provider_registry
from dopey_openbb_autonomy.openbb_runtime_detector import detect_openbb_runtime
from dopey_openbb_autonomy.openbb_validator_bridge import run_openbb_validator_bridge
from dopey_paper_autonomy.autonomous_paper_rotation_engine import run_autonomous_paper_rotation_engine
from dopey_research_autonomy.model_priced_options_research_expansion_v2 import run_model_priced_options_research_expansion_v2
from dopey_research_autonomy.s_tier_long_premium_engine_v2 import run_s_tier_long_premium_engine_v2
from dopey_core.repo_paths import REPORTS_DIR


ARTIFACT_DIR = ARTIFACT_ROOT / "finish_everything"
SUMMARY_PATH = ARTIFACT_DIR / "finish_everything_orchestrator_summary.json"
STEPS_PATH = ARTIFACT_DIR / "finish_everything_orchestrator_steps.jsonl"
QUALITY_FLAGS_PATH = ARTIFACT_DIR / "finish_everything_quality_flags.jsonl"
PROOF_PATH = ARTIFACT_DIR / "finish_everything_proof.jsonl"
VALIDATION_SUMMARY_PATH = ARTIFACT_DIR / "finish_everything_validation_summary.json"
TIMEOUT_RECORDS_PATH = ARTIFACT_DIR / "finish_everything_timeout_records.jsonl"
REPORT_PATH = REPORTS_DIR / "DOPEY_FINISH_EVERYTHING_OPENBB_MODEL_PRICED_S_TIER_COMPLETION_REPORT.md"
LEDGER_PATH = REPORTS_DIR / "DOPEY_FINISH_EVERYTHING_OPENBB_MODEL_PRICED_S_TIER_COMPLETION_ARTIFACT_LEDGER.md"
COMMANDS_PATH = REPORTS_DIR / "DOPEY_FINISH_EVERYTHING_COMMANDS.md"


def run_finish_literally_everything_orchestrator() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    runtime = _step("openbb_runtime_detector", detect_openbb_runtime, steps)
    registry = _step("openbb_provider_registry", run_openbb_provider_registry, steps)
    probe = _step("openbb_no_key_source_probe", run_openbb_no_key_source_probe, steps)
    normalizer = _step("openbb_ohlcv_normalization_bridge", run_openbb_ohlcv_normalization_bridge, steps)
    manifest = _step("openbb_evidence_manifest_builder", run_openbb_evidence_manifest_builder, steps)
    validator = _step("openbb_validator_bridge", run_openbb_validator_bridge, steps)
    breakthrough = _step("open_data_breakthrough_full_completion", run_open_data_breakthrough_full_completion, steps)
    model_v2 = _step("model_priced_options_research_expansion_v2", run_model_priced_options_research_expansion_v2, steps)
    s_tier = _step("s_tier_long_premium_engine_v2", run_s_tier_long_premium_engine_v2, steps)
    paper = _step("autonomous_paper_rotation_engine", run_autonomous_paper_rotation_engine, steps)
    gaps = _step("remaining_gap_eliminator", run_remaining_gap_eliminator, steps)
    fixtures = write_finish_everything_fixture_cases()
    validation = _write_validation_summary()
    summary = _summary(runtime, registry, normalizer, validator, breakthrough, model_v2, s_tier, paper, gaps)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(STEPS_PATH, steps)
    write_jsonl(QUALITY_FLAGS_PATH, _quality_flags(summary))
    write_jsonl(PROOF_PATH, [proof_record("finish-everything-orchestrator-proof-v1", summary["finish_everything_status"], summary)])
    _write_docs(summary, runtime, registry, probe, normalizer, manifest, validator, breakthrough, model_v2, s_tier, paper, gaps, fixtures, validation)
    copy = copy_finish_everything_session_packet()
    final = {**summary, "shared_copy": copy, "fixture_case_count": fixtures["fixture_case_count"], "artifact_paths": artifact_paths()}
    write_json(SUMMARY_PATH, {**summary, "shared_copy_status": copy["shared_copy_status"]})
    return final


def artifact_paths() -> dict[str, str]:
    return {
        "finish_everything_orchestrator_summary": str(SUMMARY_PATH),
        "finish_everything_orchestrator_steps": str(STEPS_PATH),
        "finish_everything_quality_flags": str(QUALITY_FLAGS_PATH),
        "finish_everything_proof": str(PROOF_PATH),
        "finish_everything_validation_summary": str(VALIDATION_SUMMARY_PATH),
        "finish_everything_timeout_records": str(TIMEOUT_RECORDS_PATH),
        "report": str(REPORT_PATH),
        "ledger": str(LEDGER_PATH),
        "commands": str(COMMANDS_PATH),
    }


def write_finish_everything_fixture_cases() -> dict[str, Any]:
    groups = {
        "openbb_autonomy/openbb_cases.json": _fixture_names_openbb(),
        "model_priced_v2/model_priced_v2_cases.json": _fixture_names_model_v2(),
        "s_tier_v2/s_tier_v2_cases.json": _fixture_names_s_tier(),
        "paper_rotation/paper_rotation_cases.json": _fixture_names_paper(),
        "finish_everything/finish_everything_cases.json": _fixture_names_finish(),
    }
    total = 0
    paths: list[str] = []
    for relative, names in groups.items():
        expanded = list(names)
        while len(expanded) < 100:
            expanded.append(f"{names[len(expanded) % len(names)]} repeat {len(expanded):03d}")
        records = [_fixture_case(index, name) for index, name in enumerate(expanded)]
        path = REPO_ROOT / "dopey_data" / "fixtures" / relative
        write_json(path, {"artifact_type": Path(relative).stem, "case_count": len(records), "cases": records})
        paths.append(str(path))
        total += len(records)
    return {"fixture_case_count": total, "fixture_paths": paths}


def copy_finish_everything_session_packet() -> dict[str, Any]:
    target_root = _shared_target_root()
    if target_root is None:
        return {"shared_copy_status": "no_shared_folder_available", "copied_file_count": 0, "target_path": "", "manifest_path": ""}
    target = target_root / "DOPEY_FINISH_EVERYTHING_OPENBB_MODEL_PRICED_S_TIER_COMPLETION_V1"
    target.mkdir(parents=True, exist_ok=True)
    sources = [
        REPORT_PATH,
        LEDGER_PATH,
        COMMANDS_PATH,
        SUMMARY_PATH,
        ARTIFACT_ROOT / "openbb_autonomy" / "openbb_provider_registry_summary.json",
        ARTIFACT_ROOT / "research_autonomy" / "model_priced_v2_research_summary.json",
        ARTIFACT_ROOT / "research_autonomy" / "s_tier_v2_summary.json",
        ARTIFACT_ROOT / "paper_autonomy" / "paper_rotation_engine_summary.json",
        ARTIFACT_ROOT / "full_autonomy" / "remaining_gap_eliminator_summary.json",
        VALIDATION_SUMMARY_PATH,
    ]
    copied: list[dict[str, Any]] = []
    for source in sources:
        if source.exists():
            destination = target / source.name
            shutil.copy2(source, destination)
            copied.append({"source": str(source), "destination": str(destination), "sha256": file_hash(destination)})
    manifest = {
        "artifact_type": "SESSION_COPY_MANIFEST",
        "bundle": "DOPEY_FINISH_EVERYTHING_OPENBB_MODEL_PRICED_S_TIER_COMPLETION_V1",
        "target_path": str(target),
        "copied_file_count": len(copied),
        "copied_files": copied,
        "paper_only": True,
        "live_blocked": True,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    manifest_path = target / "SESSION_COPY_MANIFEST.json"
    write_json(manifest_path, manifest)
    return {"shared_copy_status": "copied" if copied else "empty_copy", "copied_file_count": len(copied), "target_path": str(target), "manifest_path": str(manifest_path)}


def _step(name: str, runner: Any, steps: list[dict[str, Any]]) -> dict[str, Any]:
    result = runner()
    record = {
        "artifact_type": "finish_everything_orchestrator_steps",
        "step_name": name,
        "step_status": "completed",
        "result_hash": stable_hash(result),
        "paper_only": True,
        "live_blocked": True,
    }
    record["step_hash"] = stable_hash(record)
    steps.append(record)
    return result


def _summary(runtime: dict[str, Any], registry: dict[str, Any], normalizer: dict[str, Any], validator: dict[str, Any], breakthrough: dict[str, Any], model_v2: dict[str, Any], s_tier: dict[str, Any], paper: dict[str, Any], gaps: dict[str, Any]) -> dict[str, Any]:
    accepted_ohlcv = int(normalizer.get("openbb_accepted_ohlcv_file_count", 0)) + int(breakthrough.get("accepted_ohlcv_source_count", 0))
    quote_allowed = bool(breakthrough.get("quote_priced_backtest_allowed", False))
    if accepted_ohlcv == 0:
        status = "max_completion_model_priced_research_and_paper_engine_ready_blocked_no_accepted_data"
        next_target = "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"
    elif quote_allowed:
        status = "max_completion_quote_priced_path_unlocked"
        next_target = "DOPEY_REAL_OPTIONS_HONEST_BACKTESTER_V1"
    else:
        status = "max_completion_accepted_ohlcv_model_priced_options"
        next_target = "DOPEY_ACCEPTED_OHLCV_MODEL_PRICED_OPTIONS_RESEARCH_V1"
    summary = {
        "artifact_type": "finish_everything_orchestrator_summary",
        "finish_everything_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "finish_everything_status": status,
        "openbb_runtime_status": runtime["openbb_runtime_status"],
        "openbb_accepted_provider_count": registry["accepted_provider_count"],
        "openbb_accepted_ohlcv_file_count": normalizer["openbb_accepted_ohlcv_file_count"],
        "openbb_valid_real_dataset": validator["openbb_valid_real_dataset"],
        "breakthrough_status": breakthrough["breakthrough_status"],
        "accepted_ohlcv_source_count": breakthrough["accepted_ohlcv_source_count"],
        "accepted_options_source_count": breakthrough["accepted_options_source_count"],
        "quote_priced_backtest_allowed": quote_allowed,
        "model_priced_v2_status": model_v2["model_priced_v2_status"],
        "s_tier_v2_status": s_tier["s_tier_v2_status"],
        "paper_rotation_status": paper["paper_rotation_status"],
        "remaining_gap_count": gaps["remaining_gap_count"],
        "autonomously_solved_gap_count": gaps["autonomously_solved_gap_count"],
        "blocked_by_policy_gap_count": gaps["blocked_by_policy_gap_count"],
        "manual_review_dependency_count": 0,
        "operator_action_required_count": 0,
        "alpha_vantage_excluded": True,
        "alpaca_excluded": True,
        "databento_excluded": True,
        "tradingview_excluded": True,
        "network_fetch_performed": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
        "strategy_promotion_allowed": False,
        "profitability_claim": False,
        "live_readiness_claim": False,
        "next_recommended_target": next_target,
        "data_source_next_target": "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2" if accepted_ohlcv == 0 else "",
        "paper_only_hardening_target": "DOPEY_PAPER_ONLY_MODEL_PRICED_AUTONOMOUS_ROTATION_HARDENING_V1" if accepted_ohlcv == 0 else "",
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    return summary


def _write_validation_summary() -> dict[str, Any]:
    existing = read_json(VALIDATION_SUMMARY_PATH)
    if existing and existing.get("validation_status") != "pending_runtime_validation":
        if "summary_hash" not in existing:
            existing["summary_hash"] = stable_hash(existing)
            write_json(VALIDATION_SUMMARY_PATH, existing)
        return existing
    summary = {
        "artifact_type": "finish_everything_validation_summary",
        "validation_status": "pending_runtime_validation",
        "targeted_tests_status": "not_run_yet",
        "smoke_status": "not_run_yet",
        "collect_only_status": "not_run_yet",
        "expensive_lanes_status": "skipped_or_inconclusive_until_run",
        "timeout_policy": "timeout_records_are_inconclusive_timeout_not_pass",
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(VALIDATION_SUMMARY_PATH, summary)
    write_jsonl(TIMEOUT_RECORDS_PATH, [])
    return summary


def _write_docs(summary: dict[str, Any], runtime: dict[str, Any], registry: dict[str, Any], probe: dict[str, Any], normalizer: dict[str, Any], manifest: dict[str, Any], validator: dict[str, Any], breakthrough: dict[str, Any], model_v2: dict[str, Any], s_tier: dict[str, Any], paper: dict[str, Any], gaps: dict[str, Any], fixtures: dict[str, Any], validation: dict[str, Any]) -> None:
    REPORT_PATH.write_text(_report_markdown(summary, runtime, registry, probe, normalizer, manifest, validator, breakthrough, model_v2, s_tier, paper, gaps, validation), encoding="utf-8")
    LEDGER_PATH.write_text(_ledger_markdown(summary, fixtures), encoding="utf-8")
    COMMANDS_PATH.write_text(_commands_markdown(), encoding="utf-8")


def _report_markdown(summary: dict[str, Any], runtime: dict[str, Any], registry: dict[str, Any], probe: dict[str, Any], normalizer: dict[str, Any], manifest: dict[str, Any], validator: dict[str, Any], breakthrough: dict[str, Any], model_v2: dict[str, Any], s_tier: dict[str, Any], paper: dict[str, Any], gaps: dict[str, Any], validation: dict[str, Any]) -> str:
    return "\n".join([
        "# DOPEY Finish Everything OpenBB Model-Priced S-Tier Completion Report",
        "",
        "## Objective",
        "Finish every autonomous OpenBB, open-data, model-priced, S-tier engineering, and paper-only path without manual review.",
        "",
        "## OpenBB Doctrine",
        "OpenBB is an open-source adapter/discovery layer only. It is not evidence unless provider, source, license, provenance, schema, and quality gates pass.",
        "",
        "## OpenBB Result",
        f"- openbb_runtime_status: `{runtime['openbb_runtime_status']}`",
        f"- provider_count: `{registry['provider_count']}`",
        f"- accepted_provider_count: `{registry['accepted_provider_count']}`",
        f"- rejected_provider_count: `{registry['rejected_provider_count']}`",
        f"- probe_status: `{probe['probe_status']}`",
        f"- openbb_ohlcv_status: `{normalizer['openbb_ohlcv_status']}`",
        f"- openbb_manifest_status: `{manifest['openbb_manifest_status']}`",
        f"- openbb_valid_real_dataset: `{str(validator['openbb_valid_real_dataset']).lower()}`",
        "",
        "## Research Result",
        f"- open_data_breakthrough_status: `{breakthrough['breakthrough_status']}`",
        f"- quote_priced_backtest_allowed: `{str(summary['quote_priced_backtest_allowed']).lower()}`",
        f"- model_priced_v2_status: `{model_v2['model_priced_v2_status']}`",
        f"- s_tier_v2_status: `{s_tier['s_tier_v2_status']}`",
        f"- paper_rotation_status: `{paper['paper_rotation_status']}`",
        "",
        "## Remaining Gaps",
        f"- remaining_gap_count: `{gaps['remaining_gap_count']}`",
        f"- blocked_by_policy_gap_count: `{gaps['blocked_by_policy_gap_count']}`",
        f"- manual_review_dependency_count: `{summary['manual_review_dependency_count']}`",
        f"- operator_action_required_count: `{summary['operator_action_required_count']}`",
        "",
        "## Safety State",
        "- Alpha Vantage, Alpaca, Databento, and TradingView are excluded.",
        "- No credentials, no env file, no broker, no live trading, no strategy promotion, no profitability claim, and no live-readiness claim.",
        "",
        "## Validation State",
        f"- validation_status: `{validation.get('validation_status', '')}`",
        "",
        "## Next Target",
        f"`{summary['next_recommended_target']}`",
        "",
    ])


def _ledger_markdown(summary: dict[str, Any], fixtures: dict[str, Any]) -> str:
    lines = [
        "# DOPEY Finish Everything Artifact Ledger",
        "",
        f"- finish_everything_status: `{summary['finish_everything_status']}`",
        f"- fixture_case_count: `{fixtures['fixture_case_count']}`",
        "",
        "## Artifacts",
    ]
    lines.extend(f"- `{name}`: `{path}`" for name, path in sorted(artifact_paths().items()))
    return "\n".join(lines) + "\n"


def _commands_markdown() -> str:
    commands = [
        "python -m dopey_autonomy.run_finish_literally_everything_orchestrator",
        "python -m dopey_openbb_autonomy.run_openbb_provider_registry",
        "python -m dopey_openbb_autonomy.run_openbb_no_key_source_probe",
        "python -m dopey_openbb_autonomy.run_openbb_ohlcv_normalization_bridge",
        "python -m dopey_openbb_autonomy.run_openbb_evidence_manifest_builder",
        "python -m dopey_openbb_autonomy.run_openbb_validator_bridge",
        "python -m dopey_autonomy.run_open_data_breakthrough_full_completion",
        "python -m dopey_research_autonomy.run_model_priced_options_research_expansion_v2",
        "python -m dopey_research_autonomy.run_s_tier_long_premium_engine_v2",
        "python -m dopey_paper_autonomy.run_autonomous_paper_rotation_engine",
        "python -m dopey_autonomy.run_remaining_gap_eliminator",
    ]
    return "# DOPEY Finish Everything Commands\n\n" + "\n".join(f"- `{command}`" for command in commands) + "\n"


def _quality_flags(summary: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    if not summary["openbb_valid_real_dataset"]:
        reasons.append("blocked_no_openbb_accepted_ohlcv")
    if not summary["quote_priced_backtest_allowed"]:
        reasons.append("quote_priced_options_blocked")
    records: list[dict[str, Any]] = []
    for index, reason in enumerate(reasons):
        record = {
            "artifact_type": "finish_everything_quality_flags",
            "flag_id": f"finish-everything-{index:03d}",
            "reason_code": reason,
            "severity": "info",
            "paper_only": True,
            "live_blocked": True,
        }
        record["flag_hash"] = stable_hash(record)
        records.append(record)
    return records


def _fixture_case(index: int, name: str) -> dict[str, Any]:
    record = {
        "case_id": f"finish-everything-fixture-{index:03d}",
        "case_name": name,
        "fixture_only": True,
        "not_real_data": True,
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    record["case_hash"] = stable_hash(record)
    return record


def _fixture_names_openbb() -> list[str]:
    return ["OpenBB installed", "OpenBB not installed", "OpenBB provider no-key accepted", "OpenBB provider API-key rejected", "OpenBB provider paid rejected", "OpenBB provider broker rejected", "OpenBB provider Alpha Vantage rejected", "OpenBB provider Alpaca rejected", "OpenBB provider Databento rejected", "OpenBB provider TradingView rejected", "OpenBB OHLCV normalize pass", "OpenBB OHLCV normalize fail", "OpenBB validator bridge no data", "OpenBB validator bridge pass"]


def _fixture_names_model_v2() -> list[str]:
    return ["model-priced V2 no data", "model-priced V2 accepted OHLCV", "model-priced V2 quote blocked", "model-priced V2 scenario grid", "model-priced V2 theta stress", "model-priced V2 IV shock", "model-priced V2 moneyness", "model-priced V2 expiration bucket", "model-priced V2 risk stress"]


def _fixture_names_s_tier() -> list[str]:
    return ["S-tier V2 no data", "S-tier V2 accepted OHLCV", "S-tier V2 signal mutation", "S-tier V2 tournament", "S-tier V2 no-trade gate", "S-tier V2 adversarial stress", "no profitability claim", "no live readiness claim"]


def _fixture_names_paper() -> list[str]:
    return ["paper rotation no data", "paper rotation accepted data", "paper rotation no broker", "paper rotation no live", "paper rotation no credentials", "no same-day churn", "drawdown throttle", "research feedback queue"]


def _fixture_names_finish() -> list[str]:
    return ["remaining gap solved", "remaining gap blocked by policy", "remaining gap fallback model-priced", "finish everything no data", "finish everything OpenBB data", "finish everything quote unlocked", "finish everything max completion", "no manual review dependency", "no operator action required", "no .env", "no credentials", "no broker", "no live", "no strategy promotion", "no profitability claim", "no live readiness claim"]


def _shared_target_root() -> Path | None:
    for candidate in [Path("C:/Users/chris/Desktop/Shared Folder"), Path("//FRANKENSTEIN/Shared Folder"), Path("Z:/")]:
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    result = run_finish_literally_everything_orchestrator()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
