"""CLI for conservative autonomous promotion-evidence synthesis."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .evidence_synthesis import synthesize_promotion_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize only promotion evidence that existing ledgers support")
    parser.add_argument("--autoresearch-cycle", type=Path, required=True)
    parser.add_argument("--forward-predictions", type=Path, required=True)
    parser.add_argument("--public-history-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = synthesize_promotion_evidence(
        arguments.autoresearch_cycle,
        arguments.forward_predictions,
        arguments.public_history_root,
        arguments.output,
        datetime.now(timezone.utc),
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
