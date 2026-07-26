"""HTML / Markdown dashboard renderer for the V7 public signal research scoreboard."""
from __future__ import annotations

import html
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    SCOREBOARD_ROOT,
    record_with_hash,
    write_jsonl_file,
)
from dopey_autonomy.signal_research_v7_common import research_v7_proof_record, write_stage_proof


def build_html(scoreboard: dict, rows: list[dict[str, object]]) -> str:
    def row_cells(r: dict) -> str:
        return (
            f"<td>{html.escape(str(r.get('version', '')))}</td>"
            f"<td>{html.escape(str(r.get('top_family', '')))}</td>"
            f"<td>{html.escape(str(r.get('top_subfamily', '')))}</td>"
            f"<td>{html.escape(str(r.get('top_cohort', '')))}</td>"
            f"<td>{r.get('top_profit_factor', 0.0)}</td>"
            f"<td>{r.get('top_net_pnl', 0.0)}</td>"
            f"<td>{r.get('top_max_drawdown', 0.0)}</td>"
            f"<td>{r.get('top_sample_count', 0)}</td>"
            f"<td>{r.get('top_symbol_count', 0)}</td>"
            f"<td>{r.get('top_sector_count', 0)}</td>"
            f"<td>{r.get('trade_count', 0)}</td>"
            f"<td>{r.get('pf_above_110_count', 0)}</td>"
            f"<td>{r.get('improved_vs_prev_count', 0)}</td>"
        )

    html_rows = "\n".join(f"<tr>{row_cells(r)}</tr>" for r in rows)

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>DOPEY Public Signal Research Scoreboard V7</title>"
        "<style>"
        "body{font-family:sans-serif;margin:1em}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #888;padding:4px 8px;text-align:left}"
        "th{background:#eee}"
        "section{margin-top:1.5em}"
        "</style></head><body>"
        "<h1>DOPEY Public Signal Research Scoreboard V7</h1>"
        f"<p><strong>status:</strong> {html.escape(str(scoreboard.get('scoreboard_v7_status', '')))}</p>"
        f"<p><strong>v7_min_breakthrough_pf:</strong> {scoreboard.get('v7_min_breakthrough_pf', 1.10)} "
        "(hard floor, never lowered)</p>"
        f"<p><strong>thresholds_lowered:</strong> {scoreboard.get('thresholds_lowered', False)}</p>"
        f"<p><strong>public_data_only:</strong> {scoreboard.get('public_data_only', True)}</p>"
        f"<p><strong>live_trading_enabled:</strong> {scoreboard.get('live_trading_enabled', False)}</p>"
        f"<p><strong>live_gate_status:</strong> {html.escape(str(scoreboard.get('live_gate_status', '')))}</p>"
        "<section><h2>V7 counts</h2>"
        "<table><tbody>"
        f"<tr><td>v7_candidate_count</td><td>{scoreboard.get('v7_candidate_count', 0)}</td></tr>"
        f"<tr><td>v7_simulated_trade_count</td><td>{scoreboard.get('v7_simulated_trade_count', 0)}</td></tr>"
        f"<tr><td>v7_pf_above_110_count</td><td>{scoreboard.get('v7_pf_above_110_count', 0)}</td></tr>"
        f"<tr><td>v7_trade_active_pf_above_110_count</td><td>{scoreboard.get('v7_trade_active_pf_above_110_count', 0)}</td></tr>"
        f"<tr><td>v7_breakthrough_candidate_count</td><td>{scoreboard.get('v7_breakthrough_candidate_count', 0)}</td></tr>"
        f"<tr><td>v7_watchlist_count</td><td>{scoreboard.get('v7_watchlist_count', 0)}</td></tr>"
        f"<tr><td>v7_mutation_queue_count</td><td>{scoreboard.get('v7_mutation_queue_count', 0)}</td></tr>"
        f"<tr><td>v7_improved_vs_v6_count</td><td>{scoreboard.get('v7_improved_vs_v6_count', 0)}</td></tr>"
        "</tbody></table></section>"
        "<section><h2>V1-V7 comparison</h2>"
        "<table><thead><tr>"
        "<th>version</th><th>top_family</th><th>top_subfamily</th><th>top_cohort</th>"
        "<th>top_profit_factor</th><th>top_net_pnl</th><th>top_max_drawdown</th>"
        "<th>top_sample_count</th><th>top_symbol_count</th><th>top_sector_count</th>"
        "<th>trade_count</th><th>pf_above_110_count</th><th>improved_vs_prev_count</th>"
        "</tr></thead><tbody>"
        f"{html_rows}</tbody></table></section>"
        "<section><h2>No-trade contribution audit</h2>"
        f"<p>no_trade_ratio: {scoreboard.get('no_trade_ratio', 0.0)}</p>"
        f"<p>trade_active_ratio: {scoreboard.get('trade_active_ratio', 0.0)}</p>"
        f"<p>no_trade_candidate_count: {scoreboard.get('no_trade_candidate_count', 0)}</p>"
        f"<p>no_trade_only_breakthrough_blocked_count: {scoreboard.get('no_trade_only_breakthrough_blocked_count', 0)}</p>"
        f"<p>status: {html.escape(str(scoreboard.get('v7_no_trade_audit_status', '')))}</p>"
        "</section>"
        "<section><h2>Trade-active edge</h2>"
        f"<p>trade_active_candidate_count: {scoreboard.get('trade_active_candidate_count', 0)}</p>"
        f"<p>v7_trade_active_pf_above_110_count: {scoreboard.get('v7_trade_active_pf_above_110_count', 0)}</p>"
        f"<p>status: {html.escape(str(scoreboard.get('v7_trade_active_edge_status', '')))}</p>"
        "</section>"
        "<section><h2>V6 watchlist diagnosis</h2>"
        f"<p>v6_watchlist_count: {scoreboard.get('v6_watchlist_count', 0)}</p>"
        f"<p>v6_improved_watchlist_count: {scoreboard.get('v6_improved_watchlist_count', 0)}</p>"
        f"<p>v6_pf_above_110_count: {scoreboard.get('v6_pf_above_110_count', 0)}</p>"
        f"<p>v6_mutation_queue_count: {scoreboard.get('v6_mutation_queue_count', 0)}</p>"
        f"<p>top_cohort_no_trade_dominant: {scoreboard.get('v6_top_cohort_no_trade_dominant', True)}</p>"
        f"<p>status: {html.escape(str(scoreboard.get('v6_watchlist_diagnosis_v7_status', '')))}</p>"
        "</section>"
        "<section><h2>Trade-active repair policy</h2>"
        f"<p>status: {html.escape(str(scoreboard.get('v7_trade_active_repair_policy_status', '')))}</p>"
        f"<p>future_leakage_detected: {scoreboard.get('future_leakage_detected', False)}</p>"
        "</section>"
        "<section><h2>Mutation execution</h2>"
        f"<p>status: {html.escape(str(scoreboard.get('v7_mutation_exec_status', '')))}</p>"
        "</section>"
        "<section><h2>Breakthrough / watchlist</h2>"
        f"<p>breakthroughs: {scoreboard.get('v7_breakthrough_candidate_count', 0)} / watchlist: {scoreboard.get('v7_watchlist_count', 0)}</p>"
        f"<p>status: {html.escape(str(scoreboard.get('v7_gate_status', '')))}</p>"
        "</section>"
        "<section><h2>Live gate</h2>"
        f"<p>{html.escape(str(scoreboard.get('live_gate_status', '')))}</p>"
        "</section>"
        "</body></html>"
    )


