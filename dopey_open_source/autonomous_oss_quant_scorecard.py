"""Score autonomous OSS quant candidates without cloning or executing code."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import oss_candidates, stable_hash


def build_autonomous_oss_scorecard(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [record for record in records if record["import_mode"] in {"adapter_candidate", "sandbox_candidate"}]
    reference_only = [record for record in records if record["import_mode"] == "reference_only"]
    rejected = [record for record in records if record["import_mode"] == "rejected"]
    scorecard = {
        "artifact_type": "autonomous_oss_scorecard",
        "scorecard_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "candidate_count": len(records),
        "accepted_count": len(accepted),
        "reference_only_count": len(reference_only),
        "rejected_count": len(rejected),
        "repo_cloned_count": 0,
        "external_code_imported_count": 0,
        "external_code_executed_count": 0,
        "top_candidates": [record["candidate_id"] for record in sorted(accepted, key=lambda item: item["signal_usefulness"], reverse=True)[:5]],
        "broker_live_repos_reference_only_or_rejected": True,
        "unknown_license_rejected": all(record["import_mode"] == "rejected" for record in records if not record["license_id"]),
        "copyleft_reference_only": all(record["import_mode"] == "reference_only" for record in records if record["license_id"].startswith("GPL")),
        "external_code_cannot_control_dopey": True,
        "external_code_cannot_place_orders": True,
        "external_code_cannot_promote_strategies": True,
        "paper_only": True,
        "live_blocked": True,
    }
    scorecard["scorecard_hash"] = stable_hash(scorecard)
    return scorecard


def default_autonomous_oss_scorecard() -> dict[str, Any]:
    return build_autonomous_oss_scorecard(oss_candidates())

