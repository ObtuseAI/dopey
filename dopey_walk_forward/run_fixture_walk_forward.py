"""Dopey walk-forward replay runner entry point.

Usage:
    python -m dopey_walk_forward.run_fixture_walk_forward

Runs the full offline deterministic walk-forward replay and prints a concise JSON summary.
No broker connection, no credentials, no live order placement, no network.
"""
from __future__ import annotations

from .runner import main


if __name__ == "__main__":
    raise SystemExit(main())
