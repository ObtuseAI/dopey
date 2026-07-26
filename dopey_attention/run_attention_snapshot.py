"""Build the canonical governed attention snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from dopey_data.history_store import load_history_manifest

from .engine import (
    AttentionPaths,
    build_attention_snapshot,
    default_attention_policy,
    write_attention_snapshot,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_OUTPUT = (
    REPOSITORY_ROOT / "artifacts" / "dopey" / "attention" / "attention_snapshot.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a research-only, as-of-safe DOPEY attention snapshot."
    )
    parser.add_argument("--market-as-of-date", required=True)
    parser.add_argument("--decision-time-utc", required=True)
    parser.add_argument("--symbols", nargs="*")
    parser.add_argument("--output", type=Path, default=CANONICAL_OUTPUT)
    arguments = parser.parse_args()

    market_as_of_date = date.fromisoformat(arguments.market_as_of_date)
    decision_time = datetime.fromisoformat(
        arguments.decision_time_utc.replace("Z", "+00:00")
    )
    history_manifest_path = (
        REPOSITORY_ROOT / "dopey_data" / "history" / "history_dataset_manifest.json"
    )
    symbols = arguments.symbols
    if not symbols:
        manifest = load_history_manifest(history_manifest_path)
        symbols = sorted(
            {
                symbol
                for file_reference in manifest.data_files
                for symbol in file_reference.symbols
            }
        )
    paths: AttentionPaths = {
        "repository_root": REPOSITORY_ROOT,
        "history_manifest_path": history_manifest_path,
        "news_data_path": REPOSITORY_ROOT
        / "dopey_data"
        / "real"
        / "raw"
        / "news"
        / "news_events.jsonl",
        "news_manifest_path": REPOSITORY_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "news_context_manifest.json",
        "options_chain_root": REPOSITORY_ROOT
        / "dopey_data"
        / "real"
        / "raw"
        / "options_chains",
        "options_manifest_path": REPOSITORY_ROOT
        / "dopey_data"
        / "real"
        / "manifests"
        / "options_data_manifest.json",
    }
    snapshot = build_attention_snapshot(
        paths,
        list(symbols),
        market_as_of_date,
        decision_time,
        default_attention_policy(),
    )
    write_attention_snapshot(snapshot, arguments.output)
    print(
        json.dumps(
            {
                "artifact": str(arguments.output),
                "status": snapshot["status"],
                "symbol_count": snapshot["symbol_count"],
                "ranking_eligible_symbol_count": snapshot[
                    "ranking_eligible_symbol_count"
                ],
                "abstained_symbol_count": snapshot["abstained_symbol_count"],
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "live_execution_allowed": snapshot["live_execution_allowed"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
