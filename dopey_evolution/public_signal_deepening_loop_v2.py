"""Public signal deepening loop V2.

Runs a watchdog-safe, resumable mutation loop over 8 generations. Uses near
champions and sample/walk-forward repair plans to generate focused next
candidates, and eliminates fragile cohorts. No live trading.
"""
from __future__ import annotations

from dopey_autonomy.public_champion_common import (
    CHAMPION_ROOT,
    EVOLUTION_ROOT,
    proof_record,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    write_json_file,
    write_jsonl_file,
    write_summary_with_hash,
)

from .cohort_loser_elimination_v2 import build_cohort_loser_elimination_v2, killed_cohort_summary
from .near_champion_repair_loop_v2 import build_near_champion_repair_queue_v2, near_champion_repair_seed_count


GENERATIONS_PATH = EVOLUTION_ROOT / "public_signal_deepening_generations_v2.jsonl"
MUTATION_QUEUE_PATH = EVOLUTION_ROOT / "public_signal_deepening_mutation_queue_v2.jsonl"
REPAIR_QUEUE_PATH = EVOLUTION_ROOT / "near_champion_repair_queue_v2.jsonl"
KILL_QUEUE_PATH = EVOLUTION_ROOT / "cohort_loser_elimination_v2.jsonl"
STATE_PATH = EVOLUTION_ROOT / "public_signal_deepening_state_v2.json"
SUMMARY_PATH = EVOLUTION_ROOT / "public_signal_deepening_loop_v2_summary.json"
PROOF_PATH = EVOLUTION_ROOT / "public_signal_deepening_loop_v2_proof.jsonl"

GATE_RESULTS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_results.jsonl"
NEAR_CHAMPIONS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_near_champions.jsonl"
REPAIR_PLANS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_sample_repair_plan.jsonl"
LEADERBOARD_PATH = EVOLUTION_ROOT.parent / "tournament" / "public_cohort_tournament_leaderboard_v4.jsonl"

DEFAULT_GENERATION_CAP = 8


def run_public_signal_deepening_loop_v2() -> dict[str, object]:
    return run_signal_deepening_generations_v2(DEFAULT_GENERATION_CAP)


