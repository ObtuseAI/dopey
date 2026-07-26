"""Run winner promotion, loser elimination, and mutation queue generation."""
from __future__ import annotations

import json

from dopey_wealth_engine.common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl

from .loser_elimination_loop import build_loser_elimination_loop
from .research_mutation_queue import build_research_mutation_queue
from .winner_promotion_loop import build_winner_promotion_loop


ARTIFACT_DIR = ARTIFACT_ROOT / "evolution"
PROMOTION_LOOP_PATH = ARTIFACT_DIR / "winner_promotion_loop.jsonl"
ELIMINATION_LOOP_PATH = ARTIFACT_DIR / "loser_elimination_loop.jsonl"
MUTATION_QUEUE_PATH = ARTIFACT_DIR / "research_mutation_queue.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "evolution_loop_summary.json"
PROOF_PATH = ARTIFACT_DIR / "evolution_loop_proof.jsonl"


def run_winner_loser_evolution_loop() -> dict:
    scores = read_jsonl(ARTIFACT_ROOT / "tournament" / "paper_tournament_strategy_scores.jsonl")
    throttles = read_jsonl(ARTIFACT_ROOT / "risk" / "risk_throttle_records.jsonl")
    promotions = build_winner_promotion_loop(scores, throttles)
    eliminations = build_loser_elimination_loop(scores)
    queue = build_research_mutation_queue(promotions, eliminations)
    summary = {
        "artifact_type": "evolution_loop_summary",
        "evolution_loop_version": "dopey-winner-loser-evolution-v1",
        "evolution_status": "complete" if scores else "blocked_no_scores",
        "winner_promotion_count": len(promotions),
        "loser_elimination_count": len(eliminations),
        "paper_champion_count": sum(1 for record in promotions if record["promotion_level"] == "paper_champion"),
        "public_data_paper_champion_count": sum(1 for record in promotions if record.get("public_data_paper_champion")),
        "fixture_only_champion_count": sum(1 for record in promotions if record.get("fixture_only_champion")),
        "live_gate_candidate_count": sum(1 for record in promotions if record["live_gate_candidate"]),
        "mutation_queue_count": len(queue),
        "direct_live_promotion_allowed": False,
        "paper_strategy_promotion_allowed": True,
        "paper_only": True,
        "live_blocked": True,
        "live_trading_enabled": False,
    }
    if scores:
        summary["registry_write_status"] = "registries_rewritten"
        write_jsonl(PROMOTION_LOOP_PATH, promotions, False)
        write_jsonl(ELIMINATION_LOOP_PATH, eliminations, False)
        write_jsonl(MUTATION_QUEUE_PATH, queue, False)
    else:
        # A blocked run must not overwrite the existing promotion/elimination/
        # mutation registries with empty files: an empty upstream is not
        # evidence that every strategy was eliminated.
        summary["registry_write_status"] = "blocked_registries_preserved"
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("winner-loser-evolution-loop", summary["evolution_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "winner_promotion_loop": str(PROMOTION_LOOP_PATH),
        "loser_elimination_loop": str(ELIMINATION_LOOP_PATH),
        "research_mutation_queue": str(MUTATION_QUEUE_PATH),
        "evolution_loop_summary": str(SUMMARY_PATH),
        "evolution_loop_proof": str(PROOF_PATH),
    }


def main() -> int:
    summary = run_winner_loser_evolution_loop()
    print(json.dumps({
        "evolution_status": summary["evolution_status"],
        "winner_promotion_count": summary["winner_promotion_count"],
        "loser_elimination_count": summary["loser_elimination_count"],
        "registry_write_status": summary["registry_write_status"],
        "summary_path": summary["artifact_paths"]["evolution_loop_summary"],
    }, indent=2, sort_keys=True))
    # A blocked run is not a successful evolution cycle; exit non-zero so
    # schedulers and orchestrators do not record it as green.
    return 0 if summary["evolution_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
