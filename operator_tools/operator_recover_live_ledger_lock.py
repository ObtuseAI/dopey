"""Recover one stale Live Branch ledger lock after explicit operator verification."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_live.ledger import (
    recover_stale_ledger_lock_after_operator_verification,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        choices=("live", "paper-twin"),
        required=True,
    )
    parser.add_argument("--operator-confirmation", required=True)
    arguments = parser.parse_args()
    record = recover_stale_ledger_lock_after_operator_verification(
        REPOSITORY_ROOT,
        str(arguments.ledger),
        str(arguments.operator_confirmation),
        datetime.now(timezone.utc),
    )
    print(
        json.dumps(
            {
                "recovery_status": (
                    "ledger_lock_recovered_after_operator_verification"
                ),
                "ledger": arguments.ledger,
                "record_hash": record["record_hash"],
                "broker_connection_used": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
