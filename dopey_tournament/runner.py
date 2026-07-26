"""Dopey tournament runner: offline deterministic multi-strategy paper tournament orchestrator.

run_fixture_tournament() drives:
  load expanded windows -> load N genomes -> per-window analysis fusion (family-regime aware)
  -> per-genome family-aware walk-forward replay -> overfit classify -> aggression gate
  (paper-only) -> rank with deterministic tie-breakers -> champion/runner-up ->
  champion registry (family strengths/weaknesses) -> tournament ProofLedger record ->
  concise JSON summary.

Fully offline, paper-only, fixture-based, deterministic, live-blocked.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

from dopey_core.config import load_config, default_config_path
from dopey_core.proof_ledger import ProofLedger
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_execution.liquidity_model import LIQUIDITY_MODEL_VERSION
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.slippage_model import SLIPPAGE_MODEL_VERSION
from dopey_options.greeks_validation import (
    GREEKS_VALIDATION_MODEL_VERSION,
    GreekRiskVerdict,
    summarize_profile_strengths,
)
from dopey_options.iv_surface_fixture import IV_FIXTURE_MODEL_VERSION
from dopey_options.iv_surface_expansion import IV_SURFACE_EXPANSION_VERSION
from dopey_options.structure_builder import STRUCTURE_BUILDER_VERSION
from dopey_walk_forward.window_model import load_walk_forward_windows
from dopey_walk_forward.replay_engine import ReplayEngine
from dopey_walk_forward.scoring import score_walk_forward
from dopey_walk_forward.overfit_classifier import classify_overfit
from dopey_walk_forward.family_outcome import REQUIRED_REGIME_TAGS, STRATEGY_FAMILIES, family_hint
from dopey_analysis.enrichment import load_window_analysis, parse_window_analysis
from dopey_analysis.analysis_fusion import fuse_analysis
from dopey_analysis.macro_event_scenarios import build_macro_event_scenarios, scenario_for_regime
from dopey_analysis.macro_family_scoring import score_family_macro_event
from dopey_analysis.sector_peer_scenarios import (
    SECTOR_PEER_FUNDAMENTAL_FIXTURE_VERSION as FUNDAMENTAL_FIXTURE_VERSION,
    build_sector_peer_fundamental_scenarios,
)
from dopey_analysis.fundamental_family_scoring import score_family_fundamental
from dopey_analysis.models import AnalysisFusionScore
from dopey_analysis.pattern_fixture_library import build_pattern_fixture_library, summarize_pattern_fixture_library
from dopey_analysis.pattern_scorecard import score_pattern_context, summarize_pattern_scores
from dopey_data.source_value_ranker import source_scorecard_summary as build_source_scorecard_summary
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_strategy_lab.mutation_registry import latest_mutation_summary
from dopey_strategy_lab.failure_mode_registry import latest_failure_mode_summary

from .genome_set import build_tournament_genomes, build_tournament_proof_bundle
from .models import TournamentResult, StrategyTournamentScore, ChampionRegistryEntry
from .aggression_tournament import evaluate_tournament_promotion
from .ledger_tournament import (
    build_tournament_proof_entry, write_champion_registry,
    TOURNAMENT_LEDGER_PATH, CHAMPION_REGISTRY_PATH,
)

CORPUS_ID = "dopey-regime-corpus-v1"
OVERFIT_RANK = {"none": 0, "low": 1, "moderate": 2, "high": 3}
MACRO_EVENT_EXPANSION_VERSION = "dopey-macro-event-expansion-v1"
FUNDAMENTAL_EXPANSION_VERSION = "dopey-sector-peer-fundamental-expansion-v1"


@dataclass
class TournamentSummary:
    mode: str
    live_trading_enabled: bool
    tournament_status: str
    champion_strategy_id: str
    runner_up_strategy_id: str
    windows_replayed: int
    strategies_evaluated: int
    champion_registry_path: str
    proof_record_path: str
    live_blocked: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _combined_score(
    wf_overall: float,
    fusion_overall: float,
    greek_fit: float = 0.5,
    iv_score: float = 0.5,
    liquidity: float = 0.5,
    slippage: float = 0.5,
    invalidation: float = 0.5,
    holdout: float = 0.0,
    overfit_rank: int = 3,
    macro_fit: float = 0.5,
    macro_risk: float = 0.5,
    fundamental_fit: float = 0.5,
    fundamental_contradiction: float = 0.5,
) -> float:
    holdout_score = max(0.0, min(1.0, (holdout + 8.0) / 16.0))
    overfit_score = max(0.0, min(1.0, 1.0 - float(overfit_rank) / 3.0))
    macro_event_score = (
        0.04 * macro_fit
        - 0.02 * macro_risk
        + 0.01 * (macro_fit - macro_risk)
    )
    fundamental_score = (
        0.03 * fundamental_fit
        - 0.02 * fundamental_contradiction
    )
    score = (
        0.33 * wf_overall
        + 0.17 * fusion_overall
        + 0.15 * greek_fit
        + 0.08 * iv_score
        + 0.07 * liquidity
        + 0.05 * slippage
        + 0.05 * invalidation
        + 0.04 * holdout_score
        + 0.03 * overfit_score
        + macro_event_score
        + fundamental_score
    )
    return round(max(0.0, min(1.0, score)), 6)


def rank_strategy_scores(scores: list[StrategyTournamentScore]) -> list[StrategyTournamentScore]:
    """Rank strategies by combined_score with deterministic tie-breakers.

    Tie-break order (only matters when combined_score is equal):
      1. lower overfit (none<low<moderate<high)
      2. higher holdout score
      3. better liquidity robustness
      4. better invalidation quality
      5. deterministic strategy_id sort
    Never insertion order unless every tie-breaker is truly equal.
    """
    return sorted(scores, key=lambda s: (
        -s.combined_score,
        OVERFIT_RANK.get(s.overfit_level, 3),
        -s.average_greek_fit_score,
        -s.average_greek_attribution_quality,
        -s.holdout_score,
        -s.liquidity_robustness,
        -s.average_fill_quality_score,
        -s.slippage_robustness_score,
        -s.invalidation_quality,
        s.strategy_id,
    ))


def _family_scorecard(scores: list[StrategyTournamentScore]) -> dict:
    by_fam: dict[str, list[StrategyTournamentScore]] = {}
    for s in scores:
        by_fam.setdefault(s.strategy_family, []).append(s)
    out: dict[str, dict] = {}
    for fam, entries in by_fam.items():
        n = len(entries)
        out[fam] = {
            "avg_combined_score": round(sum(e.combined_score for e in entries) / n, 6),
            "avg_walk_forward": round(sum(e.walk_forward_overall for e in entries) / n, 6),
            "avg_analysis_fusion": round(sum(e.analysis_fusion_overall for e in entries) / n, 6),
            "pass_rate": round(sum(1 for e in entries if e.aggression_gate_decision in
                                   {"paper_candidate", "tournament_champion_paper_only"}) / n, 6),
            "overfit_rate": round(sum(1 for e in entries if e.overfit_level in {"moderate", "high"}) / n, 6),
            "avg_liquidity_robustness": round(
                sum(e.liquidity_robustness for e in entries) / n, 6),
            "avg_liquidity_score": round(sum(e.average_liquidity_score for e in entries) / n, 6),
            "avg_fill_quality_score": round(
                sum(e.average_fill_quality_score for e in entries) / n, 6),
            "avg_expected_slippage_pct": round(
                sum(e.average_expected_slippage_pct for e in entries) / n, 6),
            "avg_slippage_robustness_score": round(
                sum(e.slippage_robustness_score for e in entries) / n, 6),
            "avg_greek_fit_score": round(sum(e.average_greek_fit_score for e in entries) / n, 6),
            "avg_iv_context_score": round(sum(e.average_iv_context_score for e in entries) / n, 6),
            "avg_skew_score": round(sum(e.average_skew_score for e in entries) / n, 6),
            "avg_term_structure_score": round(
                sum(e.average_term_structure_score for e in entries) / n, 6),
            "avg_iv_surface_fit_score": round(
                sum(e.average_iv_surface_fit_score for e in entries) / n, 6),
            "avg_family_iv_fit_score": round(
                sum(e.average_family_iv_fit_score for e in entries) / n, 6),
            "avg_skew_term_score": round(sum(e.average_skew_term_score for e in entries) / n, 6),
            "avg_premium_overpayment_score": round(
                sum(e.average_premium_overpayment_score for e in entries) / n, 6),
            "avg_surface_instability_penalty": round(
                sum(e.average_surface_instability_penalty for e in entries) / n, 6),
            "avg_term_structure_risk_penalty": round(
                sum(e.average_term_structure_risk_penalty for e in entries) / n, 6),
            "avg_greek_attribution_quality": round(
                sum(e.average_greek_attribution_quality for e in entries) / n, 6),
            "avg_pattern_fixture_score": round(
                sum(e.average_pattern_fixture_score for e in entries) / n, 6),
            "avg_macro_fit_score": round(
                sum(e.average_macro_fit_score for e in entries) / n, 6),
            "avg_macro_opportunity_score": round(
                sum(e.average_macro_opportunity_score for e in entries) / n, 6),
            "avg_macro_risk_score": round(
                sum(e.average_macro_risk_score for e in entries) / n, 6),
            "avg_event_risk_score": round(
                sum(e.average_event_risk_score for e in entries) / n, 6),
            "avg_rate_shock_score": round(
                sum(e.average_rate_shock_score for e in entries) / n, 6),
            "avg_vix_vvix_stress_score": round(
                sum(e.average_vix_vvix_stress_score for e in entries) / n, 6),
            "avg_breadth_sector_confirmation_score": round(
                sum(e.average_breadth_sector_confirmation_score for e in entries) / n, 6),
            "avg_liquidity_regime_macro_score": round(
                sum(e.average_liquidity_regime_macro_score for e in entries) / n, 6),
            "avg_macro_contradiction_penalty": round(
                sum(e.average_macro_contradiction_penalty for e in entries) / n, 6),
            "avg_event_gap_risk_penalty": round(
                sum(e.average_event_gap_risk_penalty for e in entries) / n, 6),
            "best_macro_regime": entries[0].best_macro_regime,
            "worst_macro_regime": entries[0].worst_macro_regime,
            "best_macro_scenario": entries[0].best_macro_scenario,
            "worst_macro_scenario": entries[0].worst_macro_scenario,
            "worst_slippage_regime": entries[0].worst_slippage_regime,
            "best_liquidity_regime": entries[0].best_liquidity_regime,
            "best_fill_quality_regime": entries[0].best_fill_quality_regime,
            "best_greek_fit_regime": entries[0].best_greek_fit_regime,
            "worst_greek_risk_regime": entries[0].worst_greek_risk_regime,
            "greek_risk_verdict": entries[0].greek_risk_verdict,
            "best_iv_surface_regime": entries[0].best_iv_surface_regime,
            "worst_iv_surface_regime": entries[0].worst_iv_surface_regime,
            "worst_iv_surface_scenario": entries[0].worst_iv_surface_scenario,
            "survived_high_theta_high_vega_risk": entries[0].survived_high_theta_high_vega_risk,
            "survived_bad_fill_low_liquidity": entries[0].survived_bad_fill_low_liquidity,
            "failure_modes": sorted({fm for e in entries for fm in e.known_failure_modes}),
        }
    return out


def _best_worst_regimes(results, hint_threshold_best: float = 0.6) -> tuple[list[str], list[str]]:
    """Return (best_regimes, worst_regimes) by mean paper_pnl per regime for one genome's results."""
    by_reg: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_reg[r.regime_tag].append(r.paper_pnl)
    ranked = sorted(by_reg.items(), key=lambda kv: sum(kv[1]) / len(kv[1]), reverse=True)
    best = [r for r, _ in ranked[:3]]
    worst = [r for r, _ in ranked[-3:]]
    return best, worst


