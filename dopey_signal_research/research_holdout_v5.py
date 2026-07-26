"""V5 holdout scoring (Workstream J component).

Splits V5 trades into in-sample and out-of-sample (holdout) windows
and computes survival metrics per family/subfamily/cohort.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    TOURNAMENT_HOLDOUT_V5_PATH,
    TRADES_V5_PATH,
    utc_now_iso,
)


__all__ = ["compute_v5_holdout_scores"]


HOLDOUT_FRACTION = 0.30  # last 30% of trades are holdout


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


def compute_v5_holdout_scores() -> list[dict[str, object]]:
    trades = _read_jsonl_safe(TRADES_V5_PATH)
    if not trades:
        return []
    # Sort by trade_id (deterministic) and split
    trades_sorted = sorted(trades, key=lambda t: str(t.get("trade_id", "")))
    cut = int(len(trades_sorted) * (1.0 - HOLDOUT_FRACTION))
    in_sample = trades_sorted[:cut]
    holdout = trades_sorted[cut:]

    def _metrics(rows: list[dict[str, object]]) -> dict[str, float]:
        pnls = [float(r.get("pnl", 0.0)) for r in rows]
        if not pnls:
            return {"sample_count": 0, "net_pnl": 0.0, "pf": 0.0, "win_rate": 0.0}
        wins = sum(p for p in pnls if p > 0)
        losses = -sum(p for p in pnls if p < 0)
        pf = (wins / losses) if losses > 0 else (wins if wins > 0 else 0.0)
        win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
        return {
            "sample_count": len(rows),
            "net_pnl": round(sum(pnls), 6),
            "pf": round(pf, 6),
            "win_rate": round(win_rate, 6),
        }

    # Group by subfamily
    subfamilies: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
        lambda: {"in_sample": [], "holdout": []}
    )
    for t in in_sample:
        subfamilies[str(t.get("stable_subfamily_id", ""))]["in_sample"].append(t)
    for t in holdout:
        subfamilies[str(t.get("stable_subfamily_id", ""))]["holdout"].append(t)

    records: list[dict[str, object]] = []
    for sub, buckets in subfamilies.items():
        in_m = _metrics(buckets["in_sample"])
        out_m = _metrics(buckets["holdout"])
        # Survival: holdout PF >= 1.0 and net_pnl >= 0
        survival = out_m["pf"] >= 1.0 and out_m["net_pnl"] >= 0.0 and out_m["sample_count"] >= 5
        rec = {
            "artifact_type": "research_tournament_holdout_score_v5",
            "stable_subfamily_id": sub,
            "in_sample_sample_count": in_m["sample_count"],
            "in_sample_net_pnl": in_m["net_pnl"],
            "in_sample_pf": in_m["pf"],
            "in_sample_win_rate": in_m["win_rate"],
            "holdout_sample_count": out_m["sample_count"],
            "holdout_net_pnl": out_m["net_pnl"],
            "holdout_pf": out_m["pf"],
            "holdout_win_rate": out_m["win_rate"],
            "holdout_survival": bool(survival),
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v5_holdout() -> dict[str, object]:
    records = compute_v5_holdout_scores()
    write_jsonl_file(TOURNAMENT_HOLDOUT_V5_PATH, records)
    survival_count = sum(1 for r in records if r["holdout_survival"])
    return {
        "holdout_score_count": len(records),
        "holdout_survival_count": survival_count,
    }


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_holdout(), indent=2, sort_keys=True, default=str))
