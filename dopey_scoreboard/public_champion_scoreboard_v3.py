"""Money-first public champion scoreboard V3."""
from __future__ import annotations

import csv
from collections import Counter

from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    group_records,
    load_public_champion_gate_results,
    load_public_champion_trades,
    load_public_leaderboard,
    proof_record,
    read_jsonl_file,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
    write_summary_with_hash,
)

from .public_champion_dashboard_v3 import render_public_champion_dashboard_markdown, render_public_champion_dashboard_v3


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_champion_scoreboard_v3.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_champion_scoreboard_rows_v3.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_champion_dashboard_v3.html"
MD_PATH = SCOREBOARD_ROOT / "public_champion_dashboard_v3.md"
QUALITY_FLAGS_PATH = SCOREBOARD_ROOT / "public_champion_scoreboard_quality_flags_v3.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_champion_scoreboard_v3_proof.jsonl"


def run_public_champion_scoreboard_v3() -> dict[str, object]:
    trades = load_public_champion_trades()
    leaderboard = load_public_leaderboard()
    gate_results = load_public_champion_gate_results()
    return build_public_champion_scoreboard_v3(trades, leaderboard, gate_results)


def build_public_champion_scoreboard_v3(
    trades: list[dict[str, object]],
    leaderboard: list[dict[str, object]],
    gate_results: list[dict[str, object]],
) -> dict[str, object]:
    public_trades = [trade for trade in trades if str(trade.get("market_data_source_type", "")).startswith("public")]
    executable = [trade for trade in public_trades if str(trade.get("trade_intent", "")) in {"long_call", "long_put"}]
    promotion_by_strategy = {str(record.get("strategy_id", "")): record for record in gate_results}
    rows = scoreboard_rows(leaderboard, promotion_by_strategy)
    active_champions = [str(record.get("strategy_id", "")) for record in gate_results if bool(record.get("public_data_paper_champion", False))]
    killed_records = read_jsonl_file(SCOREBOARD_ROOT.parent / "evolution" / "public_loser_kill_queue.jsonl")
    mutation_records = read_jsonl_file(SCOREBOARD_ROOT.parent / "evolution" / "public_champion_mutation_queue.jsonl")
    scoreboard = {
        "artifact_type": "public_champion_scoreboard_v3",
        "public_champion_scoreboard_version": "dopey-public-champion-scoreboard-v3",
        "scoreboard_status": "public_champion_scoreboard_written",
        "total_public_paper_pnl": round(sum(safe_float(trade.get("paper_pnl")) for trade in executable), 6),
        "top_strategies": rows[:10],
        "worst_strategies": sorted(rows, key=lambda item: safe_float(item.get("net_pnl")))[:10],
        "active_champions": active_champions,
        "rejected_near_champions": [row for row in rows if row.get("promotion_level") == "public_watchlist"][:10],
        "trade_count": len(executable),
        "symbol_distribution": dict(Counter(str(trade.get("symbol", "")) for trade in executable).most_common()),
        "sector_distribution": dict(Counter(sector_for_symbol(str(trade.get("symbol", ""))) for trade in executable).most_common()),
        "regime_distribution": dict(Counter(str(trade.get("regime", "")) for trade in executable).most_common()),
        "split_performance": split_performance(rows),
        "drawdown_curves": drawdown_curves_by_strategy(executable),
        "best_trades": sorted(executable, key=lambda item: safe_float(item.get("paper_pnl")), reverse=True)[:20],
        "worst_trades": sorted(executable, key=lambda item: safe_float(item.get("paper_pnl")))[:20],
        "no_trade_saves": [trade for trade in public_trades if str(trade.get("trade_intent", "")) == "no_trade"][:20],
        "kill_switch_saves": [trade for trade in executable if str(trade.get("exit_reason", "")) in {"drawdown_stop", "invalidation_hit", "theta_bleed_stop"}][:20],
        "slippage_stress_impact": stress_impact(executable, "slippage_stress"),
        "theta_stress_impact": {"dte_7_or_less_pnl": round(sum(safe_float(trade.get("paper_pnl")) for trade in executable if int(trade.get("dte_bucket", 999)) <= 7), 6)},
        "iv_shock_impact": stress_impact(executable, "iv_proxy_regime"),
        "next_mutation_queue_count": len(mutation_records),
        "next_paper_tournament_candidates": mutation_records[:25],
        "loser_kill_count": len(killed_records),
        "public_data_only": all(str(trade.get("market_data_source_type", "")).startswith("public") for trade in public_trades),
        "fixture_trade_count": sum(1 for trade in public_trades if str(trade.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }
    scoreboard = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_scoreboard_csv(ROWS_PATH, rows)
    HTML_PATH.write_text(render_public_champion_dashboard_v3(scoreboard, rows), encoding="utf-8")
    MD_PATH.write_text(render_public_champion_dashboard_markdown(scoreboard, rows), encoding="utf-8")
    flags = quality_flags(scoreboard, rows)
    write_jsonl_file(QUALITY_FLAGS_PATH, flags)
    write_jsonl_file(PROOF_PATH, [proof_record("public-champion-scoreboard-v3", str(scoreboard["scoreboard_status"]), scoreboard)])
    return {**scoreboard, "artifact_paths": artifact_paths()}


def scoreboard_rows(leaderboard: list[dict[str, object]], promotion_by_strategy: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, row in enumerate(leaderboard):
        strategy_id = str(row.get("strategy_id", ""))
        promotion = promotion_by_strategy.get(strategy_id, {})
        rows.append({
            "rank": index + 1,
            "strategy_id": strategy_id,
            "setup_family": row.get("setup_family", ""),
            "net_pnl": row.get("net_pnl", 0.0),
            "expectancy": row.get("expectancy", 0.0),
            "profit_factor": row.get("profit_factor", 0.0),
            "max_drawdown": row.get("max_drawdown", 0.0),
            "sample_count": row.get("sample_count", 0),
            "symbol_count": row.get("symbol_count", 0),
            "split_pass_rate": row.get("split_pass_rate", 0.0),
            "promotion_level": promotion.get("promotion_level", "unreviewed"),
            "public_data_paper_champion": promotion.get("public_data_paper_champion", False),
        })
    return rows


def write_scoreboard_csv(path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rank", "strategy_id", "setup_family", "net_pnl", "expectancy", "profit_factor", "max_drawdown", "sample_count", "symbol_count", "split_pass_rate", "promotion_level", "public_data_paper_champion"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def split_performance(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "average_split_pass_rate": round(sum(safe_float(row.get("split_pass_rate")) for row in rows) / len(rows), 6) if rows else 0.0,
        "strategies_above_60pct": sum(1 for row in rows if safe_float(row.get("split_pass_rate")) >= 0.60),
    }


def drawdown_curves_by_strategy(trades: list[dict[str, object]]) -> dict[str, list[float]]:
    curves: dict[str, list[float]] = {}
    for strategy_id, records in group_records(trades, "strategy_id").items():
        equity = 0.0
        curve: list[float] = []
        for record in sorted(records, key=lambda item: str(item.get("entry_date", ""))):
            equity += safe_float(record.get("paper_pnl"))
            curve.append(round(equity, 6))
        curves[strategy_id] = curve[-60:]
    return curves


def stress_impact(trades: list[dict[str, object]], field_name: str) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, records in group_records(trades, field_name).items():
        output[key] = round(sum(safe_float(record.get("paper_pnl")) for record in records), 6)
    return output


def quality_flags(scoreboard: dict[str, object], rows: list[dict[str, object]]) -> list[dict[str, object]]:
    flags: list[dict[str, object]] = []
    if not bool(scoreboard.get("public_data_only", False)):
        flags.append({"artifact_type": "public_champion_scoreboard_quality_flag_v3", "flag_id": "fixture_rows_detected", "severity": "error"})
    if not rows:
        flags.append({"artifact_type": "public_champion_scoreboard_quality_flag_v3", "flag_id": "empty_scoreboard", "severity": "warning"})
    return flags


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_scoreboard_v3": str(SCOREBOARD_PATH),
        "public_champion_scoreboard_rows_v3": str(ROWS_PATH),
        "public_champion_dashboard_v3_html": str(HTML_PATH),
        "public_champion_dashboard_v3_md": str(MD_PATH),
        "public_champion_scoreboard_quality_flags_v3": str(QUALITY_FLAGS_PATH),
        "public_champion_scoreboard_v3_proof": str(PROOF_PATH),
    }

