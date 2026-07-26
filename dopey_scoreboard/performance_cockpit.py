"""Render static performance cockpit artifacts."""
from __future__ import annotations

import html
from pathlib import Path


def render_performance_cockpit(summary: dict, markdown_path: Path, html_path: Path) -> tuple[Path, Path]:
    markdown_lines = ["# DOPEY Performance Cockpit", ""]
    markdown_lines.append("- paper_only: `true`")
    markdown_lines.append("- live_trading_enabled: `false`")
    markdown_lines.append(f"- pnl_scoreboard_status: `{summary.get('pnl_scoreboard_status', '')}`")
    markdown_lines.append("")
    markdown_lines.append("## Top Strategies")
    for row in summary.get("top_strategies_by_net_pnl", []):
        markdown_lines.append(f"- `{row['strategy_family']}` pnl=`{row['net_paper_pnl']}` drawdown=`{row['max_drawdown']}` action=`{row['paper_action']}`")
    markdown_lines.append("")
    markdown_lines.append("## Killed Strategies")
    for strategy in summary.get("strategies_killed", []):
        markdown_lines.append(f"- `{strategy}`")
    markdown_lines.append("")
    markdown_lines.append("## Promoted Strategies")
    for strategy in summary.get("strategies_promoted", []):
        markdown_lines.append(f"- `{strategy}`")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")

    rows = "\n".join(
        f"<tr><td>{html.escape(str(row['strategy_family']))}</td><td>{row['net_paper_pnl']}</td><td>{row['max_drawdown']}</td><td>{html.escape(str(row['paper_action']))}</td></tr>"
        for row in summary.get("top_strategies_by_net_pnl", [])
    )
    html_doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>DOPEY Performance Cockpit</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid #cbd5e1;padding:8px;text-align:left}}th{{background:#e2e8f0}}</style></head>
<body><h1>DOPEY Performance Cockpit</h1><p>Paper-only P&amp;L cockpit. Live trading is disabled.</p>
<table><thead><tr><th>Strategy</th><th>Net Paper P&amp;L</th><th>Max Drawdown</th><th>Paper Action</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_doc, encoding="utf-8")
    return markdown_path, html_path

