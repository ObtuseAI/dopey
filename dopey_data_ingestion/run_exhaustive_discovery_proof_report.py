"""CLI for exhaustive discovery proof report generation."""
from __future__ import annotations

import json

from .exhaustive_discovery_proof_report import run_exhaustive_discovery_proof_report


def main() -> int:
    report = run_exhaustive_discovery_proof_report()
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
