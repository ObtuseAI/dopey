"""V6-vs-V7 comparison (Workstream I component).

Compares V7 tournament results against the immutable V6 baseline.  A V7
cohort is only considered improved versus V6 if its *trade-active* profit
factor exceeds the V6 top profit factor and its total profit factor stays
above the hard 1.10 floor.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v6_common import TRADES_V6_PATH
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V7_ROOT,
    RESEARCH_V7_VERSION,
    TOURNAMENT_COMPARISON_V7_PATH,
    TRADES_V7_PATH,
    load_v6_tournament_summary,
    research_v7_proof_record,
    utc_now_iso,
)


COMPARISON_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_v6_v7_comparison_v7_proof.jsonl"


__all__ = ["compute_v6_v7_comparison"]


TRADE_ACTIVE_DIRECTIONS = frozenset({"long_call", "long_put"})


def _read_jsonl_safe(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _is_trade_active(row: dict[str, object]) -> bool:
    return str(row.get("direction", "")).lower() in TRADE_ACTIVE_DIRECTIONS


def _load_trades() -> tuple[list[dict[str, object]], str]:
    trades = _read_jsonl_safe(TRADES_V7_PATH)
    if trades:
        return trades, "v7"
    trades = _read_jsonl_safe(TRADES_V6_PATH)
    return (trades, "v6") if trades else ([], "")


def compute_v6_v7_comparison() -> list[dict[str, object]]:
    v6_tournament = load_v6_tournament_summary()
    v6_top_pf = float(v6_tournament.get("top_profit_factor", 0.0) or 0.0)
    v6_top_net_pnl = float(v6_tournament.get("top_net_pnl", 0.0) or 0.0)
    v6_top_family = str(v6_tournament.get("top_family", ""))
    v6_trade_count = int(v6_tournament.get("trade_count", 0) or 0)

    trades, source_version = _load_trades()
    subfamily_pnl: dict[str, list[float]] = defaultdict(list)
    subfamily_active_pnl: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        sub = str(t.get("stable_subfamily_id", ""))
        if not sub:
            continue
        pnl = float(t.get("pnl", 0.0))
        subfamily_pnl[sub].append(pnl)
        if _is_trade_active(t):
            subfamily_active_pnl[sub].append(pnl)

    def _pf(pnls: list[float]) -> float:
        wins = sum(p for p in pnls if p > 0)
        losses = -sum(p for p in pnls if p < 0)
        if losses > 0:
            return round(wins / losses, 6)
        return round(wins, 6) if wins > 0 else 0.0

    records: list[dict[str, object]] = []
    for sub, pnls in subfamily_pnl.items():
        active_pnls = subfamily_active_pnl.get(sub, [])
        v7_total_pf = _pf(pnls)
        v7_active_pf = _pf(active_pnls)
        v7_total_pnl = round(sum(pnls), 6)
        v7_active_pnl = round(sum(active_pnls), 6)
        improved = (
            active_pnls
            and v7_active_pf > v6_top_pf
            and v7_total_pf >= MIN_BREAKTHROUGH_PF
        )
        rec = {
            "artifact_type": "research_v6_v7_comparison_v7",
            "stable_subfamily_id": sub,
            "v6_top_family": v6_top_family,
            "v6_top_pf": v6_top_pf,
            "v6_top_net_pnl": v6_top_net_pnl,
            "v6_trade_count": v6_trade_count,
            "v7_sample_count": len(pnls),
            "v7_trade_active_sample_count": len(active_pnls),
            "v7_pf": v7_total_pf,
            "v7_trade_active_pf": v7_active_pf,
            "v7_net_pnl": v7_total_pnl,
            "v7_trade_active_net_pnl": v7_active_pnl,
            "improved_vs_v6": improved,
            "data_source_version": source_version,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v6_v7_comparison() -> dict[str, object]:
    records = compute_v6_v7_comparison()
    write_jsonl_file(TOURNAMENT_COMPARISON_V7_PATH, records)
    improved = sum(1 for r in records if r["improved_vs_v6"])
    summary = {
        "artifact_type": "research_v6_v7_comparison_v7_summary",
        "comparison_count": len(records),
        "improved_vs_v6_count": improved,
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(
        COMPARISON_V7_PROOF_PATH,
        [research_v7_proof_record("research-v6-v7-comparison-v7", "comparison_complete_v7", summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v6_v7_comparison(), indent=2, sort_keys=True, default=str))
