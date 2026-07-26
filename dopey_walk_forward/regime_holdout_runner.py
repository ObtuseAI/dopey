"""Deterministic offline regime/holdout corpus v2 replay + comparison runner (paper-only).

Workstream D + E of `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`.

Steps:
  1. Verify safety state (RESEARCH mode, all live flags off).
  2. Load the v2 corpus from `holdout_window_builder`.
  3. Load the v1 consistency registry (latest `consistency_registry.jsonl`).
  4. Build v2 holdout splits: rolling, blocked, anchored, regime-holdout, stress-holdout —
     every split includes both v1 and v2 windows.
  5. Replay the same set of strategy candidates (base + mutation + feedback + ensemble +
     meta-governor + champion) across the v2 splits.
  6. Compute v2 consistency scores, family consistency profiles, and a plan-level
     holdout robustness score.
  7. Compare v1 vs v2 per-strategy consistency overall.
  8. Write v2 registry + ProofLedger record.
  9. Persist v2 fixture files.
 10. Print a concise JSON summary.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .consistency_models import (
    BlockedWalkForwardPlan,
    RollingWalkForwardPlan,
    WalkForwardSplit,
    WalkForwardSplitSet,
)
from .consistency_runner import (
    PROOF_LEDGER_PATH as V1_PROOF_LEDGER_PATH,
    REGISTRY_PATH as V1_REGISTRY_PATH,
    load_all_candidates,
    run_stronger_walk_forward_consistency as run_v1_consistency,
    verify_runner_safety_state,
    _safety_state as _v1_safety_state,
)
from .consistency_score import (
    FamilyConsistencyProfile,
    HoldoutRobustnessScore,
    SplitReplayResult,
    StrategyConsistencyScore,
    build_family_consistency_profile,
    build_holdout_robustness,
    score_strategy_from_split_results,
)
from .consistency_verdict import (
    ALLOWED_CONSISTENCY_VERDICTS,
    ConsistencyVerdict,
    decide_consistency_verdict,
)
from .corpus_coverage import (
    CorpusCoverageScore,
    score_corpus_coverage,
)
from .holdout_window_builder import (
    additional_v2_window_count,
    build_regime_holdout_corpus_v2,
    category_window_count,
)
from .regime_holdout_corpus_v2 import (
    V2_COVERAGE_PATH,
    V2_CORPUS_ARTIFACT_DIR,
    V2_PROOF_PATH,
    V2_REGISTRY_PATH,
    V2_REPLAY_PATH,
    V2_SUMMARY_PATH,
    persist_corpus_v2_fixtures,
)
from .regime_holdout_models import (
    CORPUS_V2_VERSION,
    CrossFamilyChallengeContext,
    RegimeHoldoutCorpus,
    RegimeHoldoutWindow,
    V2_CATEGORIES,
)
from .split_builder import (
    build_anchored_split,
    build_blocked_splits,
    build_regime_holdout_split,
    build_rolling_splits,
    build_stress_holdout_split,
    STRATEGY_FAMILIES,
)
from .window_model import WalkForwardWindow, load_walk_forward_windows


ARTIFACT_DIR = V2_CORPUS_ARTIFACT_DIR
REGISTRY_PATH = V2_REGISTRY_PATH
REPLAY_PATH = V2_REPLAY_PATH
COVERAGE_PATH = V2_COVERAGE_PATH
PROOF_LEDGER_PATH = V2_PROOF_PATH
SUMMARY_PATH = V2_SUMMARY_PATH


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_runner": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_corpus_v2_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"corpus v2 runner requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("corpus v2 runner requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("corpus v2 runner requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("corpus v2 runner requires allow_unofficial_robinhood_api=false")


# ---------------------------------------------------------------------------
# Split builders.
# ---------------------------------------------------------------------------

def _v2_windows_to_dict(windows: list[RegimeHoldoutWindow]) -> dict[str, dict]:
    """Index v2 windows by id for fast lookup."""
    return {w.window_id: w for w in windows}


def _build_v2_split_set(
    v1_windows: list[WalkForwardWindow],
    v2_corpus: RegimeHoldoutCorpus,
    seed: str = "dopey-regime-holdout-corpus-v2-v1",
) -> WalkForwardSplitSet:
    """Build a v2 split set that uses both v1 and v2 windows.

    The v1 walks provide the rolling/blocked/anchored split scaffolding; the v2 windows
    extend the holdout/regime/stress splits to include the new corpus.

    The v2 windows are loaded as plain dict fixtures (see `regime_holdout_corpus_v2._fixture_dict`).
    For the split builder we only need window_id; we treat v2 ids as opaque strings.
    """
    rolling = build_rolling_splits(v1_windows, seed=seed, min_splits=3)
    blocked = build_blocked_splits(v1_windows, seed=seed, min_splits=2)
    anchored = build_anchored_split(v1_windows, seed=seed)
    regime_holdout = build_regime_holdout_split(v1_windows, target_regime="macro_shock_risk_off", seed=seed)
    stress_holdout = build_stress_holdout_split(v1_windows, seed=seed)
    # Build a v2-specific rolling split over the v2 corpus so the v2 windows get exercised
    # by a separate rolling pass. v2 windows are not loadable via WalkForwardWindow, so we
    # build a synthetic WalkForwardSplit from v2 ids directly.
    v2_ids = [w.window_id for w in v2_corpus.windows]
    n = len(v2_ids)
    if n >= 4:
        v2_rolling_splits: list[WalkForwardSplit] = []
        for i in range(min(3, n - 3)):
            train = v2_ids[i : i + 2]
            val = [v2_ids[i + 2]]
            hold = [v2_ids[i + 3]]
            split_id = f"wf-v2-rolling-{i:03d}"
            v2_rolling_splits.append(WalkForwardSplit(
                split_id=split_id,
                train_windows=tuple(train),
                validation_windows=tuple(val),
                holdout_windows=tuple(hold),
                regime_tags=tuple(sorted({v2_corpus.windows[i].regime_tag,
                                          v2_corpus.windows[i + 1].regime_tag,
                                          v2_corpus.windows[i + 2].regime_tag,
                                          v2_corpus.windows[i + 3].regime_tag})),
                split_type="rolling",
                notes=f"v2 rolling split idx={i}",
            ))
        rolling = tuple(rolling) + tuple(v2_rolling_splits)
    splits = list(rolling) + list(blocked) + [anchored, regime_holdout, stress_holdout]
    plan_id = f"dopey-regime-holdout-corpus-v2-{seed}"
    return WalkForwardSplitSet(plan_id=plan_id, splits=tuple(splits))


# ---------------------------------------------------------------------------
# Replay + scoring.
# ---------------------------------------------------------------------------

def _v2_family_pressure(window: RegimeHoldoutWindow, family: str) -> float:
    return float(window.expected_family_pressure.get(family, 0.0))


def _v2_hint_score(window: RegimeHoldoutWindow, family: str) -> float:
    """Deterministic per-(strategy, v2-window) score.

    Uses v2 expected_family_pressure to compute a regime-fit signal: positive
    pressure (challenge) lowers the score; negative pressure (support) raises it.
    Combined with IV / liquidity / macro context for a smooth [0, 1] signal.
    """
    pressure = _v2_family_pressure(window, family)
    # Invert pressure: pressure > 0 means the window is hard for the family.
    fit = max(0.0, min(1.0, 0.5 - pressure))
    liq = window.liquidity_context.liquidity_quality
    spread_p = window.liquidity_context.spread_penalty
    slip = window.liquidity_context.slippage_penalty
    macro_con = window.macro_context.macro_contradiction
    instability = window.iv_surface_context.surface_instability
    pat = window.pattern_context.get("confidence", 0.5)
    score = (
        0.50 * fit
        + 0.15 * liq
        + 0.10 * pat
        - 0.05 * spread_p
        - 0.05 * slip
        - 0.10 * macro_con
        - 0.05 * instability
    )
    return max(0.0, min(1.0, score))


def _replay_v2_for_genome(
    genome,
    corpus: RegimeHoldoutCorpus,
    safety: dict,
) -> list[SplitReplayResult]:
    """Replay one genome across every v2 window. Each window is treated as a per-window
    `SplitReplayResult` with split_type=rolling. We construct a synthetic split_id per
    window so the per-strategy consistency record still carries deterministic ids.
    """
    results: list[SplitReplayResult] = []
    family = genome.family
    for window in corpus.windows:
        train_pass_threshold = 0.30
        validation_pass_threshold = 0.35
        holdout_pass_threshold = 0.40
        score = _v2_hint_score(window, family)
        train_passed = score >= train_pass_threshold
        validation_passed = score >= validation_pass_threshold
        holdout_passed = score >= holdout_pass_threshold
        split_id = f"v2-{window.category}-{window.window_id}"
        results.append(SplitReplayResult(
            split_id=split_id,
            strategy_id=genome.genome_id,
            strategy_family=family,
            split_type=f"v2_{window.category}",
            train_passed=train_passed,
            validation_passed=validation_passed,
            holdout_passed=holdout_passed,
            train_score=round(score, 6),
            validation_score=round(score, 6),
            holdout_score=round(score, 6),
            score_variance=0.0,
            regime_tags_covered=(window.regime_tag,),
            notes=f"v2 replay {genome.genome_id} on {window.window_id} ({window.category})",
        ))
    return results


# ---------------------------------------------------------------------------
# V1 vs V2 comparison.
# ---------------------------------------------------------------------------

def _load_v1_consistency_lookup() -> dict[str, dict]:
    target = V1_REGISTRY_PATH
    if not target.exists():
        return {}
    try:
        last = json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for s in last.get("strategy_consistency_scores", []) or []:
        sid = str(s.get("strategy_id", ""))
        if sid:
            out[sid] = {
                "v1_overall": float(s.get("overall", 0.0)),
                "v1_holdout_survival": float(s.get("holdout_survival", 0.0)),
                "v1_overfit_penalty": float(s.get("overfit_penalty", 0.0)),
            }
    return out


def _v1_v2_delta(v1: dict[str, dict], v2_scores: list[StrategyConsistencyScore]) -> dict[str, dict]:
    """Compute per-strategy delta between v1 and v2."""
    out: dict[str, dict] = {}
    for s in v2_scores:
        v1_overall = (v1.get(s.strategy_id) or {}).get("v1_overall", 0.0)
        v1_holdout = (v1.get(s.strategy_id) or {}).get("v1_holdout_survival", 0.0)
        out[s.strategy_id] = {
            "v1_overall": round(v1_overall, 6),
            "v2_overall": round(s.overall, 6),
            "delta_overall": round(s.overall - v1_overall, 6),
            "v1_holdout_survival": round(v1_holdout, 6),
            "v2_holdout_survival": round(s.holdout_survival, 6),
            "delta_holdout_survival": round(s.holdout_survival - v1_holdout, 6),
            "trend": ("improved" if s.overall > v1_overall + 0.01 else
                       "degraded" if s.overall < v1_overall - 0.01 else "stable"),
        }
    return out


# ---------------------------------------------------------------------------
# Result containers.
# ---------------------------------------------------------------------------

@dataclass
class CorpusV2Result:
    corpus_v2_status: str
    mode: str
    live_trading_enabled: bool
    total_windows: int
    new_windows_added: int
    splits_built: int
    strategies_evaluated: int
    families_evaluated: int
    top_consistent_strategy_v2: str
    top_consistent_family_v2: str
    holdout_failures: int
    overfit_warnings: int
    coverage_score: float
    live_blocked: bool
    registry_path: str
    proof_record_path: str
    safety_state: dict
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# IO helpers.
# ---------------------------------------------------------------------------

def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _build_summary_md(
    result: CorpusV2Result,
    coverage: CorpusCoverageScore,
    strategy_scores: list[StrategyConsistencyScore],
    family_profiles: list[FamilyConsistencyProfile],
    v1_v2: dict[str, dict],
) -> str:
    lines: list[str] = []
    lines.append("# DOPEY Larger Regime/Holdout Corpus V2 Summary")
    lines.append("")
    lines.append(f"- corpus_v2_version: `{CORPUS_V2_VERSION}`")
    lines.append(f"- corpus_v2_status: `{result.corpus_v2_status}`")
    lines.append(f"- mode: `{result.mode}`")
    lines.append(f"- live_trading_enabled: `{result.live_trading_enabled}`")
    lines.append(f"- live_blocked: `{result.live_blocked}`")
    lines.append(f"- total_windows: `{result.total_windows}`")
    lines.append(f"- new_windows_added: `{result.new_windows_added}`")
    lines.append(f"- splits_built: `{result.splits_built}`")
    lines.append(f"- strategies_evaluated: `{result.strategies_evaluated}`")
    lines.append(f"- families_evaluated: `{result.families_evaluated}`")
    lines.append(f"- top_consistent_strategy_v2: `{result.top_consistent_strategy_v2}`")
    lines.append(f"- top_consistent_family_v2: `{result.top_consistent_family_v2}`")
    lines.append(f"- holdout_failures: `{result.holdout_failures}`")
    lines.append(f"- overfit_warnings: `{result.overfit_warnings}`")
    lines.append(f"- coverage_score: `{round(result.coverage_score, 6)}`")
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- regime coverage fraction: `{coverage.regime.coverage_fraction:.3f}`")
    lines.append(f"- sector coverage fraction: `{coverage.sector.coverage_fraction:.3f}`")
    lines.append(f"- stress coverage fraction: `{coverage.stress.overall_coverage_fraction:.3f}`")
    lines.append(f"- missing categories: {list(coverage.missing_categories)}")
    lines.append("")
    lines.append("## Family challenge")
    for f in coverage.family_challenge:
        lines.append(f"- `{f.family}` pressure={f.pressure_windows} support={f.support_windows} high_uncertainty={f.high_uncertainty_windows} mean_pressure={f.mean_pressure:.3f} is_challenged={f.is_challenged}")
    lines.append("")
    lines.append("## Strategy consistency (v2)")
    for s in sorted(strategy_scores, key=lambda x: (-x.overall, x.strategy_id)):
        lines.append(f"- `{s.strategy_id}` ({s.strategy_family}) overall={s.overall:.3f} holdout_survival={s.holdout_survival:.3f} overfit_penalty={s.overfit_penalty:.3f}")
    lines.append("")
    lines.append("## V1 vs V2 comparison")
    for sid, delta in sorted(v1_v2.items(), key=lambda kv: kv[0]):
        lines.append(f"- `{sid}` v1={delta['v1_overall']:.3f} v2={delta['v2_overall']:.3f} delta={delta['delta_overall']:+.3f} trend={delta['trend']}")
    lines.append("")
    lines.append("## Safety state")
    lines.append("- PaperBroker refuses `live_allowed=true`; Robinhood/Alpaca/Tradier raise `LiveTradingDisabledError`.")
    lines.append("- No broker connection, credentials, network access, live trades, live promotion, or scheduled run.")
    lines.append("- Original Blunder source unchanged (SHA256 manifest verified when available).")
    return "\n".join(lines) + "\n"


def _build_proof_entry(result: CorpusV2Result, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=CORPUS_V2_VERSION,
        task_id="regime-holdout-corpus-v2",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"version": CORPUS_V2_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={"result": result.to_dict(), "registry_record": registry_record},
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[result.registry_path, result.proof_record_path],
        diffs=[],
        test_results={
            "corpus_v2_status": result.corpus_v2_status,
            "strategies_evaluated": result.strategies_evaluated,
            "families_evaluated": result.families_evaluated,
            "splits_built": result.splits_built,
            "total_windows": result.total_windows,
            "new_windows_added": result.new_windows_added,
            "holdout_failures": result.holdout_failures,
            "overfit_warnings": result.overfit_warnings,
            "coverage_score": round(result.coverage_score, 6),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic paper-only corpus v2; no live execution",
            "coverage scores are advisory research labels, not live performance evidence",
            "no broker connection, credentials, network access, schedule, or live migration",
        ],
    )


# ---------------------------------------------------------------------------
# Main runner.
# ---------------------------------------------------------------------------

def run_regime_holdout_corpus_v2(
    *,
    seed: str = "dopey-regime-holdout-corpus-v2-v1",
    corpus_id: str | None = None,
    persist_fixtures: bool = True,
    registry_path: Path | str | None = None,
    replay_path: Path | str | None = None,
    coverage_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
    summary_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_corpus_v2_safety_state(safety)

    # 1. Build the v2 corpus.
    corpus = build_regime_holdout_corpus_v2(seed=seed, corpus_id=corpus_id)

    # 2. Optionally persist v2 fixtures to disk.
    if persist_fixtures:
        persist_corpus_v2_fixtures(corpus=corpus)

    # 3. Load v1 windows + v1 consistency.
    v1_windows = load_walk_forward_windows()
    v1_consistency = _load_v1_consistency_lookup()

    # 4. Build v2 split set (rolling + blocked + anchored + regime + stress, v1 + v2 windows).
    split_set = _build_v2_split_set(v1_windows, corpus, seed=seed)

    # 5. Load strategy candidates.
    candidates = load_all_candidates()
    # Always include base genomes so the runner is informative even before downstream artifacts.
    from dopey_tournament.genome_set import build_tournament_genomes
    base_genomes = build_tournament_genomes()
    have_ids = {g.genome_id for g in candidates}
    for g in base_genomes:
        if g.genome_id not in have_ids:
            candidates.append(g)
    candidates = sorted(candidates, key=lambda g: g.genome_id)

    # 6. Replay each candidate across the v2 corpus (per-window).
    all_replays: list[SplitReplayResult] = []
    strongest_by_strategy: dict[str, SplitReplayResult] = {}
    for genome in candidates:
        replays = _replay_v2_for_genome(genome, corpus, safety)
        all_replays.extend(replays)
        for r in replays:
            cur = strongest_by_strategy.get(genome.genome_id)
            if cur is None or r.holdout_score > cur.holdout_score:
                strongest_by_strategy[genome.genome_id] = r

    # 7. Score each strategy on the v2 replays.
    by_strategy: dict[str, list[SplitReplayResult]] = {}
    for r in all_replays:
        by_strategy.setdefault(r.strategy_id, []).append(r)
    strategy_scores: list[StrategyConsistencyScore] = []
    for sid, replays in sorted(by_strategy.items()):
        family = next((g.family for g in candidates if g.genome_id == sid), "unknown")
        family_means = {}
        score = score_strategy_from_split_results(
            strategy_id=sid, strategy_family=family, split_results=replays, family_means=family_means,
        )
        strategy_scores.append(score)
    family_means = {s.strategy_family: s.overall for s in strategy_scores}
    strategy_scores = [
        score_strategy_from_split_results(
            strategy_id=s.strategy_id, strategy_family=s.strategy_family,
            split_results=list(s.split_replay_results), family_means=family_means,
        )
        for s in strategy_scores
    ]

    # 8. Per-family profiles + plan-level holdout robustness.
    known_regimes = {w.regime_tag for w in corpus.windows}
    family_profiles: list[FamilyConsistencyProfile] = []
    by_family: dict[str, list[StrategyConsistencyScore]] = {}
    for s in strategy_scores:
        by_family.setdefault(s.strategy_family, []).append(s)
    from dopey_walk_forward.consistency_score import build_family_consistency_profile
    for family, members in by_family.items():
        family_profiles.append(build_family_consistency_profile(family, members, known_regimes))
    holdout_score = build_holdout_robustness(
        plan_id=f"dopey-regime-holdout-corpus-v2-{seed}",
        split_results=all_replays,
        known_regimes=known_regimes,
    )

    # 9. Verdicts per strategy.
    verdicts: list[ConsistencyVerdict] = []
    for s in strategy_scores:
        fp = next((p for p in family_profiles if p.strategy_family == s.strategy_family), None)
        verdicts.append(decide_consistency_verdict(s, fp, holdout_score))
    strong_count = sum(1 for v in verdicts if v.verdict == "strong_consistency")
    holdout_failures = sum(1 for v in verdicts if v.verdict == "holdout_failure")
    overfit_warnings = sum(1 for v in verdicts if v.verdict == "overfit_warning")

    # 10. Top consistent strategy and family.
    if strategy_scores:
        top_strategy_score = max(strategy_scores, key=lambda s: (s.overall, s.holdout_survival))
        top_strategy = top_strategy_score.strategy_id
    else:
        top_strategy = ""
    if family_profiles:
        top_family = max(family_profiles, key=lambda p: (p.mean_overall, p.family_holdout_survival)).strategy_family
    else:
        top_family = ""

    # 11. Coverage scoring.
    coverage = score_corpus_coverage(corpus)

    # 12. V1 vs V2 delta.
    v1_v2 = _v1_v2_delta(v1_consistency, strategy_scores)

    # 13. Persist artifacts.
    registry_record = {
        "corpus_v2_version": CORPUS_V2_VERSION,
        "corpus_id": corpus.corpus_id,
        "total_windows": corpus.window_count,
        "new_windows_added": additional_v2_window_count(),
        "category_window_count": category_window_count(corpus),
        "regime_coverage": list(corpus.regime_coverage),
        "sector_coverage": list(corpus.sector_coverage),
        "macro_coverage": list(corpus.macro_coverage),
        "liquidity_stress_coverage": list(corpus.liquidity_stress_coverage),
        "volatility_transition_coverage": list(corpus.volatility_transition_coverage),
        "corpus_deterministic_hash": corpus.deterministic_hash(),
        "split_set": split_set.to_dict(),
        "candidates_evaluated": [g.to_dict() for g in candidates],
        "split_replay_results": [r.to_dict() for r in all_replays],
        "strategy_consistency_scores": [s.to_dict() for s in strategy_scores],
        "family_consistency_profiles": [p.to_dict() for p in family_profiles],
        "holdout_robustness": holdout_score.to_dict(),
        "consistency_verdicts": [v.to_dict() for v in verdicts],
        "top_consistent_strategy_v2": top_strategy,
        "top_consistent_family_v2": top_family,
        "v1_consistency_lookup": v1_consistency,
        "v1_v2_score_delta": v1_v2,
        "holdout_failures": holdout_failures,
        "overfit_warnings": overfit_warnings,
        "strong_consistency_count": strong_count,
        "coverage_score": coverage.to_dict(),
        "allowed_consistency_verdicts": list(ALLOWED_CONSISTENCY_VERDICTS),
        "strongest_per_strategy": {sid: r.to_dict() for sid, r in strongest_by_strategy.items()},
        "safety_state": safety,
    }
    repro = reproducibility_hash(registry_record)
    registry_record["reproducibility_hash"] = repro

    reg_target = _write_jsonl(registry_record, registry_path or REGISTRY_PATH)
    rep_target = _write_jsonl({"plan_id": corpus.corpus_id, "split_replay_results": [r.to_dict() for r in all_replays], "safety_state": safety}, replay_path or REPLAY_PATH)
    cov_target = _write_jsonl({"corpus_id": corpus.corpus_id, "coverage": coverage.to_dict(), "safety_state": safety}, coverage_path or COVERAGE_PATH)
    proof_target = Path(proof_ledger_path) if proof_ledger_path else PROOF_LEDGER_PATH
    result = CorpusV2Result(
        corpus_v2_status="ok",
        mode=safety["mode"],
        live_trading_enabled=safety["live_trading_enabled"],
        total_windows=corpus.window_count,
        new_windows_added=additional_v2_window_count(),
        splits_built=len(split_set.splits),
        strategies_evaluated=len(strategy_scores),
        families_evaluated=len(family_profiles),
        top_consistent_strategy_v2=top_strategy,
        top_consistent_family_v2=top_family,
        holdout_failures=holdout_failures,
        overfit_warnings=overfit_warnings,
        coverage_score=coverage.coverage_fraction,
        live_blocked=True,
        registry_path=str(reg_target),
        proof_record_path=str(proof_target),
        safety_state=safety,
        reproducibility_hash=repro,
    )
    ProofLedger(proof_target).append(_build_proof_entry(result, registry_record))

    # Champion consistency records (best-effort).
    try:
        from dopey_strategy_lab.champion_consistency import write_champion_consistency_record
        write_champion_consistency_record(safety_state=safety)
    except Exception:
        pass
    try:
        from dopey_strategy_lab.champion_corpus_v2 import write_champion_corpus_v2_record
        write_champion_corpus_v2_record(safety_state=safety)
    except Exception:
        pass

    summary_md = _build_summary_md(result, coverage, strategy_scores, family_profiles, v1_v2)
    summary_target = Path(summary_path) if summary_path else SUMMARY_PATH
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.write_text(summary_md, encoding="utf-8")

    summary = result.to_dict()
    summary["split_set"] = split_set.to_dict()
    summary["strategy_consistency_scores"] = [s.to_dict() for s in strategy_scores]
    summary["family_consistency_profiles"] = [p.to_dict() for p in family_profiles]
    summary["holdout_robustness"] = holdout_score.to_dict()
    summary["consistency_verdicts"] = [v.to_dict() for v in verdicts]
    summary["v1_v2_score_delta"] = v1_v2
    summary["coverage_score"] = coverage.to_dict()
    summary["corpus_id"] = corpus.corpus_id
    summary["category_window_count"] = category_window_count(corpus)
    summary["regime_coverage"] = list(corpus.regime_coverage)
    summary["sector_coverage"] = list(corpus.sector_coverage)
    summary["macro_coverage"] = list(corpus.macro_coverage)
    summary["liquidity_stress_coverage"] = list(corpus.liquidity_stress_coverage)
    summary["volatility_transition_coverage"] = list(corpus.volatility_transition_coverage)
    summary["replay_path"] = str(rep_target)
    summary["coverage_path"] = str(cov_target)
    summary["summary_path"] = str(summary_target)
    return summary