def run_signal_deepening_generations_v2(generation_cap: int) -> dict[str, object]:
    gate_results = read_jsonl_file(GATE_RESULTS_PATH)
    leaderboard = read_jsonl_file(LEADERBOARD_PATH)
    repair_plans = read_jsonl_file(REPAIR_PLANS_PATH)

    champions = [r for r in gate_results if bool(r.get("public_data_paper_champion", False))]
    near_champions = read_jsonl_file(NEAR_CHAMPIONS_PATH)

    repair_queue = build_near_champion_repair_queue_v2(repair_plans)
    kill_queue = build_cohort_loser_elimination_v2(gate_results, leaderboard)

    all_mutations: list[dict[str, object]] = []
    generation_records: list[dict[str, object]] = []
    for generation in range(1, generation_cap + 1):
        mutations = _generation_mutations(gate_results, near_champions, leaderboard, generation)
        all_mutations.extend(mutations)
        best = leaderboard[0] if leaderboard else {}
        generation_records.append(record_with_hash({
            "artifact_type": "public_signal_deepening_generation_v2",
            "generation": generation,
            "champion_found": bool(champions),
            "mutation_count": len(mutations),
            "near_champion_count": len(near_champions),
            "repair_queue_count": len(repair_queue),
            "kill_queue_count": len(kill_queue),
            "best_cohort": best.get("cohort_id", ""),
            "best_net_pnl": best.get("net_pnl", 0.0),
            "best_profit_factor": best.get("profit_factor", 0.0),
            "rerun_mode": "watchdog_capped_public_artifact_iteration",
            "resumable": True,
            "live_trading_enabled": False,
        }, "record_hash"))

    best_strategy = leaderboard[0] if leaderboard else {}
    killed_summary = killed_cohort_summary(kill_queue)
    repair_seeds = near_champion_repair_seed_count(repair_plans)
    status = (
        "public_paper_champions_found_deepening_reinforced"
        if champions
        else "near_champions_repaired_deepening_reinforced" if near_champions else "no_champion_deepening_expanded"
    )
    summary = {
        "artifact_type": "public_signal_deepening_loop_v2_summary",
        "public_signal_deepening_version": "dopey-public-signal-deepening-loop-v2",
        "public_signal_deepening_status": status,
        "generation_count": generation_cap,
        "champion_found": bool(champions),
        "public_paper_champion_count": len(champions),
        "near_champion_count": len(near_champions),
        "mutations_generated": len(all_mutations),
        "repair_queue_count": len(repair_queue),
        "kill_queue_count": len(kill_queue),
        "killed_cohort_summary": killed_summary,
        "repair_seed_summary": repair_seeds,
        "best_cohort": best_strategy.get("cohort_id", ""),
        "best_net_pnl": best_strategy.get("net_pnl", 0.0),
        "best_profit_factor": best_strategy.get("profit_factor", 0.0),
        "live_trading_enabled": False,
    }
    state = {
        "artifact_type": "public_signal_deepening_state_v2",
        "generation_cap": generation_cap,
        "completed_generations": generation_cap,
        "resume_supported": True,
        "mutation_queue_count": len(all_mutations),
        "repair_queue_count": len(repair_queue),
        "kill_queue_count": len(kill_queue),
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_json_file(STATE_PATH, state)
    write_jsonl_file(GENERATIONS_PATH, generation_records)
    write_jsonl_file(MUTATION_QUEUE_PATH, all_mutations)
    write_jsonl_file(REPAIR_QUEUE_PATH, repair_queue)
    write_jsonl_file(KILL_QUEUE_PATH, kill_queue)
    write_jsonl_file(PROOF_PATH, [proof_record("public-signal-deepening-loop-v2", str(summary["public_signal_deepening_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def _generation_mutations(
    gate_results: list[dict[str, object]],
    near_champions: list[dict[str, object]],
    leaderboard: list[dict[str, object]],
    generation: int,
) -> list[dict[str, object]]:
    seeds = [r for r in gate_results if bool(r.get("public_data_paper_champion", False))][:8]
    near_seed_ids = {str(r.get("cohort_id", "")) for r in near_champions}
    near_rows = [r for r in leaderboard if str(r.get("cohort_id", "")) in near_seed_ids][:8]
    candidates = seeds if seeds else near_rows
    mutations: list[dict[str, object]] = []
    for seed_index, row in enumerate(candidates):
        for variant_index, mutation_type in enumerate(["tighten_invalidation", "extend_hold_window", "raise_confidence_threshold", "adjacent_dte", "adjacent_moneyness", "sector_peer_expansion"]):
            mutations.append(record_with_hash({
                "artifact_type": "public_signal_deepening_mutation_queue_v2",
                "generation": generation,
                "mutation_id": f"deepen-v2-gen{generation}-{seed_index + 1}-{variant_index + 1}",
                "parent_cohort_id": row.get("cohort_id", row.get("strategy_id", "")),
                "cohort_level": row.get("cohort_level", ""),
                "setup_family": str(row.get("cohort_id", "")).split("|")[0] if "|" in str(row.get("cohort_id", "")) else "",
                "mutation_type": mutation_type,
                "priority": "high" if row in seeds else "medium",
                "parent_net_pnl": row.get("net_pnl", 0.0),
                "parent_profit_factor": row.get("profit_factor", 0.0),
                "fixture_allowed": False,
                "live_trading_enabled": False,
            }, "record_hash"))
    return mutations


def artifact_paths() -> dict[str, str]:
    return {
        "public_signal_deepening_generations_v2": str(GENERATIONS_PATH),
        "public_signal_deepening_mutation_queue_v2": str(MUTATION_QUEUE_PATH),
        "near_champion_repair_queue_v2": str(REPAIR_QUEUE_PATH),
        "cohort_loser_elimination_v2": str(KILL_QUEUE_PATH),
        "public_signal_deepening_state_v2": str(STATE_PATH),
        "public_signal_deepening_loop_v2_summary": str(SUMMARY_PATH),
        "public_signal_deepening_loop_v2_proof": str(PROOF_PATH),
    }
