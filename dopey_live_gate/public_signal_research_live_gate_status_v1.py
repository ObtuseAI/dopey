"""Public signal research live gate status V1."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.signal_research_common import RESEARCH_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, read_json_file, record_with_hash, write_jsonl_file


STATUS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v1.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_blockers_v1.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_proof_v1.jsonl"


def run_public_signal_research_live_gate_status_v1() -> dict[str, object]:
    gate = read_json_file(RESEARCH_ROOT / "research_breakthrough_gate_v1_summary.json")
    return build_live_gate_status_v1(gate)


def build_live_gate_status_v1(gate: dict[str, object]) -> dict[str, object]:
    LIVE_GATE_ROOT.mkdir(parents=True, exist_ok=True)
    status = {
        "artifact_type": "public_signal_research_live_gate_status_v1",
        "public_signal_research_live_gate_version": "dopey-public-signal-research-live-gate-v1",
        "live_gate_status": "disabled_live_gate_locked",
        "research_breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "paper_champion_candidate_locked_count": gate.get("paper_champion_candidate_locked_count", 0),
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        "env_present": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    summary = write_summary_with_hash(STATUS_PATH, status)
    blockers = [
        record_with_hash({
            "artifact_type": "public_signal_research_live_gate_blocker_v1",
            "blocker_id": "live_trading_disabled",
            "message": "Research breakthrough bundle does not enable live trading",
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }, "record_hash"),
        record_with_hash({
            "artifact_type": "public_signal_research_live_gate_blocker_v1",
            "blocker_id": "human_live_approval_required",
            "message": "Separate future bundle and human approval required",
            **live_safety_fields(),
        }, "record_hash"),
    ]
    write_jsonl_file(BLOCKERS_PATH, blockers)
    write_stage_proof(PROOF_PATH, "public-signal-research-live-gate-v1", str(summary["live_gate_status"]), summary)
    return {**summary, "artifact_paths": {"public_signal_research_live_gate_status_v1": str(STATUS_PATH)}}
