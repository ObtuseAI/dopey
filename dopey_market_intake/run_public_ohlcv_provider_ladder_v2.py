"""CLI runner for public OHLCV provider ladder V2."""
from __future__ import annotations

import json

from .provider_ladder_v2 import run_public_ohlcv_provider_ladder_v2
from .public_ohlcv_provider_models import PRIMARY_UNIVERSE


def main() -> int:
    summary = run_public_ohlcv_provider_ladder_v2(list(PRIMARY_UNIVERSE), False, 20)
    print(json.dumps({
        "provider_ladder_status": summary["provider_ladder_status"],
        "providers_attempted": summary["providers_attempted"],
        "providers_successful": summary["providers_successful"],
        "symbol_success_count": summary["symbol_success_count"],
        "public_ohlcv_rows_loaded": summary["public_ohlcv_rows_loaded"],
        "summary_path": summary["artifact_paths"]["public_ohlcv_provider_ladder_v2_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
