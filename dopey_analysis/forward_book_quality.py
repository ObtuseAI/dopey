"""Audit every open forward-paper position against the current entry policy."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from dopey_options.liquidity_engine import (
    ENTRY_POLICY_VERSION,
    forward_entry_liquidity_rejection_reasons,
    quote_relative_spread,
)
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_risk_engine.capacity_annotation import book_capacity, position_capacity
from dopey_risk_engine.forward_portfolio_policy import evaluate_forward_portfolio


REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
CHAIN_ROOT = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_book_quality.json"


def run_forward_book_quality_audit() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        summary = {
            "artifact_type": "forward_book_entry_quality",
            "book_quality_status": "blocked_missing_forward_ledger",
            "entry_policy_version": ENTRY_POLICY_VERSION,
            "open_position_count": 0,
            "conforming_open_position_count": 0,
            "nonconforming_open_position_count": 0,
            "unavailable_entry_evidence_count": 1,
            "open_book_entry_quality_green": False,
            "open_book_concentration_green": False,
            "portfolio_concentration": {},
            "positions": [],
            "policy": "audit_only_never_closes_or_rewrites_positions",
            "paper_only": True,
            "live_blocked": True,
        }
        summary["reproducibility_hash"] = reproducibility_hash(summary)
        write_json_atomic(SUMMARY_PATH, summary)
        return summary
    ledger = _load_json(LEDGER_PATH)
    positions = [audit_open_position(position) for position in ledger.get("open_positions", [])]
    nonconforming = sum(record["entry_quality_status"] == "nonconforming" for record in positions)
    unavailable = sum(record["entry_quality_status"] == "unavailable" for record in positions)
    portfolio_concentration = evaluate_forward_portfolio(list(ledger.get("open_positions", [])))
    capacity = book_capacity(
        [record["capacity_annotation"] for record in positions if "capacity_annotation" in record]
    )
    summary: dict[str, Any] = {
        "artifact_type": "forward_book_entry_quality",
        "book_quality_status": "forward_book_quality_computed",
        "entry_policy_version": ENTRY_POLICY_VERSION,
        "open_position_count": len(positions),
        "conforming_open_position_count": len(positions) - nonconforming - unavailable,
        "nonconforming_open_position_count": nonconforming,
        "unavailable_entry_evidence_count": unavailable,
        "open_book_entry_quality_green": nonconforming == 0 and unavailable == 0,
        "open_book_concentration_green": portfolio_concentration["portfolio_concentration_green"],
        "portfolio_concentration": portfolio_concentration,
        "book_capacity": capacity,
        "positions": positions,
        "policy": "audit_only_never_closes_or_rewrites_positions",
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(SUMMARY_PATH, summary)
    return summary


def audit_open_position(position: dict[str, Any]) -> dict[str, Any]:
    quote = _entry_quote(position)
    base = {
        "position_id": str(position.get("position_id", "")),
        "symbol": str(position.get("symbol", "")),
        "candidate_strategy": str(position.get("candidate_strategy", "")),
        "entry_date": str(position.get("entry_date", "")),
    }
    if quote is None:
        return {
            **base,
            "entry_quality_status": "unavailable",
            "entry_quality_reason_codes": ["entry_contract_quote_snapshot_unavailable"],
        }
    bid = float(quote["bid"])
    ask = float(quote["ask"])
    volume = int(quote["volume"])
    open_interest = int(quote["open_interest"])
    reasons = forward_entry_liquidity_rejection_reasons(bid, ask, volume, open_interest)
    entry_fill = float(position.get("entry_fill", ask))
    return {
        **base,
        "entry_quality_status": "nonconforming" if reasons else "conforming",
        "entry_quality_reason_codes": list(reasons),
        "entry_bid": bid,
        "entry_ask": ask,
        "entry_relative_spread": round(quote_relative_spread(bid, ask), 6),
        "entry_volume": volume,
        "entry_open_interest": open_interest,
        "entry_evidence_source": str(quote["entry_evidence_source"]),
        "capacity_annotation": position_capacity(entry_fill, volume, open_interest),
    }


def _entry_quote(position: dict[str, Any]) -> dict[str, Any] | None:
    frozen_fields = ("entry_bid", "entry_ask", "entry_volume", "entry_open_interest")
    if all(field in position for field in frozen_fields):
        # Normalize to the audit's schema (bid/ask/volume/open_interest); the
        # position freezes these under entry_* names, but audit_open_position
        # and the chain-reconstruction branch both read the un-prefixed keys.
        return {
            "bid": position["entry_bid"],
            "ask": position["entry_ask"],
            "volume": position["entry_volume"],
            "open_interest": position["entry_open_interest"],
            "entry_evidence_source": "position_frozen_provenance",
        }
    entry_date = str(position.get("entry_date", ""))
    symbol = str(position.get("symbol", ""))
    if not entry_date or not symbol:
        return None
    path = CHAIN_ROOT / entry_date / f"{symbol}_chain.csv"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        matches = [
            row
            for row in csv.DictReader(handle)
            if str(row.get("expiry", "")) == str(position.get("expiry", ""))
            and str(row.get("option_type", "")) == str(position.get("option_type", ""))
            and float(row.get("strike", "nan")) == float(position.get("strike", 0.0))
        ]
    if len(matches) > 1:
        raise ValueError(f"duplicate entry contract quote: path={path}, position_id={position.get('position_id')}")
    if not matches:
        return None
    return {**matches[0], "entry_evidence_source": "immutable_chain_archive_reconstruction"}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"forward book ledger is missing: path={path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"forward book ledger must be a JSON object: path={path}")
    return parsed


if __name__ == "__main__":
    result = run_forward_book_quality_audit()
    print(json.dumps({key: value for key, value in result.items() if key != "positions"}, indent=2, sort_keys=True))
