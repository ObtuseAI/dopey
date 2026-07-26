"""Repair dashboard HTML/MD for conditional champion retune."""
from __future__ import annotations


def render_public_champion_repair_dashboard_v1(scoreboard: dict[str, object]) -> str:
    sections = [
        ("Original Champions", scoreboard.get("original_champion_count", 0)),
        ("Conditional Champions", scoreboard.get("conditional_champion_names", [])),
        ("Retuned Hardened", scoreboard.get("retuned_hardened_names", [])),
        ("Retuned Conditional", scoreboard.get("retuned_conditional_names", [])),
        ("Retuned Demoted", scoreboard.get("retuned_demoted_names", [])),
        ("Salvage Candidates", scoreboard.get("salvage_candidate_names", [])),
        ("Confirmed Kills", scoreboard.get("kill_confirmed_names", [])),
        ("Live Gate", scoreboard.get("live_gate_status", "")),
    ]
    body = ["<html><body><h1>DOPEY Public Champion Repair Dashboard V1</h1>"]
    for title, content in sections:
        body.append(f"<h2>{title}</h2><pre>{content}</pre>")
    body.append("<p>live_trading_enabled: false</p></body></html>")
    return "\n".join(body)


def render_public_champion_repair_dashboard_markdown_v1(scoreboard: dict[str, object]) -> str:
    return "\n".join([
        "# DOPEY Public Champion Repair Dashboard V1",
        f"- retuned_hardened_count: `{len(scoreboard.get('retuned_hardened_names', []))}`",
        f"- retuned_conditional_count: `{len(scoreboard.get('retuned_conditional_names', []))}`",
        f"- live_gate_status: `{scoreboard.get('live_gate_status', '')}`",
        f"- live_trading_enabled: `{scoreboard.get('live_trading_enabled', False)}`",
    ]) + "\n"
