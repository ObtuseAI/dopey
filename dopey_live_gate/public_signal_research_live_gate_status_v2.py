"""Public signal research live gate status V2."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, read_json_file, record_with_hash, write_jsonl_file


STATUS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v2.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_blockers_v2.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_proof_v2.jsonl"


def run_public_signal_research_live_gate_status_v2() -> dict[str, object]:
    gate = read_json_file(RESEARCH_V2_ROOT / "research_breakthrough_gate_v2_summary.json")
    return build_live_gate_status_v2(gate)


def build_live_gate_status_v2(gate: dict[str, object]) -> dict[str, object]:
    LIVE_GATE_ROOT.mkdir(parents=True, exist_ok=True)
    status = {
        "artifact_type": "public_signal_research_live_gate_status_v2",
        "public_signal_research_live_gate_v2_version": "dopey-public-signal-research-live-gate-v2",
        "live_gate_status": "disabled_live_gate_locked",
        "research_breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "paper_champion_candidate_locked_count": gate.get("paper_champion_candidate_locked_count", 0),
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        "env_present": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    summary = write_summary_with_hash(STATUS_PATH, status)
    write_jsonl_file(BLOCKERS_PATH, [record_with_hash({"artifact_type": "public_signal_research_live_gate_blocker_v2", "blocker_id": "live_trading_disabled", **live_safety_fields(), **robinhood_policy_fields()}, "record_hash")])
    write_stage_proof(PROOF_PATH, "public-signal-research-live-gate-v2", str(summary["live_gate_status"]), summary)
    return {**summary, "artifact_paths": {"public_signal_research_live_gate_status_v2": str(STATUS_PATH)}}
