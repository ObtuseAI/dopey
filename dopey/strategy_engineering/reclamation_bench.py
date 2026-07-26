"""Reclamation Bench: refused hypotheses, diagnosed flaws, machine-checkable re-tests.

The Dodgers' quiet superpower is not stars - it is RECLAMATION: acquire the
discarded (Muncy, Turner, half a pitching staff), diagnose the ONE fixable
flaw, rework it, re-promote when the evidence says so. DOPEY refuses
hypotheses rigorously - and then forgets them. That loses information: a
refusal is usually CONDITIONAL ("no direction edge at THIS horizon", "misses
the cost line at THIS IV"), and when the world changes the right move is a
deliberate re-test, not a rediscovery from scratch.

The bench holds each refused hypothesis with:
  - the refusal source (which prosecution refused it),
  - the diagnosed flaw (specific, conditional - never just "failed"),
  - a MACHINE-CHECKABLE retest trigger evaluated against live artifacts.

Honesty invariants: the bench never un-refuses anything and never promotes.
When a trigger fires it recommends re-running the EXISTING prosecution
machinery (study/fitness/settlement) - the same gauntlet, fresh evidence.
A benched idea leaves the bench only by being re-prosecuted.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .playbook_settlement import PLAYBOOK_TRUST_VERSION
from .scanner_holdout_fitness import SCANNER_FITNESS_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
BENCH_PATH = ART / "strategy_engineering" / "reclamation_bench.json"

BENCH_VERSION = "dopey-reclamation-bench-v1"
RATED_FLOOR = 30


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Trigger predicates: each takes the live artifact bundle, returns
# (fired: bool, evidence: str). Deliberately simple and readable.
# ---------------------------------------------------------------------------

def _trigger_squeeze_forward_rated_positive(artifacts: Mapping[str, Any]) -> tuple[bool, str]:
    trust = artifacts.get("playbook_trust", {})
    if trust.get("playbook_trust_version") != PLAYBOOK_TRUST_VERSION:
        return False, "forward settlement trust artifact version is incompatible"
    per_setup = trust.get("per_setup", {})
    bucket = per_setup.get("bb_squeeze_breakout", {})
    settled = bucket.get("effective_contested_settled")
    rate = bucket.get("effective_contested_hit_rate")
    if (
        bucket.get("trust_state") == "rated"
        and isinstance(settled, int)
        and settled >= RATED_FLOOR
        and isinstance(rate, (int, float))
        and rate > 0.55
    ):
        return (
            True,
            "forward effective contested settlement rated "
            f"{rate:.1%} on clustered n={settled}",
        )
    return (
        False,
        "forward settlement not rated-positive yet "
        f"(effective_n={settled}, effective_rate={rate})",
    )


def _trigger_mean_reversion_clears_cost_line(artifacts: Mapping[str, Any]) -> tuple[bool, str]:
    scanner_artifact = artifacts.get("scanner_fitness", {})
    scanner_is_current = (
        scanner_artifact.get("scanner_fitness_version")
        == SCANNER_FITNESS_VERSION
    )
    scanner = (
        scanner_artifact.get("per_detector", {})
        if scanner_is_current
        else {}
    )
    reversion = [scanner.get(d, {}) for d in ("short_term_reversal", "band_snapback", "quality_pullback", "capitulation")]
    events = sum(int(b.get("events", 0)) for b in reversion)
    excess = (
        sum(float(b.get("mean_excess", 0.0)) * int(b.get("events", 0)) for b in reversion) / events
        if events else 0.0
    )
    vix = artifacts.get("macro", {}).get("vol_term_structure", {}).get("VIX")
    if excess >= 0.0075:
        return True, f"held-out reversion excess {excess:+.4f} exceeds the ~0.75% best-angle breakeven"
    if isinstance(vix, (int, float)) and vix < 13.0:
        return True, f"VIX {vix:.1f} < 13 lowers the option breakeven; re-run the expression grid at current IV"
    version_note = (
        ""
        if scanner_is_current
        else "; scanner fitness version incompatible"
    )
    return (
        False,
        f"excess {excess:+.4f} still below best-angle breakeven and "
        f"VIX not low enough{version_note}",
    )


def _trigger_vol_expansion_ic_flips(artifacts: Mapping[str, Any]) -> tuple[bool, str]:
    per = artifacts.get("screener_fitness", {}).get("per_archetype", {})
    ic = per.get("long_premium_vol_expansion", {}).get("mean_holdout_rank_ic")
    if isinstance(ic, (int, float)) and ic > 0.005:
        return True, f"vol_expansion held-out IC flipped positive ({ic:+.4f})"
    return False, f"vol_expansion IC still non-positive ({ic})"


def _trigger_veto_class_leaves_money(artifacts: Mapping[str, Any]) -> tuple[bool, str]:
    per_class = artifacts.get("veto_shadow", {}).get("per_veto_class", {})
    rated = {
        name: stats
        for name, stats in per_class.items()
        if int(stats.get("n", 0)) >= RATED_FLOOR and float(stats.get("mean_trade_return", 0.0)) > 0.0
    }
    if rated:
        worst_offender = max(rated.items(), key=lambda item: float(item[1]["mean_trade_return"]))
        return True, (
            f"veto class {worst_offender[0]} shows positive phantom expectancy "
            f"({float(worst_offender[1]['mean_trade_return']):+.2%} on n={int(worst_offender[1]['n'])}) - "
            "the veto is measurably leaving money on the table"
        )
    measured = sum(int(stats.get("n", 0)) for stats in per_class.values())
    return False, f"no veto class rated-positive yet (phantom closes measured: {measured})"


def _trigger_momentum_convergence_resolves(artifacts: Mapping[str, Any]) -> tuple[bool, str]:
    for family in artifacts.get("convergence", {}).get("families", []):
        if family.get("family") == "momentum_continuation":
            verdict = family.get("verdict")
            if verdict in ("corroborated", "corroborated_strong"):
                return True, f"momentum convergence resolved to {verdict} ({family.get('consensus_sign')})"
            return False, f"momentum still {verdict}"
    return False, "momentum family absent from convergence"


TriggerFn = Callable[[Mapping[str, Any]], tuple[bool, str]]

# The bench: seeded with this week's REAL refusals. Every entry names its
# refusal source and the SPECIFIC conditional flaw - never just "failed".
BENCH: tuple[dict[str, Any], ...] = (
    {
        "bench_id": "bb_squeeze_direction_5d",
        "hypothesis": "confirmed BB-squeeze breaks predict signed 5d return",
        "refused_by": "compression_expansion_study (2026-07-22)",
        "diagnosed_flaw": "no directional edge beyond drift at the 5d horizon on daily equities "
                          "(hit 47.3%/50.5%, excess -19bp/-24bp both eras)",
        "retest_recommendation": "re-run compression study at 10/20d horizons, or accept forward settlement verdict",
        "trigger_description": "forward contested settlement for bb_squeeze_breakout becomes rated >55%",
    },
    {
        "bench_id": "mean_reversion_long_option_expression",
        "hypothesis": "corroborated mean-reversion underlying edge expressed as a long option",
        "refused_by": "option_expression_cost + expression_selector (2026-07-23)",
        "diagnosed_flaw": "+0.62% underlying excess vs 0.75% best-release-angle breakeven "
                          "(deep-ITM 14DTE) - misses the cost line by 0.13%",
        "retest_recommendation": "re-run the expression grid at current IV and the scanner fitness for fresh excess",
        "trigger_description": "held-out reversion excess >= 0.75% OR VIX < 13 (lower breakeven)",
    },
    {
        "bench_id": "vol_expansion_screener_archetype",
        "hypothesis": "long-premium vol-expansion screening ranks forward returns",
        "refused_by": "screener held-out fitness (IC -0.0074)",
        "diagnosed_flaw": "negative held-out rank-IC; consistent with compression study and VRP",
        "retest_recommendation": "re-run screener fitness; only a positive IC re-opens the case",
        "trigger_description": "vol_expansion held-out IC > +0.005",
    },
    {
        "bench_id": "context_veto_classes_earn_their_keep",
        "hypothesis": "opinion vetoes (context bias, adversarial verdict) prevent negative-EV entries",
        "refused_by": "deployed by design without forward evidence; veto shadow ledger measures it (2026-07-23)",
        "diagnosed_flaw": "the veto stack rejected 387+ candidates per cycle on derived reasoning whose "
                          "forward opportunity cost was unmeasured until the shadow lane existed",
        "retest_recommendation": "re-examine any rated-positive veto class with the standard prosecution "
                                 "(study/fitness/settlement); never auto-loosen",
        "trigger_description": "any veto class reaches n>=30 phantom closes with positive mean trade return",
    },
    {
        "bench_id": "momentum_direction_contested",
        "hypothesis": "momentum-continuation entries carry directional edge",
        "refused_by": "cross_lane_convergence (contested: scanner n=9247 negative vs screener n=1 positive)",
        "diagnosed_flaw": "independent lanes disagree on sign; big-sample lane is negative",
        "retest_recommendation": "wait for convergence to resolve; re-run both lanes after data accrual",
        "trigger_description": "momentum convergence verdict becomes corroborated (either sign)",
    },
)

TRIGGERS: dict[str, TriggerFn] = {
    "bb_squeeze_direction_5d": _trigger_squeeze_forward_rated_positive,
    "mean_reversion_long_option_expression": _trigger_mean_reversion_clears_cost_line,
    "vol_expansion_screener_archetype": _trigger_vol_expansion_ic_flips,
    "context_veto_classes_earn_their_keep": _trigger_veto_class_leaves_money,
    "momentum_direction_contested": _trigger_momentum_convergence_resolves,
}


def load_artifact_bundle() -> dict[str, Any]:
    return {
        "playbook_trust": _load(ART / "playbook" / "playbook_family_trust.json"),
        "scanner_fitness": _load(ART / "evolution" / "scanner_fitness_last_eval.json"),
        "screener_fitness": _load(ART / "evolution" / "screener_fitness_last_eval.json"),
        "convergence": _load(ART / "strategy_engineering" / "cross_lane_convergence.json"),
        "macro": _load(ART / "macro_context" / "macro_context_summary.json"),
        "veto_shadow": _load(ART / "forward_walk" / "veto_shadow_summary.json"),
    }


def scout_reclamations(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate every benched hypothesis's trigger against live artifacts."""
    entries: list[dict[str, Any]] = []
    for benched in BENCH:
        trigger = TRIGGERS.get(benched["bench_id"])
        if trigger is None:
            fired, evidence = False, "no trigger registered"
        else:
            try:
                fired, evidence = trigger(artifacts)
            except Exception as error:  # noqa: BLE001 - a trigger bug must not kill the scout
                fired, evidence = False, f"trigger_error:{type(error).__name__}"
        entries.append({
            **benched,
            "status": "retest_recommended" if fired else "bench_hold",
            "trigger_evidence": evidence,
        })
    recommended = [e["bench_id"] for e in entries if e["status"] == "retest_recommended"]
    return {
        "artifact_type": "reclamation_bench",
        "bench_version": BENCH_VERSION,
        "entries": entries,
        "retest_recommended": recommended,
        "headline": (
            f"{len(recommended)}/{len(entries)} benched hypotheses warrant a re-test: "
            + ", ".join(recommended)
            if recommended
            else f"all {len(entries)} benched hypotheses hold - the refusal conditions still stand"
        ),
        "honesty_invariants": {
            "never_un_refuses": True,
            "retest_means_rerun_the_same_prosecution": True,
            "promotion_allowed": False,
        },
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def run_reclamation_bench() -> dict[str, Any]:
    from dopey_research_pipeline.artifact_io import write_json_atomic

    report = scout_reclamations(load_artifact_bundle())
    write_json_atomic(BENCH_PATH, report)
    return report
