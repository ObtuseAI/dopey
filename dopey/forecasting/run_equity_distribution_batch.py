"""CLI for a complete core-universe equity distribution research batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE

from .equity_distribution import canonical_equity_forecast_policy
from .operational import run_equity_distribution_forecast_batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-symbol", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    arguments = parser.parse_args()
    result = run_equity_distribution_forecast_batch(
        REQUIRED_HISTORY_UNIVERSE,
        str(arguments.benchmark_symbol),
        Path(arguments.output_root),
        canonical_equity_forecast_policy(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
