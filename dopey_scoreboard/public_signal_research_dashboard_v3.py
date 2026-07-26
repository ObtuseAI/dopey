"""Public signal research dashboard V3."""
from __future__ import annotations


def render_public_signal_research_dashboard_v3(summary: dict[str, object]) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>DOPEY Public Signal Research V3</title></head>
<body>
<h1>DOPEY Public Signal Research Breakthrough V3</h1>
<p>Status: {summary.get('scoreboard_status', '')}</p>
<h2>V1 vs V2 vs V3</h2>
<ul>
<li>V1 symbols: {summary.get('v1_symbol_count', 0)} | V2: {summary.get('v2_symbol_count', 0)} | V3: {summary.get('v3_symbol_count', 0)}</li>
<li>V2 top PF: {summary.get('v2_top_profit_factor', 0)} | V3 top PF: {summary.get('v3_top_profit_factor', 0)}</li>
</ul>
<h2>Mutation Queue Execution</h2>
<p>Executed: {summary.get('executed_mutation_count', 0)} / {summary.get('input_mutation_count', 0)}</p>
<h2>Family Templates</h2>
<p>Continuation: {summary.get('continuation_template_enabled', False)} | Volume: {summary.get('volume_template_enabled', False)}</p>
<h2>Live Gate</h2>
<p>{summary.get('live_gate_status', 'disabled_live_gate_locked')} — live trading disabled</p>
</body></html>"""


def render_public_signal_research_dashboard_markdown_v3(summary: dict[str, object]) -> str:
    return (
        "# DOPEY Public Signal Research Dashboard V3\n\n"
        f"- Scoreboard status: {summary.get('scoreboard_status', '')}\n"
        f"- V3 breakthrough count: {summary.get('breakthrough_candidate_count', 0)}\n"
        f"- V3 watchlist count: {summary.get('watchlist_count', 0)}\n"
        f"- Mutation queue V3: {summary.get('mutation_queue_count', 0)}\n"
        f"- Live gate: {summary.get('live_gate_status', '')}\n"
    )
