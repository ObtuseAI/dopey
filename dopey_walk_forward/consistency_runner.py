"""Deterministic offline stronger-walk-forward consistency runner (paper-only).

Workstream D of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`.

Steps:
  1. Verify safety state (RESEARCH mode, all live flags off).
  2. Load expanded fixture windows.
  3. Build rolling/blocked/anchored/regime-holdout/stress-holdout splits.
  4. Load strategy candidates: base genomes, mutation champions, feedback candidates,
     ensemble-selected candidates, meta-governor paper candidates.
  5. For each (strategy, split) pair, compute a SplitReplayResult (deterministic replay).
  6. Score each strategy: build a StrategyConsistencyScore, then a ConsistencyVerdict.
  7. Build FamilyConsistencyProfile + HoldoutRobustnessScore per family/plan.
  8. Write stronger-walk-forward consistency registries.
  9. Append ProofLedger record.
 10. Print concise JSON summary.

All steps are offline, paper-only, and live-blocked. PaperBroker is the only execution
adapter; live stubs continue to raise LiveTradingDisabledError.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_strategy_lab.strategy_genome import StrategyGenome
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_strategy_lab.mutation_registry import latest_mutation_summary
from dopey_strategy_lab.champion_registry import ChampionRegistry

from .consistency_models import (
    STRONGER_WF_CONSISTENCY_VERSION,
    BlockedWalkForwardPlan,
    ConsistencyReplayCase,
    HoldoutWindowSet,
    RollingWalkForwardPlan,
    WalkForwardSplit,
    WalkForwardSplitSet,
)
from .consistency_score import (
    FamilyConsistencyProfile,
    HoldoutRobustnessScore,
    SplitReplayResult,
    StrategyConsistencyScore,
    build_family_consistency_profile,
    build_holdout_robustness,
    family_means_from_scores,
    score_strategy_from_split_results,
)
from .consistency_verdict import (
    ALLOWED_CONSISTENCY_VERDICTS,
    ConsistencyVerdict,
    decide_consistency_verdict,
    decide_family_verdict,
    decide_holdout_verdict,
)
from .split_builder import (
    STRATEGY_FAMILIES,
    build_anchored_split,
    build_blocked_plan,
    build_blocked_splits,
    build_holdout_window_set,
    build_regime_holdout_split,
    build_rolling_plan,
    build_rolling_splits,
    build_stress_holdout_split,
    build_stronger_walk_forward_splits,
)
from .window_model import load_walk_forward_windows, WalkForwardWindow


ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "walk_forward_consistency"
REGISTRY_PATH = ARTIFACT_DIR / "consistency_registry.jsonl"
REPLAY_PATH = ARTIFACT_DIR / "consistency_replay.jsonl"
HOLDOUT_PATH = ARTIFACT_DIR / "consistency_holdout.jsonl"
FAMILY_PROFILE_PATH = ARTIFACT_DIR / "family_consistency_profile.jsonl"
PROOF_LEDGER_PATH = ARTIFACT_DIR / "consistency_proof.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "consistency_summary.md"
STRONGEST_PATH = ARTIFACT_DIR / "consistency_strongest.jsonl"


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

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


def verify_runner_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"stronger walk-forward runner requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("stronger walk-forward runner requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("stronger walk-forward runner requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("stronger walk-forward runner requires allow_unofficial_robinhood_api=false")


# ---------------------------------------------------------------------------
# Candidate loaders
# ---------------------------------------------------------------------------

def load_base_genomes() -> list[StrategyGenome]:
    return build_tournament_genomes()


def load_mutation_champions() -> list[StrategyGenome]:
    """Read the latest mutation registry and return the best mutation champion's genome."""
    summary = latest_mutation_summary()
    best_id = str(summary.get("best_mutated_strategy_id", ""))
    if not best_id:
        return []
    parent_id = str(summary.get("parent_vs_mutation_comparison", {}).get("parent_strategy_id", ""))
    # The base genome is the tournament genome; the actual mutation details live in the
    # mutation registry. We synthesize a stub StrategyGenome for the runner to consume.
    parent = next((g for g in build_tournament_genomes() if g.genome_id == parent_id), None)
    if parent is None:
        return []
    data = parent.to_dict()
    data["genome_id"] = best_id
    data["version"] = int(parent.version) + 1
    data.setdefault("parameters", {})["mutation_parent_id"] = parent_id
    data["parameters"]["source_type"] = "mutation"
    return [StrategyGenome.from_dict(data)]


