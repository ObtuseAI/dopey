"""CLI runner for V4 profitable slice miner."""
from __future__ import annotations

import json

from dopey_signal_research.profitable_slice_miner_v4 import run_profitable_slice_miner_v4


def main() -> int:
    summary = run_profitable_slice_miner_v4()
    print(
        json.dumps(
            {
                "profitable_slice_miner_status": summary["profitable_slice_miner_status"],
                "slice_count": summary["slice_count"],
                "profitable_slice_count": summary["profitable_slice_count"],
                "loss_driver_slice_count": summary["loss_driver_slice_count"],
                "summary_path": summary["artifact_paths"]["profitable_slice_miner_v4_summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
