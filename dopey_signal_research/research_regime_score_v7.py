"""V7 regime scoring (Workstream I component).

Groups V7 trades by regime cohort and computes per-regime metrics.  V7
explicitly separates trade-active (long_call / long_put) profit factor
from total profit factor.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v6_common import TRADES_V6_PATH
from dopey_autonomy.signal_research_v7_common import (
    RESEARCH_V7_ROOT,
    RESEARCH_V7_VERSION,
    TOURNAMENT_REGIME_V7_PATH,
    TRADES_V7_PATH,
    research_v7_proof_record,
    utc_now_iso,
)


REGIME_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_regime_score_v7_proof.jsonl"


__all__ = ["compute_v7_regime_scores"]


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


def _load_trades() -> tuple[list[dict[str, object]], str]:
    trades = _read_jsonl_safe(TRADES_V7_PATH)
    if trades:
        return trades, "v7"
    trades = _read_jsonl_safe(TRADES_V6_PATH)
    return (trades, "v6") if trades else ([], "")


def compute_v7_regime_scores() -> list[dict[str, object]]:
    trades, source_version = _load_trades()
    if not trades:
        return []
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for t in trades:
        key = str(t.get("regime_cohort_id", "unknown"))
        groups[key].append(t)

    records: list[dict[str, object]] = []
    for regime, rows in groups.items():
        total_m = _metrics(rows)
        active_m = _metrics([r for r in rows if _is_trade_active(r)])
        no_trade_count = sum(1 for r in rows if not _is_trade_active(r))
        rec = {
            "artifact_type": "research_tournament_regime_score_v7",
            "regime_cohort_id": regime,
            "sample_count": total_m["sample_count"],
            "trade_active_sample_count": active_m["sample_count"],
            "no_trade_sample_count": no_trade_count,
            "no_trade_ratio": round(
                no_trade_count / total_m["sample_count"], 6
            ) if total_m["sample_count"] else 0.0,
            "net_pnl": total_m["net_pnl"],
            "pf": total_m["pf"],
            "trade_active_pf": active_m["pf"],
            "trade_active_net_pnl": active_m["net_pnl"],
            "data_source_version": source_version,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v7_regime_score() -> dict[str, object]:
    records = compute_v7_regime_scores()
    write_jsonl_file(TOURNAMENT_REGIME_V7_PATH, records)
    summary = {
        "artifact_type": "research_regime_score_v7_summary",
        "regime_score_count": len(records),
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(
        REGIME_V7_PROOF_PATH,
        [research_v7_proof_record("research-regime-score-v7", "regime_scoring_complete_v7", summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v7_regime_score(), indent=2, sort_keys=True, default=str))
