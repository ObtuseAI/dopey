"""Deterministic offline ensemble strategy allocator for DOPEY.

Combines tournament, mutation, feedback, failure-mode, macro/IV/Greeks/liquidity/pattern
evidence into a paper-only simulated allocation recommendation layer. This is NOT live
portfolio management: it only produces simulated paper weights for offline analysis.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_analysis.enrichment import load_window_analysis, parse_window_analysis
from dopey_analysis.pattern_fixture_library import build_pattern_fixture_library
from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_tournament.runner import run_fixture_tournament
from dopey_walk_forward.window_model import load_walk_forward_windows

from .allocation_policy import (
    ALLOCATION_POLICY_VERSION,
    OVERFIT_RANK,
    apply_allocation_policy,
)
from .ensemble_models import (
    EnsembleAllocationResult,
    FamilyAllocationProfile,
    FORBIDDEN_ALLOCATION_DECISIONS,
    StrategyAllocationCandidate,
)
from .ensemble_replay import ENSEMBLE_REPLAY_VERSION, run_ensemble_replay
from .failure_feedback import aggregate_failure_modes, build_family_failure_profiles
from .failure_mode_registry import FAILURE_MODE_REGISTRY_PATH
from .mutation_registry import MUTATION_REGISTRY_PATH, latest_mutation_summary
from .regime_allocator import REGIME_ALLOCATOR_VERSION, build_regime_profiles, regime_class_for_tag


ENSEMBLE_ALLOCATOR_VERSION = "dopey-offline-ensemble-allocator-v1"
ENSEMBLE_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "ensemble_allocator"
ENSEMBLE_REGISTRY_PATH = ENSEMBLE_ARTIFACT_DIR / "ensemble_allocation_registry.jsonl"
ENSEMBLE_LEDGER_PATH = ENSEMBLE_ARTIFACT_DIR / "ensemble_replay.jsonl"

FEEDBACK_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "failure_feedback" / "failure_feedback_registry.jsonl"
)

CONSISTENCY_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "walk_forward_consistency" / "consistency_registry.jsonl"
)

CORPUS_V2_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "regime_holdout_corpus_v2" / "corpus_registry.jsonl"
)


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_allocator": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_ensemble_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"ensemble allocator requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("ensemble allocator requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("ensemble allocator requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("ensemble allocator requires allow_unofficial_robinhood_api=false")


def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _latest_jsonl(path: Path) -> dict | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def _failure_pressure_by_family(failure_record: dict | None) -> dict[str, float]:
    if not failure_record:
        return {}
    aggregates = aggregate_failure_modes(failure_record)
    profiles = build_family_failure_profiles(aggregates)
    out: dict[str, float] = {}
    for profile in profiles:
        pressure = float(sum(profile.recommendation_pressure.values()))
        # Soft saturation: families need substantial recurring pressure to cross the starve
        # threshold (0.40). This keeps failure pressure as a meaningful penalty rather than
        # starving every family.
        out[profile.strategy_family] = round(pressure / (pressure + 30.0), 6)
    return out


def _load_stronger_consistency_lookup(path: Path | None = None) -> dict[str, dict]:
    """Read the stronger walk-forward consistency registry and produce a lookup by strategy_id."""
    target = Path(path) if path else CONSISTENCY_REGISTRY_PATH
    if not target.exists():
        return {}
    try:
        last = json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}
    lookup: dict[str, dict] = {}
    for s in last.get("strategy_consistency_scores", []) or []:
        sid = str(s.get("strategy_id", ""))
        if not sid:
            continue
        lookup[sid] = {
            "overall": float(s.get("overall", 0.0)),
            "holdout_survival": float(s.get("holdout_survival", 0.0)),
            "overfit_penalty": float(s.get("overfit_penalty", 0.0)),
        }
    for v in last.get("consistency_verdicts", []) or []:
        sid = str(v.get("strategy_id", ""))
        if sid in lookup:
            lookup[sid]["verdict"] = str(v.get("verdict", ""))
    return lookup


def _load_corpus_v2_consistency_lookup(path: Path | None = None) -> dict[str, dict]:
    """Read the regime/holdout corpus v2 registry and produce a lookup by strategy_id."""
    target = Path(path) if path else CORPUS_V2_REGISTRY_PATH
    if not target.exists():
        return {}
    try:
        last = json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}
    lookup: dict[str, dict] = {}
    for s in last.get("strategy_consistency_scores", []) or []:
        sid = str(s.get("strategy_id", ""))
        if not sid:
            continue
        lookup[sid] = {
            "overall": float(s.get("overall", 0.0)),
            "holdout_survival": float(s.get("holdout_survival", 0.0)),
            "overfit_penalty": float(s.get("overfit_penalty", 0.0)),
        }
    for v in last.get("consistency_verdicts", []) or []:
        sid = str(v.get("strategy_id", ""))
        if sid in lookup:
            lookup[sid]["verdict"] = str(v.get("verdict", ""))
    return lookup


def _row_to_candidate(row: dict, source_type: str, failure_pressure: dict[str, float], mutation_delta: float = 0.0) -> StrategyAllocationCandidate:
    family = str(row.get("strategy_family", ""))
    return StrategyAllocationCandidate(
        strategy_id=str(row.get("strategy_id", "")),
        strategy_family=family,
        source_type=source_type,
        base_score=round(float(row.get("combined_score", row.get("base_score", 0.0))), 6),
        walk_forward_score=round(float(row.get("walk_forward_overall", row.get("walk_forward_score", 0.0))), 6),
        analysis_fusion_score=round(float(row.get("analysis_fusion_overall", row.get("analysis_fusion_score", 0.0))), 6),
        macro_fit_score=round(float(row.get("average_macro_fit_score", row.get("macro_fit_score", 0.0))), 6),
        iv_surface_fit_score=round(float(row.get("average_iv_surface_fit_score", row.get("iv_surface_fit_score", 0.0))), 6),
        greek_fit_score=round(float(row.get("average_greek_fit_score", row.get("greek_fit_score", 0.0))), 6),
        liquidity_robustness_score=round(float(row.get("liquidity_robustness_score", 0.0)), 6),
        slippage_robustness_score=round(float(row.get("slippage_robustness_score", 0.0)), 6),
        pattern_score=round(float(row.get("average_pattern_fixture_score", row.get("pattern_score", 0.0))), 6),
        failure_pressure_score=round(failure_pressure.get(family, 0.0), 6),
        overfit_level=str(row.get("overfit_level", "unknown")),
        overfit_rank=OVERFIT_RANK.get(str(row.get("overfit_level", "unknown")), 3),
        mutation_delta=round(mutation_delta, 6),
        promotion_state=str(row.get("champion_status", row.get("promotion_state", "entrant"))),
        paper_only=True,
        holdout_score=round(float(row.get("holdout_score", 0.0)), 6),
        best_regimes=[str(r) for r in row.get("best_regimes", [])],
        worst_regimes=[str(r) for r in row.get("worst_regimes", [])],
    )


def _mutation_candidate(mutation_summary: dict, base_row: dict, failure_pressure: dict[str, float]) -> StrategyAllocationCandidate | None:
    comparison = dict(mutation_summary.get("parent_vs_mutation_comparison", {}))
    best_id = str(mutation_summary.get("best_mutated_strategy_id", ""))
    best_score = float(comparison.get("best_mutated_score", 0.0))
    parent_score = float(comparison.get("parent_score", base_row.get("combined_score", 0.0)))
    if not best_id or best_score <= 0.0:
        return None
    delta = round(best_score - parent_score, 6)
    family = str(base_row.get("strategy_family", ""))
    return StrategyAllocationCandidate(
        strategy_id=best_id,
        strategy_family=family,
        source_type="mutation",
        base_score=round(best_score, 6),
        walk_forward_score=round(float(base_row.get("walk_forward_overall", 0.0)) + max(0.0, delta), 6),
        analysis_fusion_score=round(float(base_row.get("analysis_fusion_overall", 0.0)), 6),
        macro_fit_score=round(float(base_row.get("average_macro_fit_score", 0.0)), 6),
        iv_surface_fit_score=round(float(base_row.get("average_iv_surface_fit_score", 0.0)), 6),
        greek_fit_score=round(float(base_row.get("average_greek_fit_score", 0.0)), 6),
        liquidity_robustness_score=round(float(base_row.get("liquidity_robustness_score", 0.0)), 6),
        slippage_robustness_score=round(float(base_row.get("slippage_robustness_score", 0.0)), 6),
        pattern_score=round(float(base_row.get("average_pattern_fixture_score", 0.0)), 6),
        failure_pressure_score=round(failure_pressure.get(family, 0.0), 6),
        overfit_level=str(base_row.get("overfit_level", "unknown")),
        overfit_rank=OVERFIT_RANK.get(str(base_row.get("overfit_level", "unknown")), 3),
        mutation_delta=delta,
        promotion_state="mutation_candidate",
        paper_only=True,
        holdout_score=round(float(base_row.get("holdout_score", 0.0)), 6),
        best_regimes=[str(r) for r in base_row.get("best_regimes", [])],
        worst_regimes=[str(r) for r in base_row.get("worst_regimes", [])],
    )


def _feedback_candidate(feedback_record: dict | None, base_row: dict, failure_pressure: dict[str, float]) -> StrategyAllocationCandidate | None:
    if not feedback_record:
        return None
    best = feedback_record.get("best_candidate") or {}
    comparison = feedback_record.get("parent_vs_previous_mutation_vs_feedback_mutation_comparison") or {}
    best_id = str(best.get("candidate_strategy_id", comparison.get("best_feedback_strategy_id", "")))
    if not best_id:
        return None
    best_score = float(best.get("adjusted_score", comparison.get("best_feedback_score", 0.0)))
    previous_score = float(comparison.get("previous_mutation_score", base_row.get("combined_score", 0.0)))
    delta = round(best_score - previous_score, 6)
    family = str(best.get("strategy_family", base_row.get("strategy_family", "")))
    return StrategyAllocationCandidate(
        strategy_id=best_id,
        strategy_family=family,
        source_type="feedback",
        base_score=round(best_score, 6),
        walk_forward_score=round(float(base_row.get("walk_forward_overall", 0.0)) + max(0.0, delta), 6),
        analysis_fusion_score=round(float(base_row.get("analysis_fusion_overall", 0.0)), 6),
        macro_fit_score=round(float(base_row.get("average_macro_fit_score", 0.0)), 6),
        iv_surface_fit_score=round(float(base_row.get("average_iv_surface_fit_score", 0.0)), 6),
        greek_fit_score=round(float(base_row.get("average_greek_fit_score", 0.0)), 6),
        liquidity_robustness_score=round(float(base_row.get("liquidity_robustness_score", 0.0)), 6),
        slippage_robustness_score=round(float(base_row.get("slippage_robustness_score", 0.0)), 6),
        pattern_score=round(float(base_row.get("average_pattern_fixture_score", 0.0)), 6),
        failure_pressure_score=round(failure_pressure.get(family, 0.0), 6),
        overfit_level=str(best.get("overfit_level", base_row.get("overfit_level", "unknown"))),
        overfit_rank=OVERFIT_RANK.get(str(best.get("overfit_level", base_row.get("overfit_level", "unknown"))), 3),
        mutation_delta=delta,
        promotion_state="feedback_candidate",
        paper_only=True,
        holdout_score=round(float(base_row.get("holdout_score", 0.0)), 6),
        best_regimes=[str(r) for r in base_row.get("best_regimes", [])],
        worst_regimes=[str(r) for r in base_row.get("worst_regimes", [])],
    )


def _build_family_profiles(candidates: list[StrategyAllocationCandidate]) -> list[FamilyAllocationProfile]:
    grouped: dict[str, list[StrategyAllocationCandidate]] = {}
    for c in candidates:
        grouped.setdefault(c.strategy_family, []).append(c)
    profiles: list[FamilyAllocationProfile] = []
    all_regimes = {r for c in candidates for r in c.best_regimes}
    for family in sorted(grouped):
        items = grouped[family]
        scores = sorted(i.base_score for i in items)
        best = scores[-1]
        median = scores[len(scores) // 2]
        regimes_covered = {r for i in items for r in i.best_regimes}
        specialist = len(regimes_covered) <= 2
        all_weather = len(regimes_covered) >= max(3, len(all_regimes) - 1)
        top = sorted(items, key=lambda i: (-i.base_score, i.strategy_id))[0]
        profiles.append(FamilyAllocationProfile(
            strategy_family=family,
            candidate_count=len(items),
            best_score=round(best, 6),
            median_score=round(median, 6),
            family_weight=0.0,
            top_strategy_id=top.strategy_id,
            overfit_level=sorted({i.overfit_level for i in items}, key=lambda l: OVERFIT_RANK.get(l, 3))[0],
            regime_specialist=specialist,
            all_weather=all_weather,
            failure_pressure_score=round(max(i.failure_pressure_score for i in items), 6),
            best_regimes=sorted(regimes_covered),
            worst_regimes=sorted({r for i in items for r in i.worst_regimes}),
        ))
    return profiles


def _family_weights(decisions: list) -> dict[str, float]:
    family_share: dict[str, float] = {}
    for d in decisions:
        family_share[d.strategy_family] = family_share.get(d.strategy_family, 0.0) + d.recommended_weight
    return {k: round(v, 6) for k, v in family_share.items()}


def _regime_multipliers_for(candidates: list[StrategyAllocationCandidate], tournament_summary: dict) -> dict[str, float]:
    """Build a deterministic per-strategy regime multiplier from the dominant regime class."""
    macro = tournament_summary.get("macro_event_summary", {}) or {}
    # Use macro family scores to pick the dominant regime family preference, default neutral.
    multipliers: dict[str, float] = {}
    profiles = build_regime_profiles()
    regime_tags = tournament_summary.get("regime_tags_covered", []) or []
    regime_class = regime_class_for_tag(regime_tags[0]) if regime_tags else "macro_contradiction"
    profile = profiles.get(regime_class, profiles["macro_contradiction"])
    for candidate in candidates:
        multipliers[candidate.strategy_id] = profile.family_preference_multiplier.get(candidate.strategy_family, 0.80)
    return multipliers


def _build_proof_entry(summary: dict, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=ENSEMBLE_ALLOCATOR_VERSION,
        task_id="offline-ensemble-strategy-allocator",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=summary["reproducibility_hash"],
        plan_hash=reproducibility_hash({"allocator_version": ENSEMBLE_ALLOCATOR_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "allocator_summary": summary,
            "registry_record": registry_record,
            "safety_state": summary["safety_state"],
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[summary["ensemble_registry_path"], summary["proof_record_path"]],
        diffs=[],
        test_results={
            "allocator_status": summary["allocator_status"],
            "candidates_loaded": summary["candidates_loaded"],
            "weights_sum": summary["weights_sum"],
            "forbidden_live_decisions_present": sorted(
                {d["decision"] for d in summary["decisions"]}.intersection(FORBIDDEN_ALLOCATION_DECISIONS)
            ),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic paper-only allocation; no live execution",
            "weights are simulated research attention, not real capital",
            "no broker connection, credentials, network market data, schedule, or live promotion",
        ],
    )


def run_offline_ensemble_allocator(
    *,
    seed: str = "dopey-ensemble-v1",
    failure_mode_registry_path: Path | str | None = None,
    mutation_registry_path: Path | str | None = None,
    feedback_registry_path: Path | str | None = None,
    ensemble_registry_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_ensemble_safety_state(safety)

    tournament_summary = run_fixture_tournament()
    ranking = list(tournament_summary.get("strategy_ranking", []))
    if not ranking:
        raise ValueError("ensemble allocator requires tournament strategy_ranking rows")
    ranking = sorted(ranking, key=lambda r: (-float(r.get("combined_score", 0.0)), str(r.get("strategy_id", ""))))
    base_row = ranking[0]

    failure_record = _latest_jsonl(Path(failure_mode_registry_path) if failure_mode_registry_path else FAILURE_MODE_REGISTRY_PATH)
    failure_pressure = _failure_pressure_by_family(failure_record)

    mutation_summary = latest_mutation_summary(
        Path(mutation_registry_path) if mutation_registry_path else MUTATION_REGISTRY_PATH
    )
    feedback_record = _latest_jsonl(Path(feedback_registry_path) if feedback_registry_path else FEEDBACK_REGISTRY_PATH)

    candidates: list[StrategyAllocationCandidate] = [
        _row_to_candidate(row, "tournament", failure_pressure) for row in ranking
    ]
    mutation_cand = _mutation_candidate(mutation_summary, base_row, failure_pressure)
    if mutation_cand and mutation_cand.strategy_id not in {c.strategy_id for c in candidates}:
        candidates.append(mutation_cand)
    feedback_cand = _feedback_candidate(feedback_record, base_row, failure_pressure)
    if feedback_cand and feedback_cand.strategy_id not in {c.strategy_id for c in candidates}:
        candidates.append(feedback_cand)

    # Stamp stronger walk-forward consistency scores onto every candidate, if the registry exists.
    _consistency_lookup = _load_stronger_consistency_lookup()
    for cand in candidates:
        entry = _consistency_lookup.get(cand.strategy_id)
        if entry:
            cand.consistency_score = float(entry.get("overall", 0.0))
            cand.consistency_verdict = str(entry.get("verdict", ""))

    # Stamp regime/holdout corpus v2 consistency scores onto every candidate, if the registry exists.
    _corpus_v2_lookup = _load_corpus_v2_consistency_lookup()
    for cand in candidates:
        entry = _corpus_v2_lookup.get(cand.strategy_id)
        if entry:
            cand.corpus_v2_consistency_score = float(entry.get("overall", 0.0))
            cand.corpus_v2_consistency_verdict = str(entry.get("verdict", ""))

    candidates = sorted(candidates, key=lambda c: c.strategy_id)

    regime_multipliers = _regime_multipliers_for(candidates, tournament_summary)
    policy = apply_allocation_policy(candidates, regime_multipliers=regime_multipliers)
    decisions = policy.decisions
    if any(d.decision in FORBIDDEN_ALLOCATION_DECISIONS for d in decisions):
        raise ValueError("forbidden live allocation decision emitted")

    family_profiles = _build_family_profiles(candidates)
    family_weights = _family_weights(decisions)
    for profile in family_profiles:
        profile.family_weight = family_weights.get(profile.strategy_family, 0.0)

    replay = run_ensemble_replay(
        candidates,
        decisions,
        known_regimes=sorted({r for c in candidates for r in c.best_regimes + c.worst_regimes}),
    )
    top = sorted(decisions, key=lambda d: (-d.recommended_weight, d.strategy_id))[0]
    top_family = sorted(family_weights.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if family_weights else top.strategy_family

    redeployment_candidates = [
        {
            "strategy_id": d.strategy_id,
            "strategy_family": d.strategy_family,
            "decision": d.decision,
            "recommended_weight": d.recommended_weight,
            "regime_class": regime_class_for_tag(""),
        }
        for d in decisions
    ]
    # Attach dominant regime class to decisions for redeployment reasoning.
    dominant_regime = (tournament_summary.get("regime_tags_covered") or ["unknown"])[0]
    dominant_class = regime_class_for_tag(dominant_regime)
    for rc in redeployment_candidates:
        rc["regime_class"] = dominant_class

    from dopey_edge.capital_redeployment_engine import build_capital_redeployment_recommendations

    redeployment = build_capital_redeployment_recommendations(
        redeployment_candidates,
        regime_profiles={k: v.to_dict() for k, v in build_regime_profiles().items()},
        failure_pressure_by_family=failure_pressure,
    )

    result = EnsembleAllocationResult(
        allocator_status="ok",
        mode=safety["mode"],
        live_trading_enabled=safety["live_trading_enabled"],
        candidates_loaded=len(candidates),
        families_allocated=sorted(family_weights),
        decisions=[d.to_dict() for d in decisions],
        family_profiles=[p.to_dict() for p in family_profiles],
        regime_profiles=[{"regime_class": k, **v.to_dict()} for k, v in sorted(build_regime_profiles().items())],
        top_strategy=top.strategy_id,
        top_family=top_family,
        weights_sum=policy.weights_sum,
        live_blocked=True,
        safety_state=safety,
    )

    registry_record = {
        "ensemble_allocator_version": ENSEMBLE_ALLOCATOR_VERSION,
        "allocation_policy_version": ALLOCATION_POLICY_VERSION,
        "regime_allocator_version": REGIME_ALLOCATOR_VERSION,
        "ensemble_replay_version": ENSEMBLE_REPLAY_VERSION,
        "seed": seed,
        "candidates": [c.to_dict() for c in candidates],
        "decisions": result.decisions,
        "family_profiles": result.family_profiles,
        "family_weights": family_weights,
        "weights_sum": result.weights_sum,
        "replay": replay.to_dict(),
        "redeployment_recommendations": [r.to_dict() for r in redeployment],
        "source_tournament_id": tournament_summary.get("tournament_id", ""),
        "source_tournament_champion": tournament_summary.get("champion_strategy_id", ""),
        "macro_summary": tournament_summary.get("macro_event_summary", {}),
        "greek_iv_summary": tournament_summary.get("greek_iv_summary", {}),
        "iv_surface_expansion_summary": tournament_summary.get("iv_surface_expansion_summary", {}),
        "slippage_liquidity_summary": tournament_summary.get("slippage_liquidity_summary", {}),
        "overfit_summary": tournament_summary.get("overfit_summary", {}),
        "failure_pressure_by_family": failure_pressure,
        "regime_profiles": result.regime_profiles,
        "stronger_consistency_lookup": _consistency_lookup,
        "corpus_v2_consistency_lookup": _corpus_v2_lookup,
        "safety_state": safety,
    }
    repro = reproducibility_hash(registry_record)
    registry_record["reproducibility_hash"] = repro
    result.reproducibility_hash = repro

    registry_target = _write_jsonl(registry_record, ensemble_registry_path or ENSEMBLE_REGISTRY_PATH)
    proof_target = Path(proof_ledger_path) if proof_ledger_path else ENSEMBLE_LEDGER_PATH
    result.ensemble_registry_path = str(registry_target)

    summary = result.to_dict()
    summary["replay"] = replay.to_dict()
    summary["redeployment_recommendations"] = [r.to_dict() for r in redeployment]
    summary["family_weights"] = family_weights
    summary["macro_summary"] = tournament_summary.get("macro_event_summary", {})
    summary["greek_iv_summary"] = tournament_summary.get("greek_iv_summary", {})
    summary["iv_surface_expansion_summary"] = tournament_summary.get("iv_surface_expansion_summary", {})
    summary["slippage_liquidity_summary"] = tournament_summary.get("slippage_liquidity_summary", {})
    summary["overfit_summary"] = tournament_summary.get("overfit_summary", {})
    summary["failure_pressure_by_family"] = failure_pressure
    summary["source_tournament_champion"] = tournament_summary.get("champion_strategy_id", "")
    summary["single_champion_score"] = replay.single_champion_score
    summary["equal_weight_score"] = replay.equal_weight_score
    summary["allocator_weighted_score"] = replay.allocator_weighted_score
    summary["overfit_adjusted_score"] = replay.overfit_adjusted_score
    summary["best_ensemble_variant"] = replay.best_ensemble_variant
    summary["ensemble_registry_path"] = str(registry_target)
    summary["proof_record_path"] = str(proof_target)

    proof_summary = dict(summary)
    proof_summary["reproducibility_hash"] = repro
    ProofLedger(proof_target).append(_build_proof_entry(proof_summary, registry_record))
    return summary
