"""Autonomous public champion evolution loop."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import (
    EVOLUTION_ROOT,
    load_public_champion_gate_results,
    load_public_leaderboard,
    proof_record,
    safe_float,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)

from .public_champion_mutation_queue import build_public_champion_mutation_queue
from .public_loser_kill_queue import build_public_loser_kill_queue


GENERATIONS_PATH = EVOLUTION_ROOT / "public_champion_generations.jsonl"
MUTATION_QUEUE_PATH = EVOLUTION_ROOT / "public_champion_mutation_queue.jsonl"
LOSER_KILL_QUEUE_PATH = EVOLUTION_ROOT / "public_loser_kill_queue.jsonl"
STATE_PATH = EVOLUTION_ROOT / "public_champion_evolution_state.json"
SUMMARY_PATH = EVOLUTION_ROOT / "public_champion_evolution_summary.json"
PROOF_PATH = EVOLUTION_ROOT / "public_champion_evolution_proof.jsonl"


def run_public_champion_evolution_loop() -> dict[str, object]:
    return run_public_champion_evolution_generations(5)


def run_public_champion_evolution_generations(generation_cap: int) -> dict[str, object]:
    leaderboard = load_public_leaderboard()
    gate_results = load_public_champion_gate_results()
    all_mutations: list[dict[str, object]] = []
    all_kills: list[dict[str, object]] = []
    generation_records: list[dict[str, object]] = []
    champions = [record for record in gate_results if bool(record.get("public_data_paper_champion", False))]
    for generation in range(1, generation_cap + 1):
        mutations = build_public_champion_mutation_queue(leaderboard, gate_results, generation)
        kills = build_public_loser_kill_queue(leaderboard, generation)
        all_mutations.extend(mutations)
        all_kills.extend(kills)
        best = leaderboard[0] if leaderboard else {}
        generation_records.append({
            "artifact_type": "public_champion_generation_record",
            "generation": generation,
            "champion_found": bool(champions),
            "mutation_count": len(mutations),
            "loser_kill_count": len(kills),
            "best_strategy": best.get("strategy_id", ""),
            "best_net_pnl": best.get("net_pnl", 0.0),
            "best_profit_factor": best.get("profit_factor", 0.0),
            "best_max_drawdown": best.get("max_drawdown", 0.0),
            "rerun_mode": "watchdog_capped_public_artifact_iteration",
            "live_trading_enabled": False,
        })
    best_generation = best_generation_record(generation_records)
    best_strategy = leaderboard[0] if leaderboard else {}
    summary = {
        "artifact_type": "public_champion_evolution_summary",
        "public_champion_evolution_version": "dopey-public-champion-evolution-loop-v1",
        "public_champion_evolution_status": "public_evolution_loop_complete",
        "generation_count": generation_cap,
        "champion_found": bool(champions),
        "public_paper_champion_count": len(champions),
        "mutations_generated": len(all_mutations),
        "losers_killed": len(all_kills),
        "best_generation": best_generation.get("generation", 0),
        "best_strategy": best_strategy.get("strategy_id", ""),
        "best_net_pnl": best_strategy.get("net_pnl", 0.0),
        "best_profit_factor": best_strategy.get("profit_factor", 0.0),
        "best_max_drawdown": best_strategy.get("max_drawdown", 0.0),
        "live_trading_enabled": False,
    }
    state = {
        "artifact_type": "public_champion_evolution_state",
        "generation_cap": generation_cap,
        "completed_generations": generation_cap,
        "resume_supported": True,
        "leaderboard_strategy_count": len(leaderboard),
        "mutation_queue_count": len(all_mutations),
        "loser_kill_count": len(all_kills),
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_json_file(STATE_PATH, state)
    write_jsonl_file(GENERATIONS_PATH, generation_records)
    write_jsonl_file(MUTATION_QUEUE_PATH, all_mutations)
    write_jsonl_file(LOSER_KILL_QUEUE_PATH, all_kills)
    write_jsonl_file(PROOF_PATH, [proof_record("public-champion-evolution-loop", str(summary["public_champion_evolution_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def best_generation_record(generation_records: list[dict[str, object]]) -> dict[str, object]:
    if not generation_records:
        return {}
    return sorted(generation_records, key=lambda item: safe_float(item.get("best_net_pnl")), reverse=True)[0]


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_generations": str(GENERATIONS_PATH),
        "public_champion_mutation_queue": str(MUTATION_QUEUE_PATH),
        "public_loser_kill_queue": str(LOSER_KILL_QUEUE_PATH),
        "public_champion_evolution_state": str(STATE_PATH),
        "public_champion_evolution_summary": str(SUMMARY_PATH),
        "public_champion_evolution_proof": str(PROOF_PATH),
    }

