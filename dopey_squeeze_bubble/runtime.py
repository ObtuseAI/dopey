"""Daily runtime for squeeze/bubble assessment, ranking, and settlement."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey.strategy_engineering.swing_target_discovery import load_ohlcv_history
from dopey_acceleration.common import write_json_atomic

from .engine import evaluate_symbol, rank_candidates
from .intake import (
    IntelligencePaths,
    default_paths,
    load_symbol_evidence,
    require_contained_path,
)
from .models import IntelligencePolicy, default_policy
from .settlement import (
    append_forward_signals,
    build_forward_evidence_report,
    settle_forward_signals,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts" / "dopey" / "squeeze_bubble"
ASSESSMENTS_PATH = ARTIFACT_ROOT / "symbol_assessments.jsonl"
RANKINGS_PATH = ARTIFACT_ROOT / "candidate_rankings.json"
SIGNAL_LEDGER_PATH = ARTIFACT_ROOT / "forward_signal_ledger.jsonl"
SETTLEMENT_LEDGER_PATH = ARTIFACT_ROOT / "forward_settlement_ledger.jsonl"
FORWARD_EVIDENCE_PATH = ARTIFACT_ROOT / "forward_evidence_report.json"
SUMMARY_PATH = ARTIFACT_ROOT / "squeeze_bubble_summary.json"


def _write_jsonl_atomic(path: Path, records: tuple[dict[str, Any], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _assessment_lookup(
    assessments: tuple[dict[str, Any], ...],
) -> dict[str, dict[str, Any]]:
    return {str(assessment["assessment_id"]): assessment for assessment in assessments}


def _ranked_symbols(
    assessment_by_id: dict[str, dict[str, Any]],
    identifiers: tuple[str, ...],
    lane: str,
    limit: int,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "assessment_id": identifier,
            "symbol": assessment_by_id[identifier]["symbol"],
            "score": assessment_by_id[identifier][lane]["score"],
            "status": assessment_by_id[identifier][lane]["status"],
            "gate_reasons": assessment_by_id[identifier][lane]["gate_reasons"],
            "evidence_completeness": assessment_by_id[identifier][lane][
                "evidence_completeness"
            ],
            "pressure_score": assessment_by_id[identifier][lane].get("pressure_score"),
            "ignition_score": assessment_by_id[identifier][lane].get("ignition_score"),
            "fragility_score": assessment_by_id[identifier][lane].get(
                "fragility_score"
            ),
            "unwind_trigger_score": assessment_by_id[identifier][lane].get(
                "unwind_trigger_score"
            ),
            "extreme_pe_score": assessment_by_id[identifier][lane].get(
                "extreme_pe_score"
            ),
            "ipo_reflexivity_score": assessment_by_id[identifier][lane].get(
                "ipo_reflexivity_score"
            ),
            "persistence_score": assessment_by_id[identifier][lane].get(
                "persistence_score"
            ),
            "robustness_score": assessment_by_id[identifier][lane]["robustness"][
                "robustness_score"
            ],
            "liquidity_proxy_score": assessment_by_id[identifier][lane]
            .get(
                "observed_liquidity_stress",
                assessment_by_id[identifier][lane].get(
                    "observed_liquidity_air_pocket",
                    {},
                ),
            )
            .get("score"),
            "preferred_expression": assessment_by_id[identifier][lane][
                "preferred_expression"
            ],
        }
        for identifier in identifiers[:limit]
    )


def run_squeeze_bubble_intelligence(
    paths: IntelligencePaths,
    policy: IntelligencePolicy,
    observed_at: datetime,
    artifact_root: Path,
) -> dict[str, Any]:
    """Run one deterministic evidence-first intelligence cycle."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    evidence, intake = load_symbol_evidence(
        paths,
        observed_at,
        policy.maximum_source_age_days,
    )
    assessments = tuple(evaluate_symbol(record, policy) for record in evidence)
    decision_at = observed_at.astimezone(timezone.utc).isoformat()
    assessments = tuple(
        {
            **assessment,
            "decision_at_utc": decision_at,
            "paper_only": True,
            "live_blocked": True,
        }
        for assessment in assessments
    )
    rankings = rank_candidates(assessments)
    assessment_by_id = _assessment_lookup(assessments)

    root = require_contained_path(
        paths.repository_root,
        artifact_root,
        "artifact_output_root",
    )
    assessments_path = root / ASSESSMENTS_PATH.name
    rankings_path = root / RANKINGS_PATH.name
    signal_path = root / SIGNAL_LEDGER_PATH.name
    settlement_path = root / SETTLEMENT_LEDGER_PATH.name
    evidence_path = root / FORWARD_EVIDENCE_PATH.name
    summary_path = root / SUMMARY_PATH.name
    _write_jsonl_atomic(assessments_path, assessments)
    rankings_artifact = {
        "artifact_type": "squeeze_bubble_candidate_rankings",
        "ranking_version": "dopey-squeeze-bubble-rankings-v2",
        "decision_at_utc": decision_at,
        "market_data_as_of": max(
            (str(item["as_of_date"]) for item in assessments),
            default="",
        ),
        "queues": rankings,
        "top_squeeze_candidates": _ranked_symbols(
            assessment_by_id,
            rankings["squeeze_candidates"],
            "squeeze",
            20,
        ),
        "top_squeeze_watch": _ranked_symbols(
            assessment_by_id,
            rankings["squeeze_watch"],
            "squeeze",
            20,
        ),
        "top_bubble_unwind_candidates": _ranked_symbols(
            assessment_by_id,
            rankings["bubble_unwind_candidates"],
            "bubble",
            20,
        ),
        "top_bubble_fragility_monitors": _ranked_symbols(
            assessment_by_id,
            rankings["bubble_fragility_monitors"],
            "bubble",
            20,
        ),
        "top_bubble_watch": _ranked_symbols(
            assessment_by_id,
            rankings["bubble_watch"],
            "bubble",
            20,
        ),
        "rank_scores_are_probabilities": False,
        "profit_or_edge_claimed": False,
        "empirical_observations_only": True,
        "speculative_forecasting_allowed": False,
        "direct_hidden_liquidity_claimed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(rankings_path, rankings_artifact)

    recording = append_forward_signals(
        assessments,
        decision_at,
        policy.forward_horizons,
        signal_path,
    )
    settlement = settle_forward_signals(
        load_ohlcv_history(paths.history_root),
        signal_path,
        settlement_path,
    )
    forward_evidence = build_forward_evidence_report(
        settlement_path,
        policy.minimum_settled_observations,
    )
    write_json_atomic(evidence_path, forward_evidence)

    lane_gaps = tuple(intake["lane_gaps"])
    summary: dict[str, Any] = {
        "artifact_type": "squeeze_bubble_intelligence_summary",
        "engine_version": "dopey-squeeze-bubble-intelligence-v2",
        "squeeze_bubble_status": (
            "complete_research_only_with_typed_evidence_gaps"
            if lane_gaps
            else "complete_research_only"
        ),
        "decision_at_utc": decision_at,
        "symbol_count": len(assessments),
        "squeeze_candidate_count": len(rankings["squeeze_candidates"]),
        "squeeze_watch_count": len(rankings["squeeze_watch"]),
        "bubble_unwind_candidate_count": len(rankings["bubble_unwind_candidates"]),
        "bubble_fragility_monitor_count": len(rankings["bubble_fragility_monitors"]),
        "bubble_watch_count": len(rankings["bubble_watch"]),
        "intake": intake,
        "forward_recording": recording,
        "forward_settlement": settlement,
        "forward_evidence_status": forward_evidence["overall_evidence_status"],
        "artifacts": {
            "assessments": str(assessments_path),
            "rankings": str(rankings_path),
            "forward_signal_ledger": str(signal_path),
            "forward_settlement_ledger": str(settlement_path),
            "forward_evidence": str(evidence_path),
        },
        "short_interest_and_daily_short_volume_separated": True,
        "squeeze_requires_pressure_and_price_ignition": True,
        "bubble_requires_fragility_and_unwind_trigger": True,
        "squeeze_requires_persistence_and_robustness": True,
        "bubble_requires_persistence_and_robustness": True,
        "contradictory_evidence_forces_abstention": True,
        "stale_sparse_or_future_evidence_forces_abstention": True,
        "observed_liquidity_proxies_are_not_direct_hidden_liquidity": True,
        "empirical_observations_only": True,
        "speculative_forecasting_allowed": False,
        "bearish_equity_shorting_allowed": False,
        "undefined_loss_allowed": False,
        "same_session_round_trip_allowed": False,
        "paper_twin_required_for_any_live_review": True,
        "research_maturity_gate_bypassed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(summary_path, summary)
    return summary


def main() -> int:
    result = run_squeeze_bubble_intelligence(
        default_paths(REPOSITORY_ROOT),
        default_policy(),
        datetime.now(timezone.utc),
        ARTIFACT_ROOT,
    )
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
