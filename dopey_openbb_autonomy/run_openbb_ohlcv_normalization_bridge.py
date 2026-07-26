"""CLI for OpenBB OHLCV normalization bridge."""
from __future__ import annotations

import json

from .openbb_ohlcv_normalization_bridge import run_openbb_ohlcv_normalization_bridge


def main() -> int:
    result = run_openbb_ohlcv_normalization_bridge()
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
