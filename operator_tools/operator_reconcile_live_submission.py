"""Resolve one Live Branch submission only after manual broker-history verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dopey_live.ledger import reconcile_submission_after_operator_verification


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent-id", required=True)
    placement = parser.add_mutually_exclusive_group(required=True)
    placement.add_argument("--placed", action="store_true")
    placement.add_argument("--not-placed", action="store_true")
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--filled-quantity", required=True, type=float)
    parser.add_argument("--average-fill-price", required=True, type=float)
    parser.add_argument("--broker-evidence-reference", required=True)
    parser.add_argument("--operator-confirmation", required=True)
    arguments = parser.parse_args()
    record = reconcile_submission_after_operator_verification(
        REPOSITORY_ROOT,
        str(arguments.intent_id),
        bool(arguments.placed),
        str(arguments.order_id),
        str(arguments.status),
        float(arguments.filled_quantity),
        float(arguments.average_fill_price),
        str(arguments.broker_evidence_reference),
        str(arguments.operator_confirmation),
    )
    print(
        json.dumps(
            {
                "reconciliation_status": "appended",
                "intent_id": arguments.intent_id,
                "record_hash": record["record_hash"],
                "placed": arguments.placed,
                "broker_connection_used": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
