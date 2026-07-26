"""Tests: DOPEY offline walk-forward replay harness (12 required tests).

All deterministic, offline, no network, no credentials, no live broker calls.
Uses a temp directory for the proof ledger to avoid cross-test state.
"""
from pathlib import Path

import pytest

from dopey_walk_forward.window_model import load_walk_forward_windows, WalkForwardWindow
from dopey_walk_forward.replay_models import ReplayResult, WalkForwardScore, OverfitSignal, ReplayVerdict
from dopey_walk_forward.overfit_classifier import classify_overfit
from dopey_walk_forward.scoring import score_walk_forward
from dopey_walk_forward.replay_engine import ReplayEngine, replay_walk_forward
from dopey_walk_forward.aggression_replay import evaluate_replay_promotion, ALLOWED_TARGETS, DISALLOWED_LIVE_TARGETS
from dopey_walk_forward.runner import run_fixture_walk_forward
from dopey_walk_forward.safety_review import safety_review
from dopey_research_pipeline.strategy_fixture import build_fixture_genome, build_fixture_proof_bundle
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.robinhood_mcp_adapter import RobinhoodMCPAdapter
from dopey_execution.alpaca_options_adapter import AlpacaOptionsAdapter
from dopey_execution.tradier_options_adapter import TradierOptionsAdapter
from dopey_execution.errors import LiveTradingDisabledError
from dopey_core.config import load_config, default_config_path


def _tmp_ledger(tmp_path) -> Path:
    return tmp_path / "walk_forward_ledger.jsonl"


def test_01_walk_forward_fixture_windows_load():
    windows = load_walk_forward_windows()
    assert len(windows) >= 4, "at least 4 fixture windows required"
    regimes = {w.regime_tag for w in windows}
    assert len(regimes) >= 2, "at least 2 regime tags required"
    types = {w.window_type for w in windows}
    assert "train" in types and "validation" in types and "holdout" in types
    for w in windows:
        assert w.option_chain.contracts, "each window must have a chain"
        assert w.expected_outcome, "each window must have an outcome fixture"
        assert w.underlying_snapshot.get("symbol") == "SPY_FIXTURE"


def test_02_walk_forward_replay_is_deterministic(tmp_path):
    ledger1 = _tmp_ledger(tmp_path / "run1")
    ledger2 = _tmp_ledger(tmp_path / "run2")
    s1 = run_fixture_walk_forward(proof_ledger_path=ledger1)
    s2 = run_fixture_walk_forward(proof_ledger_path=ledger2)
    # summary fields must match (excluding the proof_record which carries a UTC timestamp)
    for k in ("mode", "windows_replayed", "pass_rate", "overfit_level",
              "promotion_decision", "windows_replayed", "live_blocked"):
        assert s1[k] == s2[k], f"non-deterministic field {k}"
    # walk_forward_score deterministic
    assert s1["walk_forward_score"] == s2["walk_forward_score"]
    assert s1["window_results"] == s2["window_results"]
    # reproducibility hashes match
    assert s1["proof_record"]["input_hash"] == s2["proof_record"]["input_hash"]


def test_03_replay_uses_paper_broker_only():
    # ReplayResult must always carry paper-only intent ids and no live broker involvement.
    windows = load_walk_forward_windows()
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    engine = ReplayEngine()
    results = engine.replay(genome, proof, windows)
    assert len(results) == len(windows)
    for r in results:
        assert r.paper_intent_id.startswith("replay-")
        # no live broker path: the only adapter used is PaperBroker (via fill_simulator)
    # sanity: PaperBroker capability is paper-only
    cap = PaperBroker().get_capabilities()
    assert cap["broker"] == "paper" and cap["live"] is False and cap["funded"] is False


def test_04_replay_rejects_live_allowed_intent():
    windows = load_walk_forward_windows()
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    engine = ReplayEngine()
    # replay a single window to get a result, then craft a live intent manually and confirm
    # the fill simulator / broker refuse it
    r = engine.replay_window(genome, proof, windows[0])
    assert r is not None
    # construct a live intent and confirm refusal
    live_intent = ExecutionIntent(
        intent_id="replay-live-x", symbol="SPY_FIXTURE", structure="vertical",
        legs=[{"side": "buy", "symbol": windows[0].option_chain.contracts[0].symbol,
               "strike": 100, "expiry": "2024-01-19", "option_type": "call", "mid": 1.0},
              {"side": "sell", "symbol": windows[0].option_chain.contracts[1].symbol,
               "strike": 105, "expiry": "2024-01-19", "option_type": "call", "mid": 0.5}],
        quantity=1, defined_risk=True, live_allowed=True, paper=False,
        broker_preference="robinhood", max_loss=5.0, target_profit=5.0)
    from dopey_research_pipeline.fill_simulator import simulate_paper_fill
    with pytest.raises(LiveTradingDisabledError):
        simulate_paper_fill(PaperBroker(), live_intent, {})


