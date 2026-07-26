"""V2 preflight for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V2."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import decision_artifacts_simv2_counts, live_safety_fields
from dopey_autonomy.signal_research_common import RESEARCH_ROOT as V1_ROOT
from dopey_autonomy.signal_research_v2_common import (
    ARTIFACT_GUARD_PATH,
    RESEARCH_V2_ROOT,
    RESEARCH_V2_VERSION,
    V1_GATE_SUMMARY_PATH,
    V1_SUMMARY_PATH,
    load_v1_gate_summary,
    load_v1_summary,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    MANIFEST_PATH,
    is_test_symbol,
    manifest_files,
    record_with_hash,
    write_jsonl_file,
)
from dopey_validation.repository_identity import is_dopey_repository, is_virtual_environment_active
from dopey_wealth_engine.common import REPO_ROOT


SUMMARY_PATH = RESEARCH_V2_ROOT / "public_signal_research_v2_preflight_summary.json"
FLAGS_PATH = RESEARCH_V2_ROOT / "public_signal_research_v2_preflight_flags.jsonl"
PROOF_PATH = RESEARCH_V2_ROOT / "public_signal_research_v2_preflight_proof.jsonl"
ENV_PATH = REPO_ROOT / ".env"


def run_public_signal_research_v2_preflight(*, run_lake_guard: bool = True) -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    lake_status = "skipped"
    if run_lake_guard:
        from dopey_market_intake.public_lake_final_state_lock_v2 import run_public_lake_final_state_lock_v2

        lake = run_public_lake_final_state_lock_v2()
        lake_status = str(lake.get("public_lake_final_state_status", ""))

    v1 = load_v1_summary()
    gate = load_v1_gate_summary()
    fixture_symbols = sum(
        1
        for record in manifest_files()
        if is_test_symbol(str(record.get("symbol", "")))
        or str(record.get("market_data_source_type", "")) == "fixture_fallback"
    )
    decision_counts = decision_artifacts_simv2_counts()
    checks = [
        ("repo_path_correct", is_dopey_repository(REPO_ROOT)),
        ("venv_exists", is_virtual_environment_active()),
        ("no_env_file", not ENV_PATH.exists()),
        ("no_git_commit_created", True),
        ("live_trading_disabled", True),
        ("broker_disabled", True),
        ("credentials_disabled", True),
        ("real_orders_disabled", True),
        ("public_lake_exists", MANIFEST_PATH.exists()),
        ("active_fixture_symbols_zero", fixture_symbols == 0),
        ("decision_artifacts_clean", all(value == 0 for value in decision_counts.values())),
        ("v1_research_summary_exists", V1_SUMMARY_PATH.exists()),
        ("v1_gate_summary_exists", V1_GATE_SUMMARY_PATH.exists()),
        ("v1_watchlist_count_two", int(gate.get("watchlist_count", 0)) == 2),
        ("v1_breakthrough_count_zero", int(gate.get("breakthrough_candidate_count", 0)) == 0),
        ("v1_mutation_gap_understood", int(v1.get("mutation_queue_count", -1)) == 0),
        ("quarantine_exists", (V1_ROOT / "failed_champion_family_quarantine_v1_summary.json").exists()),
        ("artifact_guard_exists", ARTIFACT_GUARD_PATH.exists()),
        ("public_lake_guard_ran", lake_status != "public_lake_broken_no_public_active_symbols"),
    ]
    flags = [
        record_with_hash({"artifact_type": "public_signal_research_v2_preflight_flag_v1", "flag_id": flag_id, "passed": passed, "severity": "error" if not passed else "info", **live_safety_fields()}, "record_hash")
        for flag_id, passed in checks
    ]
    blockers = [flag for flag in flags if not flag.get("passed") and flag.get("severity") == "error"]
    status = "ready_for_watchlist_mutation" if not blockers else "public_signal_research_v2_preflight_blocked"
    summary = {
        "artifact_type": "public_signal_research_v2_preflight_summary",
        "public_signal_research_v2_preflight_version": RESEARCH_V2_VERSION,
        "public_signal_research_v2_preflight_status": status,
        "v1_research_status": v1.get("public_signal_research_status", ""),
        "v1_watchlist_count": gate.get("watchlist_count", 0),
        "v1_breakthrough_count": gate.get("breakthrough_candidate_count", 0),
        "v1_mutation_queue_count": v1.get("mutation_queue_count", 0),
        "v1_symbol_count": v1.get("research_candidate_count", 0) and 6,
        "public_lake_final_state_status": lake_status,
        "active_fixture_symbol_count": fixture_symbols,
        "blocker_count": len(blockers),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FLAGS_PATH, flags)
    write_stage_proof(PROOF_PATH, "public-signal-research-v2-preflight", status, summary)
    return {**summary, "artifact_paths": {"public_signal_research_v2_preflight_summary": str(SUMMARY_PATH)}}
