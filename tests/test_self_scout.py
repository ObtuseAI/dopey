"""Self-Scout - adversarial self-examination, measure-only.

It must catch our own tells: directional over-concentration, duplicate-name
risk, corroboration that leans on shared machinery, and search breadth without
improvement. It reports; it never fixes or promotes.
"""
from __future__ import annotations

from dopey.strategy_engineering.self_scout import (
    build_self_scout,
    scout_concentration,
    scout_lane_independence,
)


def test_directional_concentration_flagged() -> None:
    findings = scout_concentration({"portfolio_direction_counts": {"bullish": 9, "bearish": 1}})
    assert any(f["tell"] == "directional_concentration" for f in findings)


def test_balanced_book_not_flagged() -> None:
    findings = scout_concentration({"portfolio_direction_counts": {"bullish": 5, "bearish": 5}})
    assert not any(f["tell"] == "directional_concentration" for f in findings)


def test_duplicate_symbol_flagged() -> None:
    findings = scout_concentration({"portfolio_duplicate_symbol_position_count": 2})
    assert any(f["tell"] == "duplicate_symbol_exposure" for f in findings)


def test_semi_independent_corroboration_flagged() -> None:
    convergence = {"families": [{
        "family": "mean_reversion", "verdict": "corroborated",
        "independent_lanes": ["scanner_fitness", "playbook_forward_settlement"],
    }]}
    findings = scout_lane_independence(convergence)
    assert any(f["tell"] == "semi_independent_corroboration" for f in findings)


def test_truly_independent_corroboration_not_flagged() -> None:
    convergence = {"families": [{
        "family": "mean_reversion", "verdict": "corroborated",
        "independent_lanes": ["scanner_fitness", "screener_weights"],
    }]}
    assert scout_lane_independence(convergence) == []


def test_clean_state_reports_clean_film() -> None:
    report = build_self_scout(
        forward_summary={"open_position_count": 0, "portfolio_direction_counts": {}},
        scorecard={"avoid_list": []},
        convergence={"families": []},
        trial_ledger={"distinct_config_count": 1},
        evolution_status={"surfaces_recommending_review": []},
    )
    assert report["findings"] == []
    assert "clean film" in report["headline"]
    assert report["promotion_allowed"] is False


def test_findings_sorted_by_severity_and_measure_only() -> None:
    report = build_self_scout(
        forward_summary={"open_position_count": 5, "portfolio_direction_counts": {"bullish": 9, "bearish": 1}, "portfolio_duplicate_symbol_position_count": 1},
        scorecard={"avoid_list": [{"family": "momentum"}]},
        convergence={"families": []},
        trial_ledger={"distinct_config_count": 25, "cumulative_evals": 40},
        evolution_status={"surfaces_recommending_review": [], "surfaces": []},
    )
    severities = [f["severity"] for f in report["findings"]]
    assert severities == sorted(severities, key={"critical": 0, "warn": 1, "info": 2}.get)
    assert report["not_edge_evidence"] is True
