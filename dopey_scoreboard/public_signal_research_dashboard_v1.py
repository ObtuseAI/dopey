"""Public signal research dashboard V1."""
from __future__ import annotations


def render_public_signal_research_dashboard_v1(summary: dict[str, object]) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>DOPEY Public Signal Research Dashboard V1</title></head>
<body>
<h1>DOPEY Public Signal Research Breakthrough V1</h1>
<p>Status: {summary.get('scoreboard_status', '')}</p>
<p>Feature count: {summary.get('feature_count', 0)}</p>
<p>Research candidate count: {summary.get('candidate_count', 0)}</p>
<p>Breakthrough candidate count: {summary.get('breakthrough_candidate_count', 0)}</p>
<p>Watchlist count: {summary.get('watchlist_count', 0)}</p>
<p>Quarantined families: {summary.get('quarantined_family_count', 0)}</p>
<p>Live gate: {summary.get('live_gate_status', 'disabled_live_gate_locked')}</p>
<p>Live trading enabled: false</p>
</body></html>"""


def render_public_signal_research_dashboard_markdown_v1(summary: dict[str, object]) -> str:
    return "\n".join([
        "# DOPEY Public Signal Research Dashboard V1",
        "",
        f"- scoreboard_status: `{summary.get('scoreboard_status', '')}`",
        f"- breakthrough_candidate_count: `{summary.get('breakthrough_candidate_count', 0)}`",
        f"- live_gate_status: `{summary.get('live_gate_status', '')}`",
        f"- live_trading_enabled: `false`",
    ])
