from __future__ import annotations

from blunder.inflow.models import BlunderInflowRecord, stable_id


def evaluate_promotion(record: BlunderInflowRecord) -> list[dict[str, object]]:
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

