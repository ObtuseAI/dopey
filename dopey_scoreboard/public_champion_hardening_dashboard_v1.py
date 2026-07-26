"""HTML dashboard for public champion hardening scoreboard V1."""
from __future__ import annotations


def render_public_champion_hardening_dashboard_v1(scoreboard: dict[str, object]) -> str:
    sections = [
        ("Original 9 Champions", scoreboard.get("original_champion_names", [])),
        ("Hardened Champions", scoreboard.get("hardened_champion_names", [])),
        ("Conditional Champions", scoreboard.get("conditional_champion_names", [])),
        ("Demoted Champions", scoreboard.get("demoted_champion_names", [])),
        ("Top Failure Reasons", scoreboard.get("top_failure_reasons", {})),
        ("Repair Queue Count", scoreboard.get("repair_queue_count", 0)),
        ("Live Gate", scoreboard.get("live_gate_status", "disabled_live_gate_locked")),
    ]
    body = ["<html><head><title>DOPEY Champion Hardening Dashboard V1</title></head><body>"]
    body.append("<h1>DOPEY Public Paper Champion Hardening Dashboard V1</h1>")
    for title, content in sections:
        body.append(f"<h2>{title}</h2>")
        if isinstance(content, dict):
            body.append("<ul>")
            for key, value in content.items():
                body.append(f"<li>{key}: {value}</li>")
            body.append("</ul>")
        elif isinstance(content, list):
            body.append("<ul>")
            for item in content:
                body.append(f"<li>{item}</li>")
            body.append("</ul>")
        else:
            body.append(f"<p>{content}</p>")
    body.append("<p>live_trading_enabled: false</p>")
    body.append("</body></html>")
    return "\n".join(body)


def render_public_champion_hardening_dashboard_markdown_v1(scoreboard: dict[str, object]) -> str:
    lines = [
        "# DOPEY Public Paper Champion Hardening Dashboard V1",
        "",
        f"- original champion count: `{len(scoreboard.get('original_champion_names', []))}`",
        f"- hardened champion count: `{len(scoreboard.get('hardened_champion_names', []))}`",
        f"- conditional champion count: `{len(scoreboard.get('conditional_champion_names', []))}`",
        f"- demoted champion count: `{len(scoreboard.get('demoted_champion_names', []))}`",
        f"- repair queue count: `{scoreboard.get('repair_queue_count', 0)}`",
        f"- live gate status: `{scoreboard.get('live_gate_status', '')}`",
        f"- live_trading_enabled: `{scoreboard.get('live_trading_enabled', False)}`",
    ]
    return "\n".join(lines) + "\n"
