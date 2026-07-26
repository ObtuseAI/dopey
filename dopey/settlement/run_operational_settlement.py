"""Scheduled CLI for the dedicated paper-only vNext settlement operation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey.chronos.leases import operation_lease

from .operational import run_operational_settlement


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "dopey" / "vnext" / "cross_sectional_operational"


def main() -> None:
    observed = datetime.now(timezone.utc)
    with operation_lease(
        OUTPUT_ROOT / "vnext_forward_settlement.lease",
        1_800,
        OUTPUT_ROOT / "quarantine" / "leases",
    ):
        result = run_operational_settlement(
            OUTPUT_ROOT,
            observed.date().isoformat(),
            observed.isoformat(),
        )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
