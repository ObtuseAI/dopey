"""Score machine-admissible public/open data sources."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import data_outcome, open_data_candidates, stable_hash


def build_autonomous_open_data_source_scorecard(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [record for record in records if str(record["outcome"]).startswith("accepted_")]
    ingest = [record for record in records if record["outcome"] == "accepted_for_internal_research_ingest"]
    rejected = [record for record in records if str(record["outcome"]).startswith("rejected_") or record["outcome"] == "terminal_block"]
    scorecard = {
        "artifact_type": "autonomous_open_data_source_scorecard",
        "scorecard_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "candidate_count": len(records),
        "accepted_source_count": len(accepted),
        "accepted_ingest_source_count": len(ingest),
        "rejected_source_count": len(rejected),
        "quarantined_source_count": sum(1 for record in records if str(record["outcome"]).startswith("quarantined_")),
        "daily_ohlcv_ingest_source_count": sum(1 for record in ingest if record["dataset_family"] == "daily_ohlcv"),
        "unknown_license_auto_reject": True,
        "ambiguous_terms_auto_reject": True,
        "credentialed_source_auto_reject": True,
        "paid_or_proprietary_auto_reject": True,
        "scrape_only_auto_reject": True,
        "alpha_vantage_excluded": True,
        "paper_only": True,
        "live_blocked": True,
    }
    scorecard["scorecard_hash"] = stable_hash(scorecard)
    return scorecard


def default_autonomous_open_data_source_scorecard() -> dict[str, Any]:
    records = []
    for candidate in open_data_candidates():
        records.append({"dataset_family": candidate.family, "outcome": data_outcome(candidate)})
    return build_autonomous_open_data_source_scorecard(records)

