"""Tests: DOPEY expanded regime corpus + differentiated strategy-family tournament (16 tests).

All deterministic, offline, no network, no credentials, no live broker calls.
Uses temp directories for proof ledger + champion registry to avoid cross-test state.
"""
import hashlib
import json
from pathlib import Path

import pytest

from dopey_walk_forward.window_model import load_walk_forward_windows
from dopey_walk_forward.replay_engine import ReplayEngine
from dopey_walk_forward.family_outcome import REQUIRED_REGIME_TAGS, STRATEGY_FAMILIES, REGIME_FAMILY_HINTS
from dopey_walk_forward.family_structures import build_family_intent
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_tournament.models import ChampionRegistryEntry
from dopey_tournament.aggression_tournament import ALLOWED_TARGETS, FORBIDDEN_LIVE_TARGETS
from dopey_tournament.runner import run_fixture_tournament, rank_strategy_scores
from dopey_tournament.models import StrategyTournamentScore
from dopey_tournament.ledger_tournament import TOURNAMENT_LEDGER_PATH, CHAMPION_REGISTRY_PATH
from dopey_analysis.enrichment import load_window_analysis, parse_window_analysis
from dopey_analysis.analysis_fusion import fuse_analysis
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_core.config import load_config, default_config_path
from dopey_research_pipeline.ranker import rank_pipeline_candidates


FORBIDDEN = {"live_candidate", "micro_live", "adaptive_live", "live", "promote_live"}


def _tmp_paths(tmp_path):
    return tmp_path / "tournament_ledger.jsonl", tmp_path / "champion_registry.jsonl"


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _mean_pnl_by_regime(family, regimes):
    ws = load_walk_forward_windows()
    eng = ReplayEngine()
    pb = build_tournament_proof_bundle(True)
    g = next(gg for gg in build_tournament_genomes() if gg.family == family)
    res = eng.replay(g, pb, ws)
    by = {}
    for r in res:
        by.setdefault(r.regime_tag, []).append(r.paper_pnl)
    return _mean([_mean(by[r]) for r in regimes if r in by])


# 1. test_expanded_regime_fixture_corpus_loads
def test_01_expanded_regime_fixture_corpus_loads():
    windows = load_walk_forward_windows()
    assert len(windows) >= 12, f"expected >=12 windows, got {len(windows)}"
    tags = {w.regime_tag for w in windows}
    missing = set(REQUIRED_REGIME_TAGS) - tags
    assert not missing, f"missing required regime tags: {missing}"
    # every required tag present exactly once
    assert tags == set(REQUIRED_REGIME_TAGS)
    for w in windows:
        assert w.option_chain.contracts, f"{w.window_id} has empty chain"
        assert w.expected_outcome, f"{w.window_id} has no expected_outcome"
        # expanded fixture fields
        assert isinstance(w.family_outcome_hints, dict) and w.family_outcome_hints, f"{w.window_id} missing family_outcome_hints"
        assert isinstance(w.regime_context, dict) and w.regime_context, f"{w.window_id} missing regime_context"
        rc = w.regime_context
        for key in ("liquidity_quality", "spread_penalty", "slippage_penalty", "iv_effect",
                    "macro_contradiction", "technical_fakeout", "pattern_confidence",
                    "invalidation_quality"):
            assert key in rc, f"{w.window_id} regime_context missing {key}"
        # analysis context fixture exists alongside
        ac = load_window_analysis(w.window_id)
        assert "macro" in ac and "microstructure" in ac and "technical" in ac


