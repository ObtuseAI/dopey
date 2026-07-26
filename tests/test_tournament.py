"""Tests: DOPEY offline multi-strategy paper tournament (15 required tests).

All deterministic, offline, no network, no credentials, no live broker calls.
Uses temp directories for the proof ledger + champion registry to avoid cross-test state.
"""
import hashlib
from pathlib import Path

import pytest

from dopey_analysis.models import (
    MacroContext, MicrostructureContext, TechnicalContext, FundamentalContext,
    PatternSignal, AnalysisFusionScore,
)
from dopey_analysis.macro_analysis import score_macro
from dopey_analysis.microstructure_analysis import score_microstructure
from dopey_analysis.technical_analysis import score_technical
from dopey_analysis.fundamental_analysis import score_fundamental
from dopey_analysis.pattern_recognition import score_patterns
from dopey_analysis.analysis_fusion import fuse_analysis
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_tournament.models import TournamentResult, StrategyTournamentScore, ChampionRegistryEntry
from dopey_tournament.aggression_tournament import (
    evaluate_tournament_promotion, ALLOWED_TARGETS, FORBIDDEN_LIVE_TARGETS,
)
from dopey_tournament.runner import run_fixture_tournament
from dopey_tournament.ledger_tournament import (
    TOURNAMENT_LEDGER_PATH, CHAMPION_REGISTRY_PATH,
)
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_core.config import load_config, default_config_path


def _tmp_paths(tmp_path):
    return tmp_path / "tournament_ledger.jsonl", tmp_path / "champion_registry.jsonl"


def test_01_analysis_context_models_serialize():
    models = [
        MacroContext(regime_tag="t", risk_on_score=0.7),
        MicrostructureContext(spread_quality_score=0.8),
        TechnicalContext(trend_score=0.6),
        FundamentalContext(growth_quality_score=0.7),
        PatternSignal(pattern_id="p1", confidence=0.6),
        AnalysisFusionScore(macro_score=0.7, overall_score=0.6),
    ]
    for m in models:
        d = m.to_dict()
        assert isinstance(d, dict)
        rt = type(m).from_dict(d)
        assert rt.to_dict() == d, f"{type(m).__name__} round-trip not deterministic"


def test_02_analysis_fusion_penalizes_contradictions():
    # strong technical but weak microstructure + weak macro -> contradiction penalty lowers overall
    strong_tech = TechnicalContext(trend_score=0.9, momentum_score=0.9, breakout_score=0.9,
                                   fakeout_risk_score=0.1, support_resistance_score=0.9,
                                   volume_confirmation_score=0.9, realized_volatility_score=0.9)
    weak_micro = MicrostructureContext(spread_quality_score=0.2, liquidity_score=0.2,
                                       slippage_sensitivity_score=0.9, contract_fillability_score=0.2)
    weak_macro = MacroContext(risk_on_score=0.2, event_risk_score=0.8, liquidity_regime_score=0.2)
    neutral_fund = FundamentalContext()
    patterns = [PatternSignal(pattern_id="p", confidence=0.8)]
    fusion = fuse_analysis(macro_ctx=weak_macro, micro_ctx=weak_micro, tech_ctx=strong_tech,
                           fund_ctx=neutral_fund, patterns=patterns)
    assert fusion.contradiction_penalty > 0
    assert fusion.overall_score < fusion.technical_score  # weak layers drag overall below tech
    assert fusion.overall_score < 0.6  # no single layer dominates


def test_03_tournament_loads_multiple_genomes():
    genomes = build_tournament_genomes()
    assert len(genomes) >= 4
    families = {g.family for g in genomes}
    assert len(families) >= 4
    expected = {"directional_convexity", "volatility_expansion",
                "volatility_compression", "short_duration_defined_risk"}
    assert expected.issubset(families)


def test_04_all_tournament_genomes_are_defined_risk_or_paper_safe():
    genomes = build_tournament_genomes()
    for g in genomes:
        assert g.defined_risk_only is True, f"{g.genome_id} must be defined-risk only"
        assert g.live_allowed is False, f"{g.genome_id} must be paper-only"
        risk = g.parameters.get("structure_risk", "defined")
        assert risk == "defined", f"{g.genome_id} structure_risk must be defined (no naked selling)"
        assert "naked" not in g.family.lower()
        assert "undefined" not in risk.lower()


def test_05_tournament_is_deterministic(tmp_path):
    l1, r1 = _tmp_paths(tmp_path / "run1")
    l2, r2 = _tmp_paths(tmp_path / "run2")
    s1 = run_fixture_tournament(proof_ledger_path=l1, champion_registry_path=r1)
    s2 = run_fixture_tournament(proof_ledger_path=l2, champion_registry_path=r2)
    assert s1["strategy_ranking"] == s2["strategy_ranking"]
    assert s1["champion_strategy_id"] == s2["champion_strategy_id"]
    assert s1["runner_up_strategy_id"] == s2["runner_up_strategy_id"]
    assert s1["reproducibility_hash"] == s2["reproducibility_hash"]
    assert s1["family_scorecard"] == s2["family_scorecard"]


def test_06_tournament_uses_paper_broker_only():
    # the tournament runner only constructs PaperBroker (via ReplayEngine + fill simulator)
    summary = run_fixture_tournament()
    assert summary["live_blocked"] is True
    # sanity: PaperBroker capability is the paper-only adapter
    cap = PaperBroker().get_capabilities()
    assert cap["broker"] == "paper" and cap["live"] is False and cap["funded"] is False


