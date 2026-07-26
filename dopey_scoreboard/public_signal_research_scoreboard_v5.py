"""V5 public signal research scoreboard.

Copies V4 scoreboard pattern, points at V5 artifacts, includes V1/V2/V3/V4/V5
comparison, UVXY-like corruption check, and family/subfamily separation.
"""
from __future__ import annotations

import csv

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT
from dopey_autonomy.signal_research_v4_common import (
    CANDIDATE_GENERATOR_SUMMARY_PATH,
    GATE_V4_SUMMARY_PATH,
    MUTATION_QUEUE_V4_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    TOURNAMENT_SUMMARY_PATH,
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
    SAFE_APPEND_V5_SUMMARY_PATH,
    SCORER_V5_SUMMARY_PATH,
    SIMULATOR_V5_SUMMARY_PATH,
    TOURNAMENT_V5_SUMMARY_PATH,
    V4_ANALYZER_V5_SUMMARY_PATH,
)


SCOREBOARD_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v5.json"
ROWS_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_rows_v5.csv"
HTML_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v5.html"
MD_PATH = SCOREBOARD_ROOT / "public_signal_research_dashboard_v5.md"
QUALITY_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_quality_flags_v5.jsonl"
PROOF_PATH = SCOREBOARD_ROOT / "public_signal_research_scoreboard_v5_proof.jsonl"


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _build_scoreboard_rows(
    v3_tournament: dict,
    v4_tournament: dict,
    v5_tournament: dict,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, src in (
        ("v3", v3_tournament),
        ("v4", v4_tournament),
        ("v5", v5_tournament),
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
                "improved_vs_prev_count": _safe_int(src.get("improved_vs_v3_count", 0) if label == "v4" else src.get("improved_vs_v4_count", 0)),
            }
        )
    return rows


