"""Tests: DOPEY offline paper research pipeline (10 required tests).

All tests are deterministic, offline, no network, no credentials, no live broker calls.
Uses a temp directory for the proof ledger to avoid cross-test state.
"""
from pathlib import Path

import pytest

from dopey_research_pipeline.fixtures import load_fixture_chain, fixture_symbol_set
from dopey_research_pipeline.ranker import rank_pipeline_candidates
from dopey_research_pipeline.strategy_fixture import build_fixture_genome, build_fixture_proof_bundle
from dopey_research_pipeline.aggression import evaluate_paper_promotion
from dopey_research_pipeline.intent_builder import build_paper_intent
from dopey_research_pipeline.fill_simulator import simulate_paper_fill
from dopey_research_pipeline.pipeline import run_pipeline
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.order_intent_validator import validate_intent
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_core.config import load_config, default_config_path


def _tmp_ledger(tmp_path) -> Path:
    return tmp_path / "proof_ledger.jsonl"


def test_01_fixture_chain_loads():
    chain = load_fixture_chain()
    assert chain.underlying.symbol == "SPY_FIXTURE"
    assert chain.calls(), "fixture must have calls"
    assert chain.puts(), "fixture must have puts"
    for c in chain.contracts:
        assert c.bid > 0 and c.ask > 0, "bid/ask must be present"
        assert c.delta != 0 or c.iv > 0, "greeks/iv fields present"
        assert c.open_interest >= 0 and c.volume >= 0
        assert c.expiry


def test_02_contract_ranker_is_deterministic():
    chain = load_fixture_chain()
    r1 = rank_pipeline_candidates(chain)
    r2 = rank_pipeline_candidates(chain)
    assert r1 == r2, "ranking must be deterministic"
    top1 = r1[0]["symbol"]
    top2 = r2[0]["symbol"]
    assert top1 == top2
    assert "score" in r1[0] and "liquidity" in r1[0] and "slippage" in r1[0]


def test_03_strategy_genome_fixture_is_defined_risk():
    g = build_fixture_genome()
    assert g.defined_risk_only is True
    assert g.live_allowed is False
    assert g.parameters.get("structure") == "vertical"
    assert g.parameters.get("structure_risk") == "defined"
    assert "naked" not in g.family.lower()
    assert "undefined" not in g.parameters.get("structure_risk", "")


def test_04_aggression_gate_allows_paper_only():
    chain = load_fixture_chain()
    ranked = rank_pipeline_candidates(chain)
    long_leg = next(r for r in ranked if r["option_type"] == "call")
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    cap = PaperBroker().get_capabilities()
    gate = ProofWeightedAggressionGate()
    dec = evaluate_paper_promotion(gate, genome.to_dict(), proof, long_leg["liquidity"],
                                  genome.preferred_regime, cap)
    # strong proof -> paper_candidate (never live)
    assert dec.decision == "paper_candidate"
    assert dec.decision != "promote"  # gate mapped to paper-only target
    # live promotion is impossible from this path
    assert dec.decision in {"paper_candidate", "research_only", "rejected"}
    # weak proof -> rejected
    weak_proof = build_fixture_proof_bundle(strong=False)
    dec_w = evaluate_paper_promotion(gate, genome.to_dict(), weak_proof, long_leg["liquidity"],
                                     genome.preferred_regime, cap)
    assert dec_w.decision == "rejected"


def test_05_execution_intent_builder_sets_live_allowed_false():
    chain = load_fixture_chain()
    ranked = rank_pipeline_candidates(chain)
    calls = sorted([r for r in ranked if r["option_type"] == "call"], key=lambda r: r["strike"])
    long_leg, short_leg = calls[0], calls[1]
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    promo = {"decision": "paper_candidate", "aggression_score": 1.0, "reasons": []}
    intent = build_paper_intent(genome, chain.underlying.symbol, long_leg, short_leg, promo, proof)
    assert intent.live_allowed is False
    assert "paper" in intent.broker_preference.lower()
    assert intent.defined_risk is True
    assert intent.paper is True
    assert intent.max_loss > 0
    assert intent.target_profit > 0
    assert intent.invalidation_rule


