"""Static dashboard rendering for public signal deepening scoreboard V4."""
from __future__ import annotations

import html


def render_public_signal_deepening_dashboard_v4(scoreboard: dict[str, object], rows: list[dict[str, object]]) -> str:
    table_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('rank', '')))}</td>"
        f"<td>{html.escape(str(row.get('cohort_level', '')))}</td>"
        f"<td>{html.escape(str(row.get('cohort_id', '')))}</td>"
        f"<td>{html.escape(str(row.get('net_pnl', '')))}</td>"
        f"<td>{html.escape(str(row.get('profit_factor', '')))}</td>"
        f"<td>{html.escape(str(row.get('max_drawdown', '')))}</td>"
        f"<td>{html.escape(str(row.get('sample_count', '')))}</td>"
        f"<td>{html.escape(str(row.get('promotion_level', '')))}</td>"
        "</tr>"
        for row in rows[:50]
    )
    champions = ", ".join(str(name) for name in scoreboard.get("active_champions", [])) or "none"
    killed = scoreboard.get("killed_cohort_count", 0)
    near = scoreboard.get("near_champion_count", 0)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>DOPEY Public Signal Deepening Scoreboard V4</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #151515; background: #f6f7f3; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin: 0 0 22px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ border: 1px solid #d5d8d1; padding: 7px; text-align: left; font-size: 13px; }}
    th {{ background: #e8eee1; }}
    .metric {{ display: inline-block; margin: 0 18px 10px 0; font-weight: 700; }}
    .locked {{ color: #8a3300; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>DOPEY Public Signal Deepening Scoreboard V4</h1>
  <section class="locked">Paper-only public-data artifact. Live trading disabled. No broker, credentials, or orders. No Robinhood live trading; official market-data lanes only if permitted.</section>
  <section>
    <span class="metric">total_public_paper_pnl: {scoreboard.get('total_public_paper_pnl', 0.0)}</span>
    <span class="metric">trade_count: {scoreboard.get('trade_count', 0)}</span>
    <span class="metric">active_champions: {champions}</span>
    <span class="metric">near_champions: {near}</span>
    <span class="metric">killed_cohorts: {killed}</span>
  </section>
  <section>
    <h2>Cohort Scoreboard</h2>
    <table>
      <thead><tr><th>Rank</th><th>Cohort Level</th><th>Cohort ID</th><th>Net P&amp;L</th><th>Profit Factor</th><th>Max Drawdown</th><th>Samples</th><th>Promotion</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </section>
  <section>
    <h2>Next Mutation Queue</h2>
    <p>{scoreboard.get('next_mutation_queue_count', 0)} candidates queued; {killed} fragile cohorts killed.</p>
  </section>
</body>
</html>
"""


def render_public_signal_deepening_dashboard_markdown_v4(scoreboard: dict[str, object], rows: list[dict[str, object]]) -> str:
    champions = ", ".join(str(name) for name in scoreboard.get("active_champions", [])) or "none"
    lines = [
        "# DOPEY Public Signal Deepening Scoreboard V4",
        "",
        "> Paper-only public-data artifact. Live trading disabled. No broker, credentials, or orders.",
        "> Official Robinhood agent/MCP market-data lane allowed only if official/permitted; unofficial access blocked.",
        "",
        f"- total_public_paper_pnl: `{scoreboard.get('total_public_paper_pnl', 0.0)}`",
        f"- trade_count: `{scoreboard.get('trade_count', 0)}`",
        f"- active_champions: `{champions}`",
        f"- near_champion_count: `{scoreboard.get('near_champion_count', 0)}`",
        f"- killed_cohort_count: `{scoreboard.get('killed_cohort_count', 0)}`",
        f"- next_mutation_queue_count: `{scoreboard.get('next_mutation_queue_count', 0)}`",
        "",
        "| Rank | Cohort Level | Cohort ID | Net P&L | Profit Factor | Max DD | Samples | Promotion |",
        "|------|--------------|-----------|---------|---------------|--------|---------|-----------|",
    ]
    for row in rows[:30]:
        lines.append(
            f"| {row.get('rank', '')} | {row.get('cohort_level', '')} | {row.get('cohort_id', '')} | "
            f"{row.get('net_pnl', 0.0)} | {row.get('profit_factor', 0.0)} | {row.get('max_drawdown', 0.0)} | "
            f"{row.get('sample_count', 0)} | {row.get('promotion_level', '')} |"
        )
    return "\n".join(lines) + "\n"
