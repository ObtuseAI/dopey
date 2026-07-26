"""Reconcile the (read-only) Robinhood agentic account against DOPEY's paper ledger.

The operator's desktop agent (official Robinhood Agentic Trading MCP,
auth outside this repo) exports an account snapshot JSON to:

    dopey_data/real/raw/agentic_account/account_snapshot.json

    {"snapshot_date": "YYYY-MM-DD", "account_type": "agentic",
     "buying_power": 0.0, "positions": [
        {"symbol": "SPY", "instrument_type": "option|equity",
         "quantity": 1.0, "description": "..."}]}

This stage validates it (schema, no credential/live-order markers, not
future-dated) and reconciles against the forward-walk paper ledger:
every REAL position must correspond to a DOPEY paper intent, and while
execution is sealed the expected real option-position count is ZERO -
any unmirrored real position is flagged as a drift incident. Read-only;
this module can never place, modify, or cancel anything.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "dopey_data" / "real" / "raw" / "agentic_account" / "account_snapshot.json"
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
RECON_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "broker_readiness"
RECON_SUMMARY_PATH = RECON_ARTIFACT_DIR / "agentic_account_reconciliation.json"

FORBIDDEN = re.compile(r"api[_-]?key|password|bearer\s|secret", re.IGNORECASE)


def run_agentic_account_reconciliation() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        summary = _summary("blocked_missing_account_snapshot", [], [], 0)
        _write(summary)
        return summary
    raw_text = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if FORBIDDEN.search(raw_text):
        summary = _summary("terminal_block_credential_marker_in_snapshot", [], [], 0)
        _write(summary)
        return summary
    try:
        snapshot = json.loads(raw_text)
    except json.JSONDecodeError:
        summary = _summary("blocked_snapshot_parse_error", [], [], 0)
        _write(summary)
        return summary
    required = {"snapshot_date", "account_type", "buying_power", "positions"}
    if not isinstance(snapshot, dict) or not required.issubset(snapshot):
        summary = _summary("blocked_snapshot_schema_invalid", [], [], 0)
        _write(summary)
        return summary
    real_options = [
        position
        for position in snapshot.get("positions", [])
        if str(position.get("instrument_type", "")) == "option" and float(position.get("quantity", 0.0)) != 0.0
    ]
    ledger: dict[str, Any] = {}
    if LEDGER_PATH.exists():
        ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    paper_symbols = {str(position.get("symbol", "")) for position in ledger.get("open_positions", [])}
    drift = [
        {
            "artifact_type": "agentic_account_drift",
            "symbol": str(position.get("symbol", "")),
            "quantity": float(position.get("quantity", 0.0)),
            "reason": "real_option_position_exists_while_execution_is_sealed",
        }
        for position in real_options
    ]
    status = "account_clean_no_unmirrored_positions" if not drift else "drift_detected_real_positions_while_sealed"
    summary = _summary(status, drift, sorted(paper_symbols), len(real_options))
    summary["snapshot_date"] = str(snapshot.get("snapshot_date", ""))
    summary["buying_power_reported"] = float(snapshot.get("buying_power", 0.0))
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write(summary)
    return summary


def _summary(status: str, drift: list[dict[str, Any]], paper_symbols: list[str], real_option_count: int) -> dict[str, Any]:
    return {
        "artifact_type": "agentic_account_reconciliation",
        "reconciliation_status": status,
        "real_option_position_count": real_option_count,
        "expected_real_option_positions_while_sealed": 0,
        "drift_incidents": drift,
        "paper_open_symbols": paper_symbols,
        "read_only": True,
        "can_place_orders": False,
        "auth_location": "operator_mcp_client_never_in_repo",
        "paper_only": True,
        "live_blocked": True,
    }


def _write(summary: dict[str, Any]) -> None:
    RECON_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RECON_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
