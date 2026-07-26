"""Tests: deterministic slippage/liquidity upgrade.

All tests are fixture-only, offline, paper-only, deterministic, and live-blocked.
"""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from dopey_core.config import default_config_path, load_config
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.liquidity_model import score_contract_liquidity
from dopey_execution.order_intent_validator import validate_intent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.slippage_model import SlippageModelInput, estimate_slippage
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_options.ontology import OptionContract
from dopey_research_pipeline.fill_simulator import simulate_paper_fill
from dopey_research_pipeline.intent_builder import build_paper_intent
from dopey_research_pipeline.ranker import rank_pipeline_candidates
from dopey_research_pipeline.strategy_fixture import build_fixture_genome, build_fixture_proof_bundle
from dopey_research_pipeline.fixtures import load_fixture_chain
from dopey_tournament.aggression_tournament import ALLOWED_TARGETS, FORBIDDEN_LIVE_TARGETS
from dopey_tournament.genome_set import build_tournament_genomes, build_tournament_proof_bundle
from dopey_tournament.runner import run_fixture_tournament
from dopey_walk_forward.replay_engine import ReplayEngine
from dopey_walk_forward.window_model import WALK_FORWARD_DIR, load_walk_forward_windows


def _contract(symbol: str, bid: float, ask: float, volume: int, open_interest: int) -> OptionContract:
    return OptionContract(
        symbol=symbol,
        underlying_symbol="SPY_FIXTURE",
        option_type="call",
        strike=450.0,
        expiry="2024-01-19",
        bid=bid,
        ask=ask,
        last=round((bid + ask) / 2.0, 6),
        volume=volume,
        open_interest=open_interest,
        iv=0.18,
        delta=0.5,
    )


def _tmp_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "tournament_ledger.jsonl", tmp_path / "champion_registry.jsonl"


def _replay_family(family: str):
    windows = load_walk_forward_windows()
    genome = next(g for g in build_tournament_genomes() if g.family == family)
    proof = build_tournament_proof_bundle(True)
    return ReplayEngine().replay(genome, proof, windows)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _copy_corpus(tmp_path: Path) -> Path:
    alt = tmp_path / "alt_corpus"
    alt.mkdir()
    for src in WALK_FORWARD_DIR.iterdir():
        if src.name.endswith(".json"):
            shutil.copy(src, alt / src.name)
    return alt


def test_liquidity_model_scores_tight_liquid_contract_higher():
    tight = _contract("TIGHT", 8.00, 8.08, 12000, 50000)
    wide = _contract("WIDE", 0.50, 1.40, 5, 20)
    ctx = {"quote_stability_score": 0.95, "contract_fillability_score": 0.95}
    tight_score = score_contract_liquidity(tight, "", ctx, "", "single", "", 1)
    wide_score = score_contract_liquidity(wide, "", {"quote_stability_score": 0.2}, "", "single", "", 1)
    assert tight_score.liquidity_score > wide_score.liquidity_score
    assert tight_score.liquidity_verdict in {"excellent", "good"}
    assert wide_score.liquidity_verdict in {"poor", "reject"}


def test_liquidity_model_rejects_extreme_spread_contract():
    extreme = _contract("EXTREME", 0.20, 2.40, 1, 1)
    result = score_contract_liquidity(extreme, "", {"contract_fillability_score": 0.1}, "", "single", "", 1)
    assert result.liquidity_verdict in {"poor", "reject"}
    assert result.liquidity_score < 0.25


def test_slippage_model_not_fixed_constant():
    tight = SlippageModelInput(
        mid=8.0, spread_percentage=0.01, liquidity_score=0.95, regime_tag="trend_vol_expansion",
        strategy_family="directional_convexity", structure_type="single", leg_count=1,
        quote_stability_score=0.95, slippage_sensitivity_score=0.05,
    )
    poor = SlippageModelInput(
        mid=8.0, spread_percentage=0.60, liquidity_score=0.20, regime_tag="high_spread_bad_fill",
        strategy_family="directional_convexity", structure_type="single", leg_count=1,
        quote_stability_score=0.25, slippage_sensitivity_score=0.6, high_spread_flag=True,
        low_liquidity_flag=True,
    )
    tight_result = estimate_slippage(tight)
    poor_result = estimate_slippage(poor)
    assert tight_result.expected_slippage_pct != poor_result.expected_slippage_pct
    assert poor_result.expected_slippage_pct > tight_result.expected_slippage_pct
    assert not (
        tight_result.expected_slippage_pct == 0.002
        and poor_result.expected_slippage_pct == 0.002
    )


