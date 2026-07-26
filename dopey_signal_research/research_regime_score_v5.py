"""V5 regime scoring (Workstream J component).

Groups V5 trades by regime cohort and computes per-regime metrics.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v5_common import (
    TOURNAMENT_REGIME_V5_PATH,
    TRADES_V5_PATH,
    utc_now_iso,
)


__all__ = ["compute_v5_regime_scores"]


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


def _metrics(rows: list[dict[str, object]]) -> dict[str, float]:
    pnls = [float(r.get("pnl", 0.0)) for r in rows]
    if not pnls:
        return {"sample_count": 0, "net_pnl": 0.0, "pf": 0.0}
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    pf = (wins / losses) if losses > 0 else (wins if wins > 0 else 0.0)
    return {
        "sample_count": len(rows),
        "net_pnl": round(sum(pnls), 6),
        "pf": round(pf, 6),
    }


def compute_v5_regime_scores() -> list[dict[str, object]]:
    trades = _read_jsonl_safe(TRADES_V5_PATH)
    if not trades:
        return []
    # Group by regime_cohort_id
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for t in trades:
        key = str(t.get("regime_cohort_id", "unknown"))
        groups[key].append(t)
    records: list[dict[str, object]] = []
    for regime, rows in groups.items():
        m = _metrics(rows)
        rec = {
            "artifact_type": "research_tournament_regime_score_v5",
            "regime_cohort_id": regime,
            "sample_count": m["sample_count"],
            "net_pnl": m["net_pnl"],
            "pf": m["pf"],
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v5_regime_score() -> dict[str, object]:
    records = compute_v5_regime_scores()
    write_jsonl_file(TOURNAMENT_REGIME_V5_PATH, records)
    return {"regime_score_count": len(records)}


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v5_regime_score(), indent=2, sort_keys=True, default=str))
