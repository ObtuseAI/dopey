"""CLI for paper-only autonomous rotation engine."""
from __future__ import annotations

import json

from .autonomous_paper_rotation_engine import run_autonomous_paper_rotation_engine


def main() -> int:
    result = run_autonomous_paper_rotation_engine()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