def test_slippage_model_penalizes_high_spread_bad_fill_regime():
    base = SlippageModelInput(
        mid=5.0, spread_percentage=0.04, liquidity_score=0.65, regime_tag="range_bound_pin",
        strategy_family="directional_convexity", structure_type="vertical", leg_count=2,
        quote_stability_score=0.7, slippage_sensitivity_score=0.2,
    )
    bad = SlippageModelInput(
        mid=5.0, spread_percentage=0.04, liquidity_score=0.65, regime_tag="high_spread_bad_fill",
        strategy_family="directional_convexity", structure_type="vertical", leg_count=2,
        quote_stability_score=0.7, slippage_sensitivity_score=0.2, high_spread_flag=True,
    )
    assert estimate_slippage(bad).expected_slippage_pct > estimate_slippage(base).expected_slippage_pct


def test_slippage_model_penalizes_low_liquidity_decay_regime():
    normal = SlippageModelInput(
        mid=5.0, spread_percentage=0.04, liquidity_score=0.65, regime_tag="range_bound_pin",
        strategy_family="volatility_expansion", structure_type="strangle", leg_count=2,
        quote_stability_score=0.7,
    )
    decay = SlippageModelInput(
        mid=5.0, spread_percentage=0.04, liquidity_score=0.65, regime_tag="low_liquidity_decay",
        strategy_family="volatility_expansion", structure_type="strangle", leg_count=2,
        quote_stability_score=0.7, low_liquidity_flag=True,
    )
    assert estimate_slippage(decay).expected_slippage_pct > estimate_slippage(normal).expected_slippage_pct


def test_slippage_model_penalizes_multi_leg_structures_more_than_single_leg_when_liquidity_is_equal():
    single = SlippageModelInput(
        mid=4.0, spread_percentage=0.03, liquidity_score=0.7, regime_tag="range_bound_pin",
        strategy_family="directional_convexity", structure_type="single", leg_count=1,
        quote_stability_score=0.7,
    )
    multi = SlippageModelInput(
        mid=4.0, spread_percentage=0.03, liquidity_score=0.7, regime_tag="range_bound_pin",
        strategy_family="volatility_compression", structure_type="iron_condor", leg_count=4,
        quote_stability_score=0.7,
    )
    assert estimate_slippage(multi).expected_slippage_pct > estimate_slippage(single).expected_slippage_pct


def test_paper_broker_uses_dynamic_slippage_model():
    chain = load_fixture_chain()
    ranked = rank_pipeline_candidates(chain)
    calls = sorted([r for r in ranked if r["option_type"] == "call"], key=lambda r: r["strike"])
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(True)
    promo = {"decision": "paper_candidate", "aggression_score": 1.0, "reasons": []}
    intent = build_paper_intent(genome, chain.underlying.symbol, calls[0], calls[1], promo, proof)
    fill = simulate_paper_fill(
        PaperBroker(),
        intent,
        {c.symbol: c.mid() for c in chain.contracts},
        fill_context={"regime_tag": "trend_vol_expansion", "strategy_family": genome.family,
                      "structure_type": intent.structure, "leg_count": len(intent.legs)},
    )
    assert fill["ok"] is True
    assert fill["paper_only"] is True
    assert fill["live"] is False
    assert fill["expected_slippage_pct"] > 0.0
    assert fill["expected_slippage_pct"] != 0.002
    assert "liquidity_score" in fill and "slippage_verdict" in fill
    assert fill["simulated_fill_price"] != fill["requested_net_price"]


def test_paper_broker_still_refuses_live_allowed_after_slippage_upgrade():
    intent = ExecutionIntent(
        intent_id="live-slippage-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=1.0, target_profit=1.0,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_order_validator_rejects_or_downgrades_reject_liquidity_verdict():
    intent = ExecutionIntent(
        intent_id="reject-liq-x", symbol="SPY_FIXTURE", structure="single",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0, "bid": 0.10, "ask": 2.50,
               "volume": 0, "open_interest": 0, "fillability_score": 0.05}],
        quantity=1, defined_risk=True, live_allowed=False, paper=True,
        broker_preference="paper", max_loss=1.0, target_profit=1.0,
    )
    verdict = validate_intent(
        intent,
        capability=PaperBroker().get_capabilities(),
        fill_context={"regime_tag": "high_spread_bad_fill", "strategy_family": "directional_convexity"},
    )
    assert verdict["valid"] is False or "poor_fill_candidate" in verdict["research_labels"]
    assert verdict["liquidity_checks"]


