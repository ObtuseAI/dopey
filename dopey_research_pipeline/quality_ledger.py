"""Dopey pipeline execution quality + proof-ledger record assembly.

Builds a structured execution-quality object from the paper fill, and assembles a ProofEntry
(compatible with dopey_core.proof_ledger.ProofLedger.append) for the pipeline run. Produces a
reproducibility hash. Everything is deterministic and offline.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from dopey_core.proof_ledger import ProofEntry


def build_execution_quality(fill: dict, chain_mids: dict[str, float],
                            liquidity_scores: dict[str, float]) -> dict:
    """Return a structured execution-quality object from a paper fill."""
    legs = fill.get("legs", [])
    spread_widths = []
    for leg in legs:
        mid = leg.get("requested_mid", 0.0)
        slip = abs(leg.get("simulated_slippage", 0.0))
        spread_widths.append(round(slip * 2.0, 6) if mid else 0.0)
    avg_spread = round(sum(spread_widths) / len(spread_widths), 6) if spread_widths else 0.0
    avg_liq = round(
        sum(liquidity_scores.get(l.get("symbol", ""), 0.0) for l in legs) / max(len(legs), 1), 6)
    return {
        "expected_net_mid": fill.get("requested_net_price", 0.0),
        "simulated_fill": fill.get("simulated_fill_price", 0.0),
        "simulated_slippage": fill.get("simulated_slippage", 0.0),
        "spread_width_estimate": avg_spread,
        "liquidity_score_avg": avg_liq,
        "paper_only": True,
        "execution_status": "simulated_paper_filled",
    }


def reproducibility_hash(*parts: dict) -> str:
    """Deterministic SHA256 over the JSON of the given parts (sorted keys)."""
    blob = json.dumps([p for p in parts], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_proof_entry(run_id: str, *, genome_dict: dict, intent_dict: dict, promotion_decision: dict,
                      fill: dict, execution_quality: dict, validation_verdict: dict,
                      repro_hash: str) -> ProofEntry:
    """Assemble a ProofEntry for the pipeline run, compatible with ProofLedger.append."""
    ts = datetime.now(timezone.utc).isoformat()
    final_status = "PASS" if (fill.get("ok") and validation_verdict.get("valid")) else "FAIL"
    return ProofEntry(
        run_id=run_id,
        task_id=genome_dict.get("genome_id", "unknown"),
        timestamp=ts,
        input_hash=repro_hash,
        plan_hash=reproducibility_hash(genome_dict),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "fill": fill,
            "execution_quality": execution_quality,
        },
        validation_result="VALIDATION_PASS" if validation_verdict.get("valid") else "VALIDATION_FAIL",
        repair_attempts=0,
        artifacts=[intent_dict.get("intent_id", ""), fill.get("order_id", "")],
        diffs=[],
        test_results={
            "validation_verdict": validation_verdict,
            "promotion_decision": promotion_decision,
        },
        final_status=final_status,
        lessons_candidate=[],
        promotion_candidate=[promotion_decision] if promotion_decision.get("decision") == "paper_candidate" else [],
        limitations=[
            "paper-only simulated fill; no live execution; no real market quality implied",
            "fixture-based offline run; no network or credentials used",
        ],
    )
