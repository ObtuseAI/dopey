"""CLI for continuous protected autonomous research promotion."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .cycle import run_autonomous_promotion_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate autonomous symbol and strategy promotion gates")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    output = run_autonomous_promotion_cycle(
        arguments.evidence,
        arguments.output_root,
        datetime.now(timezone.utc),
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