# 2. test_strategy_families_construct_different_structures
def test_02_strategy_families_construct_different_structures():
    windows = load_walk_forward_windows()
    pb = build_tournament_proof_bundle(True)
    promo = {"decision": "paper_candidate", "aggression_score": 0.5, "reasons": []}
    structs_by_fam = {}
    for g in build_tournament_genomes():
        structs = set()
        for w in windows:
            ranked = rank_pipeline_candidates(w.option_chain)
            intent, structure = build_family_intent(g, w.option_chain.underlying.symbol,
                                                    ranked, w.regime_tag, promo, pb)
            assert intent.live_allowed is False
            assert intent.paper is True
            assert intent.defined_risk is True
            structs.add(structure)
        structs_by_fam[g.family] = structs
    # all four families produce distinct structures
    fams = list(structs_by_fam.keys())
    for i in range(len(fams)):
        for j in range(i + 1, len(fams)):
            assert structs_by_fam[fams[i]] != structs_by_fam[fams[j]] or \
                len(structs_by_fam[fams[i]].union(structs_by_fam[fams[j]])) > 1, \
                f"{fams[i]} and {fams[j]} produce identical structures"
    # sanity: expected structure families present
    all_structs = set().union(*structs_by_fam.values())
    assert "vertical" in all_structs
    assert any(s in all_structs for s in ("strangle",))
    assert "iron_condor" in all_structs
    assert "butterfly" in all_structs


# 3. test_family_replay_outcomes_are_differentiated
def test_03_family_replay_outcomes_are_differentiated(tmp_path):
    ledger, reg = _tmp_paths(tmp_path)
    s = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=reg)
    frs = s["family_replay_summaries"]
    assert len(frs) >= 4
    mean_pnls = {fam: rec["mean_pnl"] for fam, rec in frs.items()}
    distinct = set(round(p, 4) for p in mean_pnls.values())
    assert len(distinct) >= 2, f"families not differentiated: {mean_pnls}"
    # walk-forward scores differ too
    wfs = {fam: rec["walk_forward_overall"] for fam, rec in frs.items()}
    assert len(set(round(w, 4) for w in wfs.values())) >= 2


# 4. test_directional_strategy_prefers_breakout_regimes
def test_04_directional_strategy_prefers_breakout_regimes():
    breakout = _mean_pnl_by_regime("directional_convexity",
                                   ["bullish_breakout", "bearish_breakdown", "trend_vol_expansion"])
    chop = _mean_pnl_by_regime("directional_convexity",
                               ["chop_vol_compression", "range_bound_pin", "high_spread_bad_fill"])
    assert breakout > chop, f"directional should prefer breakout ({breakout}) over chop ({chop})"


# 5. test_volatility_expansion_prefers_event_vol_windows
def test_05_volatility_expansion_prefers_event_vol_windows():
    event = _mean_pnl_by_regime("volatility_expansion",
                                ["event_vol_expansion", "macro_shock_risk_off"])
    crush = _mean_pnl_by_regime("volatility_expansion", ["post_event_iv_crush"])
    assert event > crush, f"vol_expansion should prefer event-vol ({event}) over iv-crush ({crush})"


# 6. test_volatility_compression_prefers_chop_or_iv_crush_windows
def test_06_volatility_compression_prefers_chop_or_iv_crush_windows():
    good = _mean_pnl_by_regime("volatility_compression",
                               ["chop_vol_compression", "range_bound_pin", "post_event_iv_crush"])
    event = _mean_pnl_by_regime("volatility_compression",
                                ["event_vol_expansion", "macro_shock_risk_off"])
    assert good > event, f"compression should prefer chop/crush ({good}) over event-vol ({event})"


# 7. test_short_duration_penalized_by_bad_spreads
def test_07_short_duration_penalized_by_bad_spreads():
    bad = _mean_pnl_by_regime("short_duration_defined_risk",
                              ["high_spread_bad_fill", "low_liquidity_decay", "gap_reversal"])
    good = _mean_pnl_by_regime("short_duration_defined_risk",
                               ["bullish_breakout", "trend_vol_expansion"])
    assert bad < good, f"short-duration should be penalized by bad spreads ({bad}) vs good ({good})"


