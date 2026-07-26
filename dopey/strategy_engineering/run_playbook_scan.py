"""Network-free CLI for the autonomous playbook scan.

Hunts every computable setup archetype in the strategy playbook across the
whole OHLCV spine and prints an honest, promotion-ineligible JSON report.

    python -m dopey.strategy_engineering.run_playbook_scan \
        --history-root dopey_data/history/raw
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .playbook_scanner import scan_playbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous playbook scan (paper research; no edge claimed).")
    parser.add_argument("--history-root", default="dopey_data/history/raw")
    parser.add_argument("--max-detections", type=int, default=200)
    args = parser.parse_args(argv)

    report = scan_playbook(Path(args.history_root), max_detections=args.max_detections)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
