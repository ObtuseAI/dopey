"""V5 research tournament (Workstream J).

Aggregates V5 trade-level metrics into per-family / per-subfamily /
per-cohort leaderboards, compares to V4 baseline, and writes the
tournament summary, scores, leaderboard, holdout, regime, and
comparison artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    BASELINE_V4_ROOT,
    RESEARCH_V5_VERSION,
    TOURNAMENT_COMPARISON_V5_PATH,
    TOURNAMENT_HOLDOUT_V5_PATH,
    TOURNAMENT_LEADERBOARD_V5_PATH,
    TOURNAMENT_REGIME_V5_PATH,
    TOURNAMENT_SCORES_V5_PATH,
    TOURNAMENT_V5_PROOF_PATH,
    TOURNAMENT_V5_SUMMARY_PATH,
    TRADES_V5_PATH,
    research_v5_proof_record,
    utc_now_iso,
)
from dopey_signal_research.research_holdout_v5 import compute_v5_holdout_scores
from dopey_signal_research.research_regime_score_v5 import compute_v5_regime_scores
from dopey_signal_research.research_v4_v5_comparison_v5 import compute_v4_v5_comparison


__all__ = ["run_research_tournament_v5"]


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
    # Drawdown
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


def run_research_tournament_v5() -> dict[str, object]:
    trades = _read_jsonl_safe(TRADES_V5_PATH)
    # Per subfamily aggregation
    by_sub: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_cohort: dict[str, list[dict[str, object]]] = defaultdict(list)
    for t in trades:
        by_sub[str(t.get("stable_subfamily_id", ""))].append(t)
        by_family[str(t.get("stable_family_id", ""))].append(t)
        by_cohort[str(t.get("cohort_id", ""))].append(t)

    # Per-subfamily scores
    scores: list[dict[str, object]] = []
    leaderboard: list[dict[str, object]] = []
    for sub, rows in by_sub.items():
        m = _metrics(rows)
        symbols = {str(r.get("symbol", "")) for r in rows}
        sectors = {str(r.get("sector", "")) for r in rows}
        family = str(rows[0].get("stable_family_id", ""))
        cohort = str(rows[0].get("cohort_id", ""))
        score = {
            "artifact_type": "research_tournament_score_v5",
            "stable_subfamily_id": sub,
            "stable_family_id": family,
            "cohort_id": cohort,
            "sample_count": m["sample_count"],
            "symbol_count": len(symbols),
            "sector_count": len(sectors),
            "net_pnl": m["net_pnl"],
            "profit_factor": m["pf"],
            "expectancy": m["expectancy"],
            "max_drawdown": m["max_drawdown"],
            "win_rate": m["win_rate"],
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        scores.append(record_with_hash(score, "record_hash"))
        leaderboard.append(
            {
                "artifact_type": "research_tournament_leaderboard_v5",
                **score,
            }
        )

    write_jsonl_file(TOURNAMENT_SCORES_V5_PATH, scores)
    write_jsonl_file(TOURNAMENT_LEADERBOARD_V5_PATH, leaderboard)

    # Holdout, regime, comparison
    holdout_records = compute_v5_holdout_scores()
    write_jsonl_file(TOURNAMENT_HOLDOUT_V5_PATH, holdout_records)
    regime_records = compute_v5_regime_scores()
    write_jsonl_file(TOURNAMENT_REGIME_V5_PATH, regime_records)
    comparison_records = compute_v4_v5_comparison()
    write_jsonl_file(TOURNAMENT_COMPARISON_V5_PATH, comparison_records)

    # Aggregate metrics
    if not leaderboard:
        top = {
            "top_family": "",
            "top_subfamily": "",
            "top_cohort": "",
            "top_net_pnl": 0.0,
            "top_profit_factor": 0.0,
            "top_max_drawdown": 0.0,
            "top_sample_count": 0,
            "top_symbol_count": 0,
            "top_sector_count": 0,
        }
    else:
        top_row = max(leaderboard, key=lambda r: r["profit_factor"])
        top = {
            "top_family": top_row["stable_family_id"],
            "top_subfamily": top_row["stable_subfamily_id"],
            "top_cohort": top_row["cohort_id"],
            "top_net_pnl": top_row["net_pnl"],
            "top_profit_factor": top_row["profit_factor"],
            "top_max_drawdown": top_row["max_drawdown"],
            "top_sample_count": top_row["sample_count"],
            "top_symbol_count": top_row["symbol_count"],
            "top_sector_count": top_row["sector_count"],
            # v5 rows carry no split/holdout data; null = not measured. A
            # fabricated midpoint would flow into downstream summaries.
            "top_split_pass_rate": None,
        }
    improved_vs_v4_count = sum(1 for c in comparison_records if c["improved_vs_v4"])
    pf_above_110_count = sum(1 for s in scores if s["profit_factor"] > 1.10)
    family_count = len(by_family)
    subfamily_count = len(by_sub)
    cohort_count = len(by_cohort)
    positive_family_count = sum(1 for f, rows in by_family.items() if sum(r.get("pnl", 0.0) for r in rows) > 0)
    candidate_breakthrough_count = 0  # set by gate later

    # V4 baseline reference
    v4_tournament = _read_json_safe(BASELINE_V4_ROOT / "research_tournament_v4_summary.json")
    v4_top_pf = float(v4_tournament.get("top_profit_factor", 0.0) or 0.0)

    summary = {
        "artifact_type": "research_tournament_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "research_tournament_v5_status": "research_tournament_complete_v5",
        "trade_count": len(trades),
        "family_count": family_count,
        "subfamily_count": subfamily_count,
        "cohort_count": cohort_count,
        "positive_family_count": positive_family_count,
        "candidate_breakthrough_count": candidate_breakthrough_count,
        "improved_vs_v4_count": improved_vs_v4_count,
        "pf_above_110_count": pf_above_110_count,
        "v4_top_pf": v4_top_pf,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "holdout_survival_count": sum(1 for r in holdout_records if r["holdout_survival"]),
        "regime_score_count": len(regime_records),
        "comparison_count": len(comparison_records),
        "timestamp": utc_now_iso(),
        **top,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(TOURNAMENT_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        TOURNAMENT_V5_PROOF_PATH,
        [research_v5_proof_record("research-tournament-v5", summary["research_tournament_v5_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_tournament_v5(), indent=2, sort_keys=True, default=str))
