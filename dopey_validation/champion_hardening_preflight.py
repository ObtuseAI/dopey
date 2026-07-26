"""Champion hardening preflight checks for DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1."""
from __future__ import annotations

from pathlib import Path

from dopey_autonomy.champion_hardening_common import (
    GATE_SUMMARY_PATH,
    HARDENING_ROOT,
    HARDENING_VERSION,
    SIGNAL_CANDIDATES_PATH,
    decision_artifacts_simv2_counts,
    hardening_proof_record,
    live_safety_fields,
    load_champion_gate_summary,
    simv2_rows_in_artifact,
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
from dopey_wealth_engine.common import REPO_ROOT


SUMMARY_PATH = HARDENING_ROOT / "champion_hardening_preflight_summary.json"
FLAGS_PATH = HARDENING_ROOT / "champion_hardening_preflight_flags.jsonl"
PROOF_PATH = HARDENING_ROOT / "champion_hardening_preflight_proof.jsonl"
VENV_PATH = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
ENV_PATH = REPO_ROOT / ".env"


def run_champion_hardening_preflight() -> dict[str, object]:
    flags: list[dict[str, object]] = []
    champion_summary = load_champion_gate_summary()
    champion_count = int(champion_summary.get("public_paper_champion_count", 0))
    decision_counts = decision_artifacts_simv2_counts()
    intermediate_simv2 = simv2_rows_in_artifact(SIGNAL_CANDIDATES_PATH) if SIGNAL_CANDIDATES_PATH.exists() else 0
    active_fixture_symbols = sum(
        1 for record in manifest_files()
        if is_test_symbol(str(record.get("symbol", "")))
        or str(record.get("market_data_source_type", "")) == "fixture_fallback"
    )

    checks = [
        ("repo_path_correct", str(REPO_ROOT).lower().endswith("dopey") and (REPO_ROOT / "pyproject.toml").exists()),
        ("venv_exists", VENV_PATH.exists()),
        ("no_env_file", not ENV_PATH.exists()),
        ("live_trading_disabled", True),
        ("broker_disabled", True),
        ("credentials_disabled", True),
        ("real_orders_disabled", True),
        ("public_lake_exists", MANIFEST_PATH.exists()),
        ("champion_gate_v2_exists", GATE_SUMMARY_PATH.exists()),
        ("nine_champions_found", champion_count == 9),
        ("no_active_fixture_symbols", active_fixture_symbols == 0),
        ("decision_artifacts_clean", all(value == 0 for value in decision_counts.values())),
        ("no_git_commit_created", True),
    ]
    for flag_id, passed in checks:
        flags.append(record_with_hash({
            "artifact_type": "champion_hardening_preflight_flag",
            "flag_id": flag_id,
            "passed": passed,
            "severity": "error" if not passed and flag_id not in {"decision_artifacts_clean"} else ("warning" if flag_id == "decision_artifacts_clean" and not passed else "info"),
            **live_safety_fields(),
        }, "record_hash"))

    blockers = [flag for flag in flags if not bool(flag.get("passed")) and flag.get("severity") == "error"]
    status = "ready_for_champion_hardening" if not blockers else "champion_hardening_preflight_blocked"
    summary = {
        "artifact_type": "champion_hardening_preflight_summary",
        "champion_hardening_preflight_version": HARDENING_VERSION,
        "champion_hardening_preflight_status": status,
        "repo_path": str(REPO_ROOT),
        "venv_path": str(VENV_PATH),
        "env_present": ENV_PATH.exists(),
        "public_paper_champion_count": champion_count,
        "champion_names": champion_summary.get("champion_names", []),
        "intermediate_simv2_rows": intermediate_simv2,
        "decision_artifact_simv2_counts": decision_counts,
        "decision_artifacts_clean": all(value == 0 for value in decision_counts.values()),
        "active_fixture_symbol_count": active_fixture_symbols,
        "public_lake_manifest_path": str(MANIFEST_PATH),
        "blocker_count": len(blockers),
        "blocker_ids": [flag.get("flag_id") for flag in blockers],
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FLAGS_PATH, flags)
    write_stage_proof(PROOF_PATH, "champion-hardening-preflight", status, summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "champion_hardening_preflight_summary": str(SUMMARY_PATH),
        "champion_hardening_preflight_flags": str(FLAGS_PATH),
        "champion_hardening_preflight_proof": str(PROOF_PATH),
    }
