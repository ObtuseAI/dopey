"""Consolidated evolvable-surfaces status - measure-only, recommend-only.

The status tool reads the latest fitness for each of the three surfaces and
reports whether any clears the recommendation bar. It must never apply
anything, must report the safety posture (auto_apply off everywhere), and
must handle a surface that has never run.
"""
from __future__ import annotations

import json

from operator_tools import operator_evolution_status as status
from dopey.strategy_engineering.scanner_holdout_fitness import (
    SCANNER_FITNESS_VERSION,
)


def _seed(tmp_path, monkeypatch, exit_score, screener_ic, scanner_score, scanner_per=None):
    art = tmp_path / "artifacts" / "dopey"
    (art / "evolution_fitness").mkdir(parents=True, exist_ok=True)
    (art / "screener").mkdir(parents=True, exist_ok=True)
    (art / "evolution").mkdir(parents=True, exist_ok=True)
    if exit_score is not None:
        (art / "evolution_fitness" / "last_eval.json").write_text(
            json.dumps({"score_psr": exit_score, "evaluated_at_utc": "2026-07-23T00:00:00+00:00"}),
            encoding="utf-8",
        )
    if screener_ic is not None:
        (art / "screener" / "elite_archive.json").write_text(
            json.dumps({"active_mean_holdout_rank_ic": screener_ic, "recommendation": None}),
            encoding="utf-8",
        )
    if scanner_score is not None:
        (art / "evolution" / "scanner_fitness_last_eval.json").write_text(
            json.dumps(
                {
                    "scanner_fitness_version": SCANNER_FITNESS_VERSION,
                    "score": scanner_score,
                    "holdout_events": 11478,
                    "mean_excess_over_drift": -0.0011,
                    "per_detector": scanner_per or {"short_term_reversal": {"mean_excess": 0.009}, "channel_breakout": {"mean_excess": -0.01}},
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(status, "ART", art)
    monkeypatch.setattr(status, "STATUS_PATH", art / "evolution" / "evolution_surfaces_status.json")


def test_no_edge_yields_no_recommendation(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, exit_score=0.0, screener_ic=0.007, scanner_score=0.478)
    result = status.build_status()
    assert result["surfaces_recommending_review"] == []
    assert result["consolidated_verdict"] == (
        "no evolvable surface shows held-out edge worth applying"
    )
    assert result["safety_posture"]["auto_apply_anywhere"] is False


def test_scanner_above_margin_recommends_review(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, exit_score=0.0, screener_ic=0.007, scanner_score=0.55)
    result = status.build_status()
    assert "scanner_thresholds" in result["surfaces_recommending_review"]


def test_exit_psr_above_margin_recommends(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, exit_score=0.30, screener_ic=0.007, scanner_score=0.478)
    result = status.build_status()
    assert "exit_trio" in result["surfaces_recommending_review"]


def test_missing_surface_is_named_not_crashed(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, exit_score=None, screener_ic=None, scanner_score=None)
    result = status.build_status()
    for surface in result["surfaces"]:
        assert surface.get("status") == "no_fitness_run_yet"
    assert result["surfaces_recommending_review"] == []


def test_positive_detectors_surfaced(tmp_path, monkeypatch) -> None:
    _seed(
        tmp_path, monkeypatch, exit_score=0.0, screener_ic=0.007, scanner_score=0.478,
        scanner_per={"short_term_reversal": {"mean_excess": 0.009}, "vcp": {"mean_excess": 0.003}, "channel_breakout": {"mean_excess": -0.01}},
    )
    result = status.build_status()
    scanner = next(s for s in result["surfaces"] if s["surface"] == "scanner_thresholds")
    assert scanner["detectors_with_positive_holdout_excess"] == ["short_term_reversal", "vcp"]


def test_status_artifact_is_written(tmp_path, monkeypatch) -> None:
    _seed(tmp_path, monkeypatch, exit_score=0.0, screener_ic=0.007, scanner_score=0.478)
    status.build_status()
    written = json.loads((tmp_path / "artifacts" / "dopey" / "evolution" / "evolution_surfaces_status.json").read_text())
    assert written["artifact_type"] == "evolution_surfaces_status"
    assert written["safety_posture"]["doofus_projects"] == ["dopey", "dopey_screener", "dopey_scanner"]


def test_stale_scanner_fitness_cannot_recommend_review(
    tmp_path,
    monkeypatch,
) -> None:
    _seed(
        tmp_path,
        monkeypatch,
        exit_score=0.0,
        screener_ic=0.007,
        scanner_score=0.99,
    )
    scanner_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "evolution"
        / "scanner_fitness_last_eval.json"
    )
    stale = json.loads(scanner_path.read_text(encoding="utf-8"))
    stale["scanner_fitness_version"] = "dopey-scanner-holdout-fitness-v1"
    scanner_path.write_text(json.dumps(stale), encoding="utf-8")

    result = status.build_status()
    scanner = next(
        surface
        for surface in result["surfaces"]
        if surface["surface"] == "scanner_thresholds"
    )

    assert scanner["status"] == "blocked_incompatible_fitness_version"
    assert scanner["recommends_review"] is False
    assert "scanner_thresholds" not in result["surfaces_recommending_review"]
