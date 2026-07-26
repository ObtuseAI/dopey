"""Build the money-first paper P&L scoreboard."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from dopey_wealth_engine.common import stable_hash, write_csv


def build_pnl_scoreboard(trades: list[dict], scores: list[dict], promotions: list[dict], eliminations: list[dict], output_csv: Path) -> dict:
    strategy_rows = _strategy_rows(scores)
    write_csv(output_csv, strategy_rows, [
        "strategy_family", "net_paper_pnl", "max_drawdown", "profit_factor", "win_rate",
        "expectancy", "capital_efficiency", "market_data_source_type", "paper_action",
    ])
    symbol_pnl: dict[str, float] = defaultdict(float)
    for trade in trades:
        symbol_pnl[str(trade["underlying_symbol"])] += float(trade["paper_pnl"])
    sorted_symbols = sorted(symbol_pnl.items(), key=lambda item: item[1], reverse=True)
    summary = {
        "artifact_type": "pnl_scoreboard_summary",
        "scoreboard_version": "dopey-pnl-scoreboard-v1",
        "pnl_scoreboard_status": "complete" if scores else "blocked_no_tournament_scores",
        "top_strategies_by_net_pnl": strategy_rows[:5],
        "top_strategies_by_drawdown_adjusted_pnl": sorted(strategy_rows, key=lambda item: float(item["net_paper_pnl"]) / max(abs(float(item["max_drawdown"])), 1.0), reverse=True)[:5],
        "strategies_killed": [record["strategy_family"] for record in eliminations if record["elimination_action"] == "kill"],
        "strategies_promoted": [record["strategy_family"] for record in promotions],
        "biggest_winners": sorted(trades, key=lambda item: float(item["paper_pnl"]), reverse=True)[:5],
        "biggest_losers": sorted(trades, key=lambda item: float(item["paper_pnl"]))[:5],
        "best_symbols": [{"symbol": symbol, "paper_pnl": round(value, 4)} for symbol, value in sorted_symbols[:5]],
        "worst_symbols": [{"symbol": symbol, "paper_pnl": round(value, 4)} for symbol, value in sorted_symbols[-5:]],
        "best_regimes": _regime_rows(trades, True),
        "worst_regimes": _regime_rows(trades, False),
        "overtrading_warnings": [row["strategy_family"] for row in strategy_rows if float(row.get("turnover", 0.0)) > 12.0],
        "risk_throttle_activations": [],
        "no_trade_saves": 0,
        "paper_capital_allocation": _allocation_rows(strategy_rows),
        "strategy_rows_by_market_data_source_type": _strategy_source_groups(strategy_rows),
        "public_data_top_strategies": [row for row in strategy_rows if str(row.get("market_data_source_type", "")).startswith("public")][:5],
        "fixture_fallback_top_strategies": [row for row in strategy_rows if row.get("market_data_source_type") == "fixture_fallback"][:5],
        "next_mutation_queue": [record["strategy_family"] for record in promotions[:5]],
        "paper_only": True,
        "live_blocked": True,
        "live_trading_enabled": False,
    }
    summary["summary_hash"] = stable_hash(summary)
    return summary


def _strategy_rows(scores: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for score in scores:
        action = "promote" if float(score["net_paper_pnl"]) > 0 else "reduce"
        row = {
            "strategy_family": score["strategy_family"],
            "net_paper_pnl": score["net_paper_pnl"],
            "max_drawdown": score["max_drawdown"],
            "profit_factor": score["profit_factor"],
            "win_rate": score["win_rate"],
            "expectancy": score["expectancy"],
            "capital_efficiency": score["capital_efficiency"],
            "turnover": score["turnover"],
            "market_data_source_type": score.get("market_data_source_type", "fixture_fallback"),
            "paper_action": action,
        }
        rows.append(row)
    return rows


def _strategy_source_groups(strategy_rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in strategy_rows:
        grouped[str(row.get("market_data_source_type", "fixture_fallback"))].append(row)
    return dict(sorted(grouped.items()))


def _regime_rows(trades: list[dict], descending: bool) -> list[dict]:
    by_regime: dict[str, float] = defaultdict(float)
    for trade in trades:
        key = f"{trade['trend_regime']}|{trade['volatility_regime']}"
        by_regime[key] += float(trade["paper_pnl"])
    return [
        {"regime": key, "paper_pnl": round(value, 4)}
        for key, value in sorted(by_regime.items(), key=lambda item: item[1], reverse=descending)[:5]
    ]


def _allocation_rows(strategy_rows: list[dict]) -> list[dict]:
    rows: list[dict] = []
    total_positive = sum(max(float(row["net_paper_pnl"]), 0.0) for row in strategy_rows)
    for row in strategy_rows:
        positive = max(float(row["net_paper_pnl"]), 0.0)
        rows.append({
            "strategy_family": row["strategy_family"],
            "paper_allocation_weight": round(positive / total_positive, 6) if total_positive > 0 else 0.0,
            "paper_action": row["paper_action"],
        })
    return rows
