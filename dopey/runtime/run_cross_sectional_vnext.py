"""Daily idempotent CLI for the governed cross-sectional vNext operation."""

from __future__ import annotations

import json
import os
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dopey.chronos.leases import operation_lease
from dopey.technical.history_adapter import load_default_validated_symbol_history
from dopey_data.history_store import HISTORY_MANIFEST_PATH, load_history_manifest

from .cross_sectional_vnext import run_cross_sectional_vnext


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "dopey" / "vnext" / "cross_sectional_operational"
OPERATION_STATE_PATH = OUTPUT_ROOT / "operation_state.json"
NEW_YORK = ZoneInfo("America/New_York")


def _write_state(value: dict[str, Any]) -> None:
    OPERATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OPERATION_STATE_PATH.with_name(f"{OPERATION_STATE_PATH.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, OPERATION_STATE_PATH)


def _load_state() -> dict[str, Any]:
    if not OPERATION_STATE_PATH.exists():
        return {}
    value = json.loads(OPERATION_STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"vNext operation state must be an object: path={OPERATION_STATE_PATH}")
    return value


def _latest_market_time() -> str:
    history, _ = load_default_validated_symbol_history("SPY")
    if not history:
        raise ValueError("cannot derive vNext market time without SPY history")
    market_date = datetime.fromisoformat(str(history[-1]["date"])).date()
    close_et = datetime.combine(market_date, time(16, 0), tzinfo=NEW_YORK)
    return close_et.astimezone(timezone.utc).isoformat()


def _run_operation() -> None:
    manifest = load_history_manifest(HISTORY_MANIFEST_PATH)
    symbols = tuple(manifest.required_universe)
    market_time = _latest_market_time()
    state = _load_state()
    if state.get("market_time") == market_time and state.get("operation_status") == "complete":
        summary_path = OUTPUT_ROOT / "latest_batch_summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(
                "completed vNext operation state lacks its batch summary: "
                f"state_path={OPERATION_STATE_PATH}, summary_path={summary_path}"
            )
        print(summary_path.read_text(encoding="utf-8"))
        return
    event_time = (
        str(state["event_time"])
        if state.get("market_time") == market_time and state.get("operation_status") == "in_progress_resumable"
        else datetime.now(timezone.utc).isoformat()
    )
    _write_state(
        {
            "artifact_type": "cross_sectional_vnext_operation_state",
            "operation_state_version": "dopey-cross-sectional-vnext-operation-state-v1",
            "operation_status": "in_progress_resumable",
            "event_time": event_time,
            "market_time": market_time,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    summary = run_cross_sectional_vnext(
        symbols,
        "breakout",
        event_time,
        market_time,
        OUTPUT_ROOT,
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "artifacts" / "dopey" / "equity_swing" / "cross_asset_regime.json",
        REPOSITORY_ROOT / "artifacts" / "dopey" / "equity_swing" / "news_intelligence.json",
        REPOSITORY_ROOT / "dopey_data" / "real" / "manifests" / "macro_context_manifest.json",
        REPOSITORY_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json",
        REPOSITORY_ROOT / "dopey_data" / "real" / "raw" / "earnings_calendar",
    )
    _write_state(
        {
            "artifact_type": "cross_sectional_vnext_operation_state",
            "operation_state_version": "dopey-cross-sectional-vnext-operation-state-v1",
            "operation_status": "complete",
            "event_time": event_time,
            "market_time": market_time,
            "batch_fingerprint": summary["batch_fingerprint"],
            "paper_only": True,
            "live_blocked": True,
        }
    )
    print(json.dumps(summary, sort_keys=True, indent=2))


def main() -> None:
    with operation_lease(
        OUTPUT_ROOT / "cross_sectional_vnext.lease",
        14_400,
        OUTPUT_ROOT / "quarantine" / "leases",
    ):
        _run_operation()


if __name__ == "__main__":
    main()
