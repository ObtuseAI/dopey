r"""OPERATOR TOOL - recover the exact July 2026 backtest trade-record incident.

The original ledger is immutable evidence. This tool validates its incident
size, SHA-256, and corrupt byte sequence; writes one separate recovered mirror;
validates every recovered JSONL record and stored record hash; then publishes a
manifest only after the mirror is complete. It never rewrites the source.

Usage:
    .venv\Scripts\python operator_tools\operator_recover_backtest_trade_records.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dopey_backtest.trade_records_recovery import (  # noqa: E402
    BACKTEST_TRADE_RECORDS_INCIDENT,
    recover_exact_byte_incident,
)


SOURCE_PATH: Final[Path] = (
    REPO_ROOT / "artifacts" / "dopey" / "backtest" / "backtest_trade_records.jsonl"
)
RECOVERED_PATH: Final[Path] = SOURCE_PATH.with_name(
    "backtest_trade_records.recovered.jsonl"
)
MANIFEST_PATH: Final[Path] = SOURCE_PATH.with_name(
    "backtest_trade_records.recovery_manifest.json"
)


def main() -> int:
    manifest = recover_exact_byte_incident(
        SOURCE_PATH,
        RECOVERED_PATH,
        MANIFEST_PATH,
        BACKTEST_TRADE_RECORDS_INCIDENT,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
