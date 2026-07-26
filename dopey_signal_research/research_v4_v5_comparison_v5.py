"""V4-vs-V5 comparison (Workstream J component).

Compares V5 tournament results against the immutable V4 baseline.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    BASELINE_V4_ROOT,
    TOURNAMENT_COMPARISON_V5_PATH,
    TRADES_V5_PATH,
    utc_now_iso,
)


__all__ = ["compute_v4_v5_comparison"]


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


def _read_json_safe(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def compute_v4_v5_comparison() -> list[dict[str, object]]:
    v4_tournament = _read_json_safe(BASELINE_V4_ROOT / "research_tournament_v4_summary.json")
    v4_top_pf = float(v4_tournament.get("top_profit_factor", 0.0) or 0.0)
    v4_top_net_pnl = float(v4_tournament.get("top_net_pnl", 0.0) or 0.0)
    v4_top_family = str(v4_tournament.get("top_family", ""))
    v4_trade_count = int(v4_tournament.get("trade_count", 0) or 0)

    # V5 metrics from trades
    trades = _read_jsonl_safe(TRADES_V5_PATH)
    subfamily_pnl: dict[str, list[float]] = defaultdict(list)
    family_pnl: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        subfamily_pnl[str(t.get("stable_subfamily_id", ""))].append(float(t.get("pnl", 0.0)))
        family_pnl[str(t.get("stable_family_id", ""))].append(float(t.get("pnl", 0.0)))

    records: list[dict[str, object]] = []
    for sub, pnls in subfamily_pnl.items():
        wins = sum(p for p in pnls if p > 0)
        losses = -sum(p for p in pnls if p < 0)
        v5_pf = (wins / losses) if losses > 0 else (wins if wins > 0 else 0.0)
        v5_pnl = sum(pnls)
        rec = {
            "artifact_type": "research_v4_v5_comparison_v5",
            "stable_subfamily_id": sub,
            "v4_top_family": v4_top_family,
            "v4_top_pf": v4_top_pf,
            "v4_top_net_pnl": v4_top_net_pnl,
            "v4_trade_count": v4_trade_count,
            "v5_sample_count": len(pnls),
            "v5_pf": round(v5_pf, 6),
            "v5_net_pnl": round(v5_pnl, 6),
            "improved_vs_v4": v5_pf > v4_top_pf,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v4_v5_comparison() -> dict[str, object]:
    records = compute_v4_v5_comparison()
    write_jsonl_file(TOURNAMENT_COMPARISON_V5_PATH, records)
    improved = sum(1 for r in records if r["improved_vs_v4"])
    return {
        "comparison_count": len(records),
        "improved_vs_v4_count": improved,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v4_v5_comparison(), indent=2, sort_keys=True, default=str))
