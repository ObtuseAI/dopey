"""V7 holdout scoring (Workstream I component).

Splits V7 trades into in-sample and out-of-sample (holdout) windows and
computes survival metrics per subfamily.  V7 separates trade-active
(long_call / long_put) profit factor from total profit factor so that
no-trade-only cohorts cannot masquerade as breakthroughs.
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
    TOURNAMENT_HOLDOUT_V7_PATH,
    TRADES_V7_PATH,
    research_v7_proof_record,
    utc_now_iso,
)


HOLDOUT_V7_PROOF_PATH = RESEARCH_V7_ROOT / "research_holdout_v7_proof.jsonl"


__all__ = ["compute_v7_holdout_scores"]


HOLDOUT_FRACTION = 0.30
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
        return {
            "sample_count": 0,
            "net_pnl": 0.0,
            "pf": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    pf = (wins / losses) if losses > 0 else (wins if wins > 0 else 0.0)
    expectancy = sum(pnls) / len(pnls)
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in sorted(pnls):
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
    return {
        "sample_count": len(rows),
        "net_pnl": round(sum(pnls), 6),
        "pf": round(pf, 6),
        "expectancy": round(expectancy, 6),
        "max_drawdown": round(-max_dd, 6),
        "win_rate": round(win_rate, 6),
    }


def _trade_active_metrics(rows: list[dict[str, object]]) -> dict[str, float]:
    return _metrics([r for r in rows if _is_trade_active(r)])


def _load_trades() -> tuple[list[dict[str, object]], str]:
    trades = _read_jsonl_safe(TRADES_V7_PATH)
    if trades:
        return trades, "v7"
    trades = _read_jsonl_safe(TRADES_V6_PATH)
    return (trades, "v6") if trades else ([], "")


def compute_v7_holdout_scores() -> list[dict[str, object]]:
    trades, source_version = _load_trades()
    if not trades:
        return []
    trades_sorted = sorted(trades, key=lambda t: str(t.get("trade_id", "")))
    cut = int(len(trades_sorted) * (1.0 - HOLDOUT_FRACTION))
    in_sample = trades_sorted[:cut]
    holdout = trades_sorted[cut:]

    subfamilies: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
        lambda: {"in_sample": [], "holdout": []}
    )
    for t in in_sample:
        subfamilies[str(t.get("stable_subfamily_id", ""))]["in_sample"].append(t)
    for t in holdout:
        subfamilies[str(t.get("stable_subfamily_id", ""))]["holdout"].append(t)

    records: list[dict[str, object]] = []
    for sub, buckets in subfamilies.items():
        if not sub:
            continue
        in_total = _metrics(buckets["in_sample"])
        in_active = _trade_active_metrics(buckets["in_sample"])
        out_total = _metrics(buckets["holdout"])
        out_active = _trade_active_metrics(buckets["holdout"])

        total_survival = (
            out_total["pf"] >= 1.0
            and out_total["net_pnl"] >= 0.0
            and out_total["sample_count"] >= 5
        )
        active_survival = (
            out_active["sample_count"] >= 5
            and out_active["pf"] >= MIN_BREAKTHROUGH_PF
            and out_active["net_pnl"] >= 0.0
        )
        survival = bool(total_survival and active_survival)

        rec = {
            "artifact_type": "research_tournament_holdout_score_v7",
            "stable_subfamily_id": sub,
            "in_sample_sample_count": in_total["sample_count"],
            "in_sample_trade_active_sample_count": in_active["sample_count"],
            "in_sample_net_pnl": in_total["net_pnl"],
            "in_sample_pf": in_total["pf"],
            "in_sample_trade_active_pf": in_active["pf"],
            "in_sample_win_rate": in_total["win_rate"],
            "holdout_sample_count": out_total["sample_count"],
            "holdout_trade_active_sample_count": out_active["sample_count"],
            "holdout_net_pnl": out_total["net_pnl"],
            "holdout_pf": out_total["pf"],
            "holdout_trade_active_pf": out_active["pf"],
            "holdout_win_rate": out_total["win_rate"],
            "holdout_survival": survival,
            "trade_active_survival": active_survival,
            "data_source_version": source_version,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        records.append(record_with_hash(rec, "record_hash"))
    return records


def run_v7_holdout() -> dict[str, object]:
    records = compute_v7_holdout_scores()
    write_jsonl_file(TOURNAMENT_HOLDOUT_V7_PATH, records)
    survival_count = sum(1 for r in records if r["holdout_survival"])
    active_survival_count = sum(1 for r in records if r["trade_active_survival"])
    summary = {
        "artifact_type": "research_holdout_v7_summary",
        "holdout_score_count": len(records),
        "holdout_survival_count": survival_count,
        "trade_active_survival_count": active_survival_count,
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(
        HOLDOUT_V7_PROOF_PATH,
        [research_v7_proof_record("research-holdout-v7", "holdout_scoring_complete_v7", summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_v7_holdout(), indent=2, sort_keys=True, default=str))