def _family_strengths_weaknesses(family: str, best: list[str], worst: list[str]) -> tuple[list[str], list[str]]:
    """Deterministic qualitative strength/weakness labels per family from regime performance."""
    strength_map = {
        "directional_convexity": "directional convexity in breakout/breakdown/trend regimes",
        "volatility_expansion": "long-vol convexity in event-vol / macro-shock regimes",
        "volatility_compression": "defined-risk compression in chop/range/iv-crush regimes",
        "short_duration_defined_risk": "short-DTE defined-risk in clean trend/breakout windows",
    }
    weakness_map = {
        "directional_convexity": "chop, range-pin, and bad-fill regimes",
        "volatility_expansion": "post-event IV crush and liquidity-decay regimes",
        "volatility_compression": "event-vol expansion and macro-shock regimes",
        "short_duration_defined_risk": "high-spread, low-liquidity, and gap-reversal regimes",
    }
    strengths = [f"best in: {', '.join(best)}", strength_map.get(family, "")]
    weaknesses = [f"worst in: {', '.join(worst)}", weakness_map.get(family, "")]
    return strengths, weaknesses


def _mean_values(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _regime_mean(results, field_name: str) -> dict[str, float]:
    by_regime: dict[str, list[float]] = defaultdict(list)
    for result in results:
        by_regime[result.regime_tag].append(float(getattr(result, field_name, 0.0)))
    return {regime: round(_mean_values(values), 6) for regime, values in by_regime.items()}


def _regime_with_extreme(results, field_name: str, highest: bool) -> str:
    means = _regime_mean(results, field_name)
    if not means:
        return ""
    ranked = sorted(means.items(), key=lambda item: item[1], reverse=highest)
    return ranked[0][0]


def _scenario_with_extreme(results, field_name: str, highest: bool) -> str:
    by_scenario: dict[str, list[float]] = defaultdict(list)
    for result in results:
        scenario_id = getattr(result, "iv_surface_scenario_id", "")
        if scenario_id:
            by_scenario[scenario_id].append(float(getattr(result, field_name, 0.0)))
    means = {scenario: round(_mean_values(values), 6) for scenario, values in by_scenario.items()}
    if not means:
        return ""
    ranked = sorted(means.items(), key=lambda item: item[1], reverse=highest)
    return ranked[0][0]


def _survived_bad_fill_low_liquidity(results) -> bool:
    targets = [r for r in results if r.regime_tag in {"high_spread_bad_fill", "low_liquidity_decay"}]
    if not targets:
        return False
    return all(r.verdict != "fail" for r in targets)


def _survived_high_theta_high_vega_risk(results) -> bool:
    targets = [
        r for r in results
        if r.regime_tag in {
            "event_vol_expansion",
            "post_event_iv_crush",
            "macro_shock_risk_off",
            "high_spread_bad_fill",
            "low_liquidity_decay",
        }
        or "theta_gamma_liquidity_combo" in r.greek_risk_flags
        or "iv_crush_risk_against_long_vega" in r.greek_risk_flags
    ]
    if not targets:
        return False
    return all(r.greek_risk_verdict not in {"reject", "poor_fit"} for r in targets)


def run_fixture_tournament(config_path: Path | str | None = None,
                           proof_ledger_path: Path | str | None = None,
                           champion_registry_path: Path | str | None = None,
                           strong_proof: bool = True,
                           windows_dir: Path | str | None = None) -> dict:
    """Run the full offline multi-strategy tournament. Returns a dict summary."""
    cfg = load_config(config_path or default_config_path())
    ledger_path = Path(proof_ledger_path) if proof_ledger_path else TOURNAMENT_LEDGER_PATH
    reg_path = Path(champion_registry_path) if champion_registry_path else CHAMPION_REGISTRY_PATH

    # 1. load windows + analysis contexts (analysis fixtures live alongside windows)
    windows = load_walk_forward_windows(windows_dir)
    analysis_dir = Path(windows_dir) if windows_dir else None
    window_analysis = {w.window_id: parse_window_analysis(
        load_window_analysis(w.window_id, directory=analysis_dir)) for w in windows}

    # 2. load genomes + shared proof bundle
    genomes = build_tournament_genomes()
    proof_bundle = build_tournament_proof_bundle(strong=strong_proof)
    pattern_fixtures = build_pattern_fixture_library()

    # 3. per-genome: family-aware walk-forward replay + family-regime-aware analysis fusion
    engine = ReplayEngine()
    gate = ProofWeightedAggressionGate()
    cap = PaperBroker().get_capabilities()
    tournament_id = "dopey-tournament-v1"
    macro_scenarios = build_macro_event_scenarios()
    macro_by_regime = {scenario.regime_tag: scenario for scenario in macro_scenarios}
    fundamental_scenarios = build_sector_peer_fundamental_scenarios()
    fundamental_by_regime = {scenario.regime_tag: scenario for scenario in fundamental_scenarios}

    strategy_scores: list[StrategyTournamentScore] = []
    overfit_summary: dict[str, str] = {}
    promotion_decisions: dict[str, str] = {}
    fusion_summaries: dict[str, dict] = {}
    family_replay_summaries: dict[str, dict] = {}
    per_genome_results: dict[str, list] = {}
    per_genome_wf: dict[str, object] = {}

    for genome in genomes:
        results = engine.replay(genome, proof_bundle, windows)
        per_genome_results[genome.genome_id] = results
        wf = score_walk_forward(results)
        per_genome_wf[genome.genome_id] = wf

        # analysis fusion: per-window, family-regime alignment = family hint for that regime
        fusions = []
        macro_scores = []
        fundamental_scores = []
        pattern_window_summaries = []
        for w in windows:
            ac = window_analysis[w.window_id]
            alignment = family_hint(w.regime_tag, genome.family, w.family_hints())
            pattern_scorecards = score_pattern_context(genome.family, w.regime_tag, pattern_fixtures)
            pattern_window_summary = summarize_pattern_scores(pattern_scorecards)
            pattern_window_summaries.append(pattern_window_summary)
            macro_scenario = macro_by_regime.get(w.regime_tag)
            fundamental_scenario = fundamental_by_regime.get(w.regime_tag)
            fusion = fuse_analysis(
                macro_ctx=ac["macro"], micro_ctx=ac["microstructure"], tech_ctx=ac["technical"],
                fund_ctx=ac["fundamental"], patterns=ac["patterns"],
                replay_confirmation_score=wf.consistency_score,
                family_regime_alignment=alignment,
                pattern_fixture_score=pattern_window_summary["average_pattern_score"],
                macro_event_scenario=macro_scenario,
                strategy_family=genome.family)
            fusions.append(fusion)
            if macro_scenario is not None:
                macro_scores.append(score_family_macro_event(genome.family, macro_scenario))
            if fundamental_scenario is not None:
                fundamental_scores.append(score_family_fundamental(genome.family, fundamental_scenario))
        avg_fusion_overall = round(sum(f.overall_score for f in fusions) / max(len(fusions), 1), 6)
        if fusions:
            rep_fusion = AnalysisFusionScore(
                macro_score=round(sum(f.macro_score for f in fusions) / len(fusions), 6),
                microstructure_score=round(sum(f.microstructure_score for f in fusions) / len(fusions), 6),
                technical_score=round(sum(f.technical_score for f in fusions) / len(fusions), 6),
                fundamental_score=round(sum(f.fundamental_score for f in fusions) / len(fusions), 6),
                pattern_score=round(sum(f.pattern_score for f in fusions) / len(fusions), 6),
                contradiction_penalty=round(sum(f.contradiction_penalty for f in fusions) / len(fusions), 6),
                freshness_reliability_score=1.0,
                replay_confirmation_score=wf.consistency_score,
                overall_score=avg_fusion_overall,
                summary=f"avg over {len(fusions)} windows (family-regime aware)",
            )
        else:
            rep_fusion = AnalysisFusionScore()
        fusion_summaries[genome.genome_id] = rep_fusion.to_dict()

        # overfit
        train_passed = any(r.verdict == "pass" for r in results if r.window_type == "train")
        val_passed = any(r.verdict == "pass" for r in results if r.window_type == "validation")
        holdout_passed = any(r.verdict == "pass" for r in results if r.window_type == "holdout")
        overfit = classify_overfit(
            train_passed=train_passed, validation_passed=val_passed, holdout_passed=holdout_passed,
            train_pnl=wf.train_mean_pnl, validation_pnl=wf.validation_mean_pnl,
            holdout_pnl=wf.holdout_mean_pnl, overfit_suspicion=wf.overfit_suspicion_score)
        overfit_summary[genome.genome_id] = overfit.level

        avg_liq = (sum(r.liquidity_score for r in results) / len(results)) if results else 0.0
        verdict = evaluate_tournament_promotion(
            gate, genome.to_dict(), wf.overall, rep_fusion, overfit.level,
            avg_liq, genome.preferred_regime, cap, is_champion=False)
        promotion_decisions[genome.genome_id] = verdict.decision

        known_failures = []
        if overfit.level in {"moderate", "high"}:
            known_failures.append(f"overfit_{overfit.level}")
        if wf.liquidity_robustness_score < 0.5:
            known_failures.append("weak_liquidity")
        if wf.slippage_tolerance_score < 0.5:
            known_failures.append("slippage_sensitive")
        if wf.invalidation_quality_score < 0.5:
            known_failures.append("poor_invalidation")

        best_regimes, worst_regimes = _best_worst_regimes(results)
        avg_fill_quality = round(_mean_values([r.fill_quality_score for r in results]), 6)
        avg_expected_slippage_pct = round(_mean_values([r.expected_slippage_pct for r in results]), 6)
        avg_liquidity_score = round(_mean_values([r.liquidity_score for r in results]), 6)
        slippage_robustness_score = round(max(0.0, min(1.0, 1.0 - avg_expected_slippage_pct * 8.0)), 6)
        worst_slippage_regime = _regime_with_extreme(results, "expected_slippage_pct", highest=True)
        best_liquidity_regime = _regime_with_extreme(results, "liquidity_score", highest=True)
        best_fill_quality_regime = _regime_with_extreme(results, "fill_quality_score", highest=True)
        survived_bad_fill = _survived_bad_fill_low_liquidity(results)
        avg_greek_fit = round(_mean_values([r.greek_fit_score for r in results]), 6)
        avg_delta_fit = round(_mean_values([r.delta_fit_score for r in results]), 6)
        avg_gamma_fit = round(_mean_values([r.gamma_fit_score for r in results]), 6)
        avg_theta_fit = round(_mean_values([r.theta_fit_score for r in results]), 6)
        avg_vega_fit = round(_mean_values([r.vega_fit_score for r in results]), 6)
        avg_iv_context_score = round(_mean_values([r.iv_context_score for r in results]), 6)
        avg_skew_score = round(_mean_values([r.skew_score for r in results]), 6)
        avg_term_structure_score = round(_mean_values([r.term_structure_score for r in results]), 6)
        avg_iv_surface_fit = round(_mean_values([r.iv_surface_fit_score for r in results]), 6)
        avg_family_iv_fit = round(_mean_values([r.family_iv_fit_score for r in results]), 6)
        avg_skew_term = round(_mean_values([r.skew_term_score for r in results]), 6)
        avg_premium_overpayment = round(_mean_values([r.premium_overpayment_score for r in results]), 6)
        avg_iv_crush = round(_mean_values([r.iv_crush_score for r in results]), 6)
        avg_iv_expansion = round(_mean_values([r.iv_expansion_score for r in results]), 6)
        avg_front_event_bump = round(_mean_values([r.front_event_bump_score for r in results]), 6)
        avg_skew_trap = round(_mean_values([r.skew_trap_score for r in results]), 6)
        avg_wing_elevation = round(_mean_values([r.wing_elevation_score for r in results]), 6)
        avg_surface_instability = round(_mean_values([r.surface_instability_penalty for r in results]), 6)
        avg_term_risk = round(_mean_values([r.term_structure_risk_penalty for r in results]), 6)
        avg_iv_mismatch = round(_mean_values([r.iv_crush_expansion_mismatch_penalty for r in results]), 6)
        avg_greek_attribution = round(
            _mean_values([r.greek_attribution_quality_score for r in results]), 6)
        avg_pattern_fixture_score = round(
            _mean_values([p["average_pattern_score"] for p in pattern_window_summaries]), 6)
        supporting_pattern_ids = sorted({
            pattern_id for summary in pattern_window_summaries
            for pattern_id in summary["supporting_patterns"]
        })
        penalizing_pattern_ids = sorted({
            pattern_id for summary in pattern_window_summaries
            for pattern_id in summary["penalizing_patterns"]
        })
        avg_iv_family_score = round(
            _mean_values([
                avg_iv_context_score,
                avg_skew_score,
                avg_term_structure_score,
                avg_iv_surface_fit,
                avg_family_iv_fit,
                avg_skew_term,
            ]), 6)
        best_greek_fit_regime = _regime_with_extreme(results, "greek_fit_score", highest=True)
        worst_greek_risk_regime = _regime_with_extreme(results, "greek_fit_score", highest=False)
        best_iv_surface_regime = _regime_with_extreme(results, "family_iv_fit_score", highest=True)
        worst_iv_surface_regime = _regime_with_extreme(results, "family_iv_fit_score", highest=False)
        worst_iv_surface_scenario = _scenario_with_extreme(results, "family_iv_fit_score", highest=False)
        iv_surface_verdicts = sorted({r.iv_surface_verdict for r in results if r.iv_surface_verdict})
        iv_surface_risk_flags = sorted({flag for r in results for flag in r.iv_surface_risk_flags})
        verdict_rank = {
            "excellent_fit": 0,
            "good_fit": 1,
            "acceptable_fit": 2,
            "fragile_fit": 3,
            "poor_fit": 4,
            "reject": 5,
        }
        greek_risk_verdict = "acceptable_fit"
        if results:
            greek_risk_verdict = sorted(
                [r.greek_risk_verdict or "acceptable_fit" for r in results],
                key=lambda v: verdict_rank.get(v, 5),
                reverse=True,
            )[0]
        greek_verdicts = [
            GreekRiskVerdict(
                strategy_id=r.strategy_id,
                strategy_family=genome.family,
                greek_fit_score=r.greek_fit_score,
                delta_fit_score=r.delta_fit_score,
                gamma_fit_score=r.gamma_fit_score,
                theta_fit_score=r.theta_fit_score,
                vega_fit_score=r.vega_fit_score,
                risk_flags=list(r.greek_risk_flags),
                verdict=r.greek_risk_verdict or "acceptable_fit",
            )
            for r in results
        ]
        greek_strengths, greek_weaknesses = summarize_profile_strengths(genome.family, greek_verdicts)
        survived_high_theta_high_vega = _survived_high_theta_high_vega_risk(results)
        if avg_fill_quality < 0.45:
            known_failures.append("weak_fill_quality")
        if not survived_bad_fill:
            known_failures.append("bad_fill_low_liquidity_failure")
        if avg_greek_fit < 0.45:
            known_failures.append("weak_greek_fit")
        if avg_greek_attribution < 0.45:
            known_failures.append("weak_greek_attribution")
        if not survived_high_theta_high_vega:
            known_failures.append("high_theta_high_vega_fragility")
        if avg_premium_overpayment >= 0.58:
            known_failures.append("premium_overpayment_trap")
        if avg_family_iv_fit < 0.45:
            known_failures.append("weak_iv_surface_fit")
        if avg_surface_instability >= 0.58:
            known_failures.append("surface_instability")
        if avg_term_risk >= 0.58:
            known_failures.append("term_structure_risk")

        # family-specific regime survival: fraction of best-fit regimes (hint>=0.6) that passed
        best_fit = [w.regime_tag for w in windows
                    if family_hint(w.regime_tag, genome.family, w.family_hints()) >= 0.6]
        best_fit_passed = {r.regime_tag for r in results if r.verdict == "pass" and r.regime_tag in best_fit}
        family_regime_survival = (len(best_fit_passed) / len(best_fit)) if best_fit else 0.0

        # macro-event fixture scoring per window
        avg_macro_fit = 0.5
        avg_macro_opportunity = 0.5
        avg_macro_risk = 0.5
        avg_event_risk = 0.5
        avg_rate_shock = 0.5
        avg_vix_vvix_stress = 0.5
        avg_breadth_sector = 0.5
        avg_liquidity_regime_macro = 0.5
        avg_macro_contradiction = 0.0
        avg_event_gap_risk = 0.0
        macro_event_risk_flags: list[str] = []
        best_macro_regime = ""
        worst_macro_regime = ""
        best_macro_scenario = ""
        worst_macro_scenario = ""
        # sector/peer/fundamental fixture scoring per window
        avg_fundamental_fit = 0.5
        avg_sector_fit = 0.5
        avg_peer_confirmation = 0.5
        avg_fundamental_confirmation = 0.5
        avg_valuation_risk = 0.5
        avg_earnings_quality = 0.5
        avg_crowding_risk = 0.5
        avg_fundamental_contradiction = 0.0
        avg_fragility = 0.5
        fundamental_risk_flags: list[str] = []
        best_fundamental_scenario = ""
        worst_fundamental_scenario = ""
        best_fundamental_regime = ""
        worst_fundamental_regime = ""
        family_fundamental_fit = 0.5
        if macro_scores:
            avg_macro_fit = round(_mean_values([m.macro_fit_score for m in macro_scores]), 6)
            avg_macro_opportunity = round(_mean_values([m.macro_opportunity_score for m in macro_scores]), 6)
            avg_macro_risk = round(_mean_values([m.macro_risk_score for m in macro_scores]), 6)
            avg_event_risk = round(_mean_values([m.event_risk_score for m in macro_scores]), 6)
            avg_rate_shock = round(_mean_values([m.rate_shock_score for m in macro_scores]), 6)
            avg_vix_vvix_stress = round(_mean_values([m.vix_vvix_stress_score for m in macro_scores]), 6)
            avg_breadth_sector = round(_mean_values([m.breadth_sector_confirmation_score for m in macro_scores]), 6)
            avg_liquidity_regime_macro = round(_mean_values([m.liquidity_regime_macro_score for m in macro_scores]), 6)
            avg_macro_contradiction = round(_mean_values([m.macro_contradiction_penalty for m in macro_scores]), 6)
            avg_event_gap_risk = round(_mean_values([m.event_gap_risk_penalty for m in macro_scores]), 6)
            macro_event_risk_flags = sorted({flag for m in macro_scores for flag in m.risk_flags})
            by_regime: dict[str, list[float]] = {}
            for m in macro_scores:
                by_regime.setdefault(m.regime_tag, []).append(m.macro_fit_score)
            regime_means = {regime: _mean_values(values) for regime, values in by_regime.items()}
            ranked = sorted(regime_means.items(), key=lambda kv: kv[1], reverse=True)
            best_macro_regime = ranked[0][0] if ranked else ""
            worst_macro_regime = ranked[-1][0] if ranked else ""
            by_scenario: dict[str, list[float]] = {}
            for m in macro_scores:
                by_scenario.setdefault(m.scenario_id, []).append(m.macro_fit_score)
            scenario_means = {scenario: _mean_values(values) for scenario, values in by_scenario.items()}
            ranked_scenarios = sorted(scenario_means.items(), key=lambda kv: kv[1], reverse=True)
            best_macro_scenario = ranked_scenarios[0][0] if ranked_scenarios else ""
            worst_macro_scenario = ranked_scenarios[-1][0] if ranked_scenarios else ""

        if fundamental_scores:
            avg_fundamental_fit = round(_mean_values([f.fundamental_fit_score for f in fundamental_scores]), 6)
            avg_sector_fit = round(_mean_values([f.sector_fit_score for f in fundamental_scores]), 6)
            avg_peer_confirmation = round(_mean_values([f.peer_confirmation_score for f in fundamental_scores]), 6)
            avg_fundamental_confirmation = round(_mean_values([f.fundamental_confirmation_score for f in fundamental_scores]), 6)
            avg_valuation_risk = round(_mean_values([f.valuation_risk_score for f in fundamental_scores]), 6)
            avg_earnings_quality = round(_mean_values([f.earnings_quality_score for f in fundamental_scores]), 6)
            avg_crowding_risk = round(_mean_values([f.crowding_risk_score for f in fundamental_scores]), 6)
            avg_fundamental_contradiction = round(_mean_values([f.fundamental_contradiction_penalty for f in fundamental_scores]), 6)
            avg_fragility = round(_mean_values([f.fragility_penalty for f in fundamental_scores]), 6)
            family_fundamental_fit = round(_mean_values([f.family_fundamental_fit_score for f in fundamental_scores]), 6)
            fundamental_risk_flags = sorted({flag for f in fundamental_scores for flag in f.risk_flags})
            by_fund_scenario: dict[str, list[float]] = {}
            for f in fundamental_scores:
                by_fund_scenario.setdefault(f.scenario_id, []).append(f.fundamental_fit_score)
            scenario_means_f = {scenario: _mean_values(values) for scenario, values in by_fund_scenario.items()}
            ranked_scenarios_f = sorted(scenario_means_f.items(), key=lambda kv: kv[1], reverse=True)
            best_fundamental_scenario = ranked_scenarios_f[0][0] if ranked_scenarios_f else ""
            worst_fundamental_scenario = ranked_scenarios_f[-1][0] if ranked_scenarios_f else ""
            by_fund_regime: dict[str, list[float]] = {}
            for f in fundamental_scores:
                by_fund_regime.setdefault(f.regime_tag, []).append(f.fundamental_fit_score)
            regime_means_f = {regime: _mean_values(values) for regime, values in by_fund_regime.items()}
            ranked_regimes_f = sorted(regime_means_f.items(), key=lambda kv: kv[1], reverse=True)
            best_fundamental_regime = ranked_regimes_f[0][0] if ranked_regimes_f else ""
            worst_fundamental_regime = ranked_regimes_f[-1][0] if ranked_regimes_f else ""

        combined = _combined_score(
            wf.overall,
            avg_fusion_overall,
            greek_fit=avg_greek_fit,
            iv_score=avg_iv_family_score,
            liquidity=avg_liquidity_score,
            slippage=slippage_robustness_score,
            invalidation=wf.invalidation_quality_score,
            holdout=wf.holdout_mean_pnl,
            overfit_rank=OVERFIT_RANK.get(overfit.level, 3),
            macro_fit=avg_macro_fit,
            macro_risk=avg_macro_risk,
            fundamental_fit=avg_fundamental_fit,
            fundamental_contradiction=avg_fundamental_contradiction,
        )
        strategy_scores.append(StrategyTournamentScore(
            tournament_id=tournament_id,
            strategy_id=genome.genome_id,
            strategy_family=genome.family,
            windows_replayed=len(results),
            walk_forward_overall=wf.overall,
            analysis_fusion_overall=avg_fusion_overall,
            overfit_level=overfit.level,
            aggression_gate_decision=verdict.decision,
            paper_only_rank=0,
            champion_status="entrant",
            known_failure_modes=known_failures,
            combined_score=combined,
            holdout_score=round(wf.holdout_mean_pnl, 6),
            liquidity_robustness=round(wf.liquidity_robustness_score, 6),
            invalidation_quality=round(wf.invalidation_quality_score, 6),
            paper_fill_quality=round(wf.slippage_tolerance_score, 6),
            regime_survival_score=round(wf.regime_survival_score, 6),
            family_regime_survival=round(family_regime_survival, 6),
            overfit_rank=OVERFIT_RANK.get(overfit.level, 3),
            best_regimes=best_regimes,
            worst_regimes=worst_regimes,
            average_liquidity_score=avg_liquidity_score,
            average_fill_quality_score=avg_fill_quality,
            average_expected_slippage_pct=avg_expected_slippage_pct,
            worst_slippage_regime=worst_slippage_regime,
            best_liquidity_regime=best_liquidity_regime,
            best_fill_quality_regime=best_fill_quality_regime,
            liquidity_robustness_score=round(wf.liquidity_robustness_score, 6),
            slippage_robustness_score=slippage_robustness_score,
            survived_bad_fill_low_liquidity=survived_bad_fill,
            average_greek_fit_score=avg_greek_fit,
            average_delta_fit_score=avg_delta_fit,
            average_gamma_fit_score=avg_gamma_fit,
            average_theta_fit_score=avg_theta_fit,
            average_vega_fit_score=avg_vega_fit,
            average_iv_context_score=avg_iv_context_score,
            average_skew_score=avg_skew_score,
            average_term_structure_score=avg_term_structure_score,
            average_iv_surface_fit_score=avg_iv_surface_fit,
            average_family_iv_fit_score=avg_family_iv_fit,
            average_skew_term_score=avg_skew_term,
            average_premium_overpayment_score=avg_premium_overpayment,
            average_iv_crush_score=avg_iv_crush,
            average_iv_expansion_score=avg_iv_expansion,
            average_front_event_bump_score=avg_front_event_bump,
            average_skew_trap_score=avg_skew_trap,
            average_wing_elevation_score=avg_wing_elevation,
            average_surface_instability_penalty=avg_surface_instability,
            average_term_structure_risk_penalty=avg_term_risk,
            average_iv_mismatch_penalty=avg_iv_mismatch,
            best_iv_surface_regime=best_iv_surface_regime,
            worst_iv_surface_regime=worst_iv_surface_regime,
            worst_iv_surface_scenario=worst_iv_surface_scenario,
            iv_surface_verdicts=iv_surface_verdicts,
            iv_surface_risk_flags=iv_surface_risk_flags,
            average_greek_attribution_quality=avg_greek_attribution,
            best_greek_fit_regime=best_greek_fit_regime,
            worst_greek_risk_regime=worst_greek_risk_regime,
            greek_risk_verdict=greek_risk_verdict,
            greek_strengths=greek_strengths,
            greek_weaknesses=greek_weaknesses,
            survived_high_theta_high_vega_risk=survived_high_theta_high_vega,
            average_pattern_fixture_score=avg_pattern_fixture_score,
            supporting_pattern_ids=supporting_pattern_ids,
            penalizing_pattern_ids=penalizing_pattern_ids,
            average_macro_fit_score=avg_macro_fit,
            average_macro_risk_score=avg_macro_risk,
            average_macro_opportunity_score=avg_macro_opportunity,
            average_event_risk_score=avg_event_risk,
            average_rate_shock_score=avg_rate_shock,
            average_vix_vvix_stress_score=avg_vix_vvix_stress,
            average_breadth_sector_confirmation_score=avg_breadth_sector,
            average_liquidity_regime_macro_score=avg_liquidity_regime_macro,
            average_macro_contradiction_penalty=avg_macro_contradiction,
            average_event_gap_risk_penalty=avg_event_gap_risk,
            best_macro_regime=best_macro_regime,
            worst_macro_regime=worst_macro_regime,
            best_macro_scenario=best_macro_scenario,
            worst_macro_scenario=worst_macro_scenario,
            macro_event_risk_flags=macro_event_risk_flags,
            average_fundamental_fit_score=avg_fundamental_fit,
            average_sector_fit_score=avg_sector_fit,
            average_peer_confirmation_score=avg_peer_confirmation,
            average_valuation_risk_score=avg_valuation_risk,
            average_earnings_quality_score=avg_earnings_quality,
            average_crowding_risk_score=avg_crowding_risk,
            average_fundamental_contradiction_penalty=avg_fundamental_contradiction,
            average_fragility_penalty=avg_fragility,
            fundamental_risk_flags=fundamental_risk_flags,
            best_fundamental_scenario=best_fundamental_scenario,
            worst_fundamental_scenario=worst_fundamental_scenario,
            best_fundamental_regime=best_fundamental_regime,
            worst_fundamental_regime=worst_fundamental_regime,
            family_fundamental_fit_score=family_fundamental_fit,
        ))

    # 4. rank strategies + assemble per-family / per-layer summaries
    strategy_scores = rank_strategy_scores(strategy_scores)
    for i, s in enumerate(strategy_scores, start=1):
        s.paper_only_rank = i
    if strategy_scores:
        strategy_scores[0].champion_status = "champion"
        if len(strategy_scores) > 1:
            strategy_scores[1].champion_status = "runner_up"
        champ = strategy_scores[0]
        champ_genome = next(g for g in genomes if g.genome_id == champ.strategy_id)
        champ_wf = per_genome_wf[champ.strategy_id]
        champ_rep = AnalysisFusionScore(**{k: v for k, v in fusion_summaries[champ.strategy_id].items()})
        champ_verdict = evaluate_tournament_promotion(
            gate, champ_genome.to_dict(), champ_wf.overall, champ_rep,
            overfit_summary[champ.strategy_id], champ_wf.liquidity_robustness_score,
            champ_genome.preferred_regime, cap, is_champion=True)
        if champ_verdict.decision == "rejected" and overfit_summary[champ.strategy_id] != "high":
            champ_verdict.decision = "research_only"
            champ_verdict.reasons.append("champion paper-only floor: research_only (never live)")
        promotion_decisions[champ.strategy_id] = champ_verdict.decision
        champ.aggression_gate_decision = champ_verdict.decision

    # Populate family_replay_summaries from strategy_scores
    for s in strategy_scores:
        family_replay_summaries[s.strategy_family] = {
            "strategy_id": s.strategy_id,
            "structures_used": sorted({r.structure for r in per_genome_results.get(s.strategy_id, [])}),
            "structure_risk_summaries": [r.structure_risk_summary for r in per_genome_results.get(s.strategy_id, []) if r.structure_risk_summary],
            "mean_pnl": round(sum(r.paper_pnl for r in per_genome_results.get(s.strategy_id, [])) / max(len(per_genome_results.get(s.strategy_id, [])), 1), 6) if per_genome_results.get(s.strategy_id) else 0.0,
            "pass_rate": round(sum(1 for r in per_genome_results.get(s.strategy_id, []) if r.verdict == "pass") / max(len(per_genome_results.get(s.strategy_id, [])), 1), 6) if per_genome_results.get(s.strategy_id) else 0.0,
            "walk_forward_overall": s.walk_forward_overall,
            "best_regimes": s.best_regimes,
            "worst_regimes": s.worst_regimes,
            "average_liquidity_score": s.average_liquidity_score,
            "average_fill_quality_score": s.average_fill_quality_score,
            "average_expected_slippage_pct": s.average_expected_slippage_pct,
            "worst_slippage_regime": s.worst_slippage_regime,
            "best_liquidity_regime": s.best_liquidity_regime,
            "best_fill_quality_regime": s.best_fill_quality_regime,
            "slippage_robustness_score": s.slippage_robustness_score,
            "survived_bad_fill_low_liquidity": s.survived_bad_fill_low_liquidity,
            "average_greek_fit_score": s.average_greek_fit_score,
            "average_iv_context_score": s.average_iv_context_score,
            "average_iv_surface_fit_score": s.average_iv_surface_fit_score,
            "average_family_iv_fit_score": s.average_family_iv_fit_score,
            "average_skew_term_score": s.average_skew_term_score,
            "average_premium_overpayment_score": s.average_premium_overpayment_score,
            "average_greek_attribution_quality": s.average_greek_attribution_quality,
            "best_greek_fit_regime": s.best_greek_fit_regime,
            "worst_greek_risk_regime": s.worst_greek_risk_regime,
            "greek_risk_verdict": s.greek_risk_verdict,
            "greek_strengths": s.greek_strengths,
            "greek_weaknesses": s.greek_weaknesses,
            "survived_high_theta_high_vega_risk": s.survived_high_theta_high_vega_risk,
            "average_pattern_fixture_score": s.average_pattern_fixture_score,
            "supporting_pattern_ids": s.supporting_pattern_ids,
            "penalizing_pattern_ids": s.penalizing_pattern_ids,
            "overfit_level": s.overfit_level,
            "average_macro_fit_score": s.average_macro_fit_score,
            "average_macro_risk_score": s.average_macro_risk_score,
            "best_macro_regime": s.best_macro_regime,
            "worst_macro_regime": s.worst_macro_regime,
            "best_macro_scenario": s.best_macro_scenario,
            "worst_macro_scenario": s.worst_macro_scenario,
            "macro_event_risk_flags": s.macro_event_risk_flags,
            "average_fundamental_fit_score": s.average_fundamental_fit_score,
            "average_sector_fit_score": s.average_sector_fit_score,
            "average_peer_confirmation_score": s.average_peer_confirmation_score,
            "average_valuation_risk_score": s.average_valuation_risk_score,
            "average_earnings_quality_score": s.average_earnings_quality_score,
            "average_crowding_risk_score": s.average_crowding_risk_score,
            "average_fundamental_contradiction_penalty": s.average_fundamental_contradiction_penalty,
            "average_fragility_penalty": s.average_fragility_penalty,
            "fundamental_risk_flags": s.fundamental_risk_flags,
            "best_fundamental_scenario": s.best_fundamental_scenario,
            "worst_fundamental_scenario": s.worst_fundamental_scenario,
        }

    champion_id = strategy_scores[0].strategy_id if strategy_scores else ""
    runner_up_id = strategy_scores[1].strategy_id if len(strategy_scores) > 1 else ""

    family_scorecard = _family_scorecard(strategy_scores)
    slippage_liquidity_summary = {
        s.strategy_family: {
            "strategy_id": s.strategy_id,
            "average_liquidity_score": s.average_liquidity_score,
            "average_fill_quality_score": s.average_fill_quality_score,
            "average_expected_slippage_pct": s.average_expected_slippage_pct,
            "liquidity_robustness_score": s.liquidity_robustness_score,
            "slippage_robustness_score": s.slippage_robustness_score,
            "worst_slippage_regime": s.worst_slippage_regime,
            "best_liquidity_regime": s.best_liquidity_regime,
            "best_fill_quality_regime": s.best_fill_quality_regime,
            "survived_bad_fill_low_liquidity": s.survived_bad_fill_low_liquidity,
        }
        for s in strategy_scores
    }
    greek_iv_summary = {
        s.strategy_family: {
            "strategy_id": s.strategy_id,
            "average_greek_fit_score": s.average_greek_fit_score,
            "average_iv_context_score": s.average_iv_context_score,
            "average_iv_surface_fit_score": s.average_iv_surface_fit_score,
            "average_family_iv_fit_score": s.average_family_iv_fit_score,
            "average_skew_term_score": s.average_skew_term_score,
            "average_premium_overpayment_score": s.average_premium_overpayment_score,
            "average_greek_attribution_quality": s.average_greek_attribution_quality,
            "greek_risk_verdict": s.greek_risk_verdict,
            "survived_high_theta_high_vega_risk": s.survived_high_theta_high_vega_risk,
        }
        for s in strategy_scores
    }
    iv_surface_expansion_summary = {
        "model_version": IV_SURFACE_EXPANSION_VERSION,
        "family_scores": {
            s.strategy_family: {
                "strategy_id": s.strategy_id,
                "average_iv_surface_fit_score": s.average_iv_surface_fit_score,
                "average_family_iv_fit_score": s.average_family_iv_fit_score,
            }
            for s in strategy_scores
        },
    }
    source_scorecard_summary = build_source_scorecard_summary()
    pattern_recognition_summary = summarize_pattern_fixture_library(pattern_fixtures).to_dict()
    mutation_evolution_summary = latest_mutation_summary()
    failure_mode_summary = latest_failure_mode_summary()
    macro_event_summary = {
        "model_version": MACRO_EVENT_EXPANSION_VERSION,
        "scenarios_loaded": len(macro_scenarios),
        "family_scores": {
            s.strategy_family: {
                "strategy_id": s.strategy_id,
                "average_macro_fit_score": s.average_macro_fit_score,
                "average_macro_risk_score": s.average_macro_risk_score,
            }
            for s in strategy_scores
        },
    }
    fundamental_summary = {
        "model_version": FUNDAMENTAL_EXPANSION_VERSION,
        "fixture_version": FUNDAMENTAL_FIXTURE_VERSION,
        "scenarios_loaded": len(fundamental_scenarios),
        "family_scores": {
            s.strategy_family: {
                "strategy_id": s.strategy_id,
                "average_fundamental_fit_score": s.average_fundamental_fit_score,
                "average_sector_fit_score": s.average_sector_fit_score,
                "average_peer_confirmation_score": s.average_peer_confirmation_score,
                "average_valuation_risk_score": s.average_valuation_risk_score,
                "average_earnings_quality_score": s.average_earnings_quality_score,
                "average_crowding_risk_score": s.average_crowding_risk_score,
                "average_fundamental_contradiction_penalty": s.average_fundamental_contradiction_penalty,
                "average_fragility_penalty": s.average_fragility_penalty,
                "family_fundamental_fit_score": s.family_fundamental_fit_score,
                "best_fundamental_scenario": s.best_fundamental_scenario,
                "worst_fundamental_scenario": s.worst_fundamental_scenario,
                "best_fundamental_regime": s.best_fundamental_regime,
                "worst_fundamental_regime": s.worst_fundamental_regime,
                "fundamental_risk_flags": s.fundamental_risk_flags,
            }
            for s in strategy_scores
        },
    }
    structure_builder_summary = {
        score.strategy_family: {
            "model_version": STRUCTURE_BUILDER_VERSION,
            "strategy_id": score.strategy_id,
            "structures_used": sorted({result.structure for result in per_genome_results.get(score.strategy_id, [])}),
        }
        for score in strategy_scores
    }
    worst_slippage_regimes = []
    best_fill_quality_regimes = []
    for score in strategy_scores:
        if score.worst_slippage_regime and score.worst_slippage_regime not in worst_slippage_regimes:
            worst_slippage_regimes.append(score.worst_slippage_regime)
        if score.best_fill_quality_regime and score.best_fill_quality_regime not in best_fill_quality_regimes:
            best_fill_quality_regimes.append(score.best_fill_quality_regime)
    worst_greek_risk_regimes = []
    best_greek_fit_regimes = []
    for score in strategy_scores:
        if score.worst_greek_risk_regime and score.worst_greek_risk_regime not in worst_greek_risk_regimes:
            worst_greek_risk_regimes.append(score.worst_greek_risk_regime)
        if score.best_greek_fit_regime and score.best_greek_fit_regime not in best_greek_fit_regimes:
            best_greek_fit_regimes.append(score.best_greek_fit_regime)

    # 5. family strengths/weaknesses
    best_by_fam: dict[str, list[str]] = {}
    worst_by_fam: dict[str, list[str]] = {}
    strengths_by_fam: dict[str, list[str]] = {}
    weaknesses_by_fam: dict[str, list[str]] = {}
    for s in strategy_scores:
        best_by_fam[s.strategy_family] = s.best_regimes
        worst_by_fam[s.strategy_family] = s.worst_regimes
        st, wk = _family_strengths_weaknesses(s.strategy_family, s.best_regimes, s.worst_regimes)
        strengths_by_fam[s.strategy_family] = st + s.greek_strengths
        weaknesses_by_fam[s.strategy_family] = wk + s.greek_weaknesses

    # 6. reproducibility hash
    regime_tags = [w.regime_tag for w in windows]
    repro = reproducibility_hash(
        {"tournament_id": tournament_id},
        {"corpus_id": CORPUS_ID},
        {"windows": [w.window_id for w in windows]},
        {"regime_tags": regime_tags},
        {"genomes": [g.genome_id for g in genomes]},
        {"scores": [s.to_dict() for s in strategy_scores]},
    )

    safety_state = {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_broker_only": True,
        "live_blocked": True,
        "promotion_target_paper_only": True,
    }

    # 8. write champion registry
    champ_score = strategy_scores[0] if strategy_scores else None
    run_id = f"dopey-tournament-{tournament_id}"
    champ_entry = ChampionRegistryEntry(
        tournament_id=tournament_id,
        champion_strategy_id=champion_id,
        runner_up_strategy_id=runner_up_id,
        family_ranking=[{"family": s.strategy_family, "rank": s.paper_only_rank,
                         "strategy_id": s.strategy_id, "combined_score": s.combined_score,
                         "walk_forward": s.walk_forward_overall,
                         "analysis_fusion": s.analysis_fusion_overall,
                         "average_liquidity_score": s.average_liquidity_score,
                         "average_fill_quality_score": s.average_fill_quality_score,
                         "average_expected_slippage_pct": s.average_expected_slippage_pct,
                         "worst_slippage_regime": s.worst_slippage_regime,
                         "best_liquidity_regime": s.best_liquidity_regime,
                         "survived_bad_fill_low_liquidity": s.survived_bad_fill_low_liquidity,
                         "average_greek_fit_score": s.average_greek_fit_score,
                         "average_iv_context_score": s.average_iv_context_score,
                         "average_family_iv_fit_score": s.average_family_iv_fit_score,
                         "average_premium_overpayment_score": s.average_premium_overpayment_score,
                         "worst_iv_surface_regime": s.worst_iv_surface_regime,
                         "average_greek_attribution_quality": s.average_greek_attribution_quality,
                         "best_greek_fit_regime": s.best_greek_fit_regime,
                         "worst_greek_risk_regime": s.worst_greek_risk_regime,
                         "greek_risk_verdict": s.greek_risk_verdict,
                         "survived_high_theta_high_vega_risk": s.survived_high_theta_high_vega_risk}
                        for s in strategy_scores],
        walk_forward_summary={s.strategy_id: s.walk_forward_overall for s in strategy_scores},
        analysis_fusion_summary={s.strategy_id: s.analysis_fusion_overall for s in strategy_scores},
        overfit_summary=overfit_summary,
        paper_only_promotion_status=promotion_decisions.get(champion_id, "research_only"),
        run_id=run_id,
        reproducibility_hash=repro,
        best_regimes_by_family=best_by_fam,
        worst_regimes_by_family=worst_by_fam,
        family_strengths=strengths_by_fam,
        family_weaknesses=weaknesses_by_fam,
        champion_best_regimes=champ_score.best_regimes if champ_score else [],
        champion_worst_regimes=champ_score.worst_regimes if champ_score else [],
        champion_overfit_level=champ_score.overfit_level if champ_score else "none",
        champion_replay_score=champ_score.walk_forward_overall if champ_score else 0.0,
        champion_analysis_fusion_score=champ_score.analysis_fusion_overall if champ_score else 0.0,
        safety_state=safety_state,
        corpus_id=CORPUS_ID,
        window_count=len(windows),
        average_liquidity_score=champ_score.average_liquidity_score if champ_score else 0.0,
        average_fill_quality_score=champ_score.average_fill_quality_score if champ_score else 0.0,
        worst_slippage_regime=champ_score.worst_slippage_regime if champ_score else "",
        best_liquidity_regime=champ_score.best_liquidity_regime if champ_score else "",
        liquidity_robustness_score=champ_score.liquidity_robustness_score if champ_score else 0.0,
        slippage_robustness_score=champ_score.slippage_robustness_score if champ_score else 0.0,
        survived_bad_fill_low_liquidity=champ_score.survived_bad_fill_low_liquidity if champ_score else False,
        slippage_liquidity_summary=slippage_liquidity_summary,
        greeks_validation_model_version=GREEKS_VALIDATION_MODEL_VERSION,
        iv_fixture_model_version=IV_FIXTURE_MODEL_VERSION,
        iv_surface_expansion_version=IV_SURFACE_EXPANSION_VERSION,
        average_greek_fit_score=champ_score.average_greek_fit_score if champ_score else 0.0,
        average_iv_context_score=champ_score.average_iv_context_score if champ_score else 0.0,
        average_iv_surface_fit_score=champ_score.average_iv_surface_fit_score if champ_score else 0.0,
        average_family_iv_fit_score=champ_score.average_family_iv_fit_score if champ_score else 0.0,
        average_skew_term_score=champ_score.average_skew_term_score if champ_score else 0.0,
        average_premium_overpayment_score=(
            champ_score.average_premium_overpayment_score if champ_score else 0.0),
        average_greek_attribution_quality=(
            champ_score.average_greek_attribution_quality if champ_score else 0.0),
        best_greek_fit_regime=champ_score.best_greek_fit_regime if champ_score else "",
        worst_greek_risk_regime=champ_score.worst_greek_risk_regime if champ_score else "",
        greek_strengths=champ_score.greek_strengths if champ_score else [],
        greek_weaknesses=champ_score.greek_weaknesses if champ_score else [],
        greek_iv_summary=greek_iv_summary,
        iv_surface_expansion_summary=iv_surface_expansion_summary,
        survived_high_theta_high_vega_risk=(
            champ_score.survived_high_theta_high_vega_risk if champ_score else False),
        source_scorecard_summary=source_scorecard_summary,
        pattern_recognition_summary=pattern_recognition_summary,
        mutation_evolution_summary=mutation_evolution_summary,
        structure_builder_summary=structure_builder_summary,
        failure_mode_summary=failure_mode_summary,
        best_mutated_strategy_id=mutation_evolution_summary.get("best_mutated_strategy_id", ""),
        parent_vs_mutation_comparison=mutation_evolution_summary.get("parent_vs_mutation_comparison", {}),
        average_macro_fit_score=champ_score.average_macro_fit_score if champ_score else 0.0,
        average_macro_risk_score=champ_score.average_macro_risk_score if champ_score else 0.0,
        best_macro_regime=champ_score.best_macro_regime if champ_score else "",
        worst_macro_regime=champ_score.worst_macro_regime if champ_score else "",
        macro_failure_modes=champ_score.macro_event_risk_flags if champ_score else [],
        event_risk_robustness=1.0 - (champ_score.average_event_risk_score if champ_score else 0.5),
        vix_vvix_stress_robustness=1.0 - (champ_score.average_vix_vvix_stress_score if champ_score else 0.5),
        breadth_sector_confirmation_score=(
            champ_score.average_breadth_sector_confirmation_score if champ_score else 0.0),
        macro_contradiction_score=(
            champ_score.average_macro_contradiction_penalty if champ_score else 0.0),
        macro_event_summary=macro_event_summary,
        average_fundamental_fit_score=champ_score.average_fundamental_fit_score if champ_score else 0.0,
        average_sector_fit_score=champ_score.average_sector_fit_score if champ_score else 0.0,
        average_peer_confirmation_score=champ_score.average_peer_confirmation_score if champ_score else 0.0,
        average_valuation_risk_score=champ_score.average_valuation_risk_score if champ_score else 0.0,
        average_earnings_quality_score=champ_score.average_earnings_quality_score if champ_score else 0.0,
        average_crowding_risk_score=champ_score.average_crowding_risk_score if champ_score else 0.0,
        average_fundamental_contradiction_penalty=(
            champ_score.average_fundamental_contradiction_penalty if champ_score else 0.0),
        average_fragility_penalty=champ_score.average_fragility_penalty if champ_score else 0.0,
        fundamental_risk_flags=champ_score.fundamental_risk_flags if champ_score else [],
        best_fundamental_scenario=champ_score.best_fundamental_scenario if champ_score else "",
        worst_fundamental_scenario=champ_score.worst_fundamental_scenario if champ_score else "",
        fundamental_summary=fundamental_summary,
    )
    write_champion_registry(champ_entry, path=reg_path)

    result = TournamentResult(
        tournament_id=tournament_id,
        mode=str(cfg.get("mode", "RESEARCH")),
        live_trading_enabled=bool(cfg.get("live_trading_enabled", False)),
        tournament_status="ok",
        champion_strategy_id=champion_id,
        runner_up_strategy_id=runner_up_id,
        strategy_ranking=[s.to_dict() for s in strategy_scores],
        family_scorecard=family_scorecard,
        overfit_summary=overfit_summary,
        promotion_decisions=promotion_decisions,
        champion_registry_path=str(reg_path),
        proof_record_path=str(ledger_path),
        live_blocked=True,
        reproducibility_hash=repro,
        corpus_id=CORPUS_ID,
        window_count=len(windows),
        regime_tags_covered=regime_tags,
        family_replay_summaries=family_replay_summaries,
        analysis_fusion_summaries=fusion_summaries,
        safety_state=safety_state,
        liquidity_model_version=LIQUIDITY_MODEL_VERSION,
        slippage_model_version=SLIPPAGE_MODEL_VERSION,
        slippage_liquidity_summary=slippage_liquidity_summary,
        worst_slippage_regimes=worst_slippage_regimes,
        best_fill_quality_regimes=best_fill_quality_regimes,
        greeks_validation_model_version=GREEKS_VALIDATION_MODEL_VERSION,
        iv_fixture_model_version=IV_FIXTURE_MODEL_VERSION,
        iv_surface_expansion_version=IV_SURFACE_EXPANSION_VERSION,
        greek_iv_summary=greek_iv_summary,
        iv_surface_expansion_summary=iv_surface_expansion_summary,
        worst_greek_risk_regimes=worst_greek_risk_regimes,
        best_greek_fit_regimes=best_greek_fit_regimes,
        source_scorecard_summary=source_scorecard_summary,
        pattern_recognition_summary=pattern_recognition_summary,
        mutation_evolution_summary=mutation_evolution_summary,
        structure_builder_summary=structure_builder_summary,
        failure_mode_summary=failure_mode_summary,
        macro_event_expansion_version=MACRO_EVENT_EXPANSION_VERSION,
        macro_event_summary=macro_event_summary,
        family_macro_scores=macro_event_summary["family_scores"],
        fundamental_expansion_version=FUNDAMENTAL_EXPANSION_VERSION,
        fundamental_summary=fundamental_summary,
        family_fundamental_scores=fundamental_summary["family_scores"],
    )

    entry = build_tournament_proof_entry(run_id, result=result, strategy_scores=strategy_scores,
                                          repro_hash=repro)
    ProofLedger(ledger_path).append(entry)
    summary = TournamentSummary(
        mode=result.mode,
        live_trading_enabled=result.live_trading_enabled,
        tournament_status=result.tournament_status,
        champion_strategy_id=champion_id,
        runner_up_strategy_id=runner_up_id,
        windows_replayed=len(windows),
        strategies_evaluated=len(genomes),
        champion_registry_path=str(reg_path),
        proof_record_path=str(ledger_path),
        live_blocked=True,
    ).to_dict()
    summary["strategy_ranking"] = result.strategy_ranking
    summary["family_scorecard"] = family_scorecard
    summary["overfit_summary"] = overfit_summary
    summary["promotion_decisions"] = promotion_decisions
    summary["analysis_fusion_summaries"] = fusion_summaries
    summary["family_replay_summaries"] = family_replay_summaries
    summary["liquidity_model_version"] = LIQUIDITY_MODEL_VERSION
    summary["slippage_model_version"] = SLIPPAGE_MODEL_VERSION
    summary["slippage_liquidity_summary"] = slippage_liquidity_summary
    summary["worst_slippage_regimes"] = worst_slippage_regimes
    summary["best_fill_quality_regimes"] = best_fill_quality_regimes
    summary["greeks_validation_model_version"] = GREEKS_VALIDATION_MODEL_VERSION
    summary["iv_fixture_model_version"] = IV_FIXTURE_MODEL_VERSION
    summary["iv_surface_expansion_version"] = IV_SURFACE_EXPANSION_VERSION
    summary["greek_iv_summary"] = greek_iv_summary
    summary["iv_surface_expansion_summary"] = iv_surface_expansion_summary
    summary["worst_greek_risk_regimes"] = worst_greek_risk_regimes
    summary["best_greek_fit_regimes"] = best_greek_fit_regimes
    summary["source_scorecard_summary"] = source_scorecard_summary
    summary["pattern_recognition_summary"] = pattern_recognition_summary
    summary["mutation_evolution_summary"] = mutation_evolution_summary
    summary["structure_builder_summary"] = structure_builder_summary
    summary["failure_mode_summary"] = failure_mode_summary
    summary["macro_event_expansion_version"] = MACRO_EVENT_EXPANSION_VERSION
    summary["macro_event_summary"] = macro_event_summary
    summary["family_macro_scores"] = macro_event_summary["family_scores"]
    summary["fundamental_summary"] = fundamental_summary
    summary["family_fundamental_scores"] = fundamental_summary["family_scores"]
    summary["reproducibility_hash"] = repro
    summary["corpus_id"] = CORPUS_ID
    summary["regime_tags_covered"] = regime_tags
    summary["safety_state"] = safety_state
    return summary
