"""CLI for one hash-pinned, research-only equity distribution artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .equity_distribution import canonical_equity_forecast_policy
from .operational import run_equity_distribution_forecast_artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--benchmark-symbol", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    result = run_equity_distribution_forecast_artifact(
        str(arguments.symbol),
        str(arguments.benchmark_symbol),
        Path(arguments.output),
        canonical_equity_forecast_policy(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