def test_06_order_intent_validator_rejects_live_intent():
    chain = load_fixture_chain()
    ranked = rank_pipeline_candidates(chain)
    calls = sorted([r for r in ranked if r["option_type"] == "call"], key=lambda r: r["strike"])
    symbols = fixture_symbol_set(chain)
    # build a valid paper intent first
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    promo = {"decision": "paper_candidate", "aggression_score": 1.0, "reasons": []}
    intent = build_paper_intent(genome, chain.underlying.symbol, calls[0], calls[1], promo, proof)
    cap = PaperBroker().get_capabilities()
    assert validate_intent(intent, capability=cap, fixture_symbols=symbols)["valid"] is True
    # now flip live_allowed=True -> must be rejected
    intent_live = ExecutionIntent(**{**intent.to_dict(), "live_allowed": True})
    verdict = validate_intent(intent_live, capability=cap, fixture_symbols=symbols)
    assert verdict["valid"] is False
    assert any("live_allowed" in e for e in verdict["errors"])
    # undefined-risk -> rejected
    intent_undef = ExecutionIntent(**{**intent.to_dict(), "defined_risk": False})
    assert validate_intent(intent_undef, capability=cap, fixture_symbols=symbols)["valid"] is False
    # foreign symbol -> rejected
    intent_foreign = ExecutionIntent(**{**intent.to_dict(), "legs": [
        {"side": "buy", "symbol": "FAKE999", "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
        {"side": "sell", "symbol": "FAKE888", "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5},
    ]})
    assert validate_intent(intent_foreign, capability=cap, fixture_symbols=symbols)["valid"] is False


def test_07_paper_broker_simulates_fill_only():
    chain = load_fixture_chain()
    ranked = rank_pipeline_candidates(chain)
    calls = sorted([r for r in ranked if r["option_type"] == "call"], key=lambda r: r["strike"])
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    promo = {"decision": "paper_candidate", "aggression_score": 1.0, "reasons": []}
    intent = build_paper_intent(genome, chain.underlying.symbol, calls[0], calls[1], promo, proof)
    broker = PaperBroker()
    chain_mids = {c.symbol: c.mid() for c in chain.contracts}
    fill = simulate_paper_fill(broker, intent, chain_mids)
    assert fill["ok"] is True
    assert fill["paper_only"] is True
    assert fill["paper"] is True
    assert fill["order_id"].startswith("paper-")
    assert "paper_only" in fill and fill["paper_only"] is True
    # live intent must be refused by the simulator
    intent_live = ExecutionIntent(**{**intent.to_dict(), "live_allowed": True})
    with pytest.raises(LiveTradingDisabledError):
        simulate_paper_fill(broker, intent_live, chain_mids)


def test_08_pipeline_appends_proof_ledger_record(tmp_path):
    ledger = _tmp_ledger(tmp_path)
    summary = run_pipeline(proof_ledger_path=ledger)
    assert summary["pipeline_status"] == "ok"
    assert ledger.exists(), "proof ledger file must be created"
    import json
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[-1])
    assert rec["task_id"] == summary["strategy_id"]
    assert "execution_result" in rec
    assert "validation_result" in rec
    assert rec["final_status"] == "PASS"
    er = rec["execution_result"]
    assert "fill" in er and "execution_quality" in er
    assert er["fill"]["paper_only"] is True
    assert "aggression_score" in str(rec["test_results"]["promotion_decision"]) or \
           "aggression_score" in rec["test_results"]["promotion_decision"]
    # reproducibility hash present
    assert rec["input_hash"] and len(rec["input_hash"]) == 64


def test_09_pipeline_does_not_enable_live_trading(tmp_path):
    ledger = _tmp_ledger(tmp_path)
    summary = run_pipeline(proof_ledger_path=ledger)
    assert summary["mode"] == "RESEARCH"
    assert summary["live_trading_enabled"] is False
    assert summary["live_blocked"] is True
    # default config file itself remains research-only
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_10_robinhood_alpaca_tradier_stubs_still_block_live():
    intent_live = ExecutionIntent(
        intent_id="live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": "SPYFIX240119C00440000", "strike": 440.0,
               "expiry": "2024-01-19", "option_type": "call", "mid": 13.4},
              {"side": "sell", "symbol": "SPYFIX240119C00450000", "strike": 450.0,
               "expiry": "2024-01-19", "option_type": "call", "mid": 8.25}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    with pytest.raises(LiveTradingDisabledError):
        RobinhoodMCPAdapter().place_order(intent_live)
    with pytest.raises(LiveTradingDisabledError):
        AlpacaOptionsAdapter().place_order(intent_live)
    with pytest.raises(LiveTradingDisabledError):
        TradierOptionsAdapter().place_order(intent_live)
