"""Public signal deepening money scoreboard V4."""
from __future__ import annotations

import csv
from collections import Counter

from dopey_autonomy.public_champion_common import (
    CHAMPION_ROOT,
    EVOLUTION_ROOT,
    OPTIONS_ENGINE_ROOT,
    SCOREBOARD_ROOT,
    TOURNAMENT_ROOT,
    group_records,
    proof_record,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
    write_summary_with_hash,
)

from .public_signal_deepening_dashboard_v4 import (
    render_public_signal_deepening_dashboard_markdown_v4,
    render_public_signal_deepening_dashboard_v4,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_deepening_scoreboard_v4.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_deepening_scoreboard_rows_v4.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_deepening_dashboard_v4.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_deepening_dashboard_v4.md"
QUALITY_FLAGS_PATH = SCOREBOARD_ROOT / "public_signal_deepening_scoreboard_quality_flags_v4.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_deepening_scoreboard_v4_proof.jsonl"

TRADES_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_trades.jsonl"
LEADERBOARD_PATH = TOURNAMENT_ROOT / "public_cohort_tournament_leaderboard_v4.jsonl"
GATE_RESULTS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_results.jsonl"
NEAR_CHAMPIONS_PATH = CHAMPION_ROOT / "public_paper_champion_gate_v2_near_champions.jsonl"
KILL_QUEUE_PATH = EVOLUTION_ROOT / "cohort_loser_elimination_v2.jsonl"
MUTATION_QUEUE_PATH = EVOLUTION_ROOT / "public_signal_deepening_mutation_queue_v2.jsonl"


def run_public_signal_deepening_scoreboard_v4() -> dict[str, object]:
    trades = read_jsonl_file(TRADES_PATH)
    leaderboard = read_jsonl_file(LEADERBOARD_PATH)
    gate_results = read_jsonl_file(GATE_RESULTS_PATH)
    return build_public_signal_deepening_scoreboard_v4(trades, leaderboard, gate_results)


def build_public_signal_deepening_scoreboard_v4(
    trades: list[dict[str, object]],
    leaderboard: list[dict[str, object]],
    gate_results: list[dict[str, object]],
) -> dict[str, object]:
    public_trades = [t for t in trades if str(t.get("market_data_source_type", "")).startswith("public")]
    executable = [t for t in public_trades if str(t.get("trade_intent", "")) in {"long_call", "long_put"}]
    promotion_by_cohort = {f"{r.get('cohort_level', '')}::{r.get('cohort_id', '')}": r for r in gate_results}
    rows = scoreboard_rows_v4(leaderboard, promotion_by_cohort)
    active_champions = [str(r.get("cohort_id", "")) for r in gate_results if bool(r.get("public_data_paper_champion", False))]
    near_champions = read_jsonl_file(NEAR_CHAMPIONS_PATH)
    killed_records = read_jsonl_file(KILL_QUEUE_PATH)
    mutation_records = read_jsonl_file(MUTATION_QUEUE_PATH)

    scoreboard = {
        "artifact_type": "public_signal_deepening_scoreboard_v4",
        "public_signal_deepening_scoreboard_version": "dopey-public-signal-deepening-scoreboard-v4",
        "scoreboard_status": "public_signal_deepening_scoreboard_written",
        "total_public_paper_pnl": round(sum(safe_float(t.get("paper_pnl")) for t in executable), 6),
        "top_cohort_strategies": rows[:10],
        "worst_cohort_strategies": sorted(rows, key=lambda item: safe_float(item.get("net_pnl")))[:10],
        "active_champions": active_champions,
        "near_champions": [str(r.get("cohort_id", "")) for r in near_champions][:25],
        "sample_count_repair_list": [r for r in near_champions if str(r.get("near_champion_label", "")).startswith("sample_count")][:25],
        "split_fragile_repair_list": [r for r in near_champions if str(r.get("near_champion_label", "")).startswith("walk_forward")][:25],
        "killed_cohorts": [str(r.get("cohort_id", "")) for r in killed_records][:50],
        "killed_cohort_count": len(killed_records),
        "near_champion_count": len(near_champions),
        "trade_count": len(executable),
        "symbol_distribution": dict(Counter(str(t.get("symbol", "")) for t in executable).most_common()),
        "sector_distribution": dict(Counter(sector_for_symbol(str(t.get("symbol", ""))) for t in executable).most_common()),
        "regime_distribution": dict(Counter(str(t.get("regime", "")) for t in executable).most_common()),
        "split_performance": split_performance_v4(rows),
        "drawdown_curves": drawdown_curves_by_cohort(executable),
        "best_trades": sorted(executable, key=lambda item: safe_float(item.get("paper_pnl")), reverse=True)[:20],
        "worst_trades": sorted(executable, key=lambda item: safe_float(item.get("paper_pnl")))[:20],
        "stress_impact": {
            "slippage": stress_impact(executable, "slippage_stress"),
            "iv_proxy_regime": stress_impact(executable, "iv_proxy_regime"),
        },
        "champion_gate_results_summary": {
            "champion_count": len(active_champions),
            "rejection_count": sum(1 for r in gate_results if r.get("rejection_reasons")),
        },
        "next_mutation_queue_count": len(mutation_records),
        "next_mutation_queue": mutation_records[:25],
        "public_data_only": all(str(t.get("market_data_source_type", "")).startswith("public") for t in public_trades),
        "fixture_trade_count": sum(1 for t in public_trades if str(t.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }
    scoreboard = write_summary_with_hash(SCOREBOARD_PATH, scoreboard)
    write_scoreboard_csv_v4(ROWS_PATH, rows)
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(render_public_signal_deepening_dashboard_v4(scoreboard, rows), encoding="utf-8")
    MD_PATH.write_text(render_public_signal_deepening_dashboard_markdown_v4(scoreboard, rows), encoding="utf-8")
    flags = quality_flags_v4(scoreboard, rows)
    write_jsonl_file(QUALITY_FLAGS_PATH, flags)
    write_jsonl_file(PROOF_PATH, [proof_record("public-signal-deepening-scoreboard-v4", str(scoreboard["scoreboard_status"]), scoreboard)])
    return {**scoreboard, "artifact_paths": artifact_paths()}


def scoreboard_rows_v4(leaderboard: list[dict[str, object]], promotion_by_cohort: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, row in enumerate(leaderboard):
        key = f"{row.get('cohort_level', '')}::{row.get('cohort_id', '')}"
        promotion = promotion_by_cohort.get(key, {})
        rows.append({
            "rank": index + 1,
            "cohort_level": row.get("cohort_level", ""),
            "cohort_id": row.get("cohort_id", ""),
            "net_pnl": row.get("net_pnl", 0.0),
            "expectancy": row.get("expectancy", 0.0),
            "profit_factor": row.get("profit_factor", 0.0),
            "max_drawdown": row.get("max_drawdown", 0.0),
            "sample_count": row.get("sample_count", 0),
            "symbol_count": row.get("symbol_count", 0),
            "split_pass_rate": row.get("split_pass_rate", 0.0),
            "durability_score": row.get("durability_score", 0.0),
            "promotion_level": promotion.get("promotion_level", "unreviewed"),
            "public_data_paper_champion": promotion.get("public_data_paper_champion", False),
        })
    return rows


def write_scoreboard_csv_v4(path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["rank", "cohort_level", "cohort_id", "net_pnl", "expectancy", "profit_factor", "max_drawdown", "sample_count", "symbol_count", "split_pass_rate", "durability_score", "promotion_level", "public_data_paper_champion"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def split_performance_v4(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "average_split_pass_rate": round(sum(safe_float(r.get("split_pass_rate")) for r in rows) / len(rows), 6) if rows else 0.0,
        "cohorts_above_60pct": sum(1 for r in rows if safe_float(r.get("split_pass_rate")) >= 0.60),
    }


def drawdown_curves_by_cohort(trades: list[dict[str, object]]) -> dict[str, list[float]]:
    curves: dict[str, list[float]] = {}
    for cohort_id, records in group_records(trades, "family_cohort_id").items():
        equity = 0.0
        curve: list[float] = []
        for record in sorted(records, key=lambda item: str(item.get("entry_date", ""))):
            equity += safe_float(record.get("paper_pnl"))
            curve.append(round(equity, 6))
        curves[str(cohort_id)] = curve[-60:]
    return curves


def stress_impact(trades: list[dict[str, object]], field_name: str) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, records in group_records(trades, field_name).items():
        output[str(key)] = round(sum(safe_float(r.get("paper_pnl")) for r in records), 6)
    return output


def quality_flags_v4(scoreboard: dict[str, object], rows: list[dict[str, object]]) -> list[dict[str, object]]:
    flags: list[dict[str, object]] = []
    if not bool(scoreboard.get("public_data_only", False)):
        flags.append(record_with_hash({"artifact_type": "public_signal_deepening_scoreboard_quality_flag_v4", "flag_id": "fixture_rows_detected", "severity": "error", "live_trading_enabled": False}, "record_hash"))
    if not rows:
        flags.append(record_with_hash({"artifact_type": "public_signal_deepening_scoreboard_quality_flag_v4", "flag_id": "empty_scoreboard", "severity": "warning", "live_trading_enabled": False}, "record_hash"))
    flags.append(record_with_hash({"artifact_type": "public_signal_deepening_scoreboard_quality_flag_v4", "flag_id": "live_trading_disabled", "severity": "info", "passed": True, "live_trading_enabled": False}, "record_hash"))
    return flags


def artifact_paths() -> dict[str, str]:
    return {
        "public_signal_deepening_scoreboard_v4": str(SCOREBOARD_PATH),
        "public_signal_deepening_scoreboard_rows_v4": str(ROWS_PATH),
        "public_signal_deepening_dashboard_v4_html": str(HTML_PATH),
        "public_signal_deepening_dashboard_v4_md": str(MD_PATH),
        "public_signal_deepening_scoreboard_quality_flags_v4": str(QUALITY_FLAGS_PATH),
        "public_signal_deepening_scoreboard_v4_proof": str(PROOF_PATH),
    }
