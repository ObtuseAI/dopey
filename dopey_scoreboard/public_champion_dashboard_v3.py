"""Static dashboard rendering for public champion scoreboard V3."""
from __future__ import annotations

import html


def render_public_champion_dashboard_v3(scoreboard: dict[str, object], rows: list[dict[str, object]]) -> str:
    table_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('rank', '')))}</td>"
        f"<td>{html.escape(str(row.get('strategy_id', '')))}</td>"
        f"<td>{html.escape(str(row.get('net_pnl', '')))}</td>"
        f"<td>{html.escape(str(row.get('profit_factor', '')))}</td>"
        f"<td>{html.escape(str(row.get('max_drawdown', '')))}</td>"
        f"<td>{html.escape(str(row.get('promotion_level', '')))}</td>"
        "</tr>"
        for row in rows[:50]
    )
    champions = ", ".join(str(name) for name in scoreboard.get("active_champions", [])) or "none"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>DOPEY Public Champion Scoreboard V3</title>
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
  <h1>DOPEY Public Champion Scoreboard V3</h1>
  <section class="locked">Paper-only public-data artifact. Live trading disabled. No broker, credentials, or orders.</section>
  <section>
    <span class="metric">total_public_paper_pnl: {scoreboard.get('total_public_paper_pnl', 0.0)}</span>
    <span class="metric">trade_count: {scoreboard.get('trade_count', 0)}</span>
    <span class="metric">active_champions: {champions}</span>
  </section>
  <section>
    <h2>Strategy Scoreboard</h2>
    <table>
      <thead><tr><th>Rank</th><th>Strategy</th><th>Net P&amp;L</th><th>Profit Factor</th><th>Max Drawdown</th><th>Promotion</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </section>
  <section>
    <h2>Next Mutation Queue</h2>
    <p>{scoreboard.get('next_mutation_queue_count', 0)} candidates queued; {scoreboard.get('loser_kill_count', 0)} weak strategies killed or throttled.</p>
  </section>
</body>
</html>
"""


def render_public_champion_dashboard_markdown(scoreboard: dict[str, object], rows: list[dict[str, object]]) -> str:
    lines = ["# DOPEY Public Champion Scoreboard V3", ""]
    lines.append(f"- total_public_paper_pnl: `{scoreboard.get('total_public_paper_pnl', 0.0)}`")
    lines.append(f"- trade_count: `{scoreboard.get('trade_count', 0)}`")
    lines.append(f"- active_champions: `{scoreboard.get('active_champions', [])}`")
    lines.append(f"- live_trading_enabled: `{scoreboard.get('live_trading_enabled', False)}`")
    lines.append("")
    lines.append("## Top Strategies")
    for row in rows[:15]:
        lines.append(f"- `{row.get('rank')}` `{row.get('strategy_id')}` pnl=`{row.get('net_pnl')}` pf=`{row.get('profit_factor')}` dd=`{row.get('max_drawdown')}` promotion=`{row.get('promotion_level')}`")
    lines.append("")
    lines.append("## Risk And Stress")
    lines.append(f"- slippage_stress_impact: `{scoreboard.get('slippage_stress_impact', {})}`")
    lines.append(f"- theta_stress_impact: `{scoreboard.get('theta_stress_impact', {})}`")
    lines.append(f"- iv_shock_impact: `{scoreboard.get('iv_shock_impact', {})}`")
    return "\n".join(lines) + "\n"

