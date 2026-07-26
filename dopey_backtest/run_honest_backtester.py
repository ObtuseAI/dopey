"""CLI entrypoint for DOPEY's honest offline backtester."""
from __future__ import annotations

import json

from .honest_backtester import run_honest_backtester


def main() -> int:
    result = run_honest_backtester()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

