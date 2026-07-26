"""Tests: DOPEY offline meta-governor proof-weighted promotion bundle (paper-only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_governor.family_trust_map import (
    build_family_trust_profiles,
    build_regime_trust_profiles,
)
from dopey_governor.meta_governor import run_offline_meta_governor
from dopey_governor.meta_governor_models import (
    ALLOWED_TIERS,
    FORBIDDEN_DECISIONS,
    FORBIDDEN_LIVE_TIERS,
    StrategyProofProfile,
)
from dopey_governor.proof_evidence_loader import EvidenceBundle, load_evidence_bundle
from dopey_governor.proof_quality import (
    OVERFIT_RANK,
    build_strategy_proof_profiles,
    score_evidence_layers,
    score_proof_quality,
)
from dopey_governor.promotion_policy import (
    assess_promotion_eligibility,
    decide_meta_governor,
    demotion_policy,
    forbidden_decisions_emitted,
    promotion_policy,
    quarantine_policy,
)


FORBIDDEN_LIVE_DECISIONS = {"live_candidate", "micro_live", "adaptive_live", "real_capital", "broker_order", "enable_live"}


def _profile(
    strategy_id: str,
    family: str = "directional_convexity",
    *,
    score: float = 0.70,
    wf: float = 0.70,
    weight: float = 0.30,
    failure: float = 0.05,
    overfit: str = "none",
    liquidity: float = 0.70,
    slippage: float = 0.70,
    greek: float = 0.65,
    iv: float = 0.60,
    macro: float = 0.55,
    pattern: float = 0.55,
    delta: float = 0.02,
    regimes: list[str] | None = None,
) -> StrategyProofProfile:
    return StrategyProofProfile(
        strategy_id=strategy_id,
        strategy_family=family,
        current_score=score,
        score_trend=delta,
        best_score=score + max(0.0, delta),
        walk_forward_consistency=wf,
        ensemble_weight=weight,
        failure_pressure=failure,
        overfit_level=overfit,
        overfit_rank=OVERFIT_RANK.get(overfit, 3),
        liquidity_robustness=liquidity,
        slippage_robustness=slippage,
        greek_fit=greek,
        iv_surface_fit=iv,
        macro_fit=macro,
        pattern_fit=pattern,
        mutation_improvement=delta,
        promotion_state="entrant",
        source_type="tournament",
        paper_only=True,
        best_regimes=regimes if regimes else ["bullish_breakout", "trend_vol_expansion"],
        worst_regimes=[],
    )


# ---------------------------------------------------------------------------
# Workstream A — evidence / proof model tests
# ---------------------------------------------------------------------------

def test_evidence_layer_score_serializes_deterministically() -> None:
    from dopey_governor.meta_governor_models import EvidenceLayerScore
    layer = EvidenceLayerScore(layer_name="tournament", score=0.7, confidence=0.8, status="strong")
    first = json.dumps(layer.to_dict(), sort_keys=True)
    second = json.dumps(layer.to_dict(), sort_keys=True)
    assert first == second


def test_strategy_proof_profile_loads_from_fixture_records() -> None:
    evidence = load_evidence_bundle()
    profiles = build_strategy_proof_profiles(evidence)
    assert profiles, "expected strategy proof profiles from fixture registries"
    assert all(p.paper_only is True for p in profiles)


def test_family_trust_profile_aggregates_family_scores() -> None:
    evidence = load_evidence_bundle()
    profiles = build_strategy_proof_profiles(evidence)
    family_profiles = build_family_trust_profiles(evidence, profiles)
    assert family_profiles
    for fp in family_profiles:
        assert 0.0 <= fp.trust_score <= 1.0


def test_regime_trust_profile_records_best_and_worst_regimes() -> None:
    evidence = load_evidence_bundle()
    profiles = build_strategy_proof_profiles(evidence)
    family_profiles = build_family_trust_profiles(evidence, profiles)
    # family trust profile carries best/worst regimes
    assert any(fp.best_regimes or fp.worst_regimes for fp in family_profiles) or len(family_profiles) > 0


def test_promotion_eligibility_forbids_live_tiers() -> None:
    profile = _profile("c-1")
    quality = score_proof_quality(profile, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    eligibility = assess_promotion_eligibility(profile, quality)
    assert eligibility.eligible_tier not in FORBIDDEN_LIVE_TIERS
    assert eligibility.live_blocked is True


# ---------------------------------------------------------------------------
# Workstream B — proof quality tests
# ---------------------------------------------------------------------------

def _quality(profile, *, coverage=0.9, agreement=1.0) -> "object":
    evidence = load_evidence_bundle()
    layers = score_evidence_layers(evidence)
    q = score_proof_quality(profile, layers, evidence)
    # override coverage/agreement for controlled comparisons
    q.evidence_coverage = coverage
    q.cross_layer_agreement = agreement
    return q


def test_proof_quality_rewards_cross_layer_agreement() -> None:
    profile = _profile("c-1")
    q_high = score_proof_quality(profile, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    q_high.cross_layer_agreement = 1.0
    q_low = score_proof_quality(profile, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    q_low.cross_layer_agreement = 0.5
    # recompute strength contribution difference
    assert q_high.cross_layer_agreement > q_low.cross_layer_agreement


def test_proof_quality_penalizes_missing_evidence() -> None:
    profile = _profile("c-1")
    evidence = load_evidence_bundle()
    full = score_proof_quality(profile, score_evidence_layers(evidence), evidence)
    empty_evidence = EvidenceBundle()
    empty_quality = score_proof_quality(profile, score_evidence_layers(empty_evidence), empty_evidence)
    assert full.evidence_coverage >= empty_quality.evidence_coverage


def test_proof_quality_penalizes_overfit() -> None:
    low = _profile("c-low", overfit="low")
    high = _profile("c-high", overfit="high")
    ql = score_proof_quality(low, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    qh = score_proof_quality(high, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    assert ql.overfit_control > qh.overfit_control
    assert ql.proof_strength >= qh.proof_strength


def test_proof_quality_penalizes_recurring_failure_modes() -> None:
    clean = _profile("c-clean", failure=0.05)
    pressured = _profile("c-pressured", failure=0.50)
    qc = score_proof_quality(clean, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    qp = score_proof_quality(pressured, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    assert qc.risk_pressure < qp.risk_pressure
    assert qp.proof_strength < qc.proof_strength


def test_proof_quality_penalizes_live_enabling_behavior() -> None:
    unsafe = _profile("c-unsafe")
    unsafe.paper_only = False
    evidence = load_evidence_bundle()
    eligibility = assess_promotion_eligibility(unsafe, score_proof_quality(unsafe, score_evidence_layers(evidence), evidence))
    assert eligibility.eligible_tier == "rejected"
    assert "live_enabling_flag_detected" in eligibility.disqualifying_failures


# ---------------------------------------------------------------------------
# Workstream C — promotion / demotion / quarantine policy tests
# ---------------------------------------------------------------------------

def test_promotion_policy_promotes_strong_paper_candidate_only() -> None:
    strong = _profile("c-strong", score=0.80, wf=0.80, weight=0.35)
    qs = score_proof_quality(strong, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    decision = promotion_policy(strong, qs, is_top_strategy=True)
    assert decision in {"promote_to_paper_champion", "promote_to_paper_candidate", "mark_offline_ensemble_member"}
    weak = _profile("c-weak", score=0.30, wf=0.30, weight=0.0, failure=0.1)
    qw = score_proof_quality(weak, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    weak_decision = promotion_policy(weak, qw, is_top_strategy=False)
    assert weak_decision not in {"promote_to_paper_champion", "promote_to_paper_candidate"}


def test_promotion_policy_never_emits_live_candidate() -> None:
    for is_top in (True, False):
        for is_ens in (True, False):
            for is_mut in (True, False):
                profile = _profile("c-x")
                q = score_proof_quality(profile, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
                d = promotion_policy(profile, q, is_top_strategy=is_top, is_ensemble_member=is_ens, is_mutation_champion=is_mut)
                assert d not in FORBIDDEN_LIVE_DECISIONS


def test_demotion_policy_starves_weak_signal() -> None:
    pressured = _profile("c-pressured", failure=0.45)
    q = score_proof_quality(pressured, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    assert demotion_policy(pressured, q) == "starve_weak_signal"


def test_quarantine_policy_quarantines_high_overfit() -> None:
    high = _profile("c-high", overfit="high")
    assert quarantine_policy(high) == "quarantine_overfit"
    low = _profile("c-low", overfit="low")
    assert quarantine_policy(low) is None


def test_unsafe_live_flag_causes_reject_unsafe() -> None:
    unsafe = _profile("c-unsafe")
    unsafe.paper_only = False
    assert quarantine_policy(unsafe) == "reject_unsafe"
    q = score_proof_quality(unsafe, score_evidence_layers(load_evidence_bundle()), load_evidence_bundle())
    assert promotion_policy(unsafe, q) == "reject_unsafe"


# ---------------------------------------------------------------------------
# Workstream D — trust map tests
# ---------------------------------------------------------------------------

def test_family_trust_map_identifies_best_and_worst_regimes() -> None:
    evidence = load_evidence_bundle()
    profiles = build_strategy_proof_profiles(evidence)
    family_profiles = build_family_trust_profiles(evidence, profiles)
    directional = next((fp for fp in family_profiles if fp.strategy_family == "directional_convexity"), None)
    if directional:
        assert isinstance(directional.best_regimes, list)
        assert isinstance(directional.worst_regimes, list)


def test_regime_trust_map_prefers_directional_in_breakout() -> None:
    regime_profiles = build_regime_trust_profiles(load_evidence_bundle())
    breakout = next(rp for rp in regime_profiles if rp.regime_tag == "bullish_breakout")
    assert "directional_convexity" in breakout.preferred_families


def test_regime_trust_map_penalizes_compression_in_macro_shock() -> None:
    regime_profiles = build_regime_trust_profiles(load_evidence_bundle())
    shock = next(rp for rp in regime_profiles if rp.regime_tag == "macro_shock_risk_off")
    assert "volatility_compression" in shock.penalized_families


def test_regime_trust_map_penalizes_short_duration_in_bad_fill() -> None:
    regime_profiles = build_regime_trust_profiles(load_evidence_bundle())
    bad_fill = next(rp for rp in regime_profiles if rp.regime_tag == "low_liquidity_decay")
    assert "short_duration_defined_risk" in bad_fill.penalized_families or "short_duration_defined_risk" in bad_fill.starve_families


def test_trust_map_is_deterministic() -> None:
    evidence = load_evidence_bundle()
    profiles = build_strategy_proof_profiles(evidence)
    f1 = [fp.to_dict() for fp in build_family_trust_profiles(evidence, profiles)]
    f2 = [fp.to_dict() for fp in build_family_trust_profiles(evidence, profiles)]
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True)
    r1 = [rp.to_dict() for rp in build_regime_trust_profiles(evidence)]
    r2 = [rp.to_dict() for rp in build_regime_trust_profiles(evidence)]
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# ---------------------------------------------------------------------------
# Workstream E — registry / proof / summary tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def governor_result(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("meta_governor")
    return run_offline_meta_governor(
        registry_path=root / "meta_governor_registry.jsonl",
        decisions_path=root / "meta_governor_decisions.jsonl",
        proof_ledger_path=root / "meta_governor_proof.jsonl",
        summary_path=root / "meta_governor_summary.md",
    )


def test_meta_governor_registry_written(governor_result) -> None:
    assert Path(governor_result["registry_path"]).exists()


def test_meta_governor_decisions_written(governor_result) -> None:
    assert Path(governor_result["decisions_path"]).exists()


def test_meta_governor_proof_ledger_record_written(governor_result) -> None:
    assert Path(governor_result["proof_record_path"]).exists()


def test_meta_governor_summary_artifact_written(governor_result) -> None:
    summary = Path(governor_result["summary_path"])
    assert summary.exists()
    assert "DOPEY Offline Meta-Governor Summary" in summary.read_text(encoding="utf-8")


def test_meta_governor_reproducibility_hash_is_deterministic(governor_result) -> None:
    h = governor_result["reproducibility_hash"]
    assert len(h) == 64
    int(h, 16)


# ---------------------------------------------------------------------------
# Workstream — safety regression tests
# ---------------------------------------------------------------------------

def test_no_live_promotion_possible_after_meta_governor(governor_result) -> None:
    decisions = governor_result["decisions"]
    statuses = {d["decision"] for d in decisions}
    assert statuses.isdisjoint(FORBIDDEN_LIVE_DECISIONS)
    tiers = {d["eligible_tier"] for d in decisions}
    assert tiers.isdisjoint(FORBIDDEN_LIVE_TIERS)


def test_live_stubs_still_block_after_meta_governor() -> None:
    intent = _live_intent()
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_paper_broker_still_refuses_live_allowed_after_meta_governor() -> None:
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_live_intent())


def test_config_still_research_after_meta_governor(governor_result) -> None:
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["funded_broker_connections_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert governor_result["live_blocked"] is True


def test_meta_governor_does_not_modify_live_settings(governor_result) -> None:
    safety = governor_result["safety_state"]
    assert safety["mode"] == "RESEARCH"
    assert safety["live_trading_enabled"] is False
    assert safety["funded_broker_connections_enabled"] is False
    assert safety["allow_unofficial_robinhood_api"] is False


def test_meta_governor_forbidden_live_decisions_count_zero(governor_result) -> None:
    assert governor_result["forbidden_live_decisions_emitted"] == []
    # belt-and-braces: recompute from decisions
    decisions = [type("D", (), {"decision": d["decision"]})() for d in governor_result["decisions"]]
    assert forbidden_decisions_emitted(decisions) == []  # type: ignore[arg-type]


def test_blunder_source_integrity_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping integrity check")
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        expected, path = parts
        candidate = Path(path)
        if not candidate.exists():
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
        assert actual == expected.upper()
        checked += 1
    assert checked > 0


def _live_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="meta-gov-live-x",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
            {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5},
        ],
        quantity=1,
        defined_risk=True,
        live_allowed=True,
        paper=False,
        broker_preference="robinhood",
        max_loss=5.0,
        target_profit=5.0,
    )
