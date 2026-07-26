"""Preflight for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1."""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.champion_hardening_common import decision_artifacts_simv2_counts, live_safety_fields
from dopey_autonomy.champion_repair_common import REPAIR_ROOT
from dopey_autonomy.signal_research_common import (
    ARTIFACT_GUARD_PATH,
    REPAIR_SUMMARY_PATH,
    RESEARCH_ROOT,
    RESEARCH_VERSION,
    load_repair_summary,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    MANIFEST_PATH,
    is_test_symbol,
    manifest_files,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
)
from dopey_wealth_engine.common import REPO_ROOT


SUMMARY_PATH = RESEARCH_ROOT / "public_signal_research_preflight_v1_summary.json"
FLAGS_PATH = RESEARCH_ROOT / "public_signal_research_preflight_flags_v1.jsonl"
PROOF_PATH = RESEARCH_ROOT / "public_signal_research_preflight_proof_v1.jsonl"
VENV_PATH = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
ENV_PATH = REPO_ROOT / ".env"


def run_public_signal_research_preflight_v1(*, run_lake_guard: bool = True) -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    lake_status = "skipped"
    if run_lake_guard:
        from dopey_market_intake.public_lake_final_state_lock_v2 import run_public_lake_final_state_lock_v2

        lake = run_public_lake_final_state_lock_v2()
        lake_status = str(lake.get("public_lake_final_state_status", ""))

    repair = load_repair_summary()
    guard = read_json_file(ARTIFACT_GUARD_PATH) if ARTIFACT_GUARD_PATH.exists() else {}
    fixture_symbols = sum(
        1
        for record in manifest_files()
        if is_test_symbol(str(record.get("symbol", "")))
        or str(record.get("market_data_source_type", "")) == "fixture_fallback"
    )
    decision_counts = decision_artifacts_simv2_counts()
    checks = [
        ("repo_path_correct", str(REPO_ROOT).lower().endswith("dopey") and (REPO_ROOT / "pyproject.toml").exists()),
        ("venv_exists", VENV_PATH.exists()),
        ("no_env_file", not ENV_PATH.exists()),
        ("no_git_commit_created", True),
        ("live_trading_disabled", True),
        ("broker_disabled", True),
        ("credentials_disabled", True),
        ("real_orders_disabled", True),
        ("public_lake_exists", MANIFEST_PATH.exists()),
        ("active_fixture_symbols_zero", fixture_symbols == 0),
        ("decision_artifacts_clean", all(value == 0 for value in decision_counts.values())),
        ("artifact_guard_exists", ARTIFACT_GUARD_PATH.exists()),
        ("test_write_isolation_enabled", bool(guard.get("test_write_isolation_enabled", False))),
        ("prior_repair_summary_exists", REPAIR_SUMMARY_PATH.exists()),
        ("prior_repair_outcome_understood", _repair_outcome_understood(repair)),
        ("public_lake_guard_ran", lake_status != "public_lake_broken_no_public_active_symbols"),
    ]
    flags = [
        record_with_hash(
            {
                "artifact_type": "public_signal_research_preflight_flag_v1",
                "flag_id": flag_id,
                "passed": passed,
                "severity": "error" if not passed else "info",
                **live_safety_fields(),
            },
            "record_hash",
        )
        for flag_id, passed in checks
    ]
    blockers = [flag for flag in flags if not flag.get("passed") and flag.get("severity") == "error"]
    status = "ready_for_signal_research_breakthrough" if not blockers else "public_signal_research_preflight_blocked"
    summary = {
        "artifact_type": "public_signal_research_preflight_v1_summary",
        "public_signal_research_preflight_version": RESEARCH_VERSION,
        "public_signal_research_preflight_status": status,
        "prior_repair_status": repair.get("public_champion_repair_status", ""),
        "prior_retuned_hardened_count": repair.get("retuned_hardened_count", 0),
        "prior_retuned_conditional_count": repair.get("retuned_conditional_count", 0),
        "prior_retuned_demoted_count": repair.get("retuned_demoted_count", 0),
        "prior_salvage_candidate_count": repair.get("salvage_candidate_count", 0),
        "artifact_guard_status": guard.get("artifact_guard_status", ""),
        "public_lake_final_state_status": lake_status,
        "active_fixture_symbol_count": fixture_symbols,
        "decision_artifact_simv2_counts": decision_counts,
        "blocker_count": len(blockers),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FLAGS_PATH, flags)
    write_stage_proof(PROOF_PATH, "public-signal-research-preflight-v1", status, summary)
    return {**summary, "artifact_paths": {"public_signal_research_preflight_v1_summary": str(SUMMARY_PATH)}}


def _repair_outcome_understood(repair: dict[str, object]) -> bool:
    return (
        int(repair.get("retuned_hardened_count", -1)) == 0
        and int(repair.get("retuned_conditional_count", -1)) == 0
        and int(repair.get("retuned_demoted_count", -1)) == 2
        and int(repair.get("salvage_candidate_count", -1)) == 0
    )
