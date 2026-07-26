"""CLI runner for V6 validation."""
from __future__ import annotations

import json

from dopey_validation.public_signal_research_v6_validation import run_public_signal_research_v6_validation


def main() -> int:
    summary = run_public_signal_research_v6_validation()
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary.get("validation_status", "").startswith("validation_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
