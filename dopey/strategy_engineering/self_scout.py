"""Self-Scout: watch film of our OWN tendencies before the market exploits them.

Championship staffs self-scout as hard as they scout opponents: "what are our
tells? where are we predictable, over-leveraged, or fooling ourselves?" For a
research system the analogue is adversarial self-examination of DOPEY's own
state - the failure modes that quietly turn honest machinery into theater:

  - are we entering the very contexts our own film grades as worst?
  - is the open book over-concentrated in one family or direction?
  - are the "independent" corroboration lanes actually independent, or do they
    share machinery (which would inflate confidence)?
  - is an evolvable surface being ground toward overfit (many trials, no
    improving score)?

It reports tendencies and weaknesses, ranked by severity. It fixes nothing and
promotes nothing; it hands a human (or the adversarial panel) the same honest
film a good coach demands of his own team. Measure-only, not_edge_evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
SELF_SCOUT_PATH = ART / "strategy_engineering" / "self_scout_report.json"

SELF_SCOUT_VERSION = "dopey-self-scout-v1"

# Convergence lanes that share detector machinery are only SEMI-independent.
SEMI_INDEPENDENT_LANE_PAIRS = {frozenset({"scanner_fitness", "playbook_forward_settlement"})}


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _finding(severity: str, tell: str, detail: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"severity": severity, "tell": tell, "detail": detail, "evidence": evidence}


def scout_book_vs_worst_contexts(
    forward_summary: dict[str, Any], scorecard: dict[str, Any]
) -> list[dict[str, Any]]:
    """Are we entering the contexts our own scorecard grades AVOID?"""
    avoid_families = {a["family"] for a in scorecard.get("avoid_list", [])}
    open_count = int(forward_summary.get("open_position_count", 0))
    findings: list[dict[str, Any]] = []
    # The forward walk records families on its closed/open trades; if the book is
    # concentrated in families whose worst context is AVOID-graded, flag the tell.
    directions = forward_summary.get("portfolio_direction_counts", {})
    if open_count and avoid_families:
        findings.append(
            _finding(
                "info",
                "book_in_avoid_graded_families",
                "the open book trades families whose extreme contexts the scorecard grades AVOID; "
                "confirm entries are NOT in stretched_above / deep_below contexts",
                {"open_position_count": open_count, "avoid_graded_families": sorted(avoid_families),
                 "direction_counts": directions},
            )
        )
    return findings


def scout_concentration(forward_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Over-concentration in one direction or symbol is a self-inflicted risk."""
    findings: list[dict[str, Any]] = []
    directions = forward_summary.get("portfolio_direction_counts", {})
    total = sum(int(v) for v in directions.values()) if isinstance(directions, dict) else 0
    if total >= 4:
        top = max(directions.values())
        share = top / total
        if share >= 0.8:
            findings.append(
                _finding(
                    "warn",
                    "directional_concentration",
                    f"{share:.0%} of the open book is one direction - a single regime turn hits the whole book",
                    {"direction_counts": directions},
                )
            )
    dup = int(forward_summary.get("portfolio_duplicate_symbol_position_count", 0))
    if dup > 0:
        findings.append(
            _finding("warn", "duplicate_symbol_exposure",
                     f"{dup} duplicate-symbol position(s) concentrate single-name risk",
                     {"duplicate_symbol_position_count": dup}))
    return findings


def scout_lane_independence(convergence: dict[str, Any]) -> list[dict[str, Any]]:
    """A 'corroboration' from lanes that share machinery is inflated confidence."""
    findings: list[dict[str, Any]] = []
    for family in convergence.get("families", []):
        if family.get("verdict") not in ("corroborated", "corroborated_strong"):
            continue
        lanes = set(family.get("independent_lanes", []))
        for pair in SEMI_INDEPENDENT_LANE_PAIRS:
            if pair <= lanes:
                findings.append(
                    _finding(
                        "warn",
                        "semi_independent_corroboration",
                        f"{family['family']} corroboration leans on lanes that share detector machinery "
                        f"({sorted(pair)}); treat the confidence as partial, not fully independent",
                        {"family": family["family"], "lanes": sorted(lanes)},
                    )
                )
    return findings


def scout_overfit_pressure(trial_ledger: dict[str, Any], evolution_status: dict[str, Any]) -> list[dict[str, Any]]:
    """Many search trials with no improving held-out score is overfit pressure."""
    findings: list[dict[str, Any]] = []
    distinct = int(trial_ledger.get("distinct_config_count", 0))
    cumulative = int(trial_ledger.get("cumulative_evals", 0))
    any_recommends = bool(evolution_status.get("surfaces_recommending_review"))
    if distinct >= 20 and not any_recommends:
        findings.append(
            _finding(
                "info",
                "search_breadth_without_improvement",
                f"{distinct} distinct configs evaluated ({cumulative} total runs) with no surface clearing the "
                "recommendation bar - healthy null so far, but rising trial count is exactly what the deflation "
                "penalty must keep pace with; keep watching the deflated score",
                {"distinct_config_count": distinct, "cumulative_evals": cumulative,
                 "surfaces_recommending": evolution_status.get("surfaces_recommending_review", [])},
            )
        )
    return findings


def build_self_scout(
    forward_summary: dict[str, Any],
    scorecard: dict[str, Any],
    convergence: dict[str, Any],
    trial_ledger: dict[str, Any],
    evolution_status: dict[str, Any],
) -> dict[str, Any]:
    findings = [
        *scout_book_vs_worst_contexts(forward_summary, scorecard),
        *scout_concentration(forward_summary),
        *scout_lane_independence(convergence),
        *scout_overfit_pressure(trial_ledger, evolution_status),
    ]
    order = {"critical": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    severities = {s: sum(1 for f in findings if f["severity"] == s) for s in ("critical", "warn", "info")}
    return {
        "artifact_type": "self_scout_report",
        "self_scout_version": SELF_SCOUT_VERSION,
        "findings": findings,
        "severity_counts": severities,
        "headline": (
            "clean film - no self-inflicted tells detected"
            if not findings
            else f"{severities['warn']} warn / {severities['info']} info tells - "
            + "; ".join(f["tell"] for f in findings[:3])
        ),
        "coaching_principle": (
            "self-scout as hard as you scout opponents: find your own tells before the market does. "
            "This flags weaknesses; it fixes and promotes nothing"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def run_self_scout() -> dict[str, Any]:
    from dopey_research_pipeline.artifact_io import write_json_atomic

    report = build_self_scout(
        forward_summary=_load(ART / "forward_walk" / "forward_walk_summary.json"),
        scorecard=_load(ART / "strategy_engineering" / "situational_scorecard.json"),
        convergence=_load(ART / "strategy_engineering" / "cross_lane_convergence.json"),
        trial_ledger=_load(ART / "evolution_fitness" / "trial_ledger.json"),
        evolution_status=_load(ART / "evolution" / "evolution_surfaces_status.json"),
    )
    write_json_atomic(SELF_SCOUT_PATH, report)
    return report
