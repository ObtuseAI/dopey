"""CLI entrypoint for the paper-only equity-first swing engine."""
from __future__ import annotations

import json

from .engine import run_equity_first_swing_engine


def main() -> int:
    summary = run_equity_first_swing_engine()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
