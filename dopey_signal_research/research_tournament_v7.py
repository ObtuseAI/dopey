"""V7 research tournament (Workstream I).

Aggregates V7 trade-level metrics into per-family / per-subfamily /
per-cohort leaderboards, compares to the immutable V6 baseline, and
separates trade-active (long_call / long_put) profit factor from total
profit factor.  No-trade-only cohorts are surfaced but never allowed to
rank as breakthroughs.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import TRADES_V6_PATH
from dopey_autonomy.signal_research_v7_common import (
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V7_VERSION,
    TOURNAMENT_COMPARISON_V7_PATH,
    TOURNAMENT_HOLDOUT_V7_PATH,
    TOURNAMENT_LEADERBOARD_V7_PATH,
    TOURNAMENT_REGIME_V7_PATH,
    TOURNAMENT_SCORES_V7_PATH,
    TOURNAMENT_V7_PROOF_PATH,
    TOURNAMENT_V7_SUMMARY_PATH,
    TRADES_V7_PATH,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    load_v6_tournament_summary,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_signal_research.research_holdout_v7 import compute_v7_holdout_scores
from dopey_signal_research.research_regime_score_v7 import compute_v7_regime_scores
from dopey_signal_research.research_v6_v7_comparison_v7 import compute_v6_v7_comparison


__all__ = ["run_research_tournament_v7"]


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


def _load_trades() -> tuple[list[dict[str, object]], str]:
    trades = _read_jsonl_safe(TRADES_V7_PATH)
    if trades:
        return trades, "v7"
    trades = _read_jsonl_safe(TRADES_V6_PATH)
    return (trades, "v6") if trades else ([], "")


def _rank_score(record: dict[str, object]) -> tuple[float, float, float]:
    """Rank by qualified-tier, then trade-active PF, then total PF."""
    active_pf = float(record.get("trade_active_profit_factor", 0.0))
    active_samples = int(record.get("trade_active_sample_count", 0))
    total_pf = float(record.get("profit_factor", 0.0))
    if active_samples >= V7_MIN_TRADE_ACTIVE_SAMPLE and active_pf >= MIN_BREAKTHROUGH_PF:
        return (1.0, active_pf, total_pf)
    return (0.0, active_pf, total_pf)


def run_research_tournament_v7() -> dict[str, object]:
    trades, source_version = _load_trades()

    by_sub: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_cohort: dict[str, list[dict[str, object]]] = defaultdict(list)
    for t in trades:
        by_sub[str(t.get("stable_subfamily_id", ""))].append(t)
        by_family[str(t.get("stable_family_id", ""))].append(t)
        by_cohort[str(t.get("cohort_id", ""))].append(t)

    scores: list[dict[str, object]] = []
    leaderboard: list[dict[str, object]] = []
    for sub, rows in by_sub.items():
        if not sub:
            continue
        total_m = _metrics(rows)
        active_rows = [r for r in rows if _is_trade_active(r)]
        active_m = _metrics(active_rows)
        no_trade_count = sum(1 for r in rows if not _is_trade_active(r))
        no_trade_ratio = (
            round(no_trade_count / total_m["sample_count"], 6)
            if total_m["sample_count"]
            else 0.0
        )
        symbols = {str(r.get("symbol", "")) for r in rows}
        sectors = {str(r.get("sector", "")) for r in rows}
        family = str(rows[0].get("stable_family_id", "")) if rows else ""
        cohort = str(rows[0].get("cohort_id", "")) if rows else ""
        score = {
            "artifact_type": "research_tournament_score_v7",
            "stable_subfamily_id": sub,
            "stable_family_id": family,
            "cohort_id": cohort,
            "sample_count": total_m["sample_count"],
            "trade_active_sample_count": active_m["sample_count"],
            "no_trade_sample_count": no_trade_count,
            "no_trade_ratio": no_trade_ratio,
            "no_trade_only": no_trade_count == total_m["sample_count"] and total_m["sample_count"] > 0,
            "symbol_count": len(symbols),
            "sector_count": len(sectors),
            "net_pnl": total_m["net_pnl"],
            "profit_factor": total_m["pf"],
            "trade_active_profit_factor": active_m["pf"],
            "trade_active_net_pnl": active_m["net_pnl"],
            "expectancy": total_m["expectancy"],
            "max_drawdown": total_m["max_drawdown"],
            "win_rate": total_m["win_rate"],
            "data_source_version": source_version,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        scores.append(record_with_hash(score, "record_hash"))
        leaderboard.append({"artifact_type": "research_tournament_leaderboard_v7", **score})

    write_jsonl_file(TOURNAMENT_SCORES_V7_PATH, scores)
    write_jsonl_file(TOURNAMENT_LEADERBOARD_V7_PATH, leaderboard)

    holdout_records = compute_v7_holdout_scores()
    write_jsonl_file(TOURNAMENT_HOLDOUT_V7_PATH, holdout_records)
    regime_records = compute_v7_regime_scores()
    write_jsonl_file(TOURNAMENT_REGIME_V7_PATH, regime_records)
    comparison_records = compute_v6_v7_comparison()
    write_jsonl_file(TOURNAMENT_COMPARISON_V7_PATH, comparison_records)

    if not leaderboard:
        top = {
            "top_family": "",
            "top_subfamily": "",
            "top_cohort": "",
            "top_net_pnl": 0.0,
            "top_profit_factor": 0.0,
            "top_trade_active_profit_factor": 0.0,
            "top_max_drawdown": 0.0,
            "top_sample_count": 0,
            "top_trade_active_sample_count": 0,
            "top_symbol_count": 0,
            "top_sector_count": 0,
            "top_split_pass_rate": 0.0,
            "top_no_trade_ratio": 0.0,
        }
    else:
        top_row = max(leaderboard, key=_rank_score)
        top = {
            "top_family": top_row["stable_family_id"],
            "top_subfamily": top_row["stable_subfamily_id"],
            "top_cohort": top_row["cohort_id"],
            "top_net_pnl": top_row["net_pnl"],
            "top_profit_factor": top_row["profit_factor"],
            "top_trade_active_profit_factor": top_row["trade_active_profit_factor"],
            "top_max_drawdown": top_row["max_drawdown"],
            "top_sample_count": top_row["sample_count"],
            "top_trade_active_sample_count": top_row["trade_active_sample_count"],
            "top_symbol_count": top_row["symbol_count"],
            "top_sector_count": top_row["sector_count"],
            # v7 rows carry no split/holdout data; null = not measured.
            "top_split_pass_rate": None,
            "top_no_trade_ratio": top_row["no_trade_ratio"],
        }

    improved_vs_v6_count = sum(1 for c in comparison_records if c["improved_vs_v6"])
    pf_above_110_count = sum(1 for s in scores if s["profit_factor"] > MIN_BREAKTHROUGH_PF)
    trade_active_pf_above_110_count = sum(
        1 for s in scores
        if s["trade_active_profit_factor"] > MIN_BREAKTHROUGH_PF
        and s["trade_active_sample_count"] >= V7_MIN_TRADE_ACTIVE_SAMPLE
    )
    no_trade_only_subfamily_count = sum(1 for s in scores if s["no_trade_only"])
    family_count = len(by_family)
    subfamily_count = len(by_sub)
    cohort_count = len(by_cohort)
    positive_family_count = sum(
        1 for f, rows in by_family.items() if sum(r.get("pnl", 0.0) for r in rows) > 0
    )
    candidate_breakthrough_count = 0

    v6_tournament = load_v6_tournament_summary()
    v6_top_pf = float(v6_tournament.get("top_profit_factor", 0.0) or 0.0)

    summary = {
        "artifact_type": "research_tournament_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "research_tournament_v7_status": "research_tournament_complete_v7",
        "trade_count": len(trades),
        "family_count": family_count,
        "subfamily_count": subfamily_count,
        "cohort_count": cohort_count,
        "positive_family_count": positive_family_count,
        "candidate_breakthrough_count": candidate_breakthrough_count,
        "improved_vs_v6_count": improved_vs_v6_count,
        "pf_above_110_count": pf_above_110_count,
        "trade_active_pf_above_110_count": trade_active_pf_above_110_count,
        "no_trade_only_subfamily_count": no_trade_only_subfamily_count,
        "v6_top_pf": v6_top_pf,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "holdout_survival_count": sum(1 for r in holdout_records if r["holdout_survival"]),
        "trade_active_holdout_survival_count": sum(1 for r in holdout_records if r["trade_active_survival"]),
        "regime_score_count": len(regime_records),
        "comparison_count": len(comparison_records),
        "data_source_version": source_version,
        "timestamp": utc_now_iso(),
        **top,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(TOURNAMENT_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        TOURNAMENT_V7_PROOF_PATH,
        [research_v7_proof_record("research-tournament-v7", summary["research_tournament_v7_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_tournament_v7(), indent=2, sort_keys=True, default=str))