def build_markdown(scoreboard: dict, rows: list[dict[str, object]]) -> str:
    md_rows = "\n".join(
        f"| {r.get('version', '')} | {r.get('top_family', '')} | {r.get('top_subfamily', '')} | "
        f"{r.get('top_cohort', '')} | {r.get('top_profit_factor', 0.0)} | {r.get('top_net_pnl', 0.0)} | "
        f"{r.get('top_max_drawdown', 0.0)} | {r.get('top_sample_count', 0)} | {r.get('top_symbol_count', 0)} | "
        f"{r.get('top_sector_count', 0)} | {r.get('trade_count', 0)} | {r.get('pf_above_110_count', 0)} | "
        f"{r.get('improved_vs_prev_count', 0)} |"
        for r in rows
    )

    return (
        "# DOPEY Public Signal Research Scoreboard V7\n\n"
        f"- status: `{scoreboard.get('scoreboard_v7_status', '')}`\n"
        f"- v7_min_breakthrough_pf: `{scoreboard.get('v7_min_breakthrough_pf', 1.10)}` (hard floor, never lowered)\n"
        f"- thresholds_lowered: `{scoreboard.get('thresholds_lowered', False)}`\n"
        f"- public_data_only: `{scoreboard.get('public_data_only', True)}`\n"
        f"- live_trading_enabled: `{scoreboard.get('live_trading_enabled', False)}`\n"
        f"- live_gate_status: `{scoreboard.get('live_gate_status', '')}`\n"
        f"- no_trade_only_breakthroughs_blocked: `{scoreboard.get('no_trade_only_breakthroughs_blocked', False)}`\n"
        "\n## V7 counts\n\n"
        f"- v7_candidate_count: `{scoreboard.get('v7_candidate_count', 0)}`\n"
        f"- v7_simulated_trade_count: `{scoreboard.get('v7_simulated_trade_count', 0)}`\n"
        f"- v7_pf_above_110_count: `{scoreboard.get('v7_pf_above_110_count', 0)}`\n"
        f"- v7_trade_active_pf_above_110_count: `{scoreboard.get('v7_trade_active_pf_above_110_count', 0)}`\n"
        f"- v7_breakthrough_candidate_count: `{scoreboard.get('v7_breakthrough_candidate_count', 0)}`\n"
        f"- v7_watchlist_count: `{scoreboard.get('v7_watchlist_count', 0)}`\n"
        f"- v7_mutation_queue_count: `{scoreboard.get('v7_mutation_queue_count', 0)}`\n"
        f"- v7_improved_vs_v6_count: `{scoreboard.get('v7_improved_vs_v6_count', 0)}`\n"
        "\n## V1-V7 comparison\n\n"
        "| version | top_family | top_subfamily | top_cohort | top_pf | top_net_pnl | top_dd | "
        "sample | symbols | sectors | trades | pf>1.10 | improved |\n"
        "|---------|------------|---------------|------------|--------|-------------|--------|"
        "--------|---------|---------|--------|----------|----------|\n"
        f"{md_rows}\n"
        "\n## Dashboard sections\n\n"
        "### No-trade contribution audit\n"
        f"- no_trade_ratio: `{scoreboard.get('no_trade_ratio', 0.0)}`\n"
        f"- trade_active_ratio: `{scoreboard.get('trade_active_ratio', 0.0)}`\n"
        f"- no_trade_candidate_count: `{scoreboard.get('no_trade_candidate_count', 0)}`\n"
        f"- no_trade_only_breakthrough_blocked_count: `{scoreboard.get('no_trade_only_breakthrough_blocked_count', 0)}`\n"
        f"- status: `{scoreboard.get('v7_no_trade_audit_status', '')}`\n\n"
        "### Trade-active edge\n"
        f"- trade_active_candidate_count: `{scoreboard.get('trade_active_candidate_count', 0)}`\n"
        f"- v7_trade_active_pf_above_110_count: `{scoreboard.get('v7_trade_active_pf_above_110_count', 0)}`\n"
        f"- status: `{scoreboard.get('v7_trade_active_edge_status', '')}`\n\n"
        "### V6 watchlist diagnosis\n"
        f"- v6_watchlist_count: `{scoreboard.get('v6_watchlist_count', 0)}`\n"
        f"- v6_improved_watchlist_count: `{scoreboard.get('v6_improved_watchlist_count', 0)}`\n"
        f"- v6_pf_above_110_count: `{scoreboard.get('v6_pf_above_110_count', 0)}`\n"
        f"- v6_mutation_queue_count: `{scoreboard.get('v6_mutation_queue_count', 0)}`\n"
        f"- top_cohort_no_trade_dominant: `{scoreboard.get('v6_top_cohort_no_trade_dominant', True)}`\n"
        f"- status: `{scoreboard.get('v6_watchlist_diagnosis_v7_status', '')}`\n\n"
        "### Trade-active repair policy\n"
        f"- status: `{scoreboard.get('v7_trade_active_repair_policy_status', '')}`\n"
        f"- future_leakage_detected: `{scoreboard.get('future_leakage_detected', False)}`\n\n"
        "### Mutation execution\n"
        f"- status: `{scoreboard.get('v7_mutation_exec_status', '')}`\n\n"
        "### Breakthrough / watchlist\n"
        f"- breakthroughs: `{scoreboard.get('v7_breakthrough_candidate_count', 0)}`\n"
        f"- watchlist: `{scoreboard.get('v7_watchlist_count', 0)}`\n"
        f"- status: `{scoreboard.get('v7_gate_status', '')}`\n\n"
        "### Live gate\n"
        f"- `{scoreboard.get('live_gate_status', '')}`\n"
    )


