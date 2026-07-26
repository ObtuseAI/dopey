"""CLI for S-tier long-premium engineering target V2."""
from __future__ import annotations

import json

from .s_tier_long_premium_engine_v2 import run_s_tier_long_premium_engine_v2


def main() -> int:
    result = run_s_tier_long_premium_engine_v2()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
