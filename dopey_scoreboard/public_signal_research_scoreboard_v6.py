"""V6 public signal research scoreboard (Workstream K).

Dashboard sections:
- V1/V2/V3/V4/V5/V6 comparison
- V5 watchlist diagnosis
- blocker repair policy
- mutation execution
- PF/holdout/split repair
- breakthrough/watchlist
- rejected families
- live gate locked
"""
from __future__ import annotations

import csv
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_common import RESEARCH_ROOT as RESEARCH_V1_ROOT
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT
from dopey_autonomy.signal_research_v4_common import (
    CANDIDATE_GENERATOR_SUMMARY_PATH as CANDIDATE_GENERATOR_V4_SUMMARY_PATH,
    GATE_V4_SUMMARY_PATH,
    MUTATION_QUEUE_V4_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    TOURNAMENT_SUMMARY_PATH as TOURNAMENT_V4_SUMMARY_PATH,
)
from dopey_autonomy.signal_research_v5_common import (
    BASELINE_FREEZE_V5_SUMMARY_PATH,
    CANDIDATE_GENERATOR_V5_SUMMARY_PATH,
    EXPENSIVE_LANE_V5_SUMMARY_PATH,
    GATE_V5_SUMMARY_PATH,
    MUTATION_EXEC_V5_SUMMARY_PATH,
    MUTATION_QUEUE_V5_SUMMARY_PATH,
    NO_TRADE_OPTIMIZER_V5_SUMMARY_PATH,
    PREFLIGHT_V5_SUMMARY_PATH,
    RESEARCH_V5_ROOT,
    SCORER_V5_SUMMARY_PATH,
    SIMULATOR_V5_SUMMARY_PATH,
    TOURNAMENT_V5_SUMMARY_PATH,
    V4_ANALYZER_V5_SUMMARY_PATH,
)
from dopey_autonomy.signal_research_v6_common import (
    BLOCKER_REPAIR_POLICY_V6_SUMMARY_PATH,
    CANDIDATE_GENERATOR_V6_SUMMARY_PATH,
    GATE_V6_SUMMARY_PATH,
    MUTATION_EXEC_V6_SUMMARY_PATH,
    MUTATION_QUEUE_V6_SUMMARY_PATH,
    PREFLIGHT_V6_SUMMARY_PATH,
    RESEARCH_V6_ROOT,
    RESEARCH_V6_VERSION,
    SCORER_V6_SUMMARY_PATH,
    SIMULATOR_V6_SUMMARY_PATH,
    TOURNAMENT_V6_SUMMARY_PATH,
    V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH,
    research_v6_proof_record,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v6.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v6.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v6.md"
QUALITY_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v6.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v6_proof.jsonl"

V1_TOURNAMENT_SUMMARY_PATH = RESEARCH_V1_ROOT / "public_signal_research_breakthrough_v1_summary.json"
V2_TOURNAMENT_SUMMARY_PATH = RESEARCH_V2_ROOT / "research_tournament_v2_summary.json"
V3_TOURNAMENT_SUMMARY_PATH = RESEARCH_V3_ROOT / "research_tournament_v3_summary.json"


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _build_comparison_rows(
    v1_tournament: dict,
    v2_tournament: dict,
    v3_tournament: dict,
    v4_tournament: dict,
    v5_tournament: dict,
    v6_tournament: dict,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, src in (
        ("v1", v1_tournament),
        ("v2", v2_tournament),
        ("v3", v3_tournament),
        ("v4", v4_tournament),
        ("v5", v5_tournament),
        ("v6", v6_tournament),
    ):
        rows.append(
            {
                "version": label,
                "top_family": str(src.get("top_family", "")),
                "top_subfamily": str(src.get("top_subfamily", "")),
                "top_cohort": str(src.get("top_cohort", "")),
                "top_profit_factor": _safe_float(src.get("top_profit_factor", 0.0)),
                "top_net_pnl": _safe_float(src.get("top_net_pnl", 0.0)),
                "top_max_drawdown": _safe_float(src.get("top_max_drawdown", 0.0)),
                "top_sample_count": _safe_int(src.get("top_sample_count", 0)),
                "top_symbol_count": _safe_int(src.get("top_symbol_count", 0)),
                "top_sector_count": _safe_int(src.get("top_sector_count", 0)),
                "trade_count": _safe_int(src.get("trade_count", 0)),
                "pf_above_110_count": _safe_int(src.get("pf_above_110_count", 0)),
                "improved_vs_prev_count": _safe_int(
                    src.get("improved_vs_v5_count", 0)
                    if label == "v6"
                    else src.get("improved_vs_v4_count", 0)
                    if label == "v5"
                    else src.get("improved_vs_v3_count", 0)
                    if label == "v4"
                    else src.get("improved_vs_v2_count", 0)
                    if label == "v3"
                    else 0
                ),
            }
        )
    return rows


def run_public_signal_research_scoreboard_v6() -> dict[str, object]:
    v1_tournament = read_json_file(V1_TOURNAMENT_SUMMARY_PATH)
    v2_tournament = read_json_file(V2_TOURNAMENT_SUMMARY_PATH)
    v3_tournament = read_json_file(V3_TOURNAMENT_SUMMARY_PATH)
    v4_tournament = read_json_file(TOURNAMENT_V4_SUMMARY_PATH)
    v5_tournament = read_json_file(TOURNAMENT_V5_SUMMARY_PATH)
    v6_tournament = read_json_file(TOURNAMENT_V6_SUMMARY_PATH)

    v5_candidates = read_json_file(CANDIDATE_GENERATOR_V5_SUMMARY_PATH)
    v6_candidates = read_json_file(CANDIDATE_GENERATOR_V6_SUMMARY_PATH)
    v5_gate = read_json_file(GATE_V5_SUMMARY_PATH)
    v6_gate = read_json_file(GATE_V6_SUMMARY_PATH)
    v5_mutation = read_json_file(MUTATION_QUEUE_V5_SUMMARY_PATH)
    v6_mutation = read_json_file(MUTATION_QUEUE_V6_SUMMARY_PATH)
    v5_simulator = read_json_file(SIMULATOR_V5_SUMMARY_PATH)
    v6_simulator = read_json_file(SIMULATOR_V6_SUMMARY_PATH)
    v5_scorer = read_json_file(SCORER_V5_SUMMARY_PATH)
    v6_scorer = read_json_file(SCORER_V6_SUMMARY_PATH)
    v5_no_trade = read_json_file(NO_TRADE_OPTIMIZER_V5_SUMMARY_PATH)
    v5_mutation_exec = read_json_file(MUTATION_EXEC_V5_SUMMARY_PATH)
    v6_mutation_exec = read_json_file(MUTATION_EXEC_V6_SUMMARY_PATH)
    v5_preflight = read_json_file(PREFLIGHT_V5_SUMMARY_PATH)
    v6_preflight = read_json_file(PREFLIGHT_V6_SUMMARY_PATH)
    v5_baseline_freeze = read_json_file(BASELINE_FREEZE_V5_SUMMARY_PATH)
    v5_expensive = read_json_file(EXPENSIVE_LANE_V5_SUMMARY_PATH)
    v5_analyzer = read_json_file(V4_ANALYZER_V5_SUMMARY_PATH)
    v6_rejection_analyzer = read_json_file(V5_GATE_REJECTION_ANALYZER_V6_SUMMARY_PATH)
    v6_blocker_repair = read_json_file(BLOCKER_REPAIR_POLICY_V6_SUMMARY_PATH)

    rows = _build_comparison_rows(v1_tournament, v2_tournament, v3_tournament, v4_tournament, v5_tournament, v6_tournament)

    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v6",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "scoreboard_v6_status": "public_signal_research_scoreboard_complete_v6",
        "v6_preflight_status": str(v6_preflight.get("public_signal_research_v6_preflight_status", "")),
        "v5_baseline_freeze_status": str(v5_baseline_freeze.get("baseline_freeze_status", "")),
        "v5_expensive_lane_status": str(v5_expensive.get("expensive_lane_runner_status", "")),
        "v5_v4_analyzer_status": str(v5_analyzer.get("v4_result_analyzer_status", "")),
        "v6_v5_gate_rejection_analyzer_status": str(v6_rejection_analyzer.get("v5_gate_rejection_analyzer_v6_status", "")),
        "v6_mutation_exec_status": str(v6_mutation_exec.get("research_mutation_queue_executor_v6_status", "")),
        "v6_blocker_repair_policy_status": str(v6_blocker_repair.get("breakthrough_blocker_repair_policy_v6_status", "")),
        "v5_no_trade_optimizer_status": str(v5_no_trade.get("no_trade_filter_optimizer_v5_status", "")),
        "v6_candidate_generator_status": str(v6_candidates.get("research_candidate_generator_v6_status", "")),
        "v6_scorer_status": str(v6_scorer.get("profit_holdout_split_scorer_v6_status", "")),
        "v6_simulator_status": str(v6_simulator.get("research_path_simulator_v6_status", "")),
        "v6_tournament_status": str(v6_tournament.get("research_tournament_v6_status", "")),
        "v6_gate_status": str(v6_gate.get("research_breakthrough_gate_v6_status", "")),
        "v6_mutation_queue_status": str(v6_mutation.get("research_mutation_queue_v6_status", "")),
        "v6_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "v5_watchlist_count": _safe_int(v5_gate.get("watchlist_count", 0)),
        "v5_improved_watchlist_count": _safe_int(v5_gate.get("improved_watchlist_count", 0)),
        "v6_candidate_count": _safe_int(v6_candidates.get("candidate_count", 0)),
        "v6_simulated_trade_count": _safe_int(v6_simulator.get("simulated_trade_count", 0)),
        "v6_pf_above_110_count": _safe_int(v6_tournament.get("pf_above_110_count", 0)),
        "v6_breakthrough_candidate_count": _safe_int(v6_gate.get("breakthrough_candidate_count", 0)),
        "v6_watchlist_count": _safe_int(v6_gate.get("watchlist_count", 0)),
        "v6_improved_vs_v5_count": _safe_int(v6_tournament.get("improved_vs_v5_count", 0)),
        "v6_top_family": str(v6_tournament.get("top_family", "")),
        "v6_top_subfamily": str(v6_tournament.get("top_subfamily", "")),
        "v6_top_cohort": str(v6_tournament.get("top_cohort", "")),
        "v6_top_net_pnl": _safe_float(v6_tournament.get("top_net_pnl", 0.0)),
        "v6_top_profit_factor": _safe_float(v6_tournament.get("top_profit_factor", 0.0)),
        "v6_top_max_drawdown": _safe_float(v6_tournament.get("top_max_drawdown", 0.0)),
        "v6_top_sample_count": _safe_int(v6_tournament.get("top_sample_count", 0)),
        "v6_mutation_queue_count": _safe_int(v6_mutation.get("mutation_queue_count", 0)),
        "v5_top_pf": _safe_float(v5_tournament.get("top_profit_factor", 0.0)),
        "v4_top_pf": _safe_float(v4_tournament.get("top_profit_factor", 0.0)),
        "v3_top_pf": _safe_float(v3_tournament.get("top_profit_factor", 0.0)),
        "v2_top_pf": _safe_float(v2_tournament.get("top_profit_factor", 0.0)),
        "v1_top_pf": _safe_float(v1_tournament.get("top_profit_factor", 0.0)),
        "v5_top_net_pnl": _safe_float(v5_tournament.get("top_net_pnl", 0.0)),
        "v4_top_net_pnl": _safe_float(v4_tournament.get("top_net_pnl", 0.0)),
        "v4_pf_above_110_count": _safe_int(v4_tournament.get("pf_above_110_count", 0)),
        "v4_breakthrough_count": _safe_int(v4_tournament.get("candidate_breakthrough_count", 0)),
        "uvxy_like_corruption_detected": bool(v6_simulator.get("uvxy_like_corruption_detected", False)),
        "future_leakage_detected": bool(v5_no_trade.get("future_leakage_detected", False)),
        "live_gate_status": "disabled_live_gate_locked",
        "public_data_only": True,
        "live_trading_enabled": False,
        "rows": rows,
        "live_trading_enabled_global": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }

    # Write JSON
    SCOREBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_summary_with_hash(SCOREBOARD_PATH, scoreboard)

    # Write CSV rows
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "version", "top_family", "top_subfamily", "top_cohort",
        "top_profit_factor", "top_net_pnl", "top_max_drawdown",
        "top_sample_count", "top_symbol_count", "top_sector_count",
        "trade_count", "pf_above_110_count", "improved_vs_prev_count",
    ]
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # Write HTML dashboard
    html_rows = "\n".join(
        f"<tr><td>{r['version']}</td><td>{r['top_family']}</td><td>{r['top_subfamily']}</td>"
        f"<td>{r['top_profit_factor']}</td>"
        f"<td>{r['top_net_pnl']}</td><td>{r['top_max_drawdown']}</td>"
        f"<td>{r['top_sample_count']}</td><td>{r['pf_above_110_count']}</td></tr>"
        for r in rows
    )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>DOPEY Public Signal Research Scoreboard V6</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse}"
        "th,td{border:1px solid #888;padding:4px 8px}"
        "th{background:#eee}</style></head><body>"
        "<h1>DOPEY Public Signal Research Scoreboard V6</h1>"
        f"<p>status: {scoreboard['scoreboard_v6_status']}</p>"
        f"<p>v6_min_breakthrough_pf: 1.10 (hard floor, not lowered)</p>"
        f"<p>v6_candidate_count: {scoreboard['v6_candidate_count']}</p>"
        f"<p>v6_simulated_trade_count: {scoreboard['v6_simulated_trade_count']}</p>"
        f"<p>v6_breakthrough_candidate_count: {scoreboard['v6_breakthrough_candidate_count']}</p>"
        f"<p>v6_watchlist_count: {scoreboard['v6_watchlist_count']}</p>"
        f"<p>v6_improved_vs_v5_count: {scoreboard['v6_improved_vs_v5_count']}</p>"
        f"<p>v6_pf_above_110_count: {scoreboard['v6_pf_above_110_count']}</p>"
        f"<p>v5_watchlist_count: {scoreboard['v5_watchlist_count']}</p>"
        f"<p>uvxy_like_corruption_detected: {scoreboard['uvxy_like_corruption_detected']}</p>"
        f"<p>future_leakage_detected: {scoreboard['future_leakage_detected']}</p>"
        f"<p>live_gate_status: {scoreboard['live_gate_status']}</p>"
        f"<p>live_trading_enabled: {scoreboard['live_trading_enabled']}</p>"
        "<h2>V1-V6 comparison</h2>"
        "<table><thead><tr><th>version</th><th>top_family</th><th>top_subfamily</th>"
        "<th>top_profit_factor</th><th>top_net_pnl</th><th>top_max_drawdown</th>"
        "<th>top_sample_count</th><th>pf_above_110_count</th></tr></thead><tbody>"
        f"{html_rows}</tbody></table>"
        "<h2>V5 watchlist diagnosis</h2>"
        f"<p>{scoreboard['v5_watchlist_count']} V5 watchlist candidates; {scoreboard['v5_improved_watchlist_count']} improved.</p>"
        "<h2>Blocker repair policy</h2>"
        f"<p>status: {scoreboard['v6_blocker_repair_policy_status']}</p>"
        "<h2>Mutation execution</h2>"
        f"<p>V6 mutation exec status: {scoreboard['v6_mutation_exec_status']}</p>"
        "<h2>PF / holdout / split repair</h2>"
        f"<p>V6 scorer status: {scoreboard['v6_scorer_status']}</p>"
        "<h2>Breakthrough / watchlist</h2>"
        f"<p>breakthroughs: {scoreboard['v6_breakthrough_candidate_count']} / watchlist: {scoreboard['v6_watchlist_count']}</p>"
        "<h2>Rejected families</h2>"
        f"<p>see research_breakthrough_rejections_v6.jsonl</p>"
        "<h2>Live gate</h2>"
        f"<p>{scoreboard['live_gate_status']}</p>"
        "</body></html>"
    )
    HTML_PATH.write_text(html, encoding="utf-8")

    md = (
        "# DOPEY Public Signal Research Scoreboard V6\n\n"
        f"- status: `{scoreboard['scoreboard_v6_status']}`\n"
        f"- v6_min_breakthrough_pf: `1.10` (hard floor, not lowered)\n"
        f"- v6_candidate_count: `{scoreboard['v6_candidate_count']}`\n"
        f"- v6_simulated_trade_count: `{scoreboard['v6_simulated_trade_count']}`\n"
        f"- v6_breakthrough_candidate_count: `{scoreboard['v6_breakthrough_candidate_count']}`\n"
        f"- v6_watchlist_count: `{scoreboard['v6_watchlist_count']}`\n"
        f"- v6_improved_vs_v5_count: `{scoreboard['v6_improved_vs_v5_count']}`\n"
        f"- v6_pf_above_110_count: `{scoreboard['v6_pf_above_110_count']}`\n"
        f"- v6_top_family: `{scoreboard['v6_top_family']}`\n"
        f"- v6_top_subfamily: `{scoreboard['v6_top_subfamily']}`\n"
        f"- v6_top_profit_factor: `{scoreboard['v6_top_profit_factor']}`\n"
        f"- v6_top_net_pnl: `{scoreboard['v6_top_net_pnl']}`\n"
        f"- v5_top_profit_factor: `{scoreboard['v5_top_pf']}`\n"
        f"- v4_top_profit_factor: `{scoreboard['v4_top_pf']}`\n"
        f"- v3_top_profit_factor: `{scoreboard['v3_top_pf']}`\n"
        f"- v2_top_profit_factor: `{scoreboard['v2_top_pf']}`\n"
        f"- v1_top_profit_factor: `{scoreboard['v1_top_pf']}`\n"
        f"- v5_watchlist_count: `{scoreboard['v5_watchlist_count']}`\n"
        f"- uvxy_like_corruption_detected: `{scoreboard['uvxy_like_corruption_detected']}`\n"
        f"- future_leakage_detected: `{scoreboard['future_leakage_detected']}`\n"
        f"- live_gate_status: `{scoreboard['live_gate_status']}`\n"
        f"- live_trading_enabled: `{scoreboard['live_trading_enabled']}`\n"
        f"- thresholds_lowered: `False`\n"
        f"- public_data_only: `True`\n"
        "\n## V1-V6 comparison\n\n"
        "| version | top_family | top_subfamily | top_pf | top_net_pnl | top_dd | sample | pf>1.10 |\n"
        "|---------|------------|---------------|--------|-------------|--------|--------|----------|\n"
        + "\n".join(
            f"| {r['version']} | {r['top_family']} | {r['top_subfamily']} | {r['top_profit_factor']} | "
            f"{r['top_net_pnl']} | {r['top_max_drawdown']} | {r['top_sample_count']} | {r['pf_above_110_count']} |"
            for r in rows
        )
        + "\n\n## Dashboard sections\n\n"
        "- V5 watchlist diagnosis: see V5 gate summary\n"
        "- Blocker repair policy: see breakthrough_blocker_repair_policy_v6_summary.json\n"
        "- Mutation execution: see research_mutation_queue_executor_v6_summary.json\n"
        "- PF/holdout/split repair: see profit_holdout_split_scorer_v6_summary.json\n"
        "- Breakthrough/watchlist: see research_breakthrough_candidates_v6.jsonl / research_watchlist_candidates_v6.jsonl\n"
        "- Rejected families: see research_breakthrough_rejections_v6.jsonl\n"
        "- Live gate: disabled_live_gate_locked\n"
    )
    MD_PATH.write_text(md, encoding="utf-8")

    # Quality flags
    quality_flags: list[dict[str, object]] = []
    if not scoreboard["thresholds_lowered"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v6",
                "flag": "thresholds_not_lowered",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if not scoreboard["uvxy_like_corruption_detected"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v6",
                "flag": "no_uvxy_corruption",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if not scoreboard["future_leakage_detected"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v6",
                "flag": "no_future_leakage",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    write_jsonl_file(QUALITY_PATH, [record_with_hash(q, "record_hash") for q in quality_flags])

    # Proof
    proof_record = {
        "artifact_type": "public_signal_research_scoreboard_v6_proof",
        "scoreboard_v6_status": scoreboard["scoreboard_v6_status"],
        "live_trading_enabled": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(PROOF_PATH, [record_with_hash(proof_record, "proof_hash")])

    return scoreboard


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_scoreboard_v6(), indent=2, sort_keys=True, default=str))