def test_07_tournament_rejects_live_allowed_intent():
    # construct a live intent and confirm PaperBroker + fill simulator refuse it
    windows_genomes = build_tournament_genomes()
    g = windows_genomes[0]
    intent = ExecutionIntent(
        intent_id="t-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)
    from dopey_research_pipeline.fill_simulator import simulate_paper_fill
    with pytest.raises(LiveTradingDisabledError):
        simulate_paper_fill(PaperBroker(), intent, {})


def test_08_tournament_ranks_by_walk_forward_and_analysis_fusion():
    summary = run_fixture_tournament()
    ranking = summary["strategy_ranking"]
    assert len(ranking) >= 4
    # combined_score must be present and sorted descending
    scores = [r["combined_score"] for r in ranking]
    assert scores == sorted(scores, reverse=True)
    # each entry has both walk-forward and analysis-fusion fields
    for r in ranking:
        assert "walk_forward_overall" in r
        assert "analysis_fusion_overall" in r
        assert "combined_score" in r
    # combined_score is the current multi-lane deterministic blend (walk-forward
    # dominant, then fusion/greeks/IV/liquidity/slippage/invalidation/holdout/
    # overfit + macro/fundamental adjustments) - recompute it exactly
    from dopey_tournament.runner import _combined_score
    top = ranking[0]
    expected = _combined_score(
        top["walk_forward_overall"],
        top["analysis_fusion_overall"],
        greek_fit=top["average_greek_fit_score"],
        iv_score=round(
            (top["average_iv_context_score"] + top["average_skew_score"] + top["average_term_structure_score"]
             + top["average_iv_surface_fit_score"] + top["average_family_iv_fit_score"]
             + top["average_skew_term_score"]) / 6.0, 6),
        liquidity=top["average_liquidity_score"],
        slippage=top["slippage_robustness_score"],
        invalidation=top["invalidation_quality"],
        holdout=top["holdout_score"],
        overfit_rank=top["overfit_rank"],
        macro_fit=top.get("average_macro_fit_score", 0.5),
        macro_risk=top.get("average_macro_risk_score", 0.5),
        fundamental_fit=top.get("average_fundamental_fit_score", 0.5),
        fundamental_contradiction=top.get("average_fundamental_contradiction_penalty", 0.5),
    )
    assert abs(top["combined_score"] - expected) < 1e-6


def test_09_champion_registry_written(tmp_path):
    _, reg = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(champion_registry_path=reg)
    assert reg.exists()
    import json
    lines = reg.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["champion_strategy_id"] == summary["champion_strategy_id"]
    assert entry["runner_up_strategy_id"] == summary["runner_up_strategy_id"]
    assert "family_ranking" in entry and len(entry["family_ranking"]) >= 4
    assert entry["reproducibility_hash"] and len(entry["reproducibility_hash"]) == 64


def test_10_proof_ledger_tournament_record_written(tmp_path):
    ledger, _ = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger)
    assert ledger.exists()
    import json
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[-1])
    assert rec["task_id"].startswith("tournament-")
    er = rec["execution_result"]
    assert "strategy_ranking" in er and len(er["strategy_ranking"]) >= 4
    assert "family_scorecard" in er
    assert "overfit_summary" in er
    assert "promotion_decisions" in er
    assert rec["input_hash"] and len(rec["input_hash"]) == 64


def test_11_aggression_gate_cannot_promote_live_from_tournament():
    genomes = build_tournament_genomes()
    g = genomes[0]
    gate = ProofWeightedAggressionGate()
    cap = PaperBroker().get_capabilities()
    fusion = AnalysisFusionScore(macro_score=0.8, microstructure_score=0.8, technical_score=0.8,
                                 fundamental_score=0.8, pattern_score=0.8,
                                 contradiction_penalty=0.0, freshness_reliability_score=1.0,
                                 replay_confirmation_score=0.9, overall_score=0.9, summary="perfect")
    # champion with perfect scores still cannot be live
    verdict = evaluate_tournament_promotion(gate, g.to_dict(), 1.0, fusion, "none",
                                            1.0, g.preferred_regime, cap, is_champion=True)
    assert verdict.decision in ALLOWED_TARGETS
    assert verdict.decision not in FORBIDDEN_LIVE_TARGETS
    # even a forbidden-target-shaped string never appears
    for forbidden in FORBIDDEN_LIVE_TARGETS:
        assert forbidden not in verdict.decision


def test_12_existing_live_stubs_still_block_after_tournament():
    intent_live = ExecutionIntent(
        intent_id="tour-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent_live)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent_live)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent_live)


def test_13_paper_broker_still_refuses_live_allowed_after_tournament():
    intent_live = ExecutionIntent(
        intent_id="tour-pb-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent_live)


def test_14_config_still_research_after_tournament(tmp_path):
    ledger, reg = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=reg)
    assert summary["mode"] == "RESEARCH"
    assert summary["live_trading_enabled"] is False
    assert summary["live_blocked"] is True
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert cfg["funded_broker_connections_enabled"] is False


def test_15_blunder_source_integrity_if_manifest_available():
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping destructive integrity check")
    text = manifest.read_text(encoding="utf-8-sig")
    bad = 0
    checked = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        expected, path = parts
        p = Path(path)
        if not p.exists():
            continue
        checked += 1
        actual = hashlib.sha256(p.read_bytes()).hexdigest().upper()
        if actual != expected.strip().upper():
            bad += 1
    assert bad == 0, f"{bad} Blunder source file(s) changed since baseline (checked {checked})"