def test_tournament_scores_change_when_slippage_context_changes(tmp_path):
    ledger1, reg1 = _tmp_paths(tmp_path / "base")
    ledger2, reg2 = _tmp_paths(tmp_path / "alt")
    alt = _copy_corpus(tmp_path)
    target = alt / "window_010_holdout.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["regime_context"]["spread_penalty"] = 0.95
    data["regime_context"]["slippage_penalty"] = 0.95
    data["regime_context"]["liquidity_quality"] = 0.05
    for contract in data["option_chain"]["contracts"]:
        contract["bid"] = max(0.01, round(contract["bid"] * 0.25, 6))
        contract["ask"] = round(contract["ask"] * 1.75, 6)
        contract["volume"] = 1
        contract["open_interest"] = 1
    target.write_text(json.dumps(data), encoding="utf-8")
    base = run_fixture_tournament(proof_ledger_path=ledger1, champion_registry_path=reg1)
    changed = run_fixture_tournament(proof_ledger_path=ledger2, champion_registry_path=reg2, windows_dir=alt)
    assert base["strategy_ranking"] != changed["strategy_ranking"]
    assert base["slippage_liquidity_summary"] != changed["slippage_liquidity_summary"]


def test_short_duration_penalized_more_in_bad_fill_windows():
    short = _replay_family("short_duration_defined_risk")
    directional = _replay_family("directional_convexity")
    bad = {"high_spread_bad_fill", "low_liquidity_decay"}
    short_slip = _mean([r.expected_slippage_pct for r in short if r.regime_tag in bad])
    directional_slip = _mean([r.expected_slippage_pct for r in directional if r.regime_tag in bad])
    assert short_slip > directional_slip


def test_directional_strategy_penalized_by_fakeout_bad_fill_combo():
    results = _replay_family("directional_convexity")
    bad = _mean([r.expected_slippage_pct for r in results if r.regime_tag in {"gap_reversal", "high_spread_bad_fill"}])
    clean = _mean([r.expected_slippage_pct for r in results if r.regime_tag in {"bullish_breakout", "trend_vol_expansion"}])
    assert bad > clean


def test_compression_strategy_penalized_by_macro_shock_slippage():
    results = _replay_family("volatility_compression")
    macro = _mean([r.expected_slippage_pct for r in results if r.regime_tag == "macro_shock_risk_off"])
    chop = _mean([r.expected_slippage_pct for r in results if r.regime_tag in {"chop_vol_compression", "range_bound_pin"}])
    assert macro > chop


def test_champion_registry_records_liquidity_and_slippage_metrics(tmp_path):
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    record = json.loads(registry.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["champion_strategy_id"] == summary["champion_strategy_id"]
    assert "average_liquidity_score" in record
    assert "average_fill_quality_score" in record
    assert "worst_slippage_regime" in record
    assert "best_liquidity_regime" in record
    assert "liquidity_robustness_score" in record
    assert "slippage_robustness_score" in record
    assert "survived_bad_fill_low_liquidity" in record


def test_proof_ledger_records_slippage_model_fields(tmp_path):
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    record = json.loads(ledger.read_text(encoding="utf-8").strip().splitlines()[-1])
    er = record["execution_result"]
    assert er["liquidity_model_version"] == summary["liquidity_model_version"]
    assert er["slippage_model_version"] == summary["slippage_model_version"]
    assert er["slippage_liquidity_summary"]
    assert er["worst_slippage_regimes"]
    assert er["best_fill_quality_regimes"]
    assert len(record["input_hash"]) == 64


def test_no_live_promotion_possible_after_slippage_upgrade(tmp_path):
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    for decision in summary["promotion_decisions"].values():
        assert decision in ALLOWED_TARGETS
        assert decision not in FORBIDDEN_LIVE_TARGETS
        assert "live" not in decision


def test_live_stubs_still_block_after_slippage_upgrade():
    intent = ExecutionIntent(
        intent_id="live-stubs-slippage-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "A", "strike": 100, "expiry": "2024-01-19",
               "option_type": "call", "mid": 1.0}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=1.0, target_profit=1.0,
    )
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent)


def test_config_still_research_after_slippage_upgrade(tmp_path):
    ledger, registry = _tmp_paths(tmp_path)
    summary = run_fixture_tournament(proof_ledger_path=ledger, champion_registry_path=registry)
    cfg = load_config(default_config_path())
    assert summary["mode"] == "RESEARCH"
    assert summary["live_trading_enabled"] is False
    assert summary["live_blocked"] is True
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False
    assert cfg["funded_broker_connections_enabled"] is False


def test_blunder_source_integrity_if_manifest_available():
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
        source_path = Path(path)
        if not source_path.exists():
            continue
        checked += 1
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest().upper()
        if actual != expected.strip().upper():
            bad += 1
    assert checked > 0, "no Blunder files were checked"
    assert bad == 0, f"{bad} Blunder source file(s) changed since baseline"
