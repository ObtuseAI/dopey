"""Public signal research dashboard V4 (markdown + HTML)."""


def render_public_signal_research_dashboard_v4(summary: dict[str, object]) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>DOPEY Public Signal Research V4</title></head>
<body>
<h1>DOPEY Public Signal Research Breakthrough V4</h1>
<p>Status: {summary.get('scoreboard_status', '')}</p>
<h2>V1 vs V2 vs V3 vs V4</h2>
<ul>
<li>V1 symbols: {summary.get('v1_symbol_count', 0)} | V2: {summary.get('v2_symbol_count', 0)} | V3: {summary.get('v3_symbol_count', 0)} | V4: {summary.get('v4_symbol_count', 0)}</li>
<li>V2 top PF: {summary.get('v2_top_profit_factor', 0)} | V3 top PF: {summary.get('v3_top_profit_factor', 0)} | V4 top PF: {summary.get('v4_top_profit_factor', 0)}</li>
</ul>
<h2>V4 Subfamily Separation</h2>
<p>Continuation: {summary.get('v4_continuation_candidate_count', 0)} | Volume: {summary.get('v4_volume_candidate_count', 0)}</p>
<p>Subfamily count: {summary.get('v4_subfamily_count', 0)} | Family count: {summary.get('v4_family_count', 0)} | Cohort count: {summary.get('v4_cohort_count', 0)}</p>
<h2>UVXY-like corruption check</h2>
<p>Detected: {summary.get('uvxy_like_corruption_detected', False)}</p>
<h2>Mutation Queue Execution (V3 + V4)</h2>
<p>V3 executed: {summary.get('v3_executed_mutation_count', 0)} / {summary.get('v3_input_mutation_count', 0)} | V4 mutation queue: {summary.get('v4_mutation_queue_count', 0)}</p>
<h2>Live Gate</h2>
<p>{summary.get('live_gate_status', 'disabled_live_gate_locked')} — live trading disabled</p>
</body></html>"""


def render_public_signal_research_dashboard_markdown_v4(summary: dict[str, object]) -> str:
    return (
        "# DOPEY Public Signal Research Dashboard V4\n\n"
        f"- Scoreboard status: {summary.get('scoreboard_status', '')}\n"
        f"- V4 breakthrough count: {summary.get('v4_breakthrough_candidate_count', 0)}\n"
        f"- V4 watchlist count: {summary.get('v4_watchlist_count', 0)}\n"
        f"- V4 mutation queue count: {summary.get('v4_mutation_queue_count', 0)}\n"
        f"- V4 improved vs V3 count: {summary.get('v4_improved_vs_v3_count', 0)}\n"
        f"- V4 top profit factor: {summary.get('v4_top_profit_factor', 0.0)}\n"
        f"- UVXY-like corruption detected: {summary.get('uvxy_like_corruption_detected', False)}\n"
        f"- Live gate: {summary.get('live_gate_status', '')}\n"
    )
