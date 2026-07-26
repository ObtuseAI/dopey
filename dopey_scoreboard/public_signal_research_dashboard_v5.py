"""V5 public signal research dashboard (placeholder compatibility shim)."""
from __future__ import annotations


def render_public_signal_research_dashboard_v5(scoreboard: dict) -> str:
    """Render V5 dashboard HTML (compat shim).

    The actual HTML is produced by `public_signal_research_scoreboard_v5.py`.
    This shim exists so the dashboard module is importable.
    """
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>DOPEY V5 Dashboard</title></head><body>"
        f"<h1>V5 Dashboard (compat shim)</h1>"
        f"<pre>{scoreboard}</pre>"
        "</body></html>"
    )


def render_public_signal_research_dashboard_markdown_v5(scoreboard: dict) -> str:
    """Render V5 dashboard markdown (compat shim)."""
    return f"# V5 Dashboard\n\n```\n{scoreboard}\n```\n"
