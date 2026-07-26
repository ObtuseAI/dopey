"""OPERATOR TOOL - one pane over every evolvable surface (measure-only).

DOPEY has three recursive-improvement surfaces, each with a held-out fitness
and a doofus target: the exit trio, the screener weights, and (now) the
scanner thresholds. This reads the LATEST fitness result for each and reports
a single consolidated status: current score, whether it clears a
recommendation bar, and the standing safety posture (auto_apply is off
everywhere; the evolver recommends, a human applies).

It does NOT re-run the expensive fitness lanes (run those directly to
refresh) and it NEVER applies a change. A surface only "recommends" when its
held-out score clears the neutral line by a margin - and even then, promotion
is an operator's gated decision, never this tool's.

Usage:  .venv\\Scripts\\python operator_tools\\operator_evolution_status.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402
from dopey.strategy_engineering.scanner_holdout_fitness import (  # noqa: E402
    SCANNER_FITNESS_VERSION,
)

ART = REPO / "artifacts" / "dopey"
STATUS_PATH = ART / "evolution" / "evolution_surfaces_status.json"

NEUTRAL = 0.5
# A surface must beat neutral by this margin before it even RECOMMENDS a
# review; applying anything is still a separate gated operator decision.
RECOMMEND_MARGIN = 0.02


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _exit_surface() -> dict:
    data = _load(ART / "evolution_fitness" / "last_eval.json")
    if not data:
        return {"surface": "exit_trio", "status": "no_fitness_run_yet"}
    score = float(data.get("score_psr", 0.0))
    return {
        "surface": "exit_trio",
        "config_module": "dopey_backtest/exit_policy_config.py",
        "fitness": "held-out deflated Sharpe (PSR)",
        "score": round(score, 6),
        "score_scale": "0..1 (PSR); higher = more held-out edge",
        "recommends_review": score >= RECOMMEND_MARGIN,
        "evaluated_at": str(data.get("evaluated_at_utc", "")),
    }


def _screener_surface() -> dict:
    data = _load(ART / "screener" / "elite_archive.json")
    if not data:
        return {"surface": "screener_weights", "status": "no_fitness_run_yet"}
    ic = float(data.get("active_mean_holdout_rank_ic", 0.0))
    recommendation = data.get("recommendation")
    return {
        "surface": "screener_weights",
        "config_module": "dopey_screener/screen_config.py",
        "fitness": "held-out mean rank-IC",
        "active_mean_holdout_rank_ic": round(ic, 6),
        "score": round(max(0.0, min(1.0, 0.5 + 10.0 * ic)), 6),
        "recommends_review": recommendation is not None,
        "recommendation": recommendation,
    }


def _scanner_surface() -> dict:
    data = _load(ART / "evolution" / "scanner_fitness_last_eval.json")
    if not data:
        return {"surface": "scanner_thresholds", "status": "no_fitness_run_yet"}
    observed_version = str(data.get("scanner_fitness_version", ""))
    if observed_version != SCANNER_FITNESS_VERSION:
        return {
            "surface": "scanner_thresholds",
            "status": "blocked_incompatible_fitness_version",
            "expected_scanner_fitness_version": SCANNER_FITNESS_VERSION,
            "observed_scanner_fitness_version": observed_version or "missing",
            "recommends_review": False,
        }
    score = data.get("score")
    per = data.get("per_detector", {})
    positive = sorted(
        (name for name, bucket in per.items() if bucket.get("mean_excess", 0.0) > 0.0)
    )
    return {
        "surface": "scanner_thresholds",
        "config_module": "dopey/strategy_engineering/scanner_evolvable_config.py",
        "fitness": "held-out directional excess-over-drift (deflated)",
        "score": score,
        "holdout_events": data.get("holdout_events"),
        "holdout_event_unit": data.get("holdout_event_unit"),
        "raw_detector_events": data.get("raw_detector_events"),
        "mean_excess_over_drift": data.get("mean_excess_over_drift"),
        "event_deduplication_policy_version": data.get(
            "event_deduplication_policy_version"
        ),
        "drift_baseline_policy_version": data.get(
            "drift_baseline_policy_version"
        ),
        "source_universe_hash": data.get("source_universe_hash"),
        "detectors_with_positive_holdout_excess": positive,
        "recommends_review": bool(score is not None and score >= NEUTRAL + RECOMMEND_MARGIN),
    }


def build_status() -> dict:
    surfaces = [_exit_surface(), _screener_surface(), _scanner_surface()]
    recommending = [s["surface"] for s in surfaces if s.get("recommends_review")]
    scored = [s for s in surfaces if isinstance(s.get("score"), (int, float))]
    status = {
        "artifact_type": "evolution_surfaces_status",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "neutral_line": NEUTRAL,
        "recommend_margin": RECOMMEND_MARGIN,
        "surfaces": surfaces,
        "surfaces_recommending_review": recommending,
        "consolidated_verdict": (
            f"{len(recommending)} of {len(surfaces)} surfaces recommend review"
            if recommending
            else "no evolvable surface shows held-out edge worth applying"
        ),
        "any_surface_above_neutral": any(float(s["score"]) > NEUTRAL for s in scored),
        "safety_posture": {
            "auto_apply_anywhere": False,
            "evolver_role": "recommend_only",
            "application_authority": "human_gated_commit",
            "doofus_projects": ["dopey", "dopey_screener", "dopey_scanner"],
        },
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(STATUS_PATH, status)
    return status


def main() -> int:
    status = build_status()
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
