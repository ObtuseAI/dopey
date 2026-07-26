"""Per-symbol dossiers: the "self-understanding" half of the universe governor.

Every ACTIVE symbol gets a refreshed dossier each run: what it is (role,
provenance), how healthy its data is (bars, frontier lag), how liquid it
trades (20d average dollar volume), and how USEFUL it has actually been to
the research stack (gated signals generated, best screener rank, forward-walk
participation). Usefulness is a documented mechanical score for HOUSEKEEPING
decisions only - it is never edge evidence and never touches the truth layer.

Improvement = recommendations, not action: quality-based retirement of a
probation name requires a human; core names only ever get flagged.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE

from .universe_registry import active_universe, symbol_tier

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_RAW_DIR = REPO_ROOT / "dopey_data" / "history" / "raw"
SIGNALS_PATH = REPO_ROOT / "artifacts" / "dopey" / "signals" / "directional_setup_signals.jsonl"
SCREENER_TARGETS_PATH = REPO_ROOT / "artifacts" / "dopey" / "screener" / "screener_targets.jsonl"
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"

USEFULNESS_RETIRE_THRESHOLD = 0.15
USELESS_RUNS_BEFORE_RECOMMEND = 5
SECTOR_ETFS = frozenset({"SPY", "QQQ", "DIA", "IWM", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"})
CRYPTO_PROXIES = frozenset({"IBIT", "MSTR", "COIN"})


CONTEXT_ONLY = frozenset({"VIX"})


def _role(symbol: str, registry: dict) -> str:
    if symbol in CONTEXT_ONLY or symbol.startswith("^"):
        return "context_only_volatility_index"
    if symbol in SECTOR_ETFS:
        return "index_or_sector_etf"
    if symbol in CRYPTO_PROXIES:
        return "crypto_proxy"
    if symbol_tier(symbol, registry) == "probation":
        return "discovered_probation"
    return "core_single_name"


def _tail_rows(symbol: str, count: int = 25) -> list[tuple[str, float, float]]:
    """(date, adjusted_close, volume) for the last `count` rows."""
    path = HISTORY_RAW_DIR / f"{symbol}.csv"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[tuple[str, float, float]] = []
    for line in lines[-count:]:
        parts = line.split(",")
        if len(parts) >= 8 and parts[0] != "date":
            try:
                rows.append((parts[0], float(parts[6]), float(parts[7])))
            except ValueError:
                continue
    return rows


def _jsonl_symbols(path: Path, key: str = "symbol") -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            symbol = str(record.get(key, ""))
            if symbol:
                counts[symbol] = counts.get(symbol, 0) + 1
    except OSError:
        pass
    return counts


def _screener_best_rank() -> dict[str, int]:
    best: dict[str, int] = {}
    try:
        for line in SCREENER_TARGETS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            symbol = str(record.get("symbol", ""))
            rank = record.get("rank")
            if symbol and isinstance(rank, int):
                best[symbol] = min(best.get(symbol, rank), rank)
    except OSError:
        pass
    return best


def build_dossiers(registry: dict) -> tuple[dict, list[dict], list[dict]]:
    """Refresh dossiers for every ACTIVE symbol; return (registry, dossiers,
    retire_recommendations)."""
    signal_counts = _jsonl_symbols(SIGNALS_PATH)
    screen_ranks = _screener_best_rank()
    try:
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        ledger = {}
    walk_symbols: dict[str, int] = {}
    for position in ledger.get("open_positions", []) + ledger.get("closed_trades", []):
        symbol = str(position.get("symbol", ""))
        if symbol:
            walk_symbols[symbol] = walk_symbols.get(symbol, 0) + 1

    frontier_dates = []
    dossiers: list[dict] = []
    recommendations: list[dict] = []
    rows_by_symbol = {symbol: _tail_rows(symbol) for symbol in active_universe(registry)}
    for rows in rows_by_symbol.values():
        if rows:
            frontier_dates.append(rows[-1][0])
    core_frontier = max(frontier_dates) if frontier_dates else ""

    for symbol, rows in sorted(rows_by_symbol.items()):
        tier = symbol_tier(symbol, registry)
        adv_usd = 0.0
        if rows:
            recent = rows[-20:]
            adv_usd = sum(price * volume for _, price, volume in recent) / max(len(recent), 1)
        frontier_lag = 0
        if rows and core_frontier:
            frontier_lag = 0 if rows[-1][0] >= core_frontier else min(9, sum(1 for d in frontier_dates if d > rows[-1][0]))
        signals = signal_counts.get(symbol, 0)
        best_rank = screen_ranks.get(symbol)
        walk_count = walk_symbols.get(symbol, 0)
        # documented mechanical usefulness: liquidity floor + research traction
        usefulness = round(min(1.0, (
            (0.25 if adv_usd >= 5_000_000 else adv_usd / 20_000_000)
            + min(0.35, signals / 4000.0)
            + (0.25 if best_rank is not None and best_rank <= 10 else 0.0)
            + min(0.15, walk_count * 0.05)
        )), 4)
        dossier = {
            "symbol": symbol,
            "tier": tier,
            "role": _role(symbol, registry),
            "why_in_universe": (
                "code-floor governance anchor" if symbol in REQUIRED_HISTORY_UNIVERSE
                else str(registry.get("symbols", {}).get(symbol, {}).get("why", ""))
            ),
            "data_health": {"bars_recent": len(rows), "last_date": rows[-1][0] if rows else "", "frontier_lag_sessions": frontier_lag},
            "avg_dollar_volume_20d": round(adv_usd, 2),
            "gated_signals_total": signals,
            "screener_best_rank": best_rank,
            "forward_walk_participation": walk_count,
            "usefulness_score": usefulness,
            "not_edge_evidence": True,
        }
        dossiers.append(dossier)
        if symbol in registry.get("symbols", {}):
            registry["symbols"][symbol]["dossier"] = dossier
            runs_useless = int(registry["symbols"][symbol].get("useless_runs", 0))
            runs_useless = runs_useless + 1 if usefulness < USEFULNESS_RETIRE_THRESHOLD else 0
            registry["symbols"][symbol]["useless_runs"] = runs_useless
            if tier == "probation" and runs_useless >= USELESS_RUNS_BEFORE_RECOMMEND:
                recommendations.append({
                    "symbol": symbol,
                    "recommendation": "retire_probation_symbol",
                    "reason": f"usefulness {usefulness} below {USEFULNESS_RETIRE_THRESHOLD} for {runs_useless} consecutive runs",
                    "action_required": "human confirms; machinery never quality-retires on its own",
                })
        elif (
            usefulness < USEFULNESS_RETIRE_THRESHOLD
            and symbol in REQUIRED_HISTORY_UNIVERSE
            and dossier["role"] != "context_only_volatility_index"  # context names are useful BY not trading
        ):
            recommendations.append({
                "symbol": symbol,
                "recommendation": "review_core_symbol_usefulness",
                "reason": f"core name usefulness {usefulness} - flag only, core is never auto-touched",
                "action_required": "human review only",
            })
    return registry, dossiers, recommendations
