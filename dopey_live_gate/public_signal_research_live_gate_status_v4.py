"""Public signal research live gate status V4.

Copies V3 live gate pattern, points at V4 breakthrough / watchlist
summaries, keeps live locked.
"""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, read_json_file, record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    GATE_V4_SUMMARY_PATH,
    write_stage_proof,
    write_summary_with_hash,
)


STATUS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v4.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_blockers_v4.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_proof_v4.jsonl"


def run_public_signal_research_live_gate_status_v4() -> dict[str, object]:
    gate = read_json_file(GATE_V4_SUMMARY_PATH)
    return build_live_gate_status_v4(gate)


def build_live_gate_status_v4(gate: dict[str, object]) -> dict[str, object]:
    LIVE_GATE_ROOT.mkdir(parents=True, exist_ok=True)
    status = {
        "artifact_type": "public_signal_research_live_gate_status_v4",
        "public_signal_research_live_gate_v4_version": "dopey-public-signal-research-live-gate-v4",
        "live_gate_status": "disabled_live_gate_locked",
        "live_trading_enabled": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": False,
        "research_breakthrough_candidate_count": gate.get("breakthrough_candidate_count", 0),
        "watchlist_count": gate.get("watchlist_count", 0),
        "paper_champion_candidate_locked_count": gate.get("paper_champion_candidate_locked_count", 0),
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    summary = write_summary_with_hash(STATUS_PATH, status)
    write_jsonl_file(
        BLOCKERS_PATH,
        [
            record_with_hash(
                {
                    "artifact_type": "public_signal_research_live_gate_blocker_v4",
                    "blocker_id": "live_trading_disabled",
                    **live_safety_fields(),
                    **robinhood_policy_fields(),
                },
                "record_hash",
            )
        ],
    )
    write_stage_proof(
        PROOF_PATH,
        "public-signal-research-live-gate-v4",
        str(summary["live_gate_status"]),
        summary,
    )
    return {**summary, "artifact_paths": {"public_signal_research_live_gate_status_v4": str(STATUS_PATH)}}
