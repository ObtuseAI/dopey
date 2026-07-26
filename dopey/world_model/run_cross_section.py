"""CLI for building validated local cross-sectional market context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dopey.technical.history_adapter import load_validated_symbol_history
from dopey_data.history_store import HISTORY_MANIFEST_PATH, load_history_manifest

from .cross_section import build_cross_sectional_context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build DOPEY vNext governed cross-sectional context")
    parser.add_argument("--market-time", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    manifest = load_history_manifest(HISTORY_MANIFEST_PATH)
    histories = {}
    proofs = {}
    for symbol in manifest.required_universe:
        histories[symbol], proofs[symbol] = load_validated_symbol_history(symbol, HISTORY_MANIFEST_PATH)
    result = build_cross_sectional_context(histories, proofs, arguments.market_time, 20, 50, 60)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
