"""CLI entry point for the offline read-only detector approval-intake validator."""
from __future__ import annotations

import json
import sys

from .approval_intake_validator import validate_read_only_detector_approval_intake


def main(argv: list[str] | None = None) -> int:
    result = validate_read_only_detector_approval_intake()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["approval_intake_validator_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
