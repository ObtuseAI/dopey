"""Tests for exact-DTE option research separation and fail-closed gates."""
from __future__ import annotations

from typing import Any

import pytest

from dopey_options.short_dated_horizon_policy import (
    REQUIRED_MICROSTRUCTURE_FIELDS,
    build_short_dated_horizon_audit,
)


SNAPSHOT_DATE = "2026-07-21"


def _row(dte: int, include_microstructure: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "snapshot_date": SNAPSHOT_DATE,
        "symbol": "SPY",
        "expiry": f"2026-07-{21 + dte:02d}",
        "dte_calendar": dte,
        "option_type": "call",
        "strike": 650.0,
        "bid": 1.0,
        "ask": 1.1,
        "mid": 1.05,
        "last": 1.02,
        "volume": 100,
        "open_interest": 500,
        "implied_vol": 0.2,
        "underlying_spot": 650.0,
        "source": "test_chain",
    }
    if include_microstructure:
        row.update(
            {
                "quote_timestamp_utc": "2026-07-21T20:00:00+00:00",
                "underlying_quote_timestamp_utc": "2026-07-21T20:00:00+00:00",
                "contract_symbol": f"SPY_TEST_{dte}",
                "bid_size": 50,
                "ask_size": 40,
                "expiry_timestamp_utc": f"2026-07-{21 + dte:02d}T20:00:00+00:00",
                "exercise_style": "american",
                "settlement_type": "physical",
                "multiplier": 100,
                "adjustment_status": "standard",
            }
        )
    return row


def test_exact_horizons_do_not_borrow_from_other_dte_lanes() -> None:
    rows = [_row(dte, False) for dte in (1, 2, 3, 4, 7, 10)]
    audit = build_short_dated_horizon_audit(SNAPSHOT_DATE, rows, {"fixture": True})

    lanes = {lane["lane_id"]: lane for lane in audit["horizon_lanes"]}
    assert lanes["one_dte"]["contract_row_count"] == 1
    assert lanes["two_dte"]["contract_row_count"] == 1
    assert lanes["three_dte"]["contract_row_count"] == 1
    assert lanes["four_dte"]["contract_row_count"] == 1
    assert lanes["weekly_five_to_nine_dte"]["contract_row_count"] == 1
    assert audit["short_dated_contract_row_count"] == 5
    assert audit["observable_lane_count"] == 5
    assert audit["capture_status"] == "blocked_incomplete_short_dated_capture_contract"
    assert set(audit["missing_required_microstructure_fields"]) == set(
        REQUIRED_MICROSTRUCTURE_FIELDS
    )
    assert audit["promotion_allowed"] is False
    assert audit["option_execution_enabled"] is False


def test_complete_capture_contract_still_cannot_self_promote() -> None:
    rows = [_row(dte, True) for dte in (1, 2, 3, 4, 7)]
    audit = build_short_dated_horizon_audit(SNAPSHOT_DATE, rows, {"fixture": True})

    assert audit["capture_status"] == "eligible_for_prospective_paper_capture_only"
    assert audit["missing_required_microstructure_fields"] == []
    assert all(
        lane["research_status"] == "eligible_for_prospective_paper_capture_only"
        for lane in audit["horizon_lanes"]
    )
    assert audit["promotion_allowed"] is False
    assert all(lane["promotion_allowed"] is False for lane in audit["horizon_lanes"])


def test_missing_exact_horizon_rows_are_explicitly_blocked() -> None:
    audit = build_short_dated_horizon_audit(
        SNAPSHOT_DATE,
        [_row(10, False)],
        {"fixture": True},
    )

    assert audit["capture_status"] == "blocked_no_short_dated_contract_rows"
    assert audit["observable_lane_count"] == 0
    assert all(
        lane["research_status"] == "blocked_missing_exact_horizon_contracts"
        for lane in audit["horizon_lanes"]
    )


def test_malformed_identity_and_negative_dte_fail_closed() -> None:
    mismatched = _row(1, False)
    mismatched["snapshot_date"] = "2026-07-20"
    with pytest.raises(ValueError, match="snapshot mismatch"):
        build_short_dated_horizon_audit(SNAPSHOT_DATE, [mismatched], {})

    negative = _row(1, False)
    negative["dte_calendar"] = -1
    with pytest.raises(ValueError, match="cannot be negative"):
        build_short_dated_horizon_audit(SNAPSHOT_DATE, [negative], {})
