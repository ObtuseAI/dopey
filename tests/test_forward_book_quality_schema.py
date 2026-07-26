"""Regression: forward-book audit must handle frozen-provenance positions.

An open position may carry frozen entry provenance (entry_bid/entry_ask/
entry_volume/entry_open_interest) instead of requiring a chain re-read. The
audit consumer reads un-prefixed keys (bid/ask/volume/open_interest); the two
quote branches must agree on that schema. A mismatch raised KeyError('bid') in
the live action_readiness_gate once valid data produced real open positions.
"""
from __future__ import annotations

from dopey_analysis.forward_book_quality import _entry_quote, audit_open_position


def _frozen_position(**overrides) -> dict:
    base = {
        "position_id": "p-frozen",
        "symbol": "AAPL",
        "candidate_strategy": "demo",
        "entry_date": "2026-07-10",
        "expiry": "2026-08-07",
        "option_type": "call",
        "strike": 195.0,
        "entry_bid": 1.20,
        "entry_ask": 1.30,
        "entry_volume": 50,
        "entry_open_interest": 200,
    }
    base.update(overrides)
    return base


def test_frozen_quote_exposes_audit_schema_keys():
    quote = _entry_quote(_frozen_position())
    assert quote is not None
    # the audit reads these exact keys — the frozen branch must provide them
    for key in ("bid", "ask", "volume", "open_interest"):
        assert key in quote, f"frozen quote missing audit key: {key}"
    assert quote["entry_evidence_source"] == "position_frozen_provenance"


def test_audit_open_position_frozen_provenance_no_keyerror():
    record = audit_open_position(_frozen_position())
    assert record["entry_quality_status"] in ("conforming", "nonconforming")
    assert record["entry_bid"] == 1.20
    assert record["entry_ask"] == 1.30
    assert record["entry_evidence_source"] == "position_frozen_provenance"


def test_audit_unavailable_when_no_quote():
    # No frozen fields and no reconstructable chain -> unavailable, not a crash.
    record = audit_open_position(
        {"position_id": "p2", "symbol": "", "entry_date": ""}
    )
    assert record["entry_quality_status"] == "unavailable"
