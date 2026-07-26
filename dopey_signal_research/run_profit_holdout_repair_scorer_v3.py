"""Profit factor and holdout repair scorer orchestration V3."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import (
    CANDIDATES_V3_PATH,
    PRIORITY_V3_PATH,
    RESEARCH_V3_ROOT,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file
from dopey_signal_research.holdout_split_repair_scorer_v3 import score_holdout_split_row
from dopey_signal_research.profit_factor_repair_scorer_v3 import score_profit_factor_row


PF_SCORES_PATH = RESEARCH_V3_ROOT / "profit_factor_repair_scores_v3.jsonl"
HOLDOUT_SCORES_PATH = RESEARCH_V3_ROOT / "holdout_split_repair_scores_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "profit_holdout_repair_scorer_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "profit_holdout_repair_scorer_v3_proof.jsonl"


def run_profit_holdout_repair_scorer_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    candidates = read_jsonl_file(CANDIDATES_V3_PATH)
    pf_rows = [score_profit_factor_row(c) for c in candidates]
    holdout_rows = [score_holdout_split_row(c) for c in candidates]
    priority_rows: list[dict[str, object]] = []
    pf_repair = holdout_repair = split_repair = 0

    for candidate, pf_row, holdout_row in zip(candidates, pf_rows, holdout_rows, strict=False):
        pf_score = float(pf_row.get("profit_factor_repair_score", 0.0))
        holdout_score = float(holdout_row.get("holdout_repair_score", 0.0))
        split_score = float(holdout_row.get("split_repair_score", 0.0))
        combined = pf_score * 0.4 + holdout_score * 0.3 + split_score * 0.3
        if pf_score >= 0.65:
            pf_repair += 1
        if holdout_score >= 0.65:
            holdout_repair += 1
        if split_score >= 0.65:
            split_repair += 1
        priority_rows.append(
            record_with_hash(
                {
                    "artifact_type": "candidate_pre_simulation_priority_v3",
                    "candidate_id": candidate.get("candidate_id", ""),
                    "priority_score": round(combined, 6),
                    "profit_factor_repair_score": pf_score,
                    "holdout_repair_score": holdout_score,
                    "split_repair_score": split_score,
                    "stable_family_template_id": candidate.get("stable_family_template_id", ""),
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )

    priority_rows.sort(key=lambda row: float(row.get("priority_score", 0.0)), reverse=True)
    status = "profit_holdout_repair_scored_v3"
    summary = {
        "artifact_type": "profit_holdout_repair_scorer_v3_summary",
        "profit_holdout_repair_scorer_v3_version": "dopey-public-profit-holdout-repair-scorer-v3",
        "profit_holdout_repair_scorer_status": status,
        "candidate_count": len(candidates),
        "prioritized_candidate_count": len(priority_rows),
        "profit_factor_repair_candidate_count": pf_repair,
        "holdout_repair_candidate_count": holdout_repair,
        "split_repair_candidate_count": split_repair,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(PF_SCORES_PATH, pf_rows)
    write_jsonl_file(HOLDOUT_SCORES_PATH, holdout_rows)
    write_jsonl_file(PRIORITY_V3_PATH, priority_rows)
    write_stage_proof(PROOF_PATH, "profit-holdout-repair-scorer-v3", status, summary)
    return {**summary, "artifact_paths": {"profit_holdout_repair_scorer_v3_summary": str(SUMMARY_PATH)}}
