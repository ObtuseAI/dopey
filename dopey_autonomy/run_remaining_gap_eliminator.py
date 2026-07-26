"""CLI for remaining gap eliminator."""
from __future__ import annotations

import json

from .remaining_gap_eliminator import run_remaining_gap_eliminator


def main() -> int:
    result = run_remaining_gap_eliminator()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
