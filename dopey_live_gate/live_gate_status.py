"""Build disabled live-gate status artifacts."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash

from .live_gate_models import LIVE_GATE_STATUS, LIVE_GATE_VERSION


def build_live_gate_status(evolution_summary: dict) -> tuple[dict, list[dict]]:
    status = {
        "artifact_type": "live_gate_status",
        "live_gate_version": LIVE_GATE_VERSION,
        "live_gate_status": "disabled_separate_future_gate",
        **LIVE_GATE_STATUS,
        "paper_champion_count": int(evolution_summary.get("paper_champion_count", 0)),
        "live_gate_candidate_count": int(evolution_summary.get("live_gate_candidate_count", 0)),
        "paper_only": True,
        "live_blocked": True,
    }
    status["summary_hash"] = stable_hash(status)
    blockers = [
        _blocker("human_live_approval_missing", "explicit human live approval is required"),
        _blocker("broker_credentials_forbidden", "this bundle does not create or read broker credentials"),
        _blocker("future_live_bundle_required", "live enablement requires a separate future bundle"),
        _blocker("capital_risk_review_required", "real capital sizing and risk review are outside this bundle"),
    ]
    return status, blockers


def _blocker(blocker_id: str, message: str) -> dict:
    record = {
        "artifact_type": "live_gate_blocker",
        "blocker_id": blocker_id,
        "message": message,
        "live_trading_enabled": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["record_hash"] = stable_hash(record)
    return record

