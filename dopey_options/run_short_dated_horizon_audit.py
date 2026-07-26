"""Write the fail-closed audit for 1DTE through weekly option research."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from dopey_equity_swing.contract_selector import load_option_chain_snapshot
from dopey_equity_swing.snapshot_resolution import resolve_option_snapshot

from .short_dated_horizon_policy import build_short_dated_horizon_audit


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CHAIN_ROOT = REPOSITORY_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "dopey_data"
    / "real"
    / "manifests"
    / "options_data_manifest.json"
)
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "dopey"
    / "options"
    / "short_dated_horizon_audit.json"
)


def run_short_dated_horizon_audit(
    market_as_of_date: date,
    output_path: Path,
) -> dict[str, Any]:
    decision_time = datetime.now(timezone.utc)
    snapshot = resolve_option_snapshot(
        REPOSITORY_ROOT,
        CHAIN_ROOT,
        MANIFEST_PATH,
        market_as_of_date,
        decision_time,
    )
    if snapshot["path"] is None:
        raise ValueError(
            "short-dated audit requires an exact hash-pinned option snapshot: "
            f"status={snapshot['status']}, blocker={snapshot['blocker']}"
        )
    chains = load_option_chain_snapshot(snapshot["path"], market_as_of_date)
    rows = tuple(row for symbol_rows in chains.values() for row in symbol_rows)
    input_evidence = {
        "option_snapshot_status": snapshot["status"],
        "option_manifest_sha256": snapshot["manifest_sha256"],
        "combined_chain_sha256": snapshot["combined_chain_sha256"],
        "chain_file_count": snapshot["chain_file_count"],
        "chain_row_count": snapshot["chain_row_count"],
        "manifest_chain_file_count": snapshot["manifest_chain_file_count"],
        "manifest_chain_row_count": snapshot["manifest_chain_row_count"],
    }
    audit = build_short_dated_horizon_audit(
        market_as_of_date.isoformat(),
        rows,
        input_evidence,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit


def _parse_args(arguments: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit governed 1DTE through weekly option evidence."
    )
    parser.add_argument("--as-of", required=True, help="Market date in YYYY-MM-DD form.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="JSON artifact path.",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    market_as_of_date = date.fromisoformat(str(args.as_of))
    result = run_short_dated_horizon_audit(market_as_of_date, Path(args.output))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
