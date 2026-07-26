"""CLI for threshold-gated DOPEY operational self-improvement."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .autonomous_improvement import run_autonomous_improvement_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Improve every safe paper-research lane within sealed bounds")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    result = run_autonomous_improvement_cycle(
        arguments.repo_root,
        arguments.output_root,
        datetime.now(timezone.utc),
    )
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
