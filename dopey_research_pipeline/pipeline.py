"""Dopey offline paper research pipeline: orchestrator.

run_pipeline() drives the full offline deterministic paper-only loop:
  fixture chain -> rank contracts -> build strategy genome -> aggression gate ->
  build paper execution intent -> validate intent -> simulate PaperBroker fill ->
  log execution quality -> append ProofLedger record.

Everything is offline, deterministic, and live-blocked. Returns a PipelineResult.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from dopey_core.config import load_config, default_config_path
from dopey_core.proof_ledger import ProofLedger
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.order_intent_validator import validate_intent
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_options.liquidity_engine import liquidity_score

from .fixtures import load_fixture_chain, fixture_symbol_set
from .ranker import rank_pipeline_candidates
from .strategy_fixture import build_fixture_genome, build_fixture_proof_bundle, PROMOTION_TIER_PAPER
from .aggression import evaluate_paper_promotion
from .intent_builder import build_paper_intent
from .fill_simulator import simulate_paper_fill
from .quality_ledger import build_execution_quality, build_proof_entry, reproducibility_hash


PROOF_LEDGER_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "proof_ledger"
PROOF_LEDGER_PATH = PROOF_LEDGER_DIR / "dopey_paper_pipeline.jsonl"


@dataclass
class PipelineResult:
    mode: str
    live_trading_enabled: bool
    pipeline_status: str
    strategy_id: str
    execution_intent_id: str
    paper_order_id: str
    proof_record_path: str
    live_blocked: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _pick_vertical_legs(ranked: list[dict]) -> tuple[dict, dict]:
    """Pick a long-call vertical (long lower-strike call, short higher-strike call, same expiry)."""
    calls_by_exp: dict[str, list[dict]] = {}
    for r in ranked:
        if r["option_type"] == "call":
            calls_by_exp.setdefault(r["expiry"], []).append(r)
    # choose the expiry with at least 2 calls
    for exp, legs in calls_by_exp.items():
        legs.sort(key=lambda r: r["strike"])
        if len(legs) >= 2:
            return legs[0], legs[1]
    # fallback: top two ranked calls regardless of expiry
    all_calls = [r for r in ranked if r["option_type"] == "call"]
    all_calls.sort(key=lambda r: r["strike"])
    return all_calls[0], all_calls[1]


def run_pipeline(config_path: Path | str | None = None,
                 proof_ledger_path: Path | str | None = None,
                 strong_proof: bool = True) -> dict:
    """Run the full offline paper pipeline. Returns a dict summary."""
    cfg = load_config(config_path or default_config_path())
    ledger_path = Path(proof_ledger_path) if proof_ledger_path else PROOF_LEDGER_PATH

    # 1. load fixture chain
    chain = load_fixture_chain()
    symbols = fixture_symbol_set(chain)

    # 2. rank contracts
    ranked = rank_pipeline_candidates(chain)

    # 3. build strategy genome + proof bundle
    genome = build_fixture_genome()
    proof = build_fixture_proof_bundle(strong=strong_proof)

    # 4. aggression gate (paper-only promotion mapping)
    gate = ProofWeightedAggressionGate()
    long_leg, short_leg = _pick_vertical_legs(ranked)
    liq_long = long_leg["liquidity"]
    broker_capability = PaperBroker().get_capabilities()
    promo = evaluate_paper_promotion(gate, genome.to_dict(), proof, liq_long,
                                     genome.preferred_regime, broker_capability)

    promotion_decision = {
        "decision": promo.decision,
        "aggression_score": promo.aggression.score,
        "reasons": promo.reasons,
    }

    # 5. build paper execution intent
    intent = build_paper_intent(genome, chain.underlying.symbol, long_leg, short_leg,
                                 promotion_decision, proof)

    # 6. validate intent
    capability = PaperBroker().get_capabilities()
    validation_verdict = validate_intent(intent, capability=capability, fixture_symbols=symbols)

    pipeline_status = "ok"
    fill = {"ok": False, "order_id": "", "paper": True}
    execution_quality: dict = {}
    proof_entry_dict: dict = {}

    # 7. simulate PaperBroker fill (only if validation passes)
    broker = PaperBroker()
    if validation_verdict["valid"]:
        chain_mids = {c.symbol: c.mid() for c in chain.contracts}
        fill = simulate_paper_fill(broker, intent, chain_mids)
        # 8. log execution quality
        liquidity_scores = {c.symbol: liquidity_score(c) for c in chain.contracts}
        execution_quality = build_execution_quality(fill, chain_mids, liquidity_scores)
        # 9. append ProofLedger record
        run_id = f"dopey-paper-pipeline-{intent.intent_id}"
        repro = reproducibility_hash(genome.to_dict(), intent.to_dict(), promotion_decision,
                                    fill, execution_quality, validation_verdict)
        entry = build_proof_entry(
            run_id, genome_dict=genome.to_dict(), intent_dict=intent.to_dict(),
            promotion_decision=promotion_decision, fill=fill, execution_quality=execution_quality,
            validation_verdict=validation_verdict, repro_hash=repro)
        ledger = ProofLedger(ledger_path)
        ledger.append(entry)
        proof_entry_dict = entry.to_dict()
        proof_record_path = str(ledger_path)
    else:
        pipeline_status = "validation_failed"
        proof_record_path = ""

    # 10. concise summary
    live_blocked = True  # always true: paper pipeline never produces live orders
    result = PipelineResult(
        mode=str(cfg.get("mode", "RESEARCH")),
        live_trading_enabled=bool(cfg.get("live_trading_enabled", False)),
        pipeline_status=pipeline_status,
        strategy_id=genome.genome_id,
        execution_intent_id=intent.intent_id,
        paper_order_id=str(fill.get("order_id", "")),
        proof_record_path=proof_record_path,
        live_blocked=live_blocked,
    )
    summary = result.to_dict()
    summary["promotion_decision"] = promotion_decision
    summary["aggression_score"] = promotion_decision["aggression_score"]
    summary["validation_verdict"] = validation_verdict
    summary["paper_fill"] = {"ok": fill.get("ok", False), "order_id": fill.get("order_id", ""),
                             "simulated_fill_price": fill.get("simulated_fill_price", 0.0),
                             "simulated_slippage": fill.get("simulated_slippage", 0.0)}
    summary["execution_quality"] = execution_quality
    summary["proof_record"] = proof_entry_dict
    return summary
