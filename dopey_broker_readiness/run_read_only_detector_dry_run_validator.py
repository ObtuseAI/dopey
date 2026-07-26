"""CLI for the offline read-only detector dry-run fixture validator."""
from __future__ import annotations

import json

from .read_only_detector_dry_run_validator import validate_read_only_detector_dry_run


def main() -> int:
    summary = validate_read_only_detector_dry_run()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["dry_run_validator_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
