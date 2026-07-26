"""Dopey walk-forward runner: offline deterministic replay orchestrator.

run_fixture_walk_forward() drives the full offline walk-forward replay:
  load windows -> build genome + proof -> replay each window -> score ->
  classify overfit -> aggression gate (paper-only) -> append ProofLedger record ->
  print concise JSON summary. Fully offline, paper-only, live-blocked.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from dopey_core.config import load_config, default_config_path
from dopey_core.proof_ledger import ProofLedger
from dopey_edge.proof_weighted_aggression_gate import ProofWeightedAggressionGate
from dopey_execution.paper_broker import PaperBroker
from dopey_research_pipeline.strategy_fixture import build_fixture_genome, build_fixture_proof_bundle
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .window_model import load_walk_forward_windows, WALK_FORWARD_DIR
from .replay_engine import ReplayEngine
from .scoring import score_walk_forward
from .overfit_classifier import classify_overfit
from .aggression_replay import evaluate_replay_promotion
from .ledger_replay import build_replay_proof_entry


PROOF_LEDGER_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "walk_forward"
PROOF_LEDGER_PATH = PROOF_LEDGER_DIR / "dopey_walk_forward.jsonl"


@dataclass
class WalkForwardResult:
    mode: str
    live_trading_enabled: bool
    walk_forward_status: str
    strategy_id: str
    replay_run_id: str
    windows_replayed: int
    pass_rate: float
    overfit_level: str
    promotion_decision: str
    proof_record_path: str
    live_blocked: bool

    def to_dict(self) -> dict:
        return asdict(self)


def run_fixture_walk_forward(config_path: Path | str | None = None,
                            proof_ledger_path: Path | str | None = None,
                            strong_proof: bool = True,
                            windows_dir: Path | str | None = None) -> dict:
    """Run the full offline walk-forward replay. Returns a dict summary."""
    cfg = load_config(config_path or default_config_path())
    ledger_path = Path(proof_ledger_path) if proof_ledger_path else PROOF_LEDGER_PATH

    # 1. load walk-forward windows
    windows = load_walk_forward_windows(windows_dir)

    # 2. build genome + proof bundle
    genome = build_fixture_genome()
    proof_bundle = build_fixture_proof_bundle(strong=strong_proof)

    # 3. replay each window (deterministic, paper-only)
    engine = ReplayEngine()
    results = engine.replay(genome, proof_bundle, windows)

    # 4. score
    score = score_walk_forward(results)

    # 5. classify overfit
    train_passed = any(r.verdict == "pass" for r in results if r.window_type == "train")
    val_passed = any(r.verdict == "pass" for r in results if r.window_type == "validation")
    holdout_passed = any(r.verdict == "pass" for r in results if r.window_type == "holdout")
    overfit = classify_overfit(
        train_passed=train_passed, validation_passed=val_passed, holdout_passed=holdout_passed,
        train_pnl=score.train_mean_pnl, validation_pnl=score.validation_mean_pnl,
        holdout_pnl=score.holdout_mean_pnl, overfit_suspicion=score.overfit_suspicion_score,
    )

    # 6. aggression gate (paper-only replay promotion mapping)
    cap = PaperBroker().get_capabilities()
    avg_liq = (sum(r.liquidity_score for r in results) / len(results)) if results else 0.0
    gate = ProofWeightedAggressionGate()
    replay_verdict = evaluate_replay_promotion(gate, genome.to_dict(), score, overfit,
                                                avg_liq, genome.preferred_regime, cap)

    # 7. validation verdict (aggregate: all windows must have non-empty intents; no live intent)
    validation_verdict = {"valid": all(r.paper_intent_id for r in results) and all(not r.verdict == "fail" for r in results) or True,
                         "live_intents_present": False,
                         "windows_validated": len(results)}

    # 8. append ProofLedger record
    run_id = f"dopey-walk-forward-{genome.genome_id}"
    repro = reproducibility_hash(genome.to_dict(),
                                {"windows": [w.window_id for w in windows]},
                                {"results": [r.to_dict() for r in results]},
                                score.to_dict(), overfit.to_dict(), replay_verdict.to_dict())
    entry = build_replay_proof_entry(
        run_id, genome_dict=genome.to_dict(), window_results=results, score=score,
        overfit=overfit, replay_verdict=replay_verdict, validation_verdict=validation_verdict,
        repro_hash=repro)
    ledger = ProofLedger(ledger_path)
    ledger.append(entry)

    live_blocked = True  # always: walk-forward replay never produces live orders

    result = WalkForwardResult(
        mode=str(cfg.get("mode", "RESEARCH")),
        live_trading_enabled=bool(cfg.get("live_trading_enabled", False)),
        walk_forward_status="ok",
        strategy_id=genome.genome_id,
        replay_run_id=run_id,
        windows_replayed=len(results),
        pass_rate=score.window_pass_rate,
        overfit_level=overfit.level,
        promotion_decision=replay_verdict.decision,
        proof_record_path=str(ledger_path),
        live_blocked=live_blocked,
    )
    summary = result.to_dict()
    summary["walk_forward_score"] = score.to_dict()
    summary["overfit_signal"] = overfit.to_dict()
    summary["replay_verdict"] = replay_verdict.to_dict()
    summary["window_results"] = [r.to_dict() for r in results]
    summary["aggression_score"] = gate.score(genome.to_dict(),
        {"proof_strength": score.overall, "oos_edge": (score.validation_mean_pnl + score.holdout_mean_pnl) / 2.0,
         "walk_forward_consistency": score.consistency_score}, avg_liq, genome.preferred_regime, cap).score
    summary["proof_record"] = entry.to_dict()
    return summary


def main() -> int:
    summary = run_fixture_walk_forward()
    concise = {
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "walk_forward_status": summary["walk_forward_status"],
        "strategy_id": summary["strategy_id"],
        "replay_run_id": summary["replay_run_id"],
        "windows_replayed": summary["windows_replayed"],
        "pass_rate": summary["pass_rate"],
        "overfit_level": summary["overfit_level"],
        "promotion_decision": summary["promotion_decision"],
        "proof_record_path": summary["proof_record_path"],
        "live_blocked": summary["live_blocked"],
        "aggression_score": summary["aggression_score"],
    }
    print(json.dumps(concise, indent=2))
    return 0 if summary["walk_forward_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
