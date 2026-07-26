"""CLI runner for open options autonomous normalizer."""
from __future__ import annotations

import json

from .open_options_autonomous_normalizer import run_open_options_autonomous_normalizer


def main() -> int:
    result = run_open_options_autonomous_normalizer()
    print(json.dumps({
        "open_options_normalization_status": result["open_options_normalization_status"],
        "normalized_options_file_count": result["normalized_options_file_count"],
        "quote_priced_backtest_allowed": result["quote_priced_backtest_allowed"],
        "summary_path": result["artifact_paths"]["open_options_normalization_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