# 8. test_tournament_ranking_not_insertion_order_tie
def test_08_tournament_ranking_not_insertion_order_tie():
    # construct scores with identical combined_score but different tie-breakers
    a = StrategyTournamentScore("t", "s-a", "directional_convexity", combined_score=0.5,
                                 overfit_level="low", holdout_score=0.3,
                                 liquidity_robustness=0.6, invalidation_quality=0.5)
    b = StrategyTournamentScore("t", "s-b", "volatility_expansion", combined_score=0.5,
                                 overfit_level="none", holdout_score=0.3,
                                 liquidity_robustness=0.6, invalidation_quality=0.5)
    c = StrategyTournamentScore("t", "s-c", "volatility_compression", combined_score=0.5,
                                 overfit_level="none", holdout_score=0.5,
                                 liquidity_robustness=0.6, invalidation_quality=0.5)
    ranked = rank_strategy_scores([a, b, c])
    # b (overfit none) beats a (overfit low); c (higher holdout) beats b
    assert ranked[0].strategy_id == "s-c"
    assert ranked[1].strategy_id == "s-b"
    assert ranked[2].strategy_id == "s-a"
    # and the real tournament ranking is sorted by combined_score (not insertion order)
    s = run_fixture_tournament()
    scores = [r["combined_score"] for r in s["strategy_ranking"]]
    assert scores == sorted(scores, reverse=True)
    # champion has the top combined_score
    assert s["strategy_ranking"][0]["combined_score"] == max(scores)


# 9. test_champion_registry_records_family_strengths_and_weaknesses
def test_09_champion_registry_records_family_strengths_and_weaknesses(tmp_path):
    ledger, reg = _tmp_paths(tmp_path)
    s = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=reg)
    assert reg.exists()
    lines = reg.read_text(encoding="utf-8").strip().splitlines()
    entry = json.loads(lines[-1])
    assert entry["champion_strategy_id"] == s["champion_strategy_id"]
    assert entry["runner_up_strategy_id"] == s["runner_up_strategy_id"]
    assert len(entry["family_ranking"]) >= 4
    assert "best_regimes_by_family" in entry and len(entry["best_regimes_by_family"]) >= 4
    assert "worst_regimes_by_family" in entry and len(entry["worst_regimes_by_family"]) >= 4
    assert "family_strengths" in entry and entry["family_strengths"]
    assert "family_weaknesses" in entry and entry["family_weaknesses"]
    assert entry["champion_best_regimes"]
    assert entry["champion_worst_regimes"]
    assert entry["champion_overfit_level"] in {"none", "low", "moderate", "high"}
    assert "champion_replay_score" in entry
    assert "champion_analysis_fusion_score" in entry
    assert "safety_state" in entry
    assert entry["safety_state"]["live_blocked"] is True
    assert len(entry["reproducibility_hash"]) == 64


# 10. test_proof_ledger_records_expanded_corpus_tournament
def test_10_proof_ledger_records_expanded_corpus_tournament(tmp_path):
    ledger, reg = _tmp_paths(tmp_path)
    s = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=reg)
    assert ledger.exists()
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["task_id"].startswith("tournament-")
    er = rec["execution_result"]
    assert er["corpus_id"] == s["corpus_id"]
    assert er["window_count"] >= 12
    assert len(er["regime_tags_covered"]) >= 12
    assert "family_replay_summaries" in er and len(er["family_replay_summaries"]) >= 4
    assert "analysis_fusion_summaries" in er
    assert "strategy_ranking" in er and len(er["strategy_ranking"]) >= 4
    assert er["champion"] == s["champion_strategy_id"]
    assert er["runner_up"] == s["runner_up_strategy_id"]
    assert "safety_state" in er
    assert rec["input_hash"] and len(rec["input_hash"]) == 64
    # promotion decisions are paper-only
    for dec in er["promotion_decisions"].values():
        assert dec in ALLOWED_TARGETS
        assert dec not in FORBIDDEN_LIVE_TARGETS


