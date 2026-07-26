"""CLI entrypoint for the offline read-only detector pre-run safety scanner."""
from __future__ import annotations

import json

from .pre_run_safety_scanner import validate_read_only_detector_pre_run_safety_scanner


def main() -> None:
    result = validate_read_only_detector_pre_run_safety_scanner()
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
