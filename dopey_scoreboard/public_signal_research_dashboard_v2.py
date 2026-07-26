"""Public signal research dashboard V2."""
from __future__ import annotations


def render_public_signal_research_dashboard_v2(summary: dict[str, object]) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>DOPEY Public Signal Research Dashboard V2</title></head>
<body>
<h1>DOPEY Public Signal Research Breakthrough V2</h1>
<p>Status: {summary.get('scoreboard_status', '')}</p>
<p>V1 symbol count: {summary.get('v1_symbol_count', 0)}</p>
<p>V2 symbol count: {summary.get('v2_symbol_count', 0)}</p>
<p>V1 sector count: {summary.get('v1_sector_count', 0)}</p>
<p>V2 sector count: {summary.get('v2_sector_count', 0)}</p>
<p>Breakthrough candidates: {summary.get('breakthrough_candidate_count', 0)}</p>
<p>Watchlist count: {summary.get('watchlist_count', 0)}</p>
<p>Mutation queue: {summary.get('mutation_queue_count', 0)}</p>
<p>Live gate: {summary.get('live_gate_status', 'disabled_live_gate_locked')}</p>
</body></html>"""


def render_public_signal_research_dashboard_markdown_v2(summary: dict[str, object]) -> str:
    return "\n".join([
        "# DOPEY Public Signal Research Dashboard V2",
        "",
        f"- scoreboard_status: `{summary.get('scoreboard_status', '')}`",
        f"- v2_symbol_count: `{summary.get('v2_symbol_count', 0)}`",
        f"- breakthrough_candidate_count: `{summary.get('breakthrough_candidate_count', 0)}`",
        f"- live_trading_enabled: `false`",
    ])
