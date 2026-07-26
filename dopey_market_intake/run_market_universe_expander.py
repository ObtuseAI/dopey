"""CLI runner for market universe expansion."""
from __future__ import annotations

import json

from .market_universe_expander import run_market_universe_expander


def main() -> int:
    summary = run_market_universe_expander(15)
    print(json.dumps({
        "market_universe_expansion_status": summary["market_universe_expansion_status"],
        "symbols_attempted": summary["symbols_attempted"],
        "symbols_loaded": summary["symbols_loaded"],
        "summary_path": summary["artifact_paths"]["market_universe_expansion_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
