"""CLI for the governed local public-lake candidate bridge."""
from __future__ import annotations

import argparse
import json

from .common import REPO_ROOT
from .universe import seed_universe_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed governed equity-research candidates from local public OHLCV")
    parser.add_argument("--batch-size", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(seed_universe_candidates(REPO_ROOT, int(args.batch_size)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
