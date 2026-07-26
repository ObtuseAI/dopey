"""OPERATOR TOOL - pre-snap read the current book (diagnose live, then audible).

Loads the open forward-walk positions as candidates and diagnoses each against
the live spine, the situational scorecard, the cross-lane convergence, and the
current regime - the quarterback reading the actual look and calling the
audible. Measure-only: it recommends checks; it never places or sizes an order.

Usage:  .venv\\Scripts\\python operator_tools\\operator_pre_snap_read.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.pre_snap_read import build_pre_snap_reads  # noqa: E402
from dopey.strategy_engineering.swing_target_discovery import load_ohlcv_history  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402

ART = REPO / "artifacts" / "dopey"
HISTORY_ROOT = REPO / "dopey_data" / "history" / "raw"
READS_PATH = ART / "strategy_engineering" / "pre_snap_reads.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _candidates_from_open_book() -> list[dict]:
    ledger = _load(ART / "forward_walk" / "forward_walk_ledger.json")
    candidates = []
    for position in ledger.get("open_positions", []):
        strategy = str(position.get("candidate_strategy", ""))
        candidates.append({
            "symbol": str(position.get("symbol", "")),
            "family": str(position.get("signal_family", "")),
            "direction": "bullish" if strategy == "long_call" else "bearish" if strategy == "long_put" else "unclear",
        })
    return candidates


def _spine_lookup() -> dict[str, tuple[list[float], list[str]]]:
    bars_by_symbol = load_ohlcv_history(HISTORY_ROOT)
    lookup: dict[str, tuple[list[float], list[str]]] = {}
    for symbol, bars in bars_by_symbol.items():
        rows = sorted(bars, key=lambda b: str(b["date"]))
        lookup[symbol] = ([float(b["close"]) for b in rows], [str(b["date"]) for b in rows])
    return lookup


def main() -> int:
    candidates = _candidates_from_open_book()
    spine = _spine_lookup()
    frontier = max((dates[-1] for _c, dates in spine.values() if dates), default=date.today().isoformat())
    result = build_pre_snap_reads(
        candidates,
        spine,
        _load(ART / "strategy_engineering" / "situational_scorecard.json"),
        _load(ART / "strategy_engineering" / "cross_lane_convergence.json"),
        _load(ART / "macro_context" / "macro_context_summary.json"),
        frontier,
    )
    write_json_atomic(READS_PATH, result)
    print(
        json.dumps(
            {
                "as_of_date": result["as_of_date"],
                "candidates": len(candidates),
                "audible_counts": result["audible_counts"],
                "reads": [
                    {"symbol": r["symbol"], "family": r["family"], "context": r["look"]["entry_context"],
                     "read": r["read"], "audible": r["audible"]}
                    for r in result["reads"]
                ],
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
