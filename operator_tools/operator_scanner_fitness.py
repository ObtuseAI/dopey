"""OPERATOR TOOL - held-out scanner-parameter fitness (doofus target contract).

Scores the CURRENT dopey/strategy_engineering/playbook_scanner.py evolvable
thresholds by the held-out directional edge of the scanner's self-contained
detectors (see scanner_holdout_fitness for the discipline). Emits the doofus
0..1 contract: a JSON summary line, then either a final 0..1 score line or
an invalidity marker with exit 1 (the evolver must treat that as failure,
never as a score).

Score maps deflated held-out excess-over-drift onto 0..1 with 0.5 = no edge.
Measure-only: never edits a threshold. Paper-only, live-blocked.

Usage:  .venv\\Scripts\\python operator_tools\\operator_scanner_fitness.py
"""
from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.scanner_holdout_fitness import (  # noqa: E402
    evaluate_scanner_holdout,
)
from dopey.strategy_engineering.swing_target_discovery import load_ohlcv_history  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402

HISTORY_ROOT = REPO / "dopey_data" / "history" / "raw"
LAST_EVAL_PATH = REPO / "artifacts" / "dopey" / "evolution" / "scanner_fitness_last_eval.json"
# Excess is in return units; +0.5% held-out excess -> a clearly positive score.
EXCESS_SCALE = 40.0


def _build_summary(
    evaluation: Mapping[str, object],
    evaluated_at_utc: str,
) -> dict[str, object]:
    sufficient = bool(evaluation["sample_sufficient"])
    score = (
        max(
            0.0,
            min(
                1.0,
                0.5
                + EXCESS_SCALE
                * float(evaluation["deflated_mean_excess"]),
            ),
        )
        if sufficient
        else None
    )
    return {
        "artifact_type": "scanner_fitness_evaluation",
        "evaluated_at_utc": evaluated_at_utc,
        "scanner_fitness_version": evaluation["scanner_fitness_version"],
        "holdout_events": evaluation["holdout_events"],
        "holdout_event_unit": evaluation["holdout_event_unit"],
        "raw_detector_events": evaluation["raw_detector_events"],
        "cofired_detector_event_duplicates": evaluation[
            "cofired_detector_event_duplicates"
        ],
        "event_deduplication_policy_version": evaluation[
            "event_deduplication_policy_version"
        ],
        "distinct_detectors_fired": evaluation["distinct_detectors_fired"],
        "symbols_evaluated": evaluation["symbols_evaluated"],
        "selected_symbols": evaluation["selected_symbols"],
        "symbol_selection_policy": evaluation["symbol_selection_policy"],
        "mean_excess_over_drift": evaluation["mean_excess_over_drift"],
        "event_deduped_mean_excess_over_drift": evaluation[
            "event_deduped_mean_excess_over_drift"
        ],
        "raw_detector_weighted_mean_excess_over_drift": evaluation[
            "raw_detector_weighted_mean_excess_over_drift"
        ],
        "deflated_mean_excess": evaluation["deflated_mean_excess"],
        "hit_rate": evaluation["hit_rate"],
        "raw_detector_weighted_hit_rate": evaluation[
            "raw_detector_weighted_hit_rate"
        ],
        "drift_baseline_policy": evaluation["drift_baseline_policy"],
        "drift_baseline_policy_version": evaluation[
            "drift_baseline_policy_version"
        ],
        "source_universe_hash": evaluation["source_universe_hash"],
        "source_hash_policy_version": evaluation[
            "source_hash_policy_version"
        ],
        "source_hash_fields": evaluation["source_hash_fields"],
        "detector_exception_count": evaluation["detector_exception_count"],
        "detector_exception_counts": evaluation[
            "detector_exception_counts"
        ],
        "detector_exception_budget_status": evaluation[
            "detector_exception_budget_status"
        ],
        "sample_sufficient": sufficient,
        "score": score,
        "per_detector": evaluation["per_detector"],
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def main() -> int:
    bars_by_symbol = load_ohlcv_history(HISTORY_ROOT)
    evaluation = evaluate_scanner_holdout(bars_by_symbol)
    summary = _build_summary(
        evaluation,
        datetime.now(timezone.utc).isoformat(),
    )
    write_json_atomic(LAST_EVAL_PATH, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "artifact_type"}, sort_keys=True), flush=True)
    if not bool(summary["sample_sufficient"]):
        print("insufficient_holdout_sample_measurement_invalid", flush=True)
        return 1
    print(f"{float(summary['score']):.6f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