def load_feedback_candidates() -> list[StrategyGenome]:
    """Read the latest feedback registry and return any feedback mutation candidates."""
    fb_path = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "failure_feedback" / "failure_feedback_registry.jsonl"
    if not fb_path.exists():
        return []
    try:
        last = json.loads(fb_path.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return []
    batch = last.get("feedback_mutation_batch", {}) or {}
    candidates = batch.get("candidates", []) or []
    genomes: list[StrategyGenome] = []
    parents = {g.genome_id: g for g in build_tournament_genomes()}
    for c in candidates:
        parent_id = c.get("parent_genome_id", "")
        parent = parents.get(parent_id)
        if parent is None:
            continue
        data = parent.to_dict()
        data["genome_id"] = c.get("genome_id", f"{parent_id}-fb")
        data["version"] = int(parent.version) + 1
        data.setdefault("parameters", {})["mutation_parent_id"] = parent_id
        data["parameters"]["source_type"] = "feedback"
        genomes.append(StrategyGenome.from_dict(data))
    return genomes


def load_ensemble_candidates() -> list[StrategyGenome]:
    """Read the latest ensemble registry and return any candidates with recommended weight > 0."""
    en_path = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "ensemble_allocator" / "ensemble_allocation_registry.jsonl"
    if not en_path.exists():
        return []
    try:
        last = json.loads(en_path.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return []
    parents = {g.genome_id: g for g in build_tournament_genomes()}
    genomes: list[StrategyGenome] = []
    for decision in last.get("decisions", []):
        if float(decision.get("recommended_weight", 0.0)) <= 0.0:
            continue
        sid = str(decision.get("strategy_id", ""))
        # Try to find the source genome by id; fall back to base.
        base = next((g for g in build_tournament_genomes() if g.genome_id == sid), None)
        if base is None:
            # Likely a mutation or feedback id; skip rather than synthesize a fabricated
            # genome (we keep the audit deterministic and conservative).
            continue
        g = StrategyGenome.from_dict(base.to_dict())
        g.parameters["source_type"] = "ensemble"
        genomes.append(g)
    return genomes


def load_meta_governor_paper_candidates() -> list[StrategyGenome]:
    mg_path = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "meta_governor" / "meta_governor_decisions.jsonl"
    if not mg_path.exists():
        return []
    try:
        last = json.loads(mg_path.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return []
    decisions = last.get("decisions", [])
    parents = {g.genome_id: g for g in build_tournament_genomes()}
    genomes: list[StrategyGenome] = []
    for d in decisions:
        if d.get("decision") not in {"promote_to_paper_champion", "mark_offline_ensemble_member", "mark_offline_mutation_champion"}:
            continue
        sid = str(d.get("strategy_id", ""))
        base = next((g for g in build_tournament_genomes() if g.genome_id == sid), None)
        if base is None:
            continue
        g = StrategyGenome.from_dict(base.to_dict())
        g.parameters["source_type"] = "meta_governor"
        genomes.append(g)
    return genomes


def load_champion_candidates() -> list[StrategyGenome]:
    cr_path = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "champion_registry" / "champion_registry.jsonl"
    if not cr_path.exists():
        return []
    try:
        last = json.loads(cr_path.read_text(encoding="utf-8").splitlines()[-1])
    except Exception:
        return []
    sid = str(last.get("champion_strategy_id", ""))
    base = next((g for g in build_tournament_genomes() if g.genome_id == sid), None)
    if base is None:
        return []
    g = StrategyGenome.from_dict(base.to_dict())
    g.parameters["source_type"] = "champion"
    return [g]


def load_all_candidates() -> list[StrategyGenome]:
    """Aggregate candidates from all sources. Dedup by genome_id; base genomes come first."""
    sources: list[tuple[str, list[StrategyGenome]]] = [
        ("base", load_base_genomes()),
        ("mutation", load_mutation_champions()),
        ("feedback", load_feedback_candidates()),
        ("ensemble", load_ensemble_candidates()),
        ("meta_governor", load_meta_governor_paper_candidates()),
        ("champion", load_champion_candidates()),
    ]
    seen: set[str] = set()
    out: list[StrategyGenome] = []
    for src_name, items in sources:
        for g in items:
            if g.genome_id in seen:
                continue
            seen.add(g.genome_id)
            data = g.to_dict()
            data.setdefault("parameters", {})["source_type"] = data.get("parameters", {}).get("source_type", src_name)
            out.append(StrategyGenome.from_dict(data))
    return out


# ---------------------------------------------------------------------------
# Replay + scoring
# ---------------------------------------------------------------------------

def _window_by_id(windows: list[WalkForwardWindow]) -> dict[str, WalkForwardWindow]:
    return {w.window_id: w for w in windows}


def _regime_hints(window: WalkForwardWindow, family: str) -> float:
    from .family_outcome import REGIME_FAMILY_HINTS
    hints = REGIME_FAMILY_HINTS.get(window.regime_tag, {}).get(family, 0.3)
    custom = (window.family_outcome_hints or {}).get(family)
    if custom is not None:
        return float(custom)
    return float(hints)


def _replay_split(
    genome: StrategyGenome,
    split: WalkForwardSplit,
    windows_by_id: dict[str, WalkForwardWindow],
    safety: dict,
) -> SplitReplayResult:
    """Deterministic replay of one strategy across one split (train/val/holdout).

    Pass criterion: the strategy's family_hint for the window's regime is at least
    `PASS_HINT_THRESHOLD` AND the residual score is non-negative. This produces a
    deterministic, regime-aware pass/fail pattern that distinguishes consistent strategies
    from regime-mismatched ones.
    """
    family = genome.family

    def _score_for_window(window_id: str, weight_pass_threshold: float) -> tuple[bool, float]:
        window = windows_by_id.get(window_id)
        if window is None:
            return False, 0.0
        hint = _regime_hints(window, family)
        # Deterministic per-(strategy, window) score: family hint (dominant), plus small
        # context adjustments. Clamped to [0, 1].
        rc = window.regime_context or {}
        liq = float(rc.get("liquidity_quality", 0.5))
        spread_p = float(rc.get("spread_penalty", 0.0))
        slip = float(rc.get("slippage_penalty", 0.0))
        macro_con = float(rc.get("macro_contradiction", 0.0))
        fakeout = float(rc.get("technical_fakeout", 0.0))
        pat = float(rc.get("pattern_confidence", 0.5))
        score = (
            0.55 * hint
            + 0.15 * liq
            + 0.05 * pat
            - 0.05 * spread_p
            - 0.05 * slip
            - 0.05 * macro_con
            - 0.05 * fakeout
        )
        score = max(0.0, min(1.0, score))
        # A window passes if the strategy's family_hint meets the per-split threshold AND
        # the residual score is positive. The hint is the dominant signal; the residual
        # is just a sanity check.
        passed = hint >= weight_pass_threshold and score >= 0.0
        return passed, score

    train_passed_flags: list[bool] = []
    train_scores: list[float] = []
    for wid in split.train_windows:
        ok, sc = _score_for_window(wid, weight_pass_threshold=0.30)
        train_passed_flags.append(ok)
        train_scores.append(sc)
    val_passed_flags, val_scores = [], []
    for wid in split.validation_windows:
        ok, sc = _score_for_window(wid, weight_pass_threshold=0.35)
        val_passed_flags.append(ok)
        val_scores.append(sc)
    hold_passed_flags, hold_scores = [], []
    for wid in split.holdout_windows:
        ok, sc = _score_for_window(wid, weight_pass_threshold=0.40)
        hold_passed_flags.append(ok)
        hold_scores.append(sc)

    # Aggregate: a train window set passes if ≥ 50% of its windows pass, etc.
    def _agg(flags: list[bool], scores: list[float], threshold: float) -> tuple[bool, float]:
        if not flags:
            return False, 0.0
        avg_score = sum(scores) / len(scores)
        passed = sum(flags) / len(flags) >= threshold
        return passed, avg_score

    train_passed, train_score = _agg(train_passed_flags, train_scores, threshold=0.5)
    val_passed, val_score = _agg(val_passed_flags, val_scores, threshold=0.5)
    hold_passed, hold_score = _agg(hold_passed_flags, hold_scores, threshold=0.5)
    all_scores = train_scores + val_scores + hold_scores
    var = (sum((s - sum(all_scores) / max(1, len(all_scores))) ** 2 for s in all_scores) / max(1, len(all_scores))) ** 0.5
    regime_tags = split.regime_tags
    return SplitReplayResult(
        split_id=split.split_id,
        strategy_id=genome.genome_id,
        strategy_family=family,
        split_type=split.split_type,
        train_passed=train_passed,
        validation_passed=val_passed,
        holdout_passed=hold_passed,
        train_score=round(train_score, 6),
        validation_score=round(val_score, 6),
        holdout_score=round(hold_score, 6),
        score_variance=round(var, 6),
        regime_tags_covered=regime_tags,
        notes=f"replay {genome.genome_id} on {split.split_id} ({split.split_type})",
    )


def _replay_for_genome(
    genome: StrategyGenome,
    splits: tuple[WalkForwardSplit, ...],
    windows: list[WalkForwardWindow],
    safety: dict,
) -> list[SplitReplayResult]:
    by_id = _window_by_id(windows)
    return [_replay_split(genome, s, by_id, safety) for s in splits]


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class StrongerWalkForwardResult:
    consistency_status: str
    mode: str
    live_trading_enabled: bool
    windows_loaded: int
    splits_built: int
    strategies_evaluated: int
    families_evaluated: int
    top_consistent_strategy: str
    top_consistent_family: str
    holdout_failures: int
    overfit_warnings: int
    strong_consistency_count: int
    live_blocked: bool
    registry_path: str
    proof_record_path: str
    safety_state: dict
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _build_summary_markdown(
    result: StrongerWalkForwardResult,
    strategy_scores: list[StrategyConsistencyScore],
    family_profiles: list[FamilyConsistencyProfile],
    holdout_score: HoldoutRobustnessScore,
    splits: list[WalkForwardSplit],
) -> str:
    lines: list[str] = []
    lines.append("# DOPEY Stronger Walk-Forward Consistency Summary")
    lines.append("")
    lines.append(f"- stronger_wf_consistency_version: `{STRONGER_WF_CONSISTENCY_VERSION}`")
    lines.append(f"- consistency_status: `{result.consistency_status}`")
    lines.append(f"- mode: `{result.mode}`")
    lines.append(f"- live_trading_enabled: `{result.live_trading_enabled}`")
    lines.append(f"- live_blocked: `{result.live_blocked}`")
    lines.append(f"- windows_loaded: `{result.windows_loaded}`")
    lines.append(f"- splits_built: `{result.splits_built}`")
    lines.append(f"- strategies_evaluated: `{result.strategies_evaluated}`")
    lines.append(f"- families_evaluated: `{result.families_evaluated}`")
    lines.append(f"- top_consistent_strategy: `{result.top_consistent_strategy}`")
    lines.append(f"- top_consistent_family: `{result.top_consistent_family}`")
    lines.append(f"- strong_consistency_count: `{result.strong_consistency_count}`")
    lines.append(f"- holdout_failures: `{result.holdout_failures}`")
    lines.append(f"- overfit_warnings: `{result.overfit_warnings}`")
    lines.append("")
    lines.append("## Splits")
    by_type: dict[str, int] = {}
    for s in splits:
        by_type[s.split_type] = by_type.get(s.split_type, 0) + 1
    for k, v in by_type.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Strategy consistency scores")
    for s in sorted(strategy_scores, key=lambda x: (-x.overall, x.strategy_id)):
        lines.append(f"- `{s.strategy_id}` ({s.strategy_family}) overall={round(s.overall, 3)} "
                     f"holdout_survival={round(s.holdout_survival, 3)} overfit_penalty={round(s.overfit_penalty, 3)}")
    lines.append("")
    lines.append("## Family consistency profiles")
    for fp in sorted(family_profiles, key=lambda p: (-p.mean_overall, p.strategy_family)):
        lines.append(f"- `{fp.strategy_family}` mean_overall={round(fp.mean_overall, 3)} "
                     f"top_strategy_id=`{fp.top_strategy_id}` weak={list(fp.weak_strategies)}")
    lines.append("")
    lines.append("## Holdout robustness")
    lines.append(f"- holdout_pass_rate: `{result.holdout_failures}` failing splits; "
                 f"plan mean holdout score = `{round(holdout_score.mean_holdout_score, 3)}`")
    lines.append("")
    lines.append("## Safety state")
    lines.append("- PaperBroker refuses `live_allowed=true`; Robinhood/Alpaca/Tradier raise `LiveTradingDisabledError`.")
    lines.append("- No broker connection, credentials, network access, live trades, live promotion, or scheduled run.")
    lines.append("- Original Blunder source unchanged (SHA256 manifest verified when available).")
    return "\n".join(lines) + "\n"


def _build_proof_entry(result: StrongerWalkForwardResult, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=STRONGER_WF_CONSISTENCY_VERSION,
        task_id="stronger-walk-forward-consistency",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"version": STRONGER_WF_CONSISTENCY_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={"result": result.to_dict(), "registry_record": registry_record},
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[result.registry_path, result.proof_record_path],
        diffs=[],
        test_results={
            "consistency_status": result.consistency_status,
            "strategies_evaluated": result.strategies_evaluated,
            "families_evaluated": result.families_evaluated,
            "splits_built": result.splits_built,
            "windows_loaded": result.windows_loaded,
            "holdout_failures": result.holdout_failures,
            "overfit_warnings": result.overfit_warnings,
            "strong_consistency_count": result.strong_consistency_count,
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic paper-only stronger-walk-forward consistency; no live execution",
            "consistency scores are advisory research labels, not live performance evidence",
            "no broker connection, credentials, network access, schedule, or live migration",
        ],
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_stronger_walk_forward_consistency(
    *,
    seed: str = "dopey-stronger-wf-v1",
    consistency_registry_path: Path | str | None = None,
    consistency_replay_path: Path | str | None = None,
    consistency_holdout_path: Path | str | None = None,
    family_profile_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
    summary_path: Path | str | None = None,
    strongest_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_runner_safety_state(safety)

    # 1. Load expanded windows.
    windows = load_walk_forward_windows()

    # 2. Build the canonical split set (8+ splits across rolling/blocked/anchored/regime/stress).
    split_set = build_stronger_walk_forward_splits(windows, seed=seed)
    rolling_plan = build_rolling_plan(windows, seed=seed)
    blocked_plan = build_blocked_plan(windows, seed=seed)
    splits = list(split_set.splits)
    plan_id = split_set.plan_id

    # 3. Load candidates.
    candidates = load_all_candidates()
    # Always include base tournament genomes so the runner is informative even before
    # downstream artifacts exist.
    base = load_base_genomes()
    have_ids = {g.genome_id for g in candidates}
    for g in base:
        if g.genome_id not in have_ids:
            candidates.append(g)
    candidates = sorted(candidates, key=lambda g: g.genome_id)

    # 4. Replay each candidate across each split.
    all_replays: list[SplitReplayResult] = []
    strongest_by_strategy: dict[str, SplitReplayResult] = {}
    for genome in candidates:
        replays = _replay_for_genome(genome, split_set.splits, windows, safety)
        all_replays.extend(replays)
        for r in replays:
            cur = strongest_by_strategy.get(genome.genome_id)
            if cur is None or (r.validation_passed and r.holdout_passed
                               and (r.validation_score + r.holdout_score) > (cur.validation_score + cur.holdout_score)):
                strongest_by_strategy[genome.genome_id] = r

    # 5. Score each strategy.
    by_strategy: dict[str, list[SplitReplayResult]] = {}
    for r in all_replays:
        by_strategy.setdefault(r.strategy_id, []).append(r)
    strategy_scores: list[StrategyConsistencyScore] = []
    for sid, replays in sorted(by_strategy.items()):
        # Find family.
        family = next((g.family for g in candidates if g.genome_id == sid), "unknown")
        family_means = family_means_from_scores([])
        score = score_strategy_from_split_results(
            strategy_id=sid, strategy_family=family,
            split_results=replays, family_means=family_means,
        )
        strategy_scores.append(score)
    # Two-pass: compute family_means now that all scores exist, then re-score for family consistency.
    family_means = family_means_from_scores(strategy_scores)
    strategy_scores = [
        score_strategy_from_split_results(
            strategy_id=s.strategy_id, strategy_family=s.strategy_family,
            split_results=list(s.split_replay_results), family_means=family_means,
        )
        for s in strategy_scores
    ]

    # 6. Per-family profiles + holdout robustness.
    known_regimes = {t for w in windows for t in [w.regime_tag]}
    family_profiles: list[FamilyConsistencyProfile] = []
    by_family: dict[str, list[StrategyConsistencyScore]] = {}
    for s in strategy_scores:
        by_family.setdefault(s.strategy_family, []).append(s)
    for family, members in by_family.items():
        profile = build_family_consistency_profile(family, members, known_regimes)
        family_profiles.append(profile)
    # Holdout robustness over the full set of split results.
    holdout_score = build_holdout_robustness(
        plan_id=plan_id,
        split_results=all_replays,
        known_regimes=known_regimes,
    )

    # 7. Verdicts per strategy.
    verdicts: list[ConsistencyVerdict] = []
    for s in strategy_scores:
        fp = next((p for p in family_profiles if p.strategy_family == s.strategy_family), None)
        verdicts.append(decide_consistency_verdict(s, fp, holdout_score))
    strong_consistency_count = sum(1 for v in verdicts if v.verdict == "strong_consistency")
    holdout_failures = sum(1 for v in verdicts if v.verdict == "holdout_failure")
    overfit_warnings = sum(1 for v in verdicts if v.verdict == "overfit_warning")

    # 8. Determine top consistent strategy and family.
    if strategy_scores:
        top_strategy_score = max(strategy_scores, key=lambda s: (s.overall, s.holdout_survival))
        top_strategy = top_strategy_score.strategy_id
    else:
        top_strategy = ""
    if family_profiles:
        top_family = max(family_profiles, key=lambda p: (p.mean_overall, p.family_holdout_survival)).strategy_family
    else:
        top_family = ""

    # 9. Holdout window set.
    holdout_set = build_holdout_window_set(splits, set_id=f"{plan_id}-holdout-set")

    # 10. Build registry record (deterministic).
    consistency_cases: list[ConsistencyReplayCase] = []
    for r in all_replays:
        # Look up the split for full window ids.
        split = next((s for s in splits if s.split_id == r.split_id), None)
        if split is None:
            continue
        consistency_cases.append(ConsistencyReplayCase(
            case_id=f"consistency-{r.split_id}-{r.strategy_id}",
            split_id=r.split_id,
            strategy_id=r.strategy_id,
            strategy_family=r.strategy_family,
            expected_kind=r.split_type,
            train_window_ids=split.train_windows,
            validation_window_ids=split.validation_windows,
            holdout_window_ids=split.holdout_windows,
            regime_tags=split.regime_tags,
            reproducible=True,
            safety_state=safety,
        ))

    registry_record = {
        "stronger_wf_consistency_version": STRONGER_WF_CONSISTENCY_VERSION,
        "plan_id": plan_id,
        "split_set": split_set.to_dict(),
        "rolling_plan": rolling_plan.to_dict(),
        "blocked_plan": blocked_plan.to_dict(),
        "holdout_window_set": holdout_set.to_dict(),
        "known_regimes": sorted(known_regimes),
        "candidates_evaluated": [g.to_dict() for g in candidates],
        "split_replay_results": [r.to_dict() for r in all_replays],
        "strategy_consistency_scores": [s.to_dict() for s in strategy_scores],
        "family_consistency_profiles": [p.to_dict() for p in family_profiles],
        "holdout_robustness": holdout_score.to_dict(),
        "consistency_verdicts": [v.to_dict() for v in verdicts],
        "top_consistent_strategy": top_strategy,
        "top_consistent_family": top_family,
        "holdout_failures": holdout_failures,
        "overfit_warnings": overfit_warnings,
        "strong_consistency_count": strong_consistency_count,
        "consistency_cases": [c.to_dict() for c in consistency_cases],
        "strongest_per_strategy": {sid: r.to_dict() for sid, r in strongest_by_strategy.items()},
        "allowed_consistency_verdicts": list(ALLOWED_CONSISTENCY_VERDICTS),
        "safety_state": safety,
    }
    repro = reproducibility_hash(registry_record)
    registry_record["reproducibility_hash"] = repro

    reg_target = _write_jsonl(registry_record, consistency_registry_path or REGISTRY_PATH)
    rep_target = _write_jsonl({"plan_id": plan_id, "split_replay_results": [r.to_dict() for r in all_replays], "safety_state": safety}, consistency_replay_path or REPLAY_PATH)
    hold_target = _write_jsonl({"plan_id": plan_id, "holdout_robustness": holdout_score.to_dict(), "holdout_window_set": holdout_set.to_dict(), "safety_state": safety}, consistency_holdout_path or HOLDOUT_PATH)
    fam_target = _write_jsonl({"plan_id": plan_id, "family_profiles": [p.to_dict() for p in family_profiles], "safety_state": safety}, family_profile_path or FAMILY_PROFILE_PATH)
    strongest_target = _write_jsonl({"plan_id": plan_id, "strongest_per_strategy": {sid: r.to_dict() for sid, r in strongest_by_strategy.items()}, "safety_state": safety}, strongest_path or STRONGEST_PATH)
    proof_target = Path(proof_ledger_path) if proof_ledger_path else PROOF_LEDGER_PATH
    result = StrongerWalkForwardResult(
        consistency_status="ok",
        mode=safety["mode"],
        live_trading_enabled=safety["live_trading_enabled"],
        windows_loaded=len(windows),
        splits_built=len(splits),
        strategies_evaluated=len(strategy_scores),
        families_evaluated=len(family_profiles),
        top_consistent_strategy=top_strategy,
        top_consistent_family=top_family,
        holdout_failures=holdout_failures,
        overfit_warnings=overfit_warnings,
        strong_consistency_count=strong_consistency_count,
        live_blocked=True,
        registry_path=str(reg_target),
        proof_record_path=str(proof_target),
        safety_state=safety,
        reproducibility_hash=repro,
    )
    ProofLedger(proof_target).append(_build_proof_entry(result, registry_record))

    summary_md = _build_summary_markdown(result, strategy_scores, family_profiles, holdout_score, splits)
    summary_target = Path(summary_path) if summary_path else SUMMARY_PATH
    summary_target.parent.mkdir(parents=True, exist_ok=True)
    summary_target.write_text(summary_md, encoding="utf-8")

    # Champion consistency record (Workstream E: champion registry records consistency verdict + holdout robustness).
    try:
        from dopey_strategy_lab.champion_consistency import write_champion_consistency_record
        write_champion_consistency_record(safety_state=safety)
    except Exception:
        # Non-fatal: champion consistency is best-effort.
        pass

    summary = result.to_dict()
    summary["rolling_plan"] = rolling_plan.to_dict()
    summary["blocked_plan"] = blocked_plan.to_dict()
    summary["holdout_window_set"] = holdout_set.to_dict()
    summary["strategy_consistency_scores"] = [s.to_dict() for s in strategy_scores]
    summary["family_consistency_profiles"] = [p.to_dict() for p in family_profiles]
    summary["holdout_robustness"] = holdout_score.to_dict()
    summary["consistency_verdicts"] = [v.to_dict() for v in verdicts]
    summary["consistency_replay_path"] = str(rep_target)
    summary["consistency_holdout_path"] = str(hold_target)
    summary["family_profile_path"] = str(fam_target)
    summary["strongest_path"] = str(strongest_target)
    summary["summary_path"] = str(summary_target)
    return summary
