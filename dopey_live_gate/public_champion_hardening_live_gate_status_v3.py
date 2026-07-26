"""Live gate hard lock V3 for hardened public paper champions."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    HARDENING_VERSION,
    live_safety_fields,
    robinhood_policy_fields,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    LIVE_GATE_ROOT,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
)
from dopey_wealth_engine.common import REPO_ROOT


STATUS_PATH = LIVE_GATE_ROOT / "public_champion_hardening_live_gate_status_v3.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_champion_hardening_live_gate_blockers_v3.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_champion_hardening_live_gate_proof_v3.jsonl"
GATE_SUMMARY_PATH = HARDENING_ROOT / "public_champion_hardening_gate_v1_summary.json"


def run_public_champion_hardening_live_gate_status_v3() -> dict[str, object]:
    gate_summary = read_json_file(GATE_SUMMARY_PATH)
    status = build_live_gate_status_v3(gate_summary)
    blockers = build_live_gate_blockers_v3(status)
    summary = write_summary_with_hash(STATUS_PATH, status)
    write_jsonl_file(BLOCKERS_PATH, blockers)
    write_stage_proof(PROOF_PATH, "public-champion-hardening-live-gate-status-v3", str(summary["live_gate_status"]), summary)
    return {**summary, "blocker_count": len(blockers), "artifact_paths": artifact_paths()}


def build_live_gate_status_v3(gate_summary: dict[str, object]) -> dict[str, object]:
    hardened_count = int(gate_summary.get("hardened_champion_count", 0))
    conditional_count = int(gate_summary.get("conditional_champion_count", 0))
    env_path = REPO_ROOT / ".env"
    return {
        "artifact_type": "public_champion_hardening_live_gate_status_v3",
        "public_champion_hardening_live_gate_version": "dopey-public-champion-hardening-live-gate-status-v3",
        "live_gate_status": "disabled_live_gate_locked",
        "hardened_public_paper_champion_count": hardened_count,
        "conditional_public_paper_champion_count": conditional_count,
        "live_gate_candidate_locked_count": hardened_count + conditional_count + int(gate_summary.get("demoted_champion_count", 0)),
        "live_trading_enabled": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": env_path.exists(),
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        "paper_champion_hardening_required": hardened_count == 0,
        "real_broker_adapter_required": False,
        **robinhood_policy_fields(),
        **live_safety_fields(),
    }


def build_live_gate_blockers_v3(status: dict[str, object]) -> list[dict[str, object]]:
    blockers = [
        ("live_trading_disabled", "live trading remains disabled even if champions harden"),
        ("no_broker_connection", "no broker connection is established or required in this bundle"),
        ("no_real_orders", "no real orders are placed or enabled"),
        ("no_credentials", "no broker credentials are created or stored"),
        ("no_env", "no .env file is created; secret values are never written"),
        ("capital_risk_review_required", "real capital review remains outside this bundle"),
        ("separate_future_bundle_required", "live gate requires a separate future bundle"),
        ("human_live_approval_required", "human approval is required before any live gate work"),
        ("official_robinhood_market_data_lane_research_only", "official Robinhood agent/MCP market-data access is allowed for research/paper scoring if official terms permit"),
        ("unofficial_robinhood_access_blocked", "unofficial Robinhood APIs, scraping, and reverse-engineered auth remain blocked"),
    ]
    records: list[dict[str, object]] = []
    for blocker_id, message in blockers:
        records.append(record_with_hash({
            "artifact_type": "public_champion_hardening_live_gate_blocker_v3",
            "blocker_id": blocker_id,
            "message": message,
            "hardened_public_paper_champion_count": status.get("hardened_public_paper_champion_count", 0),
            "live_trading_enabled": False,
            **live_safety_fields(),
        }, "record_hash"))
    return records


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_hardening_live_gate_status_v3": str(STATUS_PATH),
        "public_champion_hardening_live_gate_blockers_v3": str(BLOCKERS_PATH),
        "public_champion_hardening_live_gate_proof_v3": str(PROOF_PATH),
    }
