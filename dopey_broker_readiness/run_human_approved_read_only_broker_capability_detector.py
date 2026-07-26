"""CLI entrypoint for the human-approved read-only detector."""
from __future__ import annotations

import json

from .read_only_capability_detector import run_human_approved_read_only_broker_capability_detector


def main() -> None:
    result = run_human_approved_read_only_broker_capability_detector()
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
