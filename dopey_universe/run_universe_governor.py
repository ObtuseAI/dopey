"""Universe governor runner (supervisor stage 30) - fully OFFLINE.

One cycle: load registry -> discover candidates from already-fetched lane
files -> refresh every active symbol's dossier -> emit recommendations ->
write the bounded staging queue for the operator ritual's network lane ->
persist registry + summary. No network, no data staging, no code changes -
the governor understands and proposes; the governed gates and the human stay
in charge of what actually enters the spine.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .discovery_engine import build_staging_queue, discover_candidates
from .evolving_universe import run_evolving_universe_cycle
from .symbol_dossier import build_dossiers
from .universe_registry import (
    MAX_ACTIVE_UNIVERSE_SIZE,
    UNIVERSE_ARTIFACT_DIR,
    UNIVERSE_CAPACITY_POLICY,
    active_universe,
    load_registry,
    save_registry,
    tier_counts,
)

STAGING_QUEUE_PATH = UNIVERSE_ARTIFACT_DIR / "staging_queue.json"
UNIVERSE_SUMMARY_PATH = UNIVERSE_ARTIFACT_DIR / "universe_summary.json"
UNIVERSE_DOSSIERS_PATH = UNIVERSE_ARTIFACT_DIR / "symbol_dossiers.jsonl"


def run_universe_governor() -> dict:
    UNIVERSE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cycle_time = datetime.now(timezone.utc)
    registry = load_registry()
    registry, discovered = discover_candidates(registry)
    registry, evolution = run_evolving_universe_cycle(registry, cycle_time)
    registry, dossiers, recommendations = build_dossiers(registry)
    queue = build_staging_queue(registry, discovered)

    STAGING_QUEUE_PATH.write_text(json.dumps({
        "artifact_type": "universe_staging_queue",
        "generated_utc": cycle_time.isoformat(),
        "queue": queue,
        "semantics": "candidates for the operator ritual's governed staging lane - nothing is fetched or entered by this artifact",
        "paper_only": True,
        "live_blocked": True,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with UNIVERSE_DOSSIERS_PATH.open("w", encoding="utf-8") as handle:
        for dossier in dossiers:
            handle.write(json.dumps(dossier, sort_keys=True) + "\n")

    save_registry(registry)
    counts = tier_counts(registry)
    active_size = len(active_universe(registry))
    summary = {
        "artifact_type": "universe_summary",
        "generated_utc": cycle_time.isoformat(),
        "universe_status": "universe_governed",
        "active_universe_size": active_size,
        "universe_capacity_policy": UNIVERSE_CAPACITY_POLICY,
        "maximum_active_universe_size": MAX_ACTIVE_UNIVERSE_SIZE,
        "available_active_slots": max(MAX_ACTIVE_UNIVERSE_SIZE - active_size, 0),
        "evolution_status": evolution["status"],
        "promoted_this_run": evolution["promoted_symbols"],
        "demoted_this_run": evolution["demoted_symbols"],
        "evolution_reproducibility_hash": evolution["reproducibility_hash"],
        "tier_counts": counts,
        "discovered_this_run": [entry["symbol"] for entry in discovered],
        "staging_queue": [entry["symbol"] for entry in queue],
        "retire_recommendations": recommendations,
        "governance": {
            "core_floor_authority": "REQUIRED_HISTORY_UNIVERSE (code + validator); never auto-touched",
            "expansion_path": "candidate -> operator ritual probes + validator staging -> standby -> evidence-ranked probation",
            "improvement_path": "attention + liquidity + market cap + research tradability -> promote/retain/demote; mechanical death -> quarantine",
            "membership_history": "all non-core transitions retain content-addressed reasons; no staged history is deleted",
        },
        "paper_only": True,
        "live_blocked": True,
        "not_edge_evidence": True,
    }
    UNIVERSE_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run_universe_governor()
    print(json.dumps({
        "universe_status": result["universe_status"],
        "active_size": result["active_universe_size"],
        "discovered": result["discovered_this_run"],
        "staging_queue": result["staging_queue"],
        "recommendations": len(result["retire_recommendations"]),
    }, indent=2))