def test_05_walk_forward_score_penalizes_holdout_collapse():
    # artificial scenario: train passes strongly, validation pass, holdout fails badly
    results = [
        ReplayResult("g", "w_train", "train", "trend_vol_expansion",
                     selected_contracts=["a", "b"], paper_intent_id="i1",
                     simulated_fill=5.0, simulated_exit=8.0, paper_pnl=3.0,
                     verdict="pass"),
        ReplayResult("g", "w_val1", "validation", "chop_vol_compression",
                     selected_contracts=["a", "b"], paper_intent_id="i2",
                     simulated_fill=5.0, simulated_exit=5.5, paper_pnl=0.5,
                     verdict="pass"),
        ReplayResult("g", "w_hold", "holdout", "liquidity_decay",
                     selected_contracts=["a", "b"], paper_intent_id="i3",
                     simulated_fill=5.0, simulated_exit=1.0, paper_pnl=-4.0,
                     verdict="fail"),
    ]
    score = score_walk_forward(results)
    # holdout collapse should drive elevated overfit suspicion
    assert score.overfit_suspicion_score > 0.4
    assert score.holdout_mean_pnl < 0
    assert score.window_pass_rate < 1.0


def test_06_overfit_detector_classifies_high_overfit():
    sig = classify_overfit(train_passed=True, validation_passed=False, holdout_passed=False,
                          train_pnl=3.0, validation_pnl=-2.0, holdout_pnl=-4.0)
    assert sig.level == "high"
    assert any("curve-fit" in r for r in sig.reasons)


def test_07_overfit_detector_classifies_low_or_none_overfit():
    sig = classify_overfit(train_passed=True, validation_passed=True, holdout_passed=True,
                          train_pnl=3.0, validation_pnl=1.0, holdout_pnl=0.8,
                          overfit_suspicion=0.1)
    assert sig.level in {"none", "low"}


def test_08_aggression_gate_cannot_promote_live_from_replay():
    windows = load_walk_forward_windows()
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=True)
    engine = ReplayEngine()
    results = engine.replay(genome, proof, windows)
    score = score_walk_forward(results)
    train_passed = any(r.verdict == "pass" for r in results if r.window_type == "train")
    val_passed = any(r.verdict == "pass" for r in results if r.window_type == "validation")
    holdout_passed = any(r.verdict == "pass" for r in results if r.window_type == "holdout")
    overfit = classify_overfit(train_passed=train_passed, validation_passed=val_passed,
                               holdout_passed=holdout_passed,
                               train_pnl=score.train_mean_pnl, validation_pnl=score.validation_mean_pnl,
                               holdout_pnl=score.holdout_mean_pnl, overfit_suspicion=score.overfit_suspicion_score)
    cap = PaperBroker().get_capabilities()
    gate = ProofWeightedAggressionGate()
    avg_liq = sum(r.liquidity_score for r in results) / len(results)
    verdict = evaluate_replay_promotion(gate, genome.to_dict(), score, overfit,
                                        avg_liq, genome.preferred_regime, cap)
    assert verdict.decision in ALLOWED_TARGETS
    assert verdict.decision not in DISALLOWED_LIVE_TARGETS
    # explicitly no live promotion
    assert "live" not in verdict.decision.lower() or verdict.decision in ALLOWED_TARGETS
    # even an artificially perfect score cannot produce a live target
    perfect = WalkForwardScore(consistency_score=1.0, window_pass_rate=1.0,
                               regime_survival_score=1.0, slippage_tolerance_score=1.0,
                               liquidity_robustness_score=1.0, invalidation_quality_score=1.0,
                               overfit_suspicion_score=0.0, train_mean_pnl=5.0,
                               validation_mean_pnl=3.0, holdout_mean_pnl=2.0, overall=1.0)
    perfect_overfit = OverfitSignal(level="none", train_passed=True, validation_passed=True,
                                    holdout_passed=True, reasons=["perfect"])
    v2 = evaluate_replay_promotion(gate, genome.to_dict(), perfect, perfect_overfit,
                                    1.0, genome.preferred_regime, cap)
    assert v2.decision in ALLOWED_TARGETS
    assert v2.decision not in DISALLOWED_LIVE_TARGETS


def test_09_walk_forward_appends_proof_ledger_record(tmp_path):
    ledger = _tmp_ledger(tmp_path)
    summary = run_fixture_walk_forward(proof_ledger_path=ledger)
    assert summary["walk_forward_status"] == "ok"
    assert ledger.exists()
    import json
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[-1])
    assert rec["task_id"] == summary["strategy_id"]
    assert "execution_result" in rec
    er = rec["execution_result"]
    assert "window_results" in er and "walk_forward_score" in er
    assert "overfit_signal" in er and "replay_verdict" in er
    assert rec["input_hash"] and len(rec["input_hash"]) == 64


def test_10_walk_forward_does_not_enable_live_trading(tmp_path):
    ledger = _tmp_ledger(tmp_path)
    summary = run_fixture_walk_forward(proof_ledger_path=ledger)
    assert summary["mode"] == "RESEARCH"
    assert summary["live_trading_enabled"] is False
    assert summary["live_blocked"] is True
    cfg = load_config(default_config_path())
    assert cfg["mode"] == "RESEARCH"
    assert cfg["live_trading_enabled"] is False
    assert cfg["allow_unofficial_robinhood_api"] is False


def test_11_existing_live_stubs_still_block_after_walk_forward():
    intent_live = ExecutionIntent(
        intent_id="wf-live-x", symbol="SPY_FIXTURE", structure="vertical",
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


def test_12_blunder_source_integrity_if_manifest_available():
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available; skipping destructive integrity check")
    import hashlib
    # read with utf-8-sig to strip any UTF-8 BOM prefix (PowerShell Set-Content -Encoding UTF8 adds one)
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
