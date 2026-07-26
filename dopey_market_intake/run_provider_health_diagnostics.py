"""CLI runner for provider health diagnostics."""
from __future__ import annotations

import json

from .provider_health_diagnostics import run_provider_health_diagnostics
from .public_ohlcv_provider_models import PRIMARY_UNIVERSE


def main() -> int:
    summary = run_provider_health_diagnostics(list(PRIMARY_UNIVERSE), 12)
    print(json.dumps({
        "yfinance_diagnosis": summary["yfinance_diagnosis"],
        "openbb_diagnosis": summary["openbb_diagnosis"],
        "stooq_diagnosis": summary["stooq_diagnosis"],
        "yahoo_direct_diagnosis": summary["yahoo_direct_diagnosis"],
        "summary_path": summary["artifact_paths"]["provider_health_diagnostics_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
