"""CLI entrypoint for the real-history signal engine lane."""
from __future__ import annotations

import json

from .real_history_signal_engine import run_real_history_signal_engine


def main() -> int:
    result = run_real_history_signal_engine()
    print(
        json.dumps(
            {
                "signal_engine_status": result["signal_engine_status"],
                "history_dataset_status": result["history_dataset_status"],
                "real_history_used": result["real_history_used"],
                "directional_setup_count": result.get("directional_setup_count", 0),
                "long_call_candidate_count": result.get("long_call_candidate_count", 0),
                "long_put_candidate_count": result.get("long_put_candidate_count", 0),
                "no_trade_count": result.get("no_trade_count", 0),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
