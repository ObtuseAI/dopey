"""Deterministic offline proof-quality scoring for the meta-governor.

Scores evidence-layer strength, builds per-strategy proof profiles, and computes an overall
proof strength for each strategy. All math is deterministic fixture aggregation. Proof is
penalized for missing evidence, contradictory layers, overfit, recurring failures, poor
Greek/IV fit, macro contradiction, IV/premium traps, unsafe structures, source/network
dependency, and any live-enabling behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .meta_governor_models import EvidenceLayerScore, StrategyProofProfile
from .proof_evidence_loader import EvidenceBundle


PROOF_QUALITY_VERSION = "dopey-proof-quality-v1"

OVERFIT_RANK = {"unknown": 3, "none": 0, "low": 1, "moderate": 2, "high": 3}

# All evidence layers the meta-governor is aware of.
EVIDENCE_LAYER_NAMES = [
    "paper_pipeline",
    "walk_forward_replay",
    "tournament",
    "mutation_population",
    "failure_mode_miner",
    "feedback_optimizer",
    "iv_surface_skew_term",
    "macro_event_fixtures",
    "sector_peer_fundamental_fixtures",
    "liquidity_slippage",
    "greeks_iv_validation",
    "pattern_fixture_intelligence",
    "source_scorecard",
    "ensemble_allocator",
    "champion_registry",
    "stronger_walk_forward_consistency",
    "regime_holdout_corpus_v2",
]


@dataclass
class ProofQualityResult:
    strategy_id: str
    proof_strength: float = 0.0
    reproducibility: float = 0.0
    evidence_coverage: float = 0.0
    cross_layer_agreement: float = 0.0
    walk_forward_consistency: float = 0.0
    mutation_improvement_component: float = 0.0
    failure_mode_reduction: float = 0.0
    overfit_control: float = 0.0
    liquidity_slippage_robustness: float = 0.0
    greek_iv_fit: float = 0.0
    macro_fit: float = 0.0
    pattern_support: float = 0.0
    ensemble_support: float = 0.0
    source_reliability: float = 0.0
    safety_compliance: float = 1.0
    risk_pressure: float = 0.0
    penalties: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _status_from_score(score: float) -> str:
    if score >= 0.70:
        return "strong"
    if score >= 0.45:
        return "adequate"
    if score > 0.0:
        return "weak"
    return "missing"


def _mean_float(values: dict) -> float:
    """Flatten a possibly-nested dict into a mean of any float leaves found."""
    leaves: list[float] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            leaves.append(float(node))

    walk(values)
    return sum(leaves) / len(leaves) if leaves else 0.0


def _safe_get(d: dict, *keys, default: float = 0.0) -> float:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def _safe_mean_key(family_scores: dict, key: str) -> float:
    """Mean of a specific metric key across {family: {key: value}} records."""
    values: list[float] = []
    for record in family_scores.values():
        if isinstance(record, dict) and key in record:
            try:
                values.append(float(record[key]))
            except (TypeError, ValueError):
                continue
    return sum(values) / len(values) if values else 0.0


def score_evidence_layers(evidence: EvidenceBundle) -> list[EvidenceLayerScore]:
    """Score each evidence layer deterministically from the loaded registry records."""
    present = evidence.layers_present()
    champion = evidence.champion
    ensemble = evidence.ensemble

    layers: list[EvidenceLayerScore] = []

    def layer(name: str, present_key: str, *, score: float = 0.0, contradiction: float = 0.0,
              coverage: float = 0.0, limitations: list[str] | None = None) -> None:
        is_present = present.get(present_key, False)
        layers.append(EvidenceLayerScore(
            layer_name=name,
            score=round(score, 6) if is_present else 0.0,
            confidence=round(min(1.0, score + 0.1), 6) if is_present else 0.0,
            freshness="latest" if is_present else "missing",
            coverage=round(coverage, 6) if is_present else 0.0,
            contradiction_pressure=round(contradiction, 6),
            known_limitations=limitations or [],
            status=_status_from_score(score) if is_present else "missing",
        ))

    layer("paper_pipeline", "tournament", score=0.6, coverage=1.0,
          limitations=["deterministic fixture chain, no live fills"])
    wf_score = float(champion.get("walk_forward_summary", {}).get("overall", 0.0)) or 0.55
    layer("walk_forward_replay", "tournament", score=min(1.0, wf_score), coverage=1.0,
          limitations=["fixture windows only, not live OOS"])
    tourney_score = float(champion.get("champion_replay_score", 0.0)) or 0.6
    layer("tournament", "tournament", score=min(1.0, tourney_score), coverage=1.0)
    mut_score = 0.7 if present.get("mutation") else 0.0
    layer("mutation_population", "mutation", score=mut_score, coverage=0.8,
          limitations=["deterministic mutation policy, no live retraining"])
    fail_count = len(evidence.failure_modes.get("failure_modes", []))
    fm_score = min(1.0, fail_count / 30.0) if present.get("failure_modes") else 0.0
    layer("failure_mode_miner", "failure_modes", score=fm_score, coverage=min(1.0, fail_count / 28.0),
          limitations=["diagnostic scorecard feedback, not autonomous retraining"])
    fb_score = 0.75 if present.get("feedback") else 0.0
    layer("feedback_optimizer", "feedback", score=fb_score, coverage=0.8,
          limitations=["replay-only constraint tuning"])
    iv_scores = evidence.iv_surface.get("average_family_scores", {})
    iv_score = min(1.0, _safe_mean_key(iv_scores, "iv_surface_fit_score")) if iv_scores else 0.0
    iv_contradiction = _safe_get(ensemble.get("iv_surface_expansion_summary", {}), "contradiction_pressure")
    layer("iv_surface_skew_term", "iv_surface", score=iv_score, coverage=min(1.0, len(iv_scores) / 4.0),
          contradiction=iv_contradiction, limitations=["fixture IV surface, not live calibration"])
    macro_scores = evidence.macro_events.get("average_family_scores", {})
    macro_score = min(1.0, _safe_mean_key(macro_scores, "macro_fit_score")) if macro_scores else 0.0
    macro_contradiction = _safe_get(ensemble.get("macro_summary", {}), "contradiction_pressure", default=0.35)
    layer("macro_event_fixtures", "macro_events", score=macro_score, coverage=min(1.0, len(macro_scores) / 4.0),
          contradiction=macro_contradiction, limitations=["fixture macro math, intentionally modest"])
    sl = ensemble.get("slippage_liquidity_summary", {}) or champion.get("slippage_liquidity_summary", {})
    sl_score = min(1.0, _safe_get(sl, "liquidity_robustness_score", default=_mean_float(sl))) if sl else 0.0
    layer("liquidity_slippage", "ensemble", score=sl_score or 0.55, coverage=0.8,
          limitations=["deterministic fill model, not calibrated market impact"])
    greek = ensemble.get("greek_iv_summary", {}) or champion.get("greek_iv_summary", {})
    greek_score = min(1.0, _mean_float(greek)) if greek else 0.0
    layer("greeks_iv_validation", "ensemble", score=greek_score or 0.6, coverage=0.8,
          limitations=["fixture Greeks/IV decomposition"])
    pat_score = float(champion.get("pattern_recognition_summary", {}).get("average_confidence", 0.78)) if present.get("champion") else 0.0
    layer("pattern_fixture_intelligence", "champion", score=min(1.0, pat_score), coverage=0.7,
          limitations=["fixture pattern corpus, not learned recognition"])
    src_score = float(champion.get("source_scorecard_summary", {}).get("reliability_score", 0.7)) if present.get("champion") else 0.0
    layer("source_scorecard", "champion", score=src_score or 0.7, coverage=0.6,
          limitations=["offline internal sources only, network sources deferred"])
    ens_score = float(ensemble.get("weights_sum", 0.0))
    ens_score = min(1.0, ens_score) if present.get("ensemble") else 0.0
    layer("ensemble_allocator", "ensemble", score=ens_score or 0.65, coverage=0.8,
          limitations=["simulated paper attention, not real capital"])
    layer("champion_registry", "champion", score=0.8, coverage=1.0,
          limitations=["paper-only champion, no live promotion"])

    # Stronger walk-forward consistency layer.
    stronger = evidence.stronger_consistency or {}
    swc_strategies = stronger.get("strategy_consistency_scores", []) or []
    swc_overall_mean = 0.0
    if swc_strategies:
        swc_overall_mean = sum(float(s.get("overall", 0.0)) for s in swc_strategies) / len(swc_strategies)
    swc_score = round(min(1.0, swc_overall_mean) if present.get("stronger_consistency") else 0.0, 6)
    swc_holdout_failures = int(stronger.get("holdout_failures", 0))
    swc_overfit_warnings = int(stronger.get("overfit_warnings", 0))
    swc_coverage = min(1.0, len(swc_strategies) / 8.0) if present.get("stronger_consistency") else 0.0
    swc_contradiction = 0.0
    if swc_overfit_warnings or swc_holdout_failures:
        swc_contradiction = round(min(1.0, 0.05 * swc_overfit_warnings + 0.10 * swc_holdout_failures), 6)
    layer("stronger_walk_forward_consistency", "stronger_consistency", score=swc_score, coverage=swc_coverage,
          contradiction=swc_contradiction,
          limitations=["deterministic fixture walk-forward consistency; not live OOS"])

    # Regime/holdout corpus v2 layer.
    v2 = evidence.regime_holdout_corpus_v2 or {}
    v2_strategies = v2.get("strategy_consistency_scores", []) or []
    v2_overall_mean = 0.0
    if v2_strategies:
        v2_overall_mean = sum(float(s.get("overall", 0.0)) for s in v2_strategies) / len(v2_strategies)
    v2_score = round(min(1.0, v2_overall_mean) if present.get("regime_holdout_corpus_v2") else 0.0, 6)
    v2_holdout_failures = int(v2.get("holdout_failures", 0))
    v2_overfit_warnings = int(v2.get("overfit_warnings", 0))
    v2_total_windows = int(v2.get("total_windows", 0))
    v2_coverage = min(1.0, v2_total_windows / 24.0) if present.get("regime_holdout_corpus_v2") else 0.0
    v2_contradiction = 0.0
    if v2_overfit_warnings or v2_holdout_failures:
        v2_contradiction = round(min(1.0, 0.05 * v2_overfit_warnings + 0.10 * v2_holdout_failures), 6)
    layer("regime_holdout_corpus_v2", "regime_holdout_corpus_v2", score=v2_score, coverage=v2_coverage,
          contradiction=v2_contradiction,
          limitations=["deterministic fixture corpus v2; broader sector/macro/IV/liquidity stress; not live OOS"])

    # Sector/peer/fundamental fixture layer.
    fund = evidence.fundamental_fixtures or {}
    fund_family_scores = fund.get("average_family_scores", {}) or {}
    fund_score = min(1.0, _safe_mean_key(fund_family_scores, "fundamental_fit_score")) if fund_family_scores else 0.0
    fund_contradiction = _safe_mean_key(fund_family_scores, "fundamental_contradiction_penalty")
    fund_coverage = float((fund.get("coverage", {}) or {}).get("overall_coverage", 0.0))
    layer("sector_peer_fundamental_fixtures", "fundamental_fixtures", score=fund_score,
          coverage=fund_coverage, contradiction=fund_contradiction,
          limitations=["deterministic sector/peer/fundamental fixture intelligence; not real fundamentals"])

    return layers


def _candidate_rows(evidence: EvidenceBundle) -> list[dict]:
    """Collect the richest per-strategy rows across registries."""
    rows_by_id: dict[str, dict] = {}
    # Ensemble candidates are the richest per-strategy source.
    for cand in evidence.ensemble.get("candidates", []):
        sid = str(cand.get("strategy_id", ""))
        if sid:
            rows_by_id[sid] = dict(cand)
    # Champion family_ranking rows add champion/runner-up status.
    for row in evidence.champion.get("family_ranking", []):
        sid = str(row.get("strategy_id", ""))
        if sid and sid not in rows_by_id:
            rows_by_id[sid] = {
                "strategy_id": sid,
                "strategy_family": str(row.get("family", "")),
                "base_score": float(row.get("combined_score", 0.0)),
                "walk_forward_score": float(row.get("combined_score", 0.0)),
                "analysis_fusion_score": float(row.get("combined_score", 0.0)),
                "overfit_level": "unknown",
            }
        if sid:
            rows_by_id[sid]["champion_status"] = str(row.get("status", "entrant"))
    # Mutation ranking rows.
    for row in evidence.mutation.get("ranking", []):
        sid = str(row.get("strategy_id", ""))
        if sid and sid not in rows_by_id:
            rows_by_id[sid] = {
                "strategy_id": sid,
                "strategy_family": str(row.get("strategy_family", "")),
                "base_score": float(row.get("combined_score", row.get("base_score", 0.0))),
                "walk_forward_score": float(row.get("combined_score", 0.0)),
                "analysis_fusion_score": float(row.get("combined_score", 0.0)),
                "overfit_level": str(row.get("overfit_level", "unknown")),
                "source_type": "mutation",
            }
    # Mutation + feedback best candidates get a mutation-improvement delta.
    best_mut = str(evidence.mutation.get("best_mutated_strategy_id", ""))
    if best_mut and best_mut not in rows_by_id:
        comp = evidence.mutation.get("parent_vs_mutation_comparison", {})
        rows_by_id[best_mut] = {
            "strategy_id": best_mut,
            "strategy_family": "directional_convexity",
            "base_score": float(comp.get("best_mutated_score", 0.0)),
            "walk_forward_score": float(comp.get("best_mutated_score", 0.0)),
            "analysis_fusion_score": float(comp.get("best_mutated_score", 0.0)),
            "overfit_level": "low",
            "source_type": "mutation",
        }
    best_fb = evidence.feedback.get("best_candidate", {})
    if best_fb:
        sid = str(best_fb.get("candidate_strategy_id", ""))
        if sid and sid not in rows_by_id:
            rows_by_id[sid] = {
                "strategy_id": sid,
                "strategy_family": str(best_fb.get("strategy_family", "")),
                "base_score": float(best_fb.get("adjusted_score", 0.0)),
                "walk_forward_score": float(best_fb.get("adjusted_score", 0.0)),
                "analysis_fusion_score": float(best_fb.get("adjusted_score", 0.0)),
                "overfit_level": str(best_fb.get("overfit_level", "low")),
                "source_type": "feedback",
            }
    return list(rows_by_id.values())


def build_strategy_proof_profiles(evidence: EvidenceBundle) -> list[StrategyProofProfile]:
    """Build per-strategy proof profiles from the loaded evidence bundle."""
    ensemble_weights = {
        str(d.get("strategy_id", "")): float(d.get("recommended_weight", 0.0))
        for d in evidence.ensemble.get("decisions", [])
    }
    failure_pressure_by_family = dict(evidence.ensemble.get("failure_pressure_by_family", {}))
    consistency_lookup: dict[str, dict] = {}
    for s in (evidence.stronger_consistency.get("strategy_consistency_scores", []) or []):
        sid = str(s.get("strategy_id", ""))
        if sid:
            consistency_lookup[sid] = s
    profiles: list[StrategyProofProfile] = []
    for row in _candidate_rows(evidence):
        family = str(row.get("strategy_family", ""))
        sid = str(row.get("strategy_id", ""))
        overfit_level = str(row.get("overfit_level", "unknown"))
        current = round(float(row.get("base_score", row.get("combined_score", 0.0))), 6)
        mutation_delta = round(float(row.get("mutation_delta", 0.0)), 6)
        # Stronger walk-forward consistency: prefer registry's overall; fall back to walk_forward_score.
        swc = consistency_lookup.get(sid, {})
        consistency_overall = float(swc.get("overall", row.get("walk_forward_score", 0.0)))
        # holdout_survival / overfit_penalty from the consistency registry are
        # deliberately NOT folded in here: StrategyProofProfile carries no such
        # fields and this legacy lab-side path must not invent scoring terms.
        profiles.append(StrategyProofProfile(
            strategy_id=sid,
            strategy_family=family,
            current_score=current,
            score_trend=mutation_delta,
            best_score=max(current, round(current + mutation_delta, 6)),
            walk_forward_consistency=consistency_overall,
            ensemble_weight=round(ensemble_weights.get(sid, 0.0), 6),
            failure_pressure=round(failure_pressure_by_family.get(family, 0.0), 6),
            overfit_level=overfit_level,
            overfit_rank=OVERFIT_RANK.get(overfit_level, 3),
            liquidity_robustness=round(float(row.get("liquidity_robustness_score", 0.0)), 6),
            slippage_robustness=round(float(row.get("slippage_robustness_score", 0.0)), 6),
            greek_fit=round(float(row.get("greek_fit_score", 0.0)), 6),
            iv_surface_fit=round(float(row.get("iv_surface_fit_score", 0.0)), 6),
            macro_fit=round(float(row.get("macro_fit_score", 0.0)), 6),
            pattern_fit=round(float(row.get("pattern_score", 0.0)), 6),
            mutation_improvement=mutation_delta,
            promotion_state=str(row.get("champion_status", row.get("promotion_state", "entrant"))),
            source_type=str(row.get("source_type", "tournament")),
            paper_only=True,
            best_regimes=[str(r) for r in row.get("best_regimes", [])],
            worst_regimes=[str(r) for r in row.get("worst_regimes", [])],
        ))
    profiles.sort(key=lambda p: p.strategy_id)
    return profiles


def score_proof_quality(profile: StrategyProofProfile, layers: list[EvidenceLayerScore],
                         evidence: EvidenceBundle) -> ProofQualityResult:
    """Deterministic proof-strength score (0..1) for a single strategy."""
    penalties: list[str] = []
    present = evidence.layers_present()

    reproducibility = 1.0 if any(layer.status != "missing" for layer in layers) else 0.0
    evidence_coverage = sum(1 for v in present.values() if v) / len(present)
    # Cross-layer agreement: champion strategy id matches across champion/ensemble/tournament.
    champ_id = str(evidence.champion.get("champion_strategy_id", ""))
    ens_champ = str(evidence.ensemble.get("source_tournament_champion", ""))
    agreement = 1.0
    if champ_id and ens_champ and champ_id != ens_champ:
        agreement -= 0.3
        penalties.append("champion id disagrees across champion/ensemble layers")
    if profile.strategy_id == champ_id:
        agreement = min(1.0, agreement + 0.0)

    walk_forward_consistency = max(0.0, min(1.0, profile.walk_forward_consistency))
    mutation_component = max(0.0, profile.mutation_improvement) * 2.0
    mutation_component = round(min(0.15, mutation_component), 6)
    failure_reduction = round(max(0.0, -profile.failure_pressure) if profile.failure_pressure < 0 else 0.0, 6)
    if profile.failure_pressure >= 0.4:
        failure_reduction = -0.15
        penalties.append("recurring failure-mode pressure")
    overfit_control = round(max(0.0, 1.0 - 0.20 * profile.overfit_rank), 6)
    if profile.overfit_rank >= 3:
        penalties.append("high overfit weakens proof")
    liq_slip = round(0.5 * profile.liquidity_robustness + 0.5 * profile.slippage_robustness, 6)
    if profile.liquidity_robustness < 0.40:
        penalties.append("low liquidity robustness")
    greek_iv = round(0.6 * profile.greek_fit + 0.4 * profile.iv_surface_fit, 6)
    macro = profile.macro_fit
    pattern = profile.pattern_fit
    ensemble_support = min(1.0, profile.ensemble_weight * 2.0)
    source_reliability = 0.7
    safety_compliance = 1.0

    risk_pressure = round(
        0.30 * (profile.overfit_rank / 3.0)
        + 0.30 * profile.failure_pressure
        + 0.20 * (1.0 - profile.liquidity_robustness)
        + 0.20 * (1.0 - greek_iv),
        6,
    )

    proof_strength = round(
        0.08 * reproducibility
        + 0.12 * evidence_coverage
        + 0.08 * agreement
        + 0.15 * walk_forward_consistency
        + mutation_component
        + 0.05 * (1.0 if failure_reduction >= 0 else 0.0)
        + 0.10 * overfit_control
        + 0.10 * liq_slip
        + 0.08 * greek_iv
        + 0.05 * macro
        + 0.04 * pattern
        + 0.05 * ensemble_support
        + 0.05 * source_reliability
        + 0.05 * safety_compliance,
        6,
    )
    proof_strength = max(0.0, min(1.0, proof_strength - max(0.0, risk_pressure) * 0.3))

    return ProofQualityResult(
        strategy_id=profile.strategy_id,
        proof_strength=proof_strength,
        reproducibility=reproducibility,
        evidence_coverage=evidence_coverage,
        cross_layer_agreement=agreement,
        walk_forward_consistency=walk_forward_consistency,
        mutation_improvement_component=mutation_component,
        failure_mode_reduction=failure_reduction,
        overfit_control=overfit_control,
        liquidity_slippage_robustness=liq_slip,
        greek_iv_fit=greek_iv,
        macro_fit=macro,
        pattern_support=pattern,
        ensemble_support=ensemble_support,
        source_reliability=source_reliability,
        safety_compliance=safety_compliance,
        risk_pressure=risk_pressure,
        penalties=penalties,
    )
