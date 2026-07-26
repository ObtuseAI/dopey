"""V6 public signal research dashboard (placeholder compatibility shim)."""
from __future__ import annotations


def render_public_signal_research_dashboard_v6(scoreboard: dict) -> str:
    """Render V6 dashboard HTML (compat shim).

    The actual HTML is produced by `public_signal_research_scoreboard_v6.py`.
    This shim exists so the dashboard module is importable.
    """
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>DOPEY V6 Dashboard</title></head><body>"
        f"<h1>V6 Dashboard (compat shim)</h1>"
        f"<pre>{scoreboard}</pre>"
        "</body></html>"
    )


def render_public_signal_research_dashboard_markdown_v6(scoreboard: dict) -> str:
    """Render V6 dashboard markdown (compat shim)."""
    return f"# V6 Dashboard\n\n```\n{scoreboard}\n```\n"
