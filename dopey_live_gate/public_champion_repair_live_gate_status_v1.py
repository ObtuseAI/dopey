"""Live gate lock for champion repair bundle."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.champion_repair_common import REPAIR_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, read_json_file, record_with_hash, write_jsonl_file
from dopey_wealth_engine.common import REPO_ROOT


STATUS_PATH = LIVE_GATE_ROOT / "public_champion_repair_live_gate_status_v1.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_champion_repair_live_gate_blockers_v1.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_champion_repair_live_gate_proof_v1.jsonl"
RETUNE_GATE_PATH = REPAIR_ROOT / "conditional_champion_retune_hardening_gate_v1_summary.json"


def run_public_champion_repair_live_gate_status_v1() -> dict[str, object]:
    retune_gate = read_json_file(RETUNE_GATE_PATH)
    status = build_live_gate_status_v1(retune_gate)
    blockers = build_live_gate_blockers_v1(status)
    summary = write_summary_with_hash(STATUS_PATH, status)
    write_jsonl_file(BLOCKERS_PATH, blockers)
    write_stage_proof(PROOF_PATH, "public-champion-repair-live-gate-v1", str(summary["live_gate_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def build_live_gate_status_v1(retune_gate: dict[str, object]) -> dict[str, object]:
    env_path = REPO_ROOT / ".env"
    hardened = int(retune_gate.get("retuned_hardened_count", 0))
    conditional = int(retune_gate.get("retuned_conditional_count", 0))
    demoted = int(retune_gate.get("retuned_demoted_count", 0))
    return {
        "artifact_type": "public_champion_repair_live_gate_status_v1",
        "public_champion_repair_live_gate_version": "dopey-public-champion-repair-live-gate-v1",
        "live_gate_status": "disabled_live_gate_locked",
        "retuned_hardened_count": hardened,
        "retuned_conditional_count": conditional,
        "retuned_demoted_count": demoted,
        "live_gate_candidate_locked_count": hardened + conditional + demoted,
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        "env_present": env_path.exists(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def build_live_gate_blockers_v1(status: dict[str, object]) -> list[dict[str, object]]:
    blockers = [
        ("live_trading_disabled", "live trading remains disabled even if retuned champions harden"),
        ("no_broker_connection", "no broker connection is established or required"),
        ("no_real_orders", "no real orders are placed or enabled"),
        ("no_credentials", "no broker credentials are created or stored"),
        ("official_robinhood_market_data_lane_research_only", "official Robinhood market-data lane allowed for research only"),
        ("unofficial_robinhood_access_blocked", "unofficial Robinhood APIs remain blocked"),
    ]
    return [record_with_hash({"artifact_type": "public_champion_repair_live_gate_blocker_v1", "blocker_id": blocker_id, "message": message, **live_safety_fields()}, "record_hash") for blocker_id, message in blockers]


def artifact_paths() -> dict[str, str]:
    return {"public_champion_repair_live_gate_status_v1": str(STATUS_PATH)}
