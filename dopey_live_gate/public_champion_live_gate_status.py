"""Public champion live-gate hard separation status."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, proof_record, read_json_file, record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_wealth_engine.common import REPO_ROOT


STATUS_PATH = LIVE_GATE_ROOT / "public_champion_live_gate_status.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_champion_live_gate_blockers.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_champion_live_gate_proof.jsonl"


def run_public_champion_live_gate_status() -> dict[str, object]:
    champion_summary = read_json_file(LIVE_GATE_ROOT.parent / "champions" / "public_paper_champion_gate_summary.json")
    status = build_public_champion_live_gate_status(champion_summary)
    blockers = build_public_champion_live_gate_blockers(status)
    summary = write_summary_with_hash(STATUS_PATH, status)
    write_jsonl_file(BLOCKERS_PATH, blockers)
    write_jsonl_file(PROOF_PATH, [proof_record("public-champion-live-gate-status", str(summary["live_gate_status"]), summary)])
    return {**summary, "blocker_count": len(blockers), "artifact_paths": artifact_paths()}


def build_public_champion_live_gate_status(champion_summary: dict[str, object]) -> dict[str, object]:
    env_path = REPO_ROOT / ".env"
    return {
        "artifact_type": "public_champion_live_gate_status",
        "public_champion_live_gate_version": "dopey-public-champion-live-gate-status-v1",
        "live_gate_status": "disabled_separate_future_gate",
        "public_paper_champion_count": int(champion_summary.get("public_paper_champion_count", 0)),
        "live_gate_candidate_locked_count": int(champion_summary.get("live_gate_candidate_locked_count", 0)),
        "live_trading_enabled": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": env_path.exists(),
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        "paper_champion_hardening_required": True,
        "real_broker_adapter_required": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        "real_orders_placed": False,
    }


def build_public_champion_live_gate_blockers(status: dict[str, object]) -> list[dict[str, object]]:
    blockers = [
        ("capital_risk_review_required", "real capital review remains outside this bundle"),
        ("separate_future_bundle_required", "live gate requires a separate future bundle"),
        ("human_live_approval_required", "human approval is required before any live gate work"),
        ("paper_champion_hardening_required", "paper champions require deeper public stress before live consideration"),
        ("broker_adapter_not_required", "real broker adapter remains out of scope for this bundle"),
    ]
    records: list[dict[str, object]] = []
    for blocker_id, message in blockers:
        record = {
            "artifact_type": "public_champion_live_gate_blocker",
            "blocker_id": blocker_id,
            "message": message,
            "public_paper_champion_count": status.get("public_paper_champion_count", 0),
            "live_trading_enabled": False,
            "broker_connection_enabled": False,
            "real_order_enabled": False,
        }
        records.append(record_with_hash(record, "record_hash"))
    return records


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_live_gate_status": str(STATUS_PATH),
        "public_champion_live_gate_blockers": str(BLOCKERS_PATH),
        "public_champion_live_gate_proof": str(PROOF_PATH),
    }

