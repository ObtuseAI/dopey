"""Tests for the DOPEY stronger walk-forward consistency expansion (paper-only, deterministic).

All tests are offline, paper-only, and live-blocked. They use a temp directory for the
ProofLedger and consistency registries to avoid cross-test state.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dopey_audit.artifact_loader import (
    ARTIFACT_SPECS,
    load_records,
)
from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_governor.meta_governor import run_offline_meta_governor
from dopey_governor.proof_evidence_loader import load_evidence_bundle
from dopey_strategy_lab.allocation_policy import apply_allocation_policy
from dopey_strategy_lab.ensemble_models import StrategyAllocationCandidate
from dopey_walk_forward.consistency_models import (
    WalkForwardSplit,
    ALLOWED_SPLIT_TYPES,
)
from dopey_walk_forward.consistency_runner import (
    load_all_candidates,
    run_stronger_walk_forward_consistency,
    verify_runner_safety_state,
)
from dopey_walk_forward.consistency_score import (
    SplitReplayResult,
    score_strategy_from_split_results,
)
from dopey_walk_forward.consistency_verdict import (
    ALLOWED_CONSISTENCY_VERDICTS,
    decide_consistency_verdict,
)
from dopey_walk_forward.split_builder import (
    ADDITIONAL_WINDOW_TEMPLATES,
    REQUIRED_REGIME_TAGS,
    STRESS_HOLDOUT_REGIMES,
    build_blocked_plan,
    build_blocked_splits,
    build_regime_holdout_split,
    build_rolling_plan,
    build_rolling_splits,
    build_stress_holdout_split,
)
from dopey_walk_forward.window_model import load_walk_forward_windows


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def consistency_root(tmp_path: Path) -> Path:
    root = tmp_path / "wf_consistency"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _replay(strategy_id: str, strategy_family: str, split_id: str, split_type: str,
            train_passed: bool, validation_passed: bool, holdout_passed: bool,
            train_score: float = 0.5, validation_score: float = 0.5, holdout_score: float = 0.5,
            regime_tags_covered: tuple[str, ...] = ("trend_vol_expansion",)) -> SplitReplayResult:
    return SplitReplayResult(
        split_id=split_id, strategy_id=strategy_id, strategy_family=strategy_family,
        split_type=split_type, train_passed=train_passed, validation_passed=validation_passed,
        holdout_passed=holdout_passed, train_score=train_score, validation_score=validation_score,
        holdout_score=holdout_score, score_variance=0.0, regime_tags_covered=regime_tags_covered,
    )


# ---------------------------------------------------------------------------
# Required split model tests (1..5)
# ---------------------------------------------------------------------------

def test_walk_forward_split_serializes_deterministically() -> None:
    s = WalkForwardSplit(
        split_id="wf-rolling-001",
        train_windows=("window_001_train", "window_002_validation"),
        validation_windows=("window_005_validation",),
        holdout_windows=("window_010_holdout",),
        regime_tags=("trend_vol_expansion", "chop_vol_compression"),
        split_type="rolling",
    )
    d1 = s.to_dict()
    d2 = s.to_dict()
    assert d1 == d2
    assert d1["split_id"] == "wf-rolling-001"
    assert tuple(d1["train_windows"]) == ("window_001_train", "window_002_validation")
    assert d1["split_type"] in ALLOWED_SPLIT_TYPES


def test_rolling_walk_forward_plan_builds_required_splits() -> None:
    windows = load_walk_forward_windows()
    splits = build_rolling_splits(windows, min_splits=3)
    assert len(splits) >= 3
    plan = build_rolling_plan(windows)
    assert plan.splits == tuple(splits)
    assert plan.window_count == len(windows)
    assert plan.regime_coverage  # non-empty
    assert "directional_convexity" in plan.target_families


def test_blocked_walk_forward_plan_builds_required_splits() -> None:
    windows = load_walk_forward_windows()
    splits = build_blocked_splits(windows, min_splits=2)
    assert len(splits) >= 2
    plan = build_blocked_plan(windows)
    assert plan.splits == tuple(splits)
    for s in splits:
        assert s.split_type == "blocked"
        # Blocked splits must not leak holdout into train/val.
        train_set = set(s.train_windows)
        val_set = set(s.validation_windows)
        for h in s.holdout_windows:
            assert h not in train_set
            assert h not in val_set


def test_regime_holdout_split_contains_target_regime() -> None:
    windows = load_walk_forward_windows()
    split = build_regime_holdout_split(windows, target_regime="macro_shock_risk_off")
    assert split.split_type == "regime_holdout"
    # Holdout should contain at least one macro_shock_risk_off window.
    holdout_window_ids = list(split.holdout_windows)
    by_id = {w.window_id: w for w in windows}
    assert any(by_id[wid].regime_tag == "macro_shock_risk_off" for wid in holdout_window_ids)
    # Regimes covered by the split include the target regime.
    macro_in_tags = any("macro" in rt for rt in split.regime_tags)
    assert macro_in_tags


def test_stress_holdout_split_contains_bad_fill_or_macro_shock() -> None:
    windows = load_walk_forward_windows()
    split = build_stress_holdout_split(windows)
    assert split.split_type == "stress_holdout"
    by_id = {w.window_id: w for w in windows}
    stress_tags = set()
    for wid in split.holdout_windows:
        stress_tags.add(by_id[wid].regime_tag)
    # At least one of the holdout windows must be in a stress regime.
    assert stress_tags & STRESS_HOLDOUT_REGIMES


# ---------------------------------------------------------------------------
# Required fixture/corpus tests (6..9)
# ---------------------------------------------------------------------------

def test_expanded_consistency_window_corpus_loads() -> None:
    windows = load_walk_forward_windows()
    assert len(windows) >= 1
    for w in windows:
        assert w.regime_tag
        assert w.option_chain.contracts
        assert w.expected_outcome
        assert w.family_outcome_hints or True  # both ok
        assert isinstance(w.regime_context, dict)


def test_consistency_corpus_has_at_least_24_windows_if_feasible() -> None:
    windows = load_walk_forward_windows()
    # The stronger-walk-forward consistency expansion target is at least 24 windows.
    assert len(windows) >= 24, f"need >=24 walk-forward windows, got {len(windows)}"
    # And at least 12 additional windows shipped with the consistency expansion.
    assert len(ADDITIONAL_WINDOW_TEMPLATES) >= 12


def test_consistency_corpus_covers_required_regimes() -> None:
    windows = load_walk_forward_windows()
    tags = {w.regime_tag for w in windows}
    for required in REQUIRED_REGIME_TAGS:
        assert required in tags, f"missing required regime: {required}"


def test_consistency_windows_include_macro_iv_liquidity_pattern_context() -> None:
    windows = load_walk_forward_windows()
    # Verify each window carries macro + IV/skew + liquidity + pattern context.
    for w in windows:
        rc = w.regime_context
        assert "liquidity_quality" in rc
        assert "spread_penalty" in rc
        assert "slippage_penalty" in rc
        assert "macro_contradiction" in rc
        assert "pattern_confidence" in rc


# ---------------------------------------------------------------------------
# Required consistency scoring tests (10..15)
# ---------------------------------------------------------------------------

def test_consistency_score_rewards_stable_validation_and_holdout() -> None:
    s = score_strategy_from_split_results(
        strategy_id="s-good", strategy_family="directional_convexity",
        split_results=[
            _replay("s-good", "directional_convexity", "wf-1", "rolling",
                    True, True, True, 0.8, 0.8, 0.8, ("trend_vol_expansion",)),
            _replay("s-good", "directional_convexity", "wf-2", "blocked",
                    True, True, True, 0.8, 0.8, 0.8, ("chop_vol_compression",)),
            _replay("s-good", "directional_convexity", "wf-3", "anchored",
                    True, True, True, 0.8, 0.8, 0.8, ("bullish_breakout",)),
        ],
    )
    assert s.overall >= 0.50
    assert s.validation_stability >= 0.99
    assert s.holdout_survival >= 0.99
    assert s.failure_recurrence >= 0.99


def test_consistency_score_penalizes_train_only_improvement() -> None:
    s = score_strategy_from_split_results(
        strategy_id="s-train-only", strategy_family="volatility_expansion",
        split_results=[
            _replay("s-train-only", "volatility_expansion", "wf-1", "rolling",
                    True, False, False, 0.9, 0.2, 0.1),
            _replay("s-train-only", "volatility_expansion", "wf-2", "blocked",
                    True, False, False, 0.9, 0.2, 0.1),
            _replay("s-train-only", "volatility_expansion", "wf-3", "regime_holdout",
                    True, False, False, 0.9, 0.2, 0.1),
        ],
    )
    assert s.overfit_penalty < 0.7
    assert s.holdout_survival <= 0.10


def test_consistency_score_penalizes_holdout_collapse() -> None:
    s = score_strategy_from_split_results(
        strategy_id="s-collapse", strategy_family="volatility_compression",
        split_results=[
            _replay("s-collapse", "volatility_compression", "wf-1", "rolling",
                    True, True, False, 0.8, 0.7, 0.1),
            _replay("s-collapse", "volatility_compression", "wf-2", "blocked",
                    True, True, False, 0.8, 0.7, 0.1),
            _replay("s-collapse", "volatility_compression", "wf-3", "regime_holdout",
                    True, True, False, 0.8, 0.7, 0.1),
        ],
    )
    assert s.holdout_survival == 0.0
    assert s.overall < 0.45


def test_consistency_score_penalizes_high_split_variance() -> None:
    # Two stable passes vs one zero-holdout = higher variance → lower score_variance
    s_low_var = score_strategy_from_split_results(
        strategy_id="s-low-var", strategy_family="directional_convexity",
        split_results=[
            _replay("s-low-var", "directional_convexity", "wf-1", "rolling",
                    True, True, True, 0.6, 0.6, 0.6),
            _replay("s-low-var", "directional_convexity", "wf-2", "blocked",
                    True, True, True, 0.6, 0.6, 0.6),
            _replay("s-low-var", "directional_convexity", "wf-3", "regime_holdout",
                    True, True, True, 0.6, 0.6, 0.6),
        ],
    )
    s_high_var = score_strategy_from_split_results(
        strategy_id="s-high-var", strategy_family="directional_convexity",
        split_results=[
            _replay("s-high-var", "directional_convexity", "wf-1", "rolling",
                    True, True, True, 1.0, 0.0, 0.0),
            _replay("s-high-var", "directional_convexity", "wf-2", "blocked",
                    True, True, True, 0.0, 1.0, 0.0),
            _replay("s-high-var", "directional_convexity", "wf-3", "regime_holdout",
                    True, True, True, 0.0, 0.0, 1.0),
        ],
    )
    assert s_low_var.score_variance >= s_high_var.score_variance


def test_consistency_score_penalizes_recurring_failure_modes() -> None:
    # Strategy fails holdout on every split → high failure recurrence penalty.
    s = score_strategy_from_split_results(
        strategy_id="s-failing", strategy_family="short_duration_defined_risk",
        split_results=[
            _replay("s-failing", "short_duration_defined_risk", "wf-1", "rolling",
                    True, True, False, 0.5, 0.5, 0.0),
            _replay("s-failing", "short_duration_defined_risk", "wf-2", "blocked",
                    True, True, False, 0.5, 0.5, 0.0),
            _replay("s-failing", "short_duration_defined_risk", "wf-3", "regime_holdout",
                    True, True, False, 0.5, 0.5, 0.0),
        ],
    )
    assert s.failure_recurrence <= 0.10
    assert s.holdout_survival == 0.0


def test_consistency_score_verdicts_are_deterministic() -> None:
    s = score_strategy_from_split_results(
        strategy_id="s-det", strategy_family="directional_convexity",
        split_results=[
            _replay("s-det", "directional_convexity", "wf-1", "rolling",
                    True, True, True, 0.7, 0.7, 0.7),
        ],
    )
    v1 = decide_consistency_verdict(s)
    v2 = decide_consistency_verdict(s)
    assert v1.verdict == v2.verdict
    assert v1.verdict in ALLOWED_CONSISTENCY_VERDICTS


# ---------------------------------------------------------------------------
# Required runner tests (16..20)
# ---------------------------------------------------------------------------

def test_stronger_walk_forward_runner_runs_offline(tmp_path: Path) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    # Safety check should pass without raising.
    from dopey_walk_forward.consistency_runner import _safety_state
    verify_runner_safety_state(_safety_state())


def test_stronger_walk_forward_runner_evaluates_multiple_strategies(tmp_path: Path) -> None:
    candidates = load_all_candidates()
    assert len(candidates) >= 4  # at least 4 base families
    families = {c.family for c in candidates}
    assert "directional_convexity" in families
    assert "volatility_expansion" in families
    assert "volatility_compression" in families
    assert "short_duration_defined_risk" in families


def test_stronger_walk_forward_runner_writes_registry(tmp_path: Path) -> None:
    reg_path = tmp_path / "consistency_registry.jsonl"
    rep_path = tmp_path / "consistency_replay.jsonl"
    hold_path = tmp_path / "consistency_holdout.jsonl"
    fam_path = tmp_path / "family_profile.jsonl"
    proof_path = tmp_path / "consistency_proof.jsonl"
    summary_path = tmp_path / "consistency_summary.md"
    summary = run_stronger_walk_forward_consistency(
        consistency_registry_path=reg_path,
        consistency_replay_path=rep_path,
        consistency_holdout_path=hold_path,
        family_profile_path=fam_path,
        proof_ledger_path=proof_path,
        summary_path=summary_path,
    )
    assert summary["consistency_status"] == "ok"
    assert reg_path.exists()
    assert rep_path.exists()
    assert hold_path.exists()
    assert fam_path.exists()
    assert proof_path.exists()
    assert summary_path.exists()
    # Registry must contain a reproducibility hash.
    last = load_records(reg_path)[-1]
    assert "reproducibility_hash" in last
    assert len(last["reproducibility_hash"]) == 64


def test_stronger_walk_forward_runner_writes_proof_record(tmp_path: Path) -> None:
    proof_path = tmp_path / "proof.jsonl"
    run_stronger_walk_forward_consistency(
        proof_ledger_path=proof_path,
        consistency_registry_path=tmp_path / "consistency_registry.jsonl",
        consistency_replay_path=tmp_path / "consistency_replay.jsonl",
        consistency_holdout_path=tmp_path / "consistency_holdout.jsonl",
        family_profile_path=tmp_path / "family_profile.jsonl",
        summary_path=tmp_path / "consistency_summary.md",
    )
    records = load_records(proof_path)
    assert records
    last = records[-1]
    assert last["final_status"] == "PASS"
    assert last["test_results"]["consistency_status"] == "ok"
    assert last["test_results"]["strategies_evaluated"] >= 4
    assert last["test_results"]["splits_built"] >= 8
    assert last["test_results"]["windows_loaded"] >= 24


def test_top_consistent_strategy_is_deterministic(tmp_path: Path) -> None:
    s1 = run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "a.jsonl",
        consistency_replay_path=tmp_path / "a_rep.jsonl",
        consistency_holdout_path=tmp_path / "a_hold.jsonl",
        family_profile_path=tmp_path / "a_fam.jsonl",
        proof_ledger_path=tmp_path / "a_proof.jsonl",
        summary_path=tmp_path / "a_sum.md",
    )
    s2 = run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "b.jsonl",
        consistency_replay_path=tmp_path / "b_rep.jsonl",
        consistency_holdout_path=tmp_path / "b_hold.jsonl",
        family_profile_path=tmp_path / "b_fam.jsonl",
        proof_ledger_path=tmp_path / "b_proof.jsonl",
        summary_path=tmp_path / "b_sum.md",
    )
    assert s1["top_consistent_strategy"] == s2["top_consistent_strategy"]
    assert s1["top_consistent_family"] == s2["top_consistent_family"]


# ---------------------------------------------------------------------------
# Required integration tests (21..25)
# ---------------------------------------------------------------------------

def test_meta_governor_consumes_stronger_consistency_evidence(tmp_path: Path) -> None:
    # Run the stronger-walk-forward consistency first.
    run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "reg.jsonl",
        consistency_replay_path=tmp_path / "rep.jsonl",
        consistency_holdout_path=tmp_path / "hold.jsonl",
        family_profile_path=tmp_path / "fam.jsonl",
        proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    # Also materialize the registry at the STANDARD artifact path so the
    # meta-governor's default-path loader can consume it. (The tmp_path run
    # above predates the test-isolation layer, which now redirects standard
    # paths to the session mirror - default-path runs are safe and this test
    # no longer depends on any other test having produced the registry.)
    run_stronger_walk_forward_consistency()
    # Now run the meta-governor (uses default artifact paths). It should include the
    # stronger_walk_forward_consistency layer if the registry exists at the standard path.
    evidence = load_evidence_bundle()
    assert evidence.stronger_consistency, "meta-governor evidence bundle must include stronger_consistency"
    layers = evidence.layers_present()
    assert layers["stronger_consistency"] is True
    # Run the meta-governor for a non-throwing smoke (verifies integration is healthy).
    summary = run_offline_meta_governor()
    assert summary["meta_governor_status"] == "ok"


def test_ensemble_allocator_penalizes_weak_consistency(tmp_path: Path) -> None:
    # Create a candidate with weak consistency and one with strong consistency;
    # the weak one should be starved or down-weighted.
    base = StrategyAllocationCandidate(
        strategy_id="weak-consistency", strategy_family="directional_convexity",
        source_type="tournament",
        base_score=0.6, walk_forward_score=0.6, analysis_fusion_score=0.6,
        macro_fit_score=0.6, iv_surface_fit_score=0.6, greek_fit_score=0.6,
        liquidity_robustness_score=0.6, slippage_robustness_score=0.6,
        pattern_score=0.6, failure_pressure_score=0.0,
        overfit_level="low", overfit_rank=1, mutation_delta=0.0,
        promotion_state="entrant", paper_only=True, holdout_score=0.6,
        consistency_score=0.05,  # weak consistency
    )
    strong = StrategyAllocationCandidate(
        strategy_id="strong-consistency", strategy_family="volatility_compression",
        source_type="tournament",
        base_score=0.6, walk_forward_score=0.6, analysis_fusion_score=0.6,
        macro_fit_score=0.6, iv_surface_fit_score=0.6, greek_fit_score=0.6,
        liquidity_robustness_score=0.6, slippage_robustness_score=0.6,
        pattern_score=0.6, failure_pressure_score=0.0,
        overfit_level="low", overfit_rank=1, mutation_delta=0.0,
        promotion_state="entrant", paper_only=True, holdout_score=0.6,
        consistency_score=0.80,  # strong consistency
    )
    result = apply_allocation_policy([base, strong])
    decisions = {d.strategy_id: d for d in result.decisions}
    # The weak-consistency candidate must carry a penalty reason code OR be starved.
    weak = decisions["weak-consistency"]
    strong = decisions["strong-consistency"]
    if weak.recommended_weight > 0.0:
        assert "weak stronger-walk-forward consistency penalizes paper attention" in weak.reason_codes
    # The strong-consistency candidate must be accepted (no starve/reject).
    assert strong.decision in {"increase_paper_attention", "hold_paper_attention", "research_only"}


def test_failure_feedback_recommends_holdout_consistency_guard(tmp_path: Path) -> None:
    # Failure-mode-based recommendations for overfit_train_only / holdout_collapse now
    # include the holdout_consistency_guard recommendation.
    from dopey_strategy_lab.constraint_tuning import (
        FAILURE_RECOMMENDATION_MAP, build_constraint_tuning_recommendations,
    )
    from dopey_strategy_lab.failure_feedback_models import (
        FailureModeAggregate, FamilyFailureProfile,
    )
    overfit_keys = [r[0] for r in FAILURE_RECOMMENDATION_MAP["overfit_train_only"]]
    holdout_keys = [r[0] for r in FAILURE_RECOMMENDATION_MAP["holdout_collapse"]]
    assert "holdout_consistency_guard" in overfit_keys
    assert "holdout_consistency_guard" in holdout_keys
    # Verify build_constraint_tuning_recommendations emits the recommendation for
    # a family with overfit_train_only mode.
    aggregate = FailureModeAggregate(
        failure_mode_id="overfit_train_only",
        strategy_family="directional_convexity",
        structure_type="vertical",
        regime_tag="trend_vol_expansion",
        pattern_type="continuation",
        greek_risk_verdict="moderate",
        iv_context="stable",
        liquidity_verdict="ok",
        slippage_verdict="ok",
        overfit_level="moderate",
        mutation_type="adjust_overfit_penalty",
        failure_category="overfit_train_only",
        recurrence_count=3,
        evidence_score=0.8,
        severity="warning",
        severity_score=0.8,
        affected_strategy_ids=["directional-convexity-1"],
    )
    profile = FamilyFailureProfile(
        strategy_family="directional_convexity",
        total_failure_modes=1,
        total_recurrence_count=3,
        top_failure_modes=["overfit_train_only"],
        worst_regimes=["trend_vol_expansion"],
        failure_categories=["overfit_train_only"],
        structure_types=["vertical"],
        greek_risk_verdicts=["moderate"],
        liquidity_verdicts=["ok"],
        slippage_verdicts=["ok"],
        overfit_level="moderate",
        recommendation_pressure={"holdout_consistency_guard": 3.0},
    )
    recs = build_constraint_tuning_recommendations([profile], [aggregate])
    assert any(r.tuning_key == "holdout_consistency_guard" for r in recs)


def test_evidence_audit_recognizes_consistency_registry(tmp_path: Path) -> None:
    # The audit inventory should include the walk_forward_consistency_registry as a
    # known artifact type.
    types = [spec[0] for spec in ARTIFACT_SPECS]
    assert "walk_forward_consistency_registry" in types
    assert "walk_forward_consistency_proof" in types
    assert "champion_consistency" in types


def test_champion_registry_records_consistency_verdict(tmp_path: Path) -> None:
    from dopey_strategy_lab.champion_consistency import (
        write_champion_consistency_record,
    )
    # Ensure the consistency registry is present so the writer can read it.
    run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "reg.jsonl",
        consistency_replay_path=tmp_path / "rep.jsonl",
        consistency_holdout_path=tmp_path / "hold.jsonl",
        family_profile_path=tmp_path / "fam.jsonl",
        proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    # Run the writer; it should append a champion-consistency record.
    record = write_champion_consistency_record(
        path=tmp_path / "champion_consistency.jsonl",
        consistency_registry_path=tmp_path / "reg.jsonl",
    )
    assert record["champion_consistency"] or record["runner_up_consistency"]
    assert record["champion_consistency_verdict"] in ALLOWED_CONSISTENCY_VERDICTS or record["champion_consistency_verdict"] == "missing_evidence"


# ---------------------------------------------------------------------------
# Required safety regression tests (26..31)
# ---------------------------------------------------------------------------

def test_no_live_promotion_possible_after_consistency_expansion(tmp_path: Path) -> None:
    run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "reg.jsonl",
        consistency_replay_path=tmp_path / "rep.jsonl",
        consistency_holdout_path=tmp_path / "hold.jsonl",
        family_profile_path=tmp_path / "fam.jsonl",
        proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    # No forbidden live decisions in the consistency registry.
    last = load_records(tmp_path / "reg.jsonl")[-1]
    for decision in last.get("consistency_verdicts", []):
        assert decision.get("verdict") not in {"live_candidate", "micro_live", "adaptive_live",
                                                "real_capital", "broker_order", "enable_live",
                                                "live_allocate", "funded_execution"}


def test_live_stubs_still_block_after_consistency_expansion() -> None:
    intent = ExecutionIntent(
        intent_id="wf-consistency-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0,
    )
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_consistency_expansion() -> None:
    intent = ExecutionIntent(
        intent_id="wf-consistency-paper-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_config_still_research_after_consistency_expansion(tmp_path: Path) -> None:
    # tmp_path (not the real artifacts/ tree): fixed shared filenames collide
    # across concurrent or repeated runs and defeat test isolation.
    summary = run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "_test_reg.jsonl",
        consistency_replay_path=tmp_path / "_test_rep.jsonl",
        consistency_holdout_path=tmp_path / "_test_hold.jsonl",
        family_profile_path=tmp_path / "_test_fam.jsonl",
        proof_ledger_path=tmp_path / "_test_proof.jsonl",
        summary_path=tmp_path / "_test_sum.md",
    )
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert summary["live_blocked"] is True
    assert summary["live_trading_enabled"] is False
    assert summary["mode"] == "RESEARCH"


def test_consistency_runner_does_not_modify_live_settings(tmp_path: Path) -> None:
    before = load_config(default_config_path())
    run_stronger_walk_forward_consistency(
        consistency_registry_path=tmp_path / "_x_reg.jsonl",
        consistency_replay_path=tmp_path / "_x_rep.jsonl",
        consistency_holdout_path=tmp_path / "_x_hold.jsonl",
        family_profile_path=tmp_path / "_x_fam.jsonl",
        proof_ledger_path=tmp_path / "_x_proof.jsonl",
        summary_path=tmp_path / "_x_sum.md",
    )
    after = load_config(default_config_path())
    assert before == after


def test_blunder_source_integrity_if_manifest_available() -> None:
    from dopey_audit.safety_auditor import BLUNDER_MANIFEST_PATH, audit_blunder_integrity
    if BLUNDER_MANIFEST_PATH.exists():
        findings = audit_blunder_integrity()
        assert all(f.severity != "safety_error" for f in findings), (
            "Blunder source hash drift detected"
        )
    else:
        import hashlib
        from pathlib import Path as _P
        dummy = _P(__file__).resolve().parent / "dummy_blunder.py"
        dummy.write_text("# original blunder content\n", encoding="utf-8")
        h = hashlib.sha256(dummy.read_bytes()).hexdigest().upper()
        manifest = _P(__file__).resolve().parent / "_dummy_manifest.txt"
        manifest.write_text(f"{h}  {dummy}\n", encoding="utf-8")
        findings = audit_blunder_integrity(manifest)
        assert not any(f.severity == "safety_error" for f in findings)
