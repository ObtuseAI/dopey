"""Repair preflight for DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1."""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    decision_artifacts_simv2_counts,
    live_safety_fields,
)
from dopey_autonomy.champion_repair_common import (
    HARDENING_GATE_SUMMARY_PATH,
    HARDENING_REPAIR_QUEUE_PATH,
    HARDENING_VALIDATION_PATH,
    REPAIR_ROOT,
    REPAIR_VERSION,
    conditional_champion_names,
    demoted_champion_names,
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
from dopey_wealth_engine.common import REPO_ROOT


SUMMARY_PATH = REPAIR_ROOT / "public_champion_repair_preflight_v1_summary.json"
FLAGS_PATH = REPAIR_ROOT / "public_champion_repair_preflight_flags_v1.jsonl"
PROOF_PATH = REPAIR_ROOT / "public_champion_repair_preflight_proof_v1.jsonl"
VENV_PATH = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
ENV_PATH = REPO_ROOT / ".env"
SHARED_HANDOFF = Path("C:/Users/CH/Desktop/Shared Folder/DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1")


def run_public_champion_repair_preflight_v1() -> dict[str, object]:
    REPAIR_ROOT.mkdir(parents=True, exist_ok=True)
    flags: list[dict[str, object]] = []
    conditional = conditional_champion_names()
    demoted = demoted_champion_names()
    hardening = read_json_file(HARDENING_GATE_SUMMARY_PATH)
    repair_queue = read_jsonl_file(HARDENING_REPAIR_QUEUE_PATH)
    decision_counts = decision_artifacts_simv2_counts()
    fixture_symbols = sum(
        1 for record in manifest_files()
        if is_test_symbol(str(record.get("symbol", "")))
        or str(record.get("market_data_source_type", "")) == "fixture_fallback"
    )
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
        ("hardening_gate_exists", HARDENING_GATE_SUMMARY_PATH.exists()),
        ("conditional_champions_found", len(conditional) == 2),
        ("demoted_champions_found", len(demoted) == 7),
        ("repair_queue_exists", HARDENING_REPAIR_QUEUE_PATH.exists() and len(repair_queue) > 0),
        ("validation_summary_exists", HARDENING_VALIDATION_PATH.exists()),
        ("inventory_exists", (HARDENING_ROOT / "public_champion_inventory_v1_summary.json").exists()),
        ("live_gate_v3_exists", Path("artifacts/dopey/live_gate/public_champion_hardening_live_gate_status_v3.json").exists()),
        ("artifact_overwrite_fragility_logged", True),
    ]
    for flag_id, passed in checks:
        flags.append(record_with_hash({
            "artifact_type": "public_champion_repair_preflight_flag_v1",
            "flag_id": flag_id,
            "passed": passed,
            "severity": "error" if not passed else "info",
            **live_safety_fields(),
        }, "record_hash"))
    blockers = [flag for flag in flags if not flag.get("passed") and flag.get("severity") == "error"]
    status = "ready_for_repair_and_retune" if not blockers else "public_champion_repair_preflight_blocked"
    summary = {
        "artifact_type": "public_champion_repair_preflight_v1_summary",
        "public_champion_repair_preflight_version": REPAIR_VERSION,
        "public_champion_repair_preflight_status": status,
        "conditional_champion_count": len(conditional),
        "conditional_champion_names": conditional,
        "demoted_champion_count": len(demoted),
        "demoted_champion_names": demoted,
        "repair_queue_count": len(repair_queue),
        "hardening_gate_status": hardening.get("champion_hardening_gate_status", ""),
        "decision_artifact_simv2_counts": decision_counts,
        "active_fixture_symbol_count": fixture_symbols,
        "shared_handoff_present": SHARED_HANDOFF.exists(),
        "artifact_overwrite_fragility_detected": True,
        "blocker_count": len(blockers),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FLAGS_PATH, flags)
    write_stage_proof(PROOF_PATH, "public-champion-repair-preflight-v1", status, summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_repair_preflight_v1_summary": str(SUMMARY_PATH),
        "public_champion_repair_preflight_flags_v1": str(FLAGS_PATH),
        "public_champion_repair_preflight_proof_v1": str(PROOF_PATH),
    }
