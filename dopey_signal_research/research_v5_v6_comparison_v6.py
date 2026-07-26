"""V5-vs-V6 comparison (Workstream H component).

Compares V6 tournament results against the immutable V5 baseline.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v6_common import (
    BASELINE_V5_ROOT,
    TOURNAMENT_COMPARISON_V6_PATH,
    TRADES_V6_PATH,
    utc_now_iso,
)


__all__ = ["compute_v5_v6_comparison"]


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


def compute_v5_v6_comparison() -> list[dict[str, object]]:
    v5_tournament = _read_json_safe(BASELINE_V5_ROOT / "research_tournament_v5_summary.json")
    if not v5_tournament:
        # Fallback to live V5 tournament summary if baseline snapshot missing
        from dopey_autonomy.signal_research_v6_common import load_v5_tournament_summary

        v5_tournament = load_v5_tournament_summary()
    v5_top_pf = float(v5_tournament.get("top_profit_factor", 0.0) or 0.0)
    v5_top_net_pnl = float(v5_tournament.get("top_net_pnl", 0.0) or 0.0)
    v5_top_family = str(v5_tournament.get("top_family", ""))
    v5_trade_count = int(v5_tournament.get("trade_count", 0) or 0)

    trades = _read_jsonl_safe(TRADES_V6_PATH)
    subfamily_pnl: dict[str, list[float]] = defaultdict(list)
    family_pnl: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        subfamily_pnl[str(t.get("stable_subfamily_id", ""))].append(float(t.get("pnl", 0.0)))
        family_pnl[str(t.get("stable_family_id", ""))].append(float(t.get("pnl", 0.0)))

    records: list[dict[str, object]] = []
    for sub, pnls in subfamily_pnl.items():
        wins = sum(p for p in pnls if p > 0)
        losses = -sum(p for p in pnls if p < 0)
        v6_pf = (wins / losses) if losses > 0 else (wins if wins > 0 else 0.0)
        v6_pnl = sum(pnls)
        rec = {
            "artifact_type": "research_v5_v6_comparison_v6",
            "stable_subfamily_id": sub,
            "v5_top_family": v5_top_family,
            "v5_top_pf": v5_top_pf,
            "v5_top_net_pnl": v5_top_net_pnl,
            "v5_trade_count": v5_trade_count,
            "v6_sample_count": len(pnls),
            "v6_pf": round(v6_pf, 6),
            "v6_net_pnl": round(v6_pnl, 6),
            "improved_vs_v5": v6_pf > v5_top_pf,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v5_v6_comparison() -> dict[str, object]:
    records = compute_v5_v6_comparison()
    write_jsonl_file(TOURNAMENT_COMPARISON_V6_PATH, records)
    improved = sum(1 for r in records if r["improved_vs_v5"])
    return {
        "comparison_count": len(records),
        "improved_vs_v5_count": improved,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_v6_comparison(), indent=2, sort_keys=True, default=str))
