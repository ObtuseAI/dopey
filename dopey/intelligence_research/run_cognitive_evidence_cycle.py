"""CLI for protected cross-domain cognitive-method evaluation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .evidence_cycle import run_cognitive_evidence_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate cognitive methods without execution authority")
    parser.add_argument("--discovery-cycle", type=Path, required=True)
    parser.add_argument("--task-store-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--visible-variants", type=int, required=True)
    arguments = parser.parse_args()
    output = run_cognitive_evidence_cycle(
        arguments.discovery_cycle,
        arguments.task_store_root,
        arguments.output_root,
        arguments.visible_variants,
        datetime.now(timezone.utc),
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
