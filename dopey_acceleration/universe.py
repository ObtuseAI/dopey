"""Bridge the protected public lake into governed equity-research candidates."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dopey_market_intake.public_universe_expansion_v2 import candidate_symbol_universe_v2
from dopey_universe.universe_registry import (
    MAX_ACTIVE_UNIVERSE_SIZE,
    UNIVERSE_CAPACITY_POLICY,
    active_universe,
    load_registry,
    record_candidate,
    save_registry,
)

from .common import ARTIFACT_ROOT, REPO_ROOT, stamped, write_json_atomic


PUBLIC_DAILY_ROOT = REPO_ROOT / "dopey_data" / "market_lake" / "public" / "daily_ohlcv"
HISTORY_ROOT = REPO_ROOT / "dopey_data" / "history" / "raw"
PLAN_PATH = ARTIFACT_ROOT / "universe_expansion_plan.json"
SEED_PATH = ARTIFACT_ROOT / "universe_candidate_seed.json"


def _row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def _priority_order(public_symbols: set[str]) -> list[str]:
    canonical = candidate_symbol_universe_v2()
    canonical_rank = {symbol: index for index, symbol in enumerate(canonical)}
    return sorted(public_symbols, key=lambda symbol: (canonical_rank.get(symbol, len(canonical)), symbol))


def build_universe_expansion_plan(repo_root: Path, batch_size: int) -> dict[str, Any]:
    if repo_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(f"repository root mismatch: expected={REPO_ROOT}, actual={repo_root}")
    if batch_size < 1 or batch_size > 50:
        raise ValueError(f"batch_size must be between 1 and 50: actual={batch_size}")
    public_symbols = {path.stem.upper() for path in PUBLIC_DAILY_ROOT.glob("*.csv")}
    history_symbols = {path.stem.upper() for path in HISTORY_ROOT.glob("*.csv")}
    registry = load_registry()
    active_symbol_count = len(active_universe(registry))
    registered = set(str(symbol).upper() for symbol in registry.get("symbols", {}))
    candidates = [symbol for symbol in _priority_order(public_symbols - history_symbols) if symbol not in registered]
    selected = candidates[:batch_size]
    selected_records = [
        {
            "symbol": symbol,
            "priority_rank": index + 1,
            "public_row_count": _row_count(PUBLIC_DAILY_ROOT / f"{symbol}.csv"),
            "source_path": str(PUBLIC_DAILY_ROOT / f"{symbol}.csv"),
            "entry_authority": "governed_candidate_only",
            "options_required_for_equity_research": False,
            "options_required_for_contract_selection": True,
        }
        for index, symbol in enumerate(selected)
    ]
    plan = stamped(
        {
            "artifact_type": "governed_universe_expansion_plan",
            "universe_expansion_version": "dopey-equity-first-universe-bridge-v6",
            "public_lake_symbol_count": len(public_symbols),
            "history_spine_symbol_count": len(history_symbols),
            "registered_non_core_symbol_count": len(registered),
            "active_symbol_count": active_symbol_count,
            "universe_capacity_policy": UNIVERSE_CAPACITY_POLICY,
            "maximum_active_universe_size": MAX_ACTIVE_UNIVERSE_SIZE,
            "available_active_slots": max(MAX_ACTIVE_UNIVERSE_SIZE - active_symbol_count, 0),
            "available_unregistered_public_candidates": len(candidates),
            "selected_batch": selected_records,
            "remaining_after_batch": max(len(candidates) - len(selected), 0),
            "governance": "candidate -> local public history staging -> validator -> standby -> evolving evidence-ranked probation; no automatic core mutation",
            "direction_policy": "stock technicals and fundamentals may research symbols without listed options; options only select contracts",
            "not_edge_evidence": True,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    write_json_atomic(PLAN_PATH, plan)
    return plan


def seed_universe_candidates(repo_root: Path, batch_size: int) -> dict[str, Any]:
    plan = build_universe_expansion_plan(repo_root, batch_size)
    registry = load_registry()
    seeded: list[str] = []
    for record in plan["selected_batch"]:
        symbol = str(record["symbol"])
        registry = record_candidate(
            registry,
            symbol,
            "protected_public_lake_inventory",
            {
                "why": "real public OHLCV already exists locally but is absent from the governed history spine",
                "discovery_score": round(1.0 - 0.005 * int(record["priority_rank"]), 4),
                "public_row_count": int(record["public_row_count"]),
                "public_path": str(record["source_path"]),
                "options_role": "optional_contract_selection_after_equity_direction",
            },
        )
        seeded.append(symbol)
    save_registry(registry)
    result = stamped(
        {
            "artifact_type": "governed_universe_candidate_seed",
            "seeded_symbols": seeded,
            "seeded_count": len(seeded),
            "candidate_only": True,
            "core_mutated": False,
            "validator_bypassed": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    write_json_atomic(SEED_PATH, result)
    return result