def run_public_signal_research_scoreboard_v5() -> dict[str, object]:
    v3_tournament = read_json_file(RESEARCH_V3_ROOT / "research_tournament_v3_summary.json")
    v4_tournament = read_json_file(TOURNAMENT_SUMMARY_PATH)
    v5_tournament = read_json_file(TOURNAMENT_V5_SUMMARY_PATH)
    v5_candidates = read_json_file(CANDIDATE_GENERATOR_V5_SUMMARY_PATH)
    v5_gate = read_json_file(GATE_V5_SUMMARY_PATH)
    v5_mutation = read_json_file(MUTATION_QUEUE_V5_SUMMARY_PATH)
    v5_simulator = read_json_file(SIMULATOR_V5_SUMMARY_PATH)
    v5_scorer = read_json_file(SCORER_V5_SUMMARY_PATH)
    v5_no_trade = read_json_file(NO_TRADE_OPTIMIZER_V5_SUMMARY_PATH)
    v5_mutation_exec = read_json_file(MUTATION_EXEC_V5_SUMMARY_PATH)
    v5_preflight = read_json_file(PREFLIGHT_V5_SUMMARY_PATH)
    v5_baseline_freeze = read_json_file(BASELINE_FREEZE_V5_SUMMARY_PATH)
    v5_safe_append = read_json_file(SAFE_APPEND_V5_SUMMARY_PATH)
    v5_expensive = read_json_file(EXPENSIVE_LANE_V5_SUMMARY_PATH)
    v5_analyzer = read_json_file(V4_ANALYZER_V5_SUMMARY_PATH)

    rows = _build_scoreboard_rows(v3_tournament, v4_tournament, v5_tournament)

    scoreboard = {
        "artifact_type": "public_signal_research_scoreboard_v5",
        "public_signal_research_v5_version": "dopey-public-signal-research-breakthrough-v5",
        "scoreboard_v5_status": "public_signal_research_scoreboard_complete_v5",
        "v5_preflight_status": str(v5_preflight.get("public_signal_research_v5_preflight_status", "")),
        "v5_baseline_freeze_status": str(v5_baseline_freeze.get("baseline_freeze_status", "")),
        "v5_safe_append_status": str(v5_safe_append.get("safe_append_docs_status", "")),
        "v5_expensive_lane_status": str(v5_expensive.get("expensive_lane_runner_status", "")),
        "v5_v4_analyzer_status": str(v5_analyzer.get("v4_result_analyzer_status", "")),
        "v5_mutation_exec_status": str(v5_mutation_exec.get("research_mutation_queue_executor_v5_status", "")),
        "v5_no_trade_optimizer_status": str(v5_no_trade.get("no_trade_filter_optimizer_v5_status", "")),
        "v5_candidate_generator_status": str(v5_candidates.get("research_candidate_generator_v5_status", "")),
        "v5_scorer_status": str(v5_scorer.get("profit_holdout_split_scorer_v5_status", "")),
        "v5_simulator_status": str(v5_simulator.get("research_path_simulator_v5_status", "")),
        "v5_tournament_status": str(v5_tournament.get("research_tournament_v5_status", "")),
        "v5_gate_status": str(v5_gate.get("research_breakthrough_gate_v5_status", "")),
        "v5_mutation_queue_status": str(v5_mutation.get("research_mutation_queue_v5_status", "")),
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "v5_candidate_count": _safe_int(v5_candidates.get("candidate_count", 0)),
        "v5_simulated_trade_count": _safe_int(v5_simulator.get("simulated_trade_count", 0)),
        "v5_pf_above_110_count": _safe_int(v5_tournament.get("pf_above_110_count", 0)),
        "v5_breakthrough_candidate_count": _safe_int(v5_gate.get("breakthrough_candidate_count", 0)),
        "v5_watchlist_count": _safe_int(v5_gate.get("watchlist_count", 0)),
        "v5_improved_vs_v4_count": _safe_int(v5_tournament.get("improved_vs_v4_count", 0)),
        "v5_top_family": str(v5_tournament.get("top_family", "")),
        "v5_top_subfamily": str(v5_tournament.get("top_subfamily", "")),
        "v5_top_cohort": str(v5_tournament.get("top_cohort", "")),
        "v5_top_net_pnl": _safe_float(v5_tournament.get("top_net_pnl", 0.0)),
        "v5_top_profit_factor": _safe_float(v5_tournament.get("top_profit_factor", 0.0)),
        "v5_top_max_drawdown": _safe_float(v5_tournament.get("top_max_drawdown", 0.0)),
        "v5_top_sample_count": _safe_int(v5_tournament.get("top_sample_count", 0)),
        "v5_mutation_queue_count": _safe_int(v5_mutation.get("mutation_queue_count", 0)),
        "v3_top_pf": _safe_float(v3_tournament.get("top_profit_factor", 0.0)),
        "v4_top_pf": _safe_float(v4_tournament.get("top_profit_factor", 0.0)),
        "v4_top_net_pnl": _safe_float(v4_tournament.get("top_net_pnl", 0.0)),
        "v4_pf_above_110_count": _safe_int(v4_tournament.get("pf_above_110_count", 0)),
        "v4_breakthrough_count": _safe_int(v4_tournament.get("candidate_breakthrough_count", 0)),
        "v4_watchlist_count": _safe_int(v4_tournament.get("candidate_breakthrough_count", 0)),  # V4 used candidate_breakthrough_count; we report both
        "uvxy_like_corruption_detected": bool(v5_simulator.get("uvxy_like_corruption_detected", False)),
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
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=list(rows[0].keys()) if rows else [
                "version", "top_family", "top_subfamily", "top_cohort",
                "top_profit_factor", "top_net_pnl", "top_max_drawdown",
                "top_sample_count", "top_symbol_count", "top_sector_count",
                "trade_count", "pf_above_110_count", "improved_vs_prev_count",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # Write HTML dashboard (minimal)
    html_rows = "\n".join(
        f"<tr><td>{r['version']}</td><td>{r['top_family']}</td><td>{r['top_subfamily']}</td>"
        f"<td>{r['top_cofit_factor' if False else 'top_profit_factor']}</td>"
        f"<td>{r['top_net_pnl']}</td><td>{r['top_max_drawdown']}</td>"
        f"<td>{r['top_sample_count']}</td><td>{r['pf_above_110_count']}</td></tr>"
        for r in rows
    )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>DOPEY Public Signal Research Scoreboard V5</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse}"
        "th,td{border:1px solid #888;padding:4px 8px}"
        "th{background:#eee}</style></head><body>"
        "<h1>DOPEY Public Signal Research Scoreboard V5</h1>"
        f"<p>status: {scoreboard['scoreboard_v5_status']}</p>"
        f"<p>v5_min_breakthrough_pf: 1.10 (hard floor, not lowered)</p>"
        f"<p>v5_candidate_count: {scoreboard['v5_candidate_count']}</p>"
        f"<p>v5_simulated_trade_count: {scoreboard['v5_simulated_trade_count']}</p>"
        f"<p>v5_breakthrough_candidate_count: {scoreboard['v5_breakthrough_candidate_count']}</p>"
        f"<p>v5_watchlist_count: {scoreboard['v5_watchlist_count']}</p>"
        f"<p>v5_improved_vs_v4_count: {scoreboard['v5_improved_vs_v4_count']}</p>"
        f"<p>v5_pf_above_110_count: {scoreboard['v5_pf_above_110_count']}</p>"
        f"<p>uvxy_like_corruption_detected: {scoreboard['uvxy_like_corruption_detected']}</p>"
        f"<p>future_leakage_detected: {scoreboard['future_leakage_detected']}</p>"
        f"<p>live_gate_status: {scoreboard['live_gate_status']}</p>"
        f"<p>live_trading_enabled: {scoreboard['live_trading_enabled']}</p>"
        "<h2>Per-version comparison</h2>"
        "<table><thead><tr><th>version</th><th>top_family</th><th>top_subfamily</th>"
        "<th>top_profit_factor</th><th>top_net_pnl</th><th>top_max_drawdown</th>"
        "<th>top_sample_count</th><th>pf_above_110_count</th></tr></thead><tbody>"
        f"{html_rows}</tbody></table></body></html>"
    )
    HTML_PATH.write_text(html, encoding="utf-8")

    md = (
        "# DOPEY Public Signal Research Scoreboard V5\n\n"
        f"- status: `{scoreboard['scoreboard_v5_status']}`\n"
        f"- v5_min_breakthrough_pf: `1.10` (hard floor, not lowered)\n"
        f"- v5_candidate_count: `{scoreboard['v5_candidate_count']}`\n"
        f"- v5_simulated_trade_count: `{scoreboard['v5_simulated_trade_count']}`\n"
        f"- v5_breakthrough_candidate_count: `{scoreboard['v5_breakthrough_candidate_count']}`\n"
        f"- v5_watchlist_count: `{scoreboard['v5_watchlist_count']}`\n"
        f"- v5_improved_vs_v4_count: `{scoreboard['v5_improved_vs_v4_count']}`\n"
        f"- v5_pf_above_110_count: `{scoreboard['v5_pf_above_110_count']}`\n"
        f"- v5_top_family: `{scoreboard['v5_top_family']}`\n"
        f"- v5_top_subfamily: `{scoreboard['v5_top_subfamily']}`\n"
        f"- v5_top_profit_factor: `{scoreboard['v5_top_profit_factor']}`\n"
        f"- v5_top_net_pnl: `{scoreboard['v5_top_net_pnl']}`\n"
        f"- v4_top_profit_factor: `{scoreboard['v4_top_pf']}`\n"
        f"- v4_top_net_pnl: `{scoreboard['v4_top_net_pnl']}`\n"
        f"- uvxy_like_corruption_detected: `{scoreboard['uvxy_like_corruption_detected']}`\n"
        f"- future_leakage_detected: `{scoreboard['future_leakage_detected']}`\n"
        f"- live_gate_status: `{scoreboard['live_gate_status']}`\n"
        f"- live_trading_enabled: `{scoreboard['live_trading_enabled']}`\n"
        f"- thresholds_lowered: `False`\n"
        f"- public_data_only: `True`\n"
    )
    MD_PATH.write_text(md, encoding="utf-8")

    # Quality flags
    quality_flags: list[dict[str, object]] = []
    if not scoreboard["thresholds_lowered"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v5",
                "flag": "thresholds_not_lowered",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if not scoreboard["uvxy_like_corruption_detected"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v5",
                "flag": "no_uvxy_corruption",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if not scoreboard["future_leakage_detected"]:
        quality_flags.append(
            {
                "artifact_type": "public_signal_research_scoreboard_quality_flag_v5",
                "flag": "no_future_leakage",
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    write_jsonl_file(QUALITY_PATH, [record_with_hash(q, "record_hash") for q in quality_flags])

    # Proof
    proof_record = {
        "artifact_type": "public_signal_research_scoreboard_v5_proof",
        "scoreboard_v5_status": scoreboard["scoreboard_v5_status"],
        "live_trading_enabled": False,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(PROOF_PATH, [record_with_hash(proof_record, "proof_hash")])

    return scoreboard


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_scoreboard_v5(), indent=2, sort_keys=True, default=str))
