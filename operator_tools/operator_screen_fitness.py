"""OPERATOR TOOL - held-out screener-weight fitness (doofus target contract).

Scores the CURRENT dopey_screener/screen_config.py weights by mean held-out
rank-IC (dates strictly after TRAIN_END_DATE, point-in-time spine factors
only - snapshot factor families are excluded because today's fundamentals /
attention / flow snapshots cannot be honestly back-cast). Prints ONE final
line in [0, 1] so the external evolver (doofus) can hill-climb screen weights
under the exact same measure-only, human-committed discipline as the exit
trio: the evolver may propose, only a human applies.

Exit code 0 with a parseable last line = valid measurement.
Exit code 1 = measurement invalid (insufficient held-out sample) - the
evolver must treat this as failure, never as a score.

Usage:  .venv\\Scripts\\python operator_tools\\operator_screen_fitness.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402
from dopey_screener.elite_archive import current_weights, evaluate_weight_set  # noqa: E402

# Map mean rank-IC (weak-signal territory, typically |IC| < 0.1) into [0, 1]
# monotonically: 0.5 = no rank information, saturating toward 0/1 at |IC|=0.2.
IC_SCALE = 2.5
LAST_EVAL_PATH = REPO / "artifacts" / "dopey" / "evolution" / "screener_fitness_last_eval.json"


def main() -> int:
    evaluation = evaluate_weight_set(current_weights())
    mean_ic = float(evaluation["mean_holdout_rank_ic"])
    sufficient = bool(evaluation["sample_sufficient"])
    score = max(0.0, min(1.0, 0.5 + IC_SCALE * mean_ic)) if sufficient else None
    summary = {
        "config_id": evaluation["config_id"],
        "mean_holdout_rank_ic": mean_ic,
        "sample_sufficient": sufficient,
        "score": score,
        "fitness_scope": evaluation["fitness_scope"],
        "per_archetype": evaluation["per_archetype"],
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }
    # Persist so the cross-lane convergence engine can read per-archetype ICs
    # without re-running the full held-out screener evaluation.
    write_json_atomic(LAST_EVAL_PATH, {"artifact_type": "screener_fitness_evaluation", **summary})
    print(json.dumps(summary, sort_keys=True))
    if not sufficient:
        print("insufficient_holdout_sample_measurement_invalid")
        return 1
    print(f"{score:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