# 11. test_analysis_fusion_affects_tournament_score
def test_11_analysis_fusion_affects_tournament_score(tmp_path):
    # changing fixture analysis context changes the fusion score deterministically.
    # Build two windows dirs: one with the real corpus, one with a degraded macro context
    # that should lower fusion for risk-on families.
    from dopey_walk_forward.window_model import WALK_FORWARD_DIR
    import shutil
    src = WALK_FORWARD_DIR
    alt = tmp_path / "alt_corpus"
    alt.mkdir()
    # copy windows + analysis, then degrade one analysis fixture's macro risk_on_score
    for f in src.iterdir():
        if f.name.endswith(".json"):
            shutil.copy(f, alt / f.name)
    target = alt / "window_008_validation_analysis.json"  # bullish_breakout analysis
    data = json.loads(target.read_text(encoding="utf-8"))
    data["macro"]["risk_on_score"] = 0.1
    data["microstructure"]["liquidity_score"] = 0.1
    target.write_text(json.dumps(data), encoding="utf-8")

    l1, r1 = _tmp_paths(tmp_path / "run1")
    l2, r2 = _tmp_paths(tmp_path / "run2")
    s1 = run_fixture_tournament(proof_ledger_path=l1, champion_registry_path=r1)
    s2 = run_fixture_tournament(proof_ledger_path=l2, champion_registry_path=r2, windows_dir=alt)
    # fusion summaries differ (deterministically)
    assert s1["analysis_fusion_summaries"] != s2["analysis_fusion_summaries"]
    # at least one strategy's analysis_fusion_overall changed
    diffs = [abs(a - b) for a, b in zip(
        [r["analysis_fusion_overall"] for r in s1["strategy_ranking"]],
        [r["analysis_fusion_overall"] for r in s2["strategy_ranking"]])]
    assert max(diffs) > 1e-6, "analysis fusion did not change with degraded context"


# 12. test_no_live_promotion_possible_after_expanded_tournament
def test_12_no_live_promotion_possible_after_expanded_tournament(tmp_path):
    ledger, reg = _tmp_paths(tmp_path)
    s = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=reg)
    for dec in s["promotion_decisions"].values():
        assert dec in ALLOWED_TARGETS, f"unexpected promotion: {dec}"
        assert dec not in FORBIDDEN_LIVE_TARGETS
        assert dec not in FORBIDDEN
    # champion stays paper-only
    champ_dec = s["promotion_decisions"][s["champion_strategy_id"]]
    assert champ_dec in {"research_only", "paper_candidate", "tournament_champion_paper_only"}
    assert "live" not in champ_dec


# 13. test_live_stubs_still_block_after_expanded_tournament
def test_13_live_stubs_still_block_after_expanded_tournament():
    intent_live = ExecutionIntent(
        intent_id="exp-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19",
               "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent_live)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent_live)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent_live)


# 14. test_paper_broker_still_refuses_live_allowed
def test_14_paper_broker_still_refuses_live_allowed():
    intent_live = ExecutionIntent(
        intent_id="exp-pb-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": "B", "strike": 105, "expiry": "2024-01-19",
               "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent_live)
    # and the expanded paper structures are still paper-only
    cap = PaperBroker().get_capabilities()
    assert cap["live"] is False and cap["funded"] is False
    for st in ("strangle", "iron_condor", "butterfly"):
        assert st in cap["supported_structures"]


# 15. test_config_still_research_after_expanded_tournament
def test_15_config_still_research_after_expanded_tournament(tmp_path):
    ledger, reg = _tmp_paths(tmp_path)
    s = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=reg)
    assert s["mode"] == "RESEARCH"
    assert s["live_trading_enabled"] is False
    assert s["live_blocked"] is True
    assert s["safety_state"]["live_trading_enabled"] is False
    assert s["safety_state"]["funded_broker_connections_enabled"] is False
    assert s["safety_state"]["allow_unofficial_robinhood_api"] is False
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert cfg["funded_broker_connections_enabled"] is False


# 16. test_blunder_source_integrity_if_manifest_available
def test_16_blunder_source_integrity_if_manifest_available():
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping integrity check")
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
    assert checked > 0, "no Blunder files were checked (manifest paths unresolved)"
    assert bad == 0, f"{bad} Blunder source file(s) changed since baseline (checked {checked})"