def write_dashboard(
    scoreboard: dict,
    rows: list[dict[str, object]],
    html_path: Path,
    md_path: Path,
) -> dict[str, object]:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(build_html(scoreboard, rows), encoding="utf-8")
    md_path.write_text(build_markdown(scoreboard, rows), encoding="utf-8")
    return {
        "html_path": str(html_path),
        "md_path": str(md_path),
        "dashboard_v7_status": "public_signal_research_dashboard_complete_v7",
    }


def run_public_signal_research_dashboard_v7() -> dict[str, object]:
    """Self-contained entry point: regenerate the full scoreboard and dashboards."""
    # Import here to avoid circular import at module load.
    from dopey_scoreboard.public_signal_research_scoreboard_v7 import (
        HTML_PATH,
        MD_PATH,
        PROOF_PATH as SCOREBOARD_PROOF_PATH,
        QUALITY_PATH,
        ROWS_PATH,
        SCOREBOARD_PATH,
        run_public_signal_research_scoreboard_v7,
    )

    scoreboard = run_public_signal_research_scoreboard_v7()
    rows = scoreboard.get("rows", [])
    if not isinstance(rows, list):
        rows = []

    dashboard = write_dashboard(scoreboard, rows, HTML_PATH, MD_PATH)

    # Dashboard-specific proof record
    proof_payload = {
        "scoreboard_path": str(SCOREBOARD_PATH),
        "rows_path": str(ROWS_PATH),
        "html_path": str(HTML_PATH),
        "md_path": str(MD_PATH),
        "quality_flags_path": str(QUALITY_PATH),
        "scoreboard_proof_path": str(SCOREBOARD_PROOF_PATH),
        "dashboard_v7_status": dashboard["dashboard_v7_status"],
        "live_gate_status": str(scoreboard.get("live_gate_status", "disabled_live_gate_locked")),
    }
    write_stage_proof(
        SCOREBOARD_ROOT / "public_signal_research_dashboard_v7_proof.jsonl",
        "public_signal_research_dashboard_v7",
        dashboard["dashboard_v7_status"],
        proof_payload,
    )

    return {**scoreboard, **dashboard}


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_dashboard_v7(), indent=2, sort_keys=True, default=str))
