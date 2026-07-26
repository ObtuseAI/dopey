"""CLI for planning or executing the research acceleration schedule."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from .common import REPO_ROOT
from .cycle import run_acceleration_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or execute allowlisted DOPEY research lanes")
    parser.add_argument("--mode", choices=("plan", "execute"), required=True)
    parser.add_argument("--lane", action="append", dest="lanes")
    args = parser.parse_args()
    lane_ids = tuple(str(value) for value in (args.lanes or []))
    result = run_acceleration_cycle(REPO_ROOT, str(args.mode), lane_ids, datetime.now(timezone.utc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if str(result.get("cycle_status", "")) == "completed_with_failures" else 0


if __name__ == "__main__":
    raise SystemExit(main())
