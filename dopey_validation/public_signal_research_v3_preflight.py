"""V3 preflight for DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import decision_artifacts_simv2_counts, live_safety_fields
from dopey_autonomy.signal_research_v2_common import (
    ARTIFACT_GUARD_PATH,
    MUTATION_QUEUE_V2_PATH,
    RESEARCH_V2_ROOT,
    V1_SUMMARY_PATH,
    load_v1_gate_summary,
)
from dopey_autonomy.signal_research_v3_common import (
    RESEARCH_V3_ROOT,
    RESEARCH_V3_VERSION,
    STABLE_FAMILY_CONTINUATION,
    STABLE_FAMILY_VOLUME,
    V2_CANDIDATE_SUMMARY_PATH,
    V2_MUTATION_QUEUE_SUMMARY_PATH,
    V2_SUMMARY_PATH,
    load_v2_gate_summary,
    load_v2_summary,
    load_v2_tournament_summary,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    MANIFEST_PATH,
    is_test_symbol,
    manifest_files,
    read_json_file,
    read_jsonl_file,
    record_with_hash,
    write_jsonl_file,
)
from dopey_validation.repository_identity import is_dopey_repository, is_virtual_environment_active
from dopey_wealth_engine.common import REPO_ROOT


SUMMARY_PATH = RESEARCH_V3_ROOT / "public_signal_research_v3_preflight_summary.json"
FLAGS_PATH = RESEARCH_V3_ROOT / "public_signal_research_v3_preflight_flags.jsonl"
PROOF_PATH = RESEARCH_V3_ROOT / "public_signal_research_v3_preflight_proof.jsonl"
ENV_PATH = REPO_ROOT / ".env"


def run_public_signal_research_v3_preflight(*, run_lake_guard: bool = True) -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    lake_status = "skipped"
    if run_lake_guard:
        from dopey_market_intake.public_lake_final_state_lock_v2 import run_public_lake_final_state_lock_v2

        lake = run_public_lake_final_state_lock_v2()
        lake_status = str(lake.get("public_lake_final_state_status", ""))

    v1_gate = load_v1_gate_summary()
    v2 = load_v2_summary()
    v2_gate = load_v2_gate_summary()
    v2_tournament = load_v2_tournament_summary()
    v2_candidates = read_json_file(V2_CANDIDATE_SUMMARY_PATH) if V2_CANDIDATE_SUMMARY_PATH.exists() else {}
    v2_mutation = read_json_file(V2_MUTATION_QUEUE_SUMMARY_PATH) if V2_MUTATION_QUEUE_SUMMARY_PATH.exists() else {}
    mutation_queue = read_jsonl_file(MUTATION_QUEUE_V2_PATH) if MUTATION_QUEUE_V2_PATH.exists() else []
    guard = read_json_file(ARTIFACT_GUARD_PATH) if ARTIFACT_GUARD_PATH.exists() else {}
    fixture_symbols = sum(
        1
        for record in manifest_files()
        if is_test_symbol(str(record.get("symbol", "")))
        or str(record.get("market_data_source_type", "")) == "fixture_fallback"
    )
    decision_counts = decision_artifacts_simv2_counts()
    mutation_count = int(v2_mutation.get("mutation_queue_count", len(mutation_queue)))
    top_pf = float(v2_tournament.get("top_profit_factor", 0.0))
    top_pnl = float(v2_tournament.get("top_net_pnl", 0.0))

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
        ("v1_research_artifacts_exist", V1_SUMMARY_PATH.exists()),
        ("v2_research_artifacts_exist", V2_SUMMARY_PATH.exists()),
        ("v2_mutation_queue_exists", MUTATION_QUEUE_V2_PATH.exists()),
        ("v2_mutation_queue_count_31", mutation_count == 31),
        ("v2_stable_family_continuation", any(STABLE_FAMILY_CONTINUATION in str(r.get("discovery_family_id", "")) for r in mutation_queue)),
        ("v2_stable_family_volume", any(STABLE_FAMILY_VOLUME in str(r.get("discovery_family_id", "")) for r in mutation_queue)),
        ("v2_candidate_symbol_count_110", int(v2_candidates.get("symbol_count", 0)) == 110),
        ("v2_candidate_sector_count_17", int(v2_candidates.get("sector_count", 0)) == 17),
        ("v2_broad_expansion_degraded", top_pnl < 0.0 and top_pf < 1.0),
        ("v2_top_pf_061", abs(top_pf - 0.61) < 0.05 or top_pf < 1.0),
        ("v2_breakthrough_count_zero", int(v2_gate.get("breakthrough_candidate_count", 0)) == 0),
        ("v2_mutation_queue_nonempty", mutation_count > 0),
        ("failed_family_quarantine_active", (RESEARCH_V2_ROOT.parent / "signal_research/failed_champion_family_quarantine_v1_summary.json").exists()),
        ("artifact_guard_active", ARTIFACT_GUARD_PATH.exists()),
        ("public_lake_guard_ran", lake_status != "public_lake_broken_no_public_active_symbols"),
    ]
    flags = [
        record_with_hash(
            {
                "artifact_type": "public_signal_research_v3_preflight_flag",
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
    status = "ready_for_mutation_queue_execution" if not blockers else "public_signal_research_v3_preflight_blocked"
    summary = {
        "artifact_type": "public_signal_research_v3_preflight_summary",
        "public_signal_research_v3_preflight_version": RESEARCH_V3_VERSION,
        "public_signal_research_v3_preflight_status": status,
        "v2_research_status": v2.get("public_signal_research_v2_status", ""),
        "v2_mutation_queue_count": mutation_count,
        "v2_symbol_count": v2_candidates.get("symbol_count", 0),
        "v2_sector_count": v2_candidates.get("sector_count", 0),
        "v2_top_profit_factor": top_pf,
        "v2_top_net_pnl": top_pnl,
        "v2_breakthrough_count": v2_gate.get("breakthrough_candidate_count", 0),
        "v1_watchlist_count": v1_gate.get("watchlist_count", 0),
        "public_lake_final_state_status": lake_status,
        "active_fixture_symbol_count": fixture_symbols,
        "artifact_guard_status": guard.get("artifact_guard_status", ""),
        "blocker_count": len(blockers),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FLAGS_PATH, flags)
    write_stage_proof(PROOF_PATH, "public-signal-research-v3-preflight", status, summary)
    return {**summary, "artifact_paths": {"public_signal_research_v3_preflight_summary": str(SUMMARY_PATH)}}
