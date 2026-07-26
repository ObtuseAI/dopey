"""Append matured underlying outcomes with bounded, resumable validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dopey_equity_swing.context_settlement import settle_context_decisions


REPO_ROOT = Path(__file__).resolve().parent.parent
DECISION_LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "context_decision_ledger.jsonl"
OUTCOME_LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "context_outcome_ledger.jsonl"
CURSOR_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "context_settlement_cursor.json"
LATEST_OPERATION_PATH = REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "latest_context_settlement.json"
HISTORY_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "history" / "history_dataset_manifest.json"
HISTORY_VALIDATION_PATH = REPO_ROOT / "artifacts" / "dopey" / "history" / "history_dataset_validation.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=500)
    arguments = parser.parse_args()
    result = settle_context_decisions(
        DECISION_LEDGER_PATH,
        OUTCOME_LEDGER_PATH,
        HISTORY_MANIFEST_PATH,
        HISTORY_VALIDATION_PATH,
        CURSOR_PATH,
        LATEST_OPERATION_PATH,
        int(arguments.batch_size),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
