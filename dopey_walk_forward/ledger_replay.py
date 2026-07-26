"""Dopey walk-forward proof-ledger record assembly.

Builds a ProofEntry (compatible with dopey_core.proof_ledger.ProofLedger.append) for a
walk-forward replay run. Produces a reproducibility hash. Offline; no network.
"""
from __future__ import annotations

from datetime import datetime, timezone

from dopey_core.proof_ledger import ProofEntry
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .replay_models import ReplayResult, WalkForwardScore, OverfitSignal, ReplayVerdict


def build_replay_proof_entry(run_id: str, *, genome_dict: dict, window_results: list[ReplayResult],
                            score: WalkForwardScore, overfit: OverfitSignal,
                            replay_verdict: ReplayVerdict, validation_verdict: dict,
                            repro_hash: str) -> ProofEntry:
    """Assemble a ProofEntry for a walk-forward replay run."""
    ts = datetime.now(timezone.utc).isoformat()
    final_status = "PASS" if (replay_verdict.decision in {"replay_promoted_paper_candidate", "paper_candidate"}) else (
        "PASS_WITH_NOTES" if replay_verdict.decision == "research_only" else "FAIL")
    return ProofEntry(
        run_id=run_id,
        task_id=genome_dict.get("genome_id", "unknown"),
        timestamp=ts,
        input_hash=repro_hash,
        plan_hash=reproducibility_hash(genome_dict),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "window_results": [r.to_dict() for r in window_results],
            "walk_forward_score": score.to_dict(),
            "overfit_signal": overfit.to_dict(),
            "replay_verdict": replay_verdict.to_dict(),
        },
        validation_result="VALIDATION_PASS" if validation_verdict.get("valid") else "VALIDATION_FAIL",
        repair_attempts=0,
        artifacts=[r.window_id for r in window_results],
        diffs=[],
        test_results={
            "validation_verdict": validation_verdict,
            "replay_verdict": replay_verdict.to_dict(),
            "overfit_signal": overfit.to_dict(),
        },
        final_status=final_status,
        lessons_candidate=[],
        promotion_candidate=[replay_verdict.to_dict()] if replay_verdict.decision in {
            "replay_promoted_paper_candidate", "paper_candidate"} else [],
        limitations=[
            "fixture-based offline walk-forward replay; no live execution; no real market quality implied",
            "deterministic simulated exits; no network or credentials used",
            "paper-only promotion target; live promotion is impossible from this path",
        ],
    )
