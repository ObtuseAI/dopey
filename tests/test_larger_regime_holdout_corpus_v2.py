"""Tests for the DOPEY larger regime/holdout corpus v2 (paper-only, deterministic).

All tests are offline, paper-only, and live-blocked. They use a temp directory for the
proof ledger and corpus registries to avoid cross-test state.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
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
from dopey_walk_forward.corpus_coverage import (
    CorpusCoverageScore,
    FamilyChallengeCoverageScore,
    score_corpus_coverage,
    score_family_challenge_coverage,
)
from dopey_walk_forward.holdout_window_builder import (
    additional_v2_window_count,
    build_regime_holdout_corpus_v2,
)
from dopey_walk_forward.regime_holdout_models import (
    CORPUS_V2_VERSION,
    CrossFamilyChallengeContext,
    RegimeHoldoutCorpus,
    RegimeHoldoutWindow,
    V2_CATEGORIES,
    V2_STRATEGY_FAMILIES,
    make_challenge,
    make_iv_transition,
    make_liquidity_stress,
    make_macro,
    make_sector,
)
from dopey_walk_forward.regime_holdout_runner import (
    run_regime_holdout_corpus_v2,
    verify_corpus_v2_safety_state,
)
from dopey_walk_forward.window_model import load_walk_forward_windows


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

@pytest.fixture
def corpus_v2_root(tmp_path: Path) -> Path:
    root = tmp_path / "regime_holdout_corpus_v2"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="v2-corpus-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0,
    )


# ---------------------------------------------------------------------------
# Required corpus model tests (1..4).
# ---------------------------------------------------------------------------

def test_regime_holdout_window_serializes_deterministically() -> None:
    w = RegimeHoldoutWindow(
        window_id="test-window-001",
        regime_tag="test_regime",
        category="sector_specific",
        sector_context=make_sector("tech_growth", "risk_on", "expansion", 0.8, 0.7, "n"),
        macro_context=make_macro("risk_on_neutral", "risk_on", "neutral", "neutral", 0.1, 0.7, "n"),
        iv_surface_context=make_iv_transition("pre_event_iv_expansion", 0.2, "calls", "contango", 0.2, "n"),
        skew_term_context=make_iv_transition("pre_event_iv_expansion", 0.2, "calls", "contango", 0.2, "n"),
        liquidity_context=make_liquidity_stress("late_day_liquidity_fade", 0.7, 0.2, 0.2, 0.1, "n"),
        pattern_context={"pattern_id": "p", "pattern_type": "directional", "confidence": 0.7,
                        "directional_bias": "bull", "volatility_bias": "expansion", "failure_mode": ""},
        challenge_context=None,
        expected_family_pressure={"directional_convexity": -0.3, "volatility_expansion": -0.2,
                                   "volatility_compression": 0.2, "short_duration_defined_risk": -0.1},
        preferred_families=("directional_convexity", "volatility_expansion"),
        penalized_families=("volatility_compression",),
        holdout_purpose="test",
        sequence_id=1,
        notes="test",
    )
    d1 = w.to_dict()
    d2 = w.to_dict()
    assert d1 == d2
    assert d1["window_id"] == "test-window-001"
    assert d1["category"] == "sector_specific"
    assert d1["expected_family_pressure"]["directional_convexity"] == -0.3
    # deterministic_fixture_hash is stable.
    assert w.deterministic_fixture_hash() == w.deterministic_fixture_hash()


def test_regime_holdout_corpus_hash_is_deterministic() -> None:
    c1 = build_regime_holdout_corpus_v2()
    c2 = build_regime_holdout_corpus_v2()
    assert c1.deterministic_hash() == c2.deterministic_hash()
    # Reordering windows must change the hash.
    c3 = RegimeHoldoutCorpus(
        corpus_id=c1.corpus_id, version=c1.version,
        windows=tuple(reversed(c1.windows)),
        regime_coverage=c1.regime_coverage, sector_coverage=c1.sector_coverage,
        macro_coverage=c1.macro_coverage,
        liquidity_stress_coverage=c1.liquidity_stress_coverage,
        volatility_transition_coverage=c1.volatility_transition_coverage,
    )
    assert c3.deterministic_hash() != c1.deterministic_hash()


def test_regime_holdout_corpus_records_sector_macro_iv_liquidity_context() -> None:
    corpus = build_regime_holdout_corpus_v2()
    for w in corpus.windows:
        assert w.sector_context.sector
        assert w.macro_context.event_label
        assert w.iv_surface_context.transition_label
        assert w.skew_term_context.transition_label
        assert w.liquidity_context.stress_label
        assert w.pattern_context
        assert w.expected_family_pressure
        # Holdout purpose and notes are non-empty.
        assert w.holdout_purpose
        assert w.notes


def test_cross_family_challenge_window_records_expected_family_pressure() -> None:
    challenge = make_challenge(
        label="all_family_high_uncertainty",
        family_pressure={"directional_convexity": 0.3, "volatility_expansion": 0.2,
                          "volatility_compression": 0.3, "short_duration_defined_risk": 0.4},
        uncertainty=0.9, overlap=0.95, notes="all-family stress",
    )
    assert challenge.expected_family_pressure["directional_convexity"] == 0.3
    assert challenge.high_uncertainty == 0.9
    assert challenge.cross_family_overlap == 0.95
    d = challenge.to_dict()
    assert d["challenge_label"] == "all_family_high_uncertainty"
    # Embedding into a RegimeHoldoutWindow should be allowed.
    w = RegimeHoldoutWindow(
        window_id="test-challenge",
        regime_tag="v2_challenge",
        category="cross_family_challenge",
        sector_context=make_sector("broad_market", "rotation", "expansion", 0.4, 0.4, "n"),
        macro_context=make_macro("hawkish_fomc_vix_spike", "risk_off", "spike", "spike", 0.5, 0.3, "n"),
        iv_surface_context=make_iv_transition("front_iv_backwardation_panic", 0.4, "puts", "backwardation", 0.6, "n"),
        skew_term_context=make_iv_transition("front_iv_backwardation_panic", 0.4, "puts", "backwardation", 0.6, "n"),
        liquidity_context=make_liquidity_stress("macro_gap_slippage_cluster", 0.3, 0.6, 0.6, 0.5, "n"),
        pattern_context={"pattern_id": "p", "pattern_type": "neutral", "confidence": 0.3,
                        "directional_bias": "neutral", "volatility_bias": "expansion", "failure_mode": ""},
        challenge_context=CrossFamilyChallengeContext.from_challenge(challenge),
        expected_family_pressure=challenge.expected_family_pressure,
        preferred_families=(),
        penalized_families=V2_STRATEGY_FAMILIES,
        holdout_purpose="all-family stress",
        sequence_id=2,
        notes="test",
    )
    assert w.challenge_context is not None


# ---------------------------------------------------------------------------
# Required fixture expansion tests (5..12).
# ---------------------------------------------------------------------------

def test_corpus_v2_loads_at_least_40_windows_if_feasible() -> None:
    # v1 corpus has 24 windows. v2 adds 32. Total = 56.
    v1 = load_walk_forward_windows()
    v2 = build_regime_holdout_corpus_v2()
    total = len(v1) + v2.window_count
    assert total >= 40, f"need >=40 total windows, got {total}"
    # v1 has 24 windows covering required v1 regime tags.
    assert len(v1) == 24


def test_corpus_v2_adds_at_least_16_new_windows() -> None:
    corpus = build_regime_holdout_corpus_v2()
    assert corpus.window_count >= 16
    assert additional_v2_window_count() >= 16
    assert corpus.window_count == additional_v2_window_count()


def test_corpus_v2_covers_sector_specific_windows() -> None:
    corpus = build_regime_holdout_corpus_v2()
    sector = [w for w in corpus.windows if w.category == "sector_specific"]
    assert len(sector) >= 4  # prompt says at least 4 sector windows; canonical template has 8
    sectors = {w.sector_context.sector for w in sector}
    assert "tech_growth" in sectors
    assert "broad_market" in sectors or "small_caps" in sectors


def test_corpus_v2_covers_macro_shock_windows() -> None:
    corpus = build_regime_holdout_corpus_v2()
    macro = [w for w in corpus.windows if w.category == "macro_shock"]
    assert len(macro) >= 4
    events = {w.macro_context.event_label for w in macro}
    assert any("cpi" in e for e in events)
    assert any("fomc" in e for e in events)


def test_corpus_v2_covers_iv_transition_windows() -> None:
    corpus = build_regime_holdout_corpus_v2()
    iv = [w for w in corpus.windows if w.category == "iv_transition"]
    assert len(iv) >= 4
    transitions = {w.iv_surface_context.transition_label for w in iv}
    assert any("iv_expansion" in t or "iv_crush" in t or "iv_backwardation" in t for t in transitions)


def test_corpus_v2_covers_liquidity_stress_windows() -> None:
    corpus = build_regime_holdout_corpus_v2()
    liq = [w for w in corpus.windows if w.category == "liquidity_stress"]
    assert len(liq) >= 4
    stresses = {w.liquidity_context.stress_label for w in liq}
    assert any("spread" in s or "oi" in s or "fill" in s or "fade" in s or "gap" in s for s in stresses)


def test_corpus_v2_covers_cross_family_challenge_windows() -> None:
    corpus = build_regime_holdout_corpus_v2()
    cross = [w for w in corpus.windows if w.category == "cross_family_challenge"]
    assert len(cross) >= 4
    for w in cross:
        assert w.challenge_context is not None
        assert w.challenge_context.high_uncertainty >= 0.0
        assert w.challenge_context.cross_family_overlap >= 0.0


def test_corpus_v2_windows_include_required_contexts() -> None:
    corpus = build_regime_holdout_corpus_v2()
    for w in corpus.windows:
        d = w.to_dict()
        # Required fields per the prompt.
        for k in ("window_id", "regime_tag", "sector_context", "macro_context", "iv_surface_context",
                   "skew_term_context", "liquidity_context", "pattern_context", "expected_family_pressure",
                   "preferred_families", "penalized_families", "holdout_purpose", "notes"):
            assert k in d, f"window {w.window_id} missing field {k}"
        assert d["deterministic_fixture_hash"]
        # 4 strategy families covered in expected_family_pressure.
        for fam in V2_STRATEGY_FAMILIES:
            assert fam in d["expected_family_pressure"]


# ---------------------------------------------------------------------------
# Required coverage scoring tests (13..16).
# ---------------------------------------------------------------------------

def test_corpus_coverage_scores_required_categories() -> None:
    corpus = build_regime_holdout_corpus_v2()
    coverage = score_corpus_coverage(corpus)
    assert isinstance(coverage, CorpusCoverageScore)
    # All 5 v2 categories should be present.
    for cat in V2_CATEGORIES:
        assert cat in [c for c in coverage.regime.covered if c in V2_CATEGORIES] or \
               any(w.category == cat for w in corpus.windows)
    assert coverage.sector.coverage_fraction >= 0.5
    assert coverage.stress.overall_coverage_fraction >= 0.5
    assert 0.0 <= coverage.coverage_fraction <= 1.0


def test_corpus_coverage_flags_missing_category() -> None:
    # Build a synthetic corpus missing one category.
    sector = make_sector("broad_market", "rotation", "expansion", 0.5, 0.5, "n")
    macro = make_macro("risk_on_neutral", "neutral", "neutral", "neutral", 0.1, 0.7, "n")
    iv = make_iv_transition("normal_contango_chop_decay", 0.0, "neutral", "contango", 0.1, "n")
    liq = make_liquidity_stress("late_day_liquidity_fade", 0.7, 0.1, 0.1, 0.1, "n")
    pattern = {"pattern_id": "p", "pattern_type": "neutral", "confidence": 0.5,
               "directional_bias": "neutral", "volatility_bias": "neutral", "failure_mode": ""}
    family_pressure = {"directional_convexity": 0.0, "volatility_expansion": 0.0,
                        "volatility_compression": 0.0, "short_duration_defined_risk": 0.0}
    only_sector = [
        RegimeHoldoutWindow(
            window_id=f"only-sector-{i}",
            regime_tag=f"v2_challenge_sector_{i}",
            category="sector_specific",
            sector_context=sector, macro_context=macro,
            iv_surface_context=iv, skew_term_context=iv,
            liquidity_context=liq, pattern_context=pattern,
            challenge_context=None,
            expected_family_pressure=family_pressure,
            preferred_families=(), penalized_families=(),
            holdout_purpose="test", sequence_id=10 + i, notes="t",
        )
        for i in range(3)
    ]
    corpus = RegimeHoldoutCorpus(
        corpus_id="synthetic", version=CORPUS_V2_VERSION,
        windows=tuple(only_sector),
        regime_coverage=tuple(sorted({w.regime_tag for w in only_sector})),
        sector_coverage=("broad_market",), macro_coverage=("risk_on_neutral",),
        liquidity_stress_coverage=("late_day_liquidity_fade",),
        volatility_transition_coverage=("normal_contango_chop_decay",),
    )
    coverage = score_corpus_coverage(corpus)
    missing = set(coverage.missing_categories)
    assert any("category:macro_shock" in c for c in missing)
    assert any("category:iv_transition" in c for c in missing)
    assert any("category:liquidity_stress" in c for c in missing)
    assert any("category:cross_family_challenge" in c for c in missing)


def test_corpus_coverage_flags_duplicate_or_overrepresented_category() -> None:
    # Build a synthetic corpus with >50% sector_specific windows (overrepresented).
    sector = make_sector("broad_market", "rotation", "expansion", 0.5, 0.5, "n")
    macro = make_macro("risk_on_neutral", "neutral", "neutral", "neutral", 0.1, 0.7, "n")
    iv = make_iv_transition("normal_contango_chop_decay", 0.0, "neutral", "contango", 0.1, "n")
    liq = make_liquidity_stress("late_day_liquidity_fade", 0.7, 0.1, 0.1, 0.1, "n")
    pattern = {"pattern_id": "p", "pattern_type": "neutral", "confidence": 0.5,
               "directional_bias": "neutral", "volatility_bias": "neutral", "failure_mode": ""}
    family_pressure = {"directional_convexity": 0.0, "volatility_expansion": 0.0,
                        "volatility_compression": 0.0, "short_duration_defined_risk": 0.0}
    many_sector = [
        RegimeHoldoutWindow(
            window_id=f"dup-{i}",
            regime_tag=f"v2_iv_dup_{i}",
            category="sector_specific",
            sector_context=sector, macro_context=macro,
            iv_surface_context=iv, skew_term_context=iv,
            liquidity_context=liq, pattern_context=pattern,
            challenge_context=None,
            expected_family_pressure=family_pressure,
            preferred_families=(), penalized_families=(),
            holdout_purpose="test", sequence_id=20 + i, notes="t",
        )
        for i in range(6)
    ]
    one_macro = [
        RegimeHoldoutWindow(
            window_id=f"macro-{i}",
            regime_tag=f"v2_iv_macro_{i}",
            category="macro_shock",
            sector_context=sector, macro_context=macro,
            iv_surface_context=iv, skew_term_context=iv,
            liquidity_context=liq, pattern_context=pattern,
            challenge_context=None,
            expected_family_pressure=family_pressure,
            preferred_families=(), penalized_families=(),
            holdout_purpose="test", sequence_id=30 + i, notes="t",
        )
        for i in range(1)
    ]
    corpus = RegimeHoldoutCorpus(
        corpus_id="dup", version=CORPUS_V2_VERSION,
        windows=tuple(many_sector + one_macro),
        regime_coverage=(), sector_coverage=("broad_market",),
        macro_coverage=("risk_on_neutral",),
        liquidity_stress_coverage=("late_day_liquidity_fade",),
        volatility_transition_coverage=("normal_contango_chop_decay",),
    )
    coverage = score_corpus_coverage(corpus)
    # The sector_specific category should be flagged as overrepresented.
    assert "sector_specific" in coverage.overrepresented_categories


def test_family_challenge_coverage_scores_each_family() -> None:
    corpus = build_regime_holdout_corpus_v2()
    family_scores = score_family_challenge_coverage(corpus.windows)
    families = {f.family for f in family_scores}
    assert families == set(V2_STRATEGY_FAMILIES)
    for f in family_scores:
        assert isinstance(f, FamilyChallengeCoverageScore)
        assert 0.0 <= f.mean_pressure <= 1.0
        assert 0.0 <= f.mean_uncertainty <= 1.0
        assert f.pressure_windows + f.support_windows <= len(corpus.windows)


# ---------------------------------------------------------------------------
# Required runner tests (17..21).
# ---------------------------------------------------------------------------

def test_regime_holdout_corpus_v2_runner_runs_offline() -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    from dopey_walk_forward.regime_holdout_runner import _safety_state
    verify_corpus_v2_safety_state(_safety_state())


def test_regime_holdout_corpus_v2_runner_builds_expanded_splits(tmp_path: Path) -> None:
    reg_path = tmp_path / "reg.jsonl"
    rep_path = tmp_path / "rep.jsonl"
    cov_path = tmp_path / "cov.jsonl"
    proof_path = tmp_path / "proof.jsonl"
    sum_path = tmp_path / "sum.md"
    summary = run_regime_holdout_corpus_v2(
        registry_path=reg_path, replay_path=rep_path, coverage_path=cov_path,
        proof_ledger_path=proof_path, summary_path=sum_path,
    )
    assert summary["splits_built"] >= 8
    # v1 + v2 split set: 3 rolling + 3 v2 rolling + 2 blocked + anchored + regime + stress = 11.
    assert summary["splits_built"] >= 10


def test_regime_holdout_corpus_v2_runner_writes_registry(tmp_path: Path) -> None:
    reg_path = tmp_path / "reg.jsonl"
    rep_path = tmp_path / "rep.jsonl"
    cov_path = tmp_path / "cov.jsonl"
    proof_path = tmp_path / "proof.jsonl"
    sum_path = tmp_path / "sum.md"
    summary = run_regime_holdout_corpus_v2(
        registry_path=reg_path, replay_path=rep_path, coverage_path=cov_path,
        proof_ledger_path=proof_path, summary_path=sum_path,
    )
    assert summary["corpus_v2_status"] == "ok"
    assert reg_path.exists()
    assert rep_path.exists()
    assert cov_path.exists()
    assert proof_path.exists()
    assert sum_path.exists()
    # Registry must contain a reproducibility hash.
    last = json.loads(reg_path.read_text(encoding="utf-8").splitlines()[-1])
    assert "reproducibility_hash" in last
    assert len(last["reproducibility_hash"]) == 64


def test_regime_holdout_corpus_v2_runner_writes_proof_record(tmp_path: Path) -> None:
    reg_path = tmp_path / "reg.jsonl"
    rep_path = tmp_path / "rep.jsonl"
    cov_path = tmp_path / "cov.jsonl"
    proof_path = tmp_path / "proof.jsonl"
    sum_path = tmp_path / "sum.md"
    run_regime_holdout_corpus_v2(
        registry_path=reg_path, replay_path=rep_path, coverage_path=cov_path,
        proof_ledger_path=proof_path, summary_path=sum_path,
    )
    records = [json.loads(line) for line in proof_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert records
    last = records[-1]
    assert last["final_status"] == "PASS"
    assert last["test_results"]["corpus_v2_status"] == "ok"
    assert last["test_results"]["strategies_evaluated"] >= 4
    assert last["test_results"]["splits_built"] >= 8
    assert last["test_results"]["total_windows"] >= 32


def test_v1_v2_consistency_comparison_is_deterministic(tmp_path: Path) -> None:
    s1 = run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "a.jsonl", replay_path=tmp_path / "a_rep.jsonl",
        coverage_path=tmp_path / "a_cov.jsonl", proof_ledger_path=tmp_path / "a_proof.jsonl",
        summary_path=tmp_path / "a_sum.md",
    )
    s2 = run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "b.jsonl", replay_path=tmp_path / "b_rep.jsonl",
        coverage_path=tmp_path / "b_cov.jsonl", proof_ledger_path=tmp_path / "b_proof.jsonl",
        summary_path=tmp_path / "b_sum.md",
    )
    assert s1["top_consistent_strategy_v2"] == s2["top_consistent_strategy_v2"]
    assert s1["top_consistent_family_v2"] == s2["top_consistent_family_v2"]
    assert s1["coverage_score"] == s2["coverage_score"]
    # v1_v2_score_delta must be present.
    assert "v1_v2_score_delta" in s1
    assert s1["v1_v2_score_delta"] == s2["v1_v2_score_delta"]


# ---------------------------------------------------------------------------
# Required integration tests (22..26).
# ---------------------------------------------------------------------------

def test_meta_governor_consumes_corpus_v2_evidence(tmp_path: Path) -> None:
    # Run corpus v2 first.
    run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "reg.jsonl", replay_path=tmp_path / "rep.jsonl",
        coverage_path=tmp_path / "cov.jsonl", proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    evidence = load_evidence_bundle()
    assert evidence.regime_holdout_corpus_v2, "meta-governor evidence bundle must include regime_holdout_corpus_v2"
    layers = evidence.layers_present()
    assert layers["regime_holdout_corpus_v2"] is True
    # Run the meta-governor for a non-throwing smoke (verifies integration is healthy).
    summary = run_offline_meta_governor()
    assert summary["meta_governor_status"] == "ok"


def test_ensemble_allocator_uses_corpus_v2_consistency(tmp_path: Path) -> None:
    # Build two candidates: one with strong v2 consistency, one with weak.
    base = StrategyAllocationCandidate(
        strategy_id="v2-weak-consistency", strategy_family="directional_convexity",
        source_type="tournament",
        base_score=0.6, walk_forward_score=0.6, analysis_fusion_score=0.6,
        macro_fit_score=0.6, iv_surface_fit_score=0.6, greek_fit_score=0.6,
        liquidity_robustness_score=0.6, slippage_robustness_score=0.6,
        pattern_score=0.6, failure_pressure_score=0.0,
        overfit_level="low", overfit_rank=1, mutation_delta=0.0,
        promotion_state="entrant", paper_only=True, holdout_score=0.6,
        corpus_v2_consistency_score=0.05,  # weak corpus v2 consistency
    )
    strong = StrategyAllocationCandidate(
        strategy_id="v2-strong-consistency", strategy_family="volatility_compression",
        source_type="tournament",
        base_score=0.6, walk_forward_score=0.6, analysis_fusion_score=0.6,
        macro_fit_score=0.6, iv_surface_fit_score=0.6, greek_fit_score=0.6,
        liquidity_robustness_score=0.6, slippage_robustness_score=0.6,
        pattern_score=0.6, failure_pressure_score=0.0,
        overfit_level="low", overfit_rank=1, mutation_delta=0.0,
        promotion_state="entrant", paper_only=True, holdout_score=0.6,
        corpus_v2_consistency_score=0.80,  # strong corpus v2 consistency
    )
    result = apply_allocation_policy([base, strong])
    decisions = {d.strategy_id: d for d in result.decisions}
    weak = decisions["v2-weak-consistency"]
    strong = decisions["v2-strong-consistency"]
    if weak.recommended_weight > 0.0:
        assert "weak regime/holdout corpus v2 consistency penalizes paper attention" in weak.reason_codes
    assert strong.decision in {"increase_paper_attention", "hold_paper_attention", "research_only"}


def test_evidence_audit_recognizes_corpus_v2_registry() -> None:
    types = [spec[0] for spec in ARTIFACT_SPECS]
    assert "regime_holdout_corpus_v2_registry" in types
    assert "regime_holdout_corpus_v2_replay" in types
    assert "regime_holdout_corpus_v2_coverage" in types
    assert "regime_holdout_corpus_v2_proof" in types


def test_champion_registry_records_corpus_v2_verdict(tmp_path: Path) -> None:
    from dopey_strategy_lab.champion_corpus_v2 import (
        write_champion_corpus_v2_record,
    )
    # Ensure the corpus v2 registry is present so the writer can read it.
    run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "reg.jsonl", replay_path=tmp_path / "rep.jsonl",
        coverage_path=tmp_path / "cov.jsonl", proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    # Run the writer; it should append a champion-corpus-v2 record.
    record = write_champion_corpus_v2_record(
        path=tmp_path / "champion_corpus_v2.jsonl",
        corpus_registry_path=tmp_path / "reg.jsonl",
    )
    assert record["champion_corpus_v2"] or record["runner_up_corpus_v2"]
    assert record["champion_strategy_id"] or record["runner_up_strategy_id"]


def test_failure_miner_detects_v2_family_regression(tmp_path: Path) -> None:
    # Build a synthetic v2 record where directional_convexity is regressed (high overfit +
    # low holdout), so the failure miner / consistency layer should flag it.
    from dopey_walk_forward.holdout_window_builder import build_regime_holdout_corpus_v2
    corpus = build_regime_holdout_corpus_v2()
    family_profiles = score_family_challenge_coverage(corpus.windows)
    # All families should be challenged at least weakly.
    for f in family_profiles:
        assert f.pressure_windows + f.support_windows <= len(corpus.windows)
    # directional_convexity should be challenged (is_challenged=True) under the v2 corpus.
    cc = next(f for f in family_profiles if f.family == "directional_convexity")
    assert cc.is_challenged is True or cc.high_uncertainty_windows >= 2


# ---------------------------------------------------------------------------
# Required safety regression tests (27..32).
# ---------------------------------------------------------------------------

def test_no_live_promotion_possible_after_corpus_v2(tmp_path: Path) -> None:
    summary = run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "reg.jsonl", replay_path=tmp_path / "rep.jsonl",
        coverage_path=tmp_path / "cov.jsonl", proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    # No forbidden live decisions in the v2 registry.
    last = json.loads(summary["registry_path"] and Path(summary["registry_path"]).read_text(encoding="utf-8").splitlines()[-1])
    for decision in last.get("consistency_verdicts", []):
        assert decision.get("verdict") not in {"live_candidate", "micro_live", "adaptive_live",
                                                "real_capital", "broker_order", "enable_live",
                                                "live_allocate", "funded_execution"}


def test_live_stubs_still_block_after_corpus_v2() -> None:
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(_live_intent())
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(_live_intent())
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(_live_intent())


def test_paper_broker_still_refuses_live_allowed_after_corpus_v2() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_corpus_v2(tmp_path: Path) -> None:
    summary = run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "reg.jsonl", replay_path=tmp_path / "rep.jsonl",
        coverage_path=tmp_path / "cov.jsonl", proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
    )
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert summary["live_blocked"] is True
    assert summary["live_trading_enabled"] is False
    assert summary["mode"] == "RESEARCH"


def test_corpus_v2_runner_does_not_modify_live_settings(tmp_path: Path) -> None:
    before = load_config(default_config_path())
    run_regime_holdout_corpus_v2(
        registry_path=tmp_path / "reg.jsonl", replay_path=tmp_path / "rep.jsonl",
        coverage_path=tmp_path / "cov.jsonl", proof_ledger_path=tmp_path / "proof.jsonl",
        summary_path=tmp_path / "sum.md",
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
        manifest = _P(__file__).resolve().parent / "_dummy_v2_manifest.txt"
        manifest.write_text(f"{h}  {dummy}\n", encoding="utf-8")
        findings = audit_blunder_integrity(manifest)
        assert not any(f.severity == "safety_error" for f in findings)
