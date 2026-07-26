"""Dopey promotion recommender: evaluate promotion eligibility (recommend-only).

Forked verbatim from Blunder inflow promotion_bridge.py (Z:\\BFORK-20260630-020500\\blunder\\
inflow\\promotion_bridge.py). Renamed module; internal import re-routed to dopey_oss_miner
models. Eligibility requires replay fixtures + zero risk + no contradictions. All promoted
candidates require rollback + demotion paths. This is recommend-only; it never auto-deploys.

DOPEY lineage: Blunder inflow/promotion_bridge.py -> dopey_oss_miner.promotion_recommender
"""
from __future__ import annotations

from ._models import DopeyInflowRecord, stable_id


def evaluate_promotion(record: DopeyInflowRecord) -> list[dict[str, object]]:
    promotions: list[dict[str, object]] = []
    for candidate in record["capability_candidates"]:
        fixture_ids = [fixture["fixture_id"] for fixture in record["replay_fixtures"] if fixture["candidate_id"] == candidate["candidate_id"]]
        eligible = (
            record["promotion_status"] == "quarantined"
            and record["risk_score"] == 0
            and bool(fixture_ids)
            and "REPLAY_FIXTURE_CREATED" in record["validation_refs"]
            and not record["contradiction_flags"]
        )
        promotions.append({
            "skill_token_id": stable_id([record["record_id"], str(candidate["candidate_id"]), "skill"]),
            "candidate_id": candidate["candidate_id"],
            "source_record_id": record["record_id"],
            "eligible": eligible,
            "promotion_status": "promotion_eligible" if eligible else "rejected_or_waiting",
            "rollback_path_required": True,
            "demotion_path_required": True,
            "active_skill_token": eligible,
            "reason": "PROMOTION_GATES_PASS" if eligible else "PROMOTION_GATES_NOT_SATISFIED",
        })
    if any(item["eligible"] for item in promotions):
        record["promotion_status"] = "promotion_eligible"
    return promotions
