"""Owner-initiated liquidations and legacy paper-twin terminal classification.

The owner may sell any position directly in the brokerage app. A locally
attributed position that disappeared broker-side must settle - via an
append-only ledger event carrying the broker sell-fill evidence - instead of
hard-blocking every future cycle; an UNEXPLAINED disappearance must still
block. Separately: an order placed before execution-snapshot capture existed
can never bear an independent twin result; it is terminally classified and
reported separately by the release gate, while post-capability orders keep
the strict missing-result accounting.
"""
from __future__ import annotations

from pathlib import Path

from dopey_live.ledger import append_record, ledger_path, paper_twin_path, read_ledger
from dopey_live.models import AccountSnapshot, LiveExecutionIntent
from dopey_live.service import (
    _complete_legacy_twin_observations,
    _open_live_positions,
    _position_ownership_blocker,
    _settle_owner_liquidations,
)
from dopey_validation.live_pivot_release_gate import _live_ledger_evidence


def _intent(symbol: str = "GOOGL", intent_id: str = "entry-1") -> LiveExecutionIntent:
    return LiveExecutionIntent(
        intent_id=intent_id,
        instrument="equity",
        symbol=symbol,
        side="buy",
        order_type="market",
        limit_price=0.0,
        time_in_force="day",
        extended_hours=False,
        notional_usd=200.0,
        quantity=0.0,
        source_as_of_date="2026-07-19",
        source_hash="a" * 64,
        thesis_direction="bullish",
        analysis_symbol=symbol,
        analysis_relationship="self",
        analysis_reference_price=100.0,
        analysis_invalidation_price=90.0,
        analysis_target_price=110.0,
        daily_leverage_multiple=1.0,
        daily_reset=False,
        maximum_holding_sessions=10,
        reference_price=100.0,
        invalidation_price=90.0,
        target_price=110.0,
        expected_hold_trading_days=10,
        execution_snapshot=None,
        option_contract={},
        reason_codes=("fixture",),
    )


def _seed_filled_buy(
    repository_root: Path,
    order_id: str = "order-1",
    quantity: float = 1.1,
    twin_hash: str = "",
) -> None:
    append_record(
        ledger_path(repository_root),
        "live_order_result",
        {
            "order_id": order_id,
            "intent_id": "entry-1",
            "instrument": "equity",
            "symbol": "GOOGL",
            "side": "buy",
            "placed": True,
            "status": "filled",
            "filled_quantity": quantity,
            "average_fill_price": 180.0,
            "market_date": "2026-07-20",
            "paper_twin_record_hash": twin_hash,
            "intent": _intent().to_dict(),
        },
    )


def _account(
    positions: tuple[dict, ...] = (),
    equity_orders: tuple[dict, ...] = (),
) -> AccountSnapshot:
    return AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=500.0,
        total_equity_usd=500.0,
        equity_positions=positions,
        option_positions=(),
        recent_equity_orders=equity_orders,
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )


def _owner_sell(order_id: str = "owner-sell-1", quantity: float = 1.1) -> dict:
    return {
        "order_id": order_id,
        "symbol": "GOOGL",
        "side": "sell",
        "status": "filled",
        "market_date": "2026-07-22",
        "submitted_at": "2026-07-22T15:00:00+00:00",
        "filled_at": "2026-07-22T15:00:01+00:00",
        "filled_quantity": quantity,
        "average_fill_price": 185.0,
    }


def test_owner_sell_evidence_settles_missing_position(tmp_path: Path) -> None:
    _seed_filled_buy(tmp_path)
    account = _account(positions=(), equity_orders=(_owner_sell(),))

    assert _position_ownership_blocker(tmp_path, account) == (
        "broker_position_missing_locally_attributed_quantity"
    )
    settled = _settle_owner_liquidations(tmp_path, account)
    assert len(settled) == 1
    payload = settled[0]["payload"]
    assert payload["evidence_broker_order_ids"] == ["owner-sell-1"]
    assert payload["liquidated_quantity"] == 1.1
    assert _open_live_positions(tmp_path) == {}
    assert _position_ownership_blocker(tmp_path, account) == ""


def test_settlement_is_idempotent_across_cycles(tmp_path: Path) -> None:
    _seed_filled_buy(tmp_path)
    account = _account(equity_orders=(_owner_sell(),))
    assert len(_settle_owner_liquidations(tmp_path, account)) == 1
    assert _settle_owner_liquidations(tmp_path, account) == ()
    liquidation_records = [
        record
        for record in read_ledger(ledger_path(tmp_path))
        if record.get("event_type") == "live_position_owner_liquidation_observed"
    ]
    assert len(liquidation_records) == 1


def test_unexplained_disappearance_still_blocks(tmp_path: Path) -> None:
    _seed_filled_buy(tmp_path)
    account = _account()  # no position, no owner sell evidence
    assert _settle_owner_liquidations(tmp_path, account) == ()
    assert _position_ownership_blocker(tmp_path, account) == (
        "broker_position_missing_locally_attributed_quantity"
    )


def test_insufficient_owner_sell_quantity_still_blocks(tmp_path: Path) -> None:
    _seed_filled_buy(tmp_path, quantity=2.0)
    account = _account(equity_orders=(_owner_sell(quantity=0.5),))
    assert _settle_owner_liquidations(tmp_path, account) == ()
    assert _position_ownership_blocker(tmp_path, account) != ""


def test_partial_owner_sell_settles_missing_portion_only(tmp_path: Path) -> None:
    _seed_filled_buy(tmp_path, quantity=3.0)
    account = _account(
        positions=({"symbol": "GOOGL", "instrument": "equity", "quantity": 2.0},),
        equity_orders=(_owner_sell(quantity=1.0),),
    )
    settled = _settle_owner_liquidations(tmp_path, account)
    assert len(settled) == 1
    assert settled[0]["payload"]["liquidated_quantity"] == 1.0
    remaining = _open_live_positions(tmp_path)
    assert len(remaining) == 1
    assert next(iter(remaining.values()))[2] == 2.0
    assert _position_ownership_blocker(tmp_path, account) == ""


def test_system_sell_orders_are_not_owner_evidence(tmp_path: Path) -> None:
    _seed_filled_buy(tmp_path)
    # A sell whose order_id IS in our ledger is a system order, not owner action.
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "order_id": "owner-sell-1",
            "intent_id": "exit-1",
            "instrument": "equity",
            "symbol": "GOOGL",
            "side": "sell",
            "placed": False,
            "status": "rejected",
            "filled_quantity": 0.0,
            "average_fill_price": 0.0,
            "market_date": "2026-07-21",
            "paper_twin_record_hash": "",
            "intent": _intent(intent_id="exit-1").to_dict(),
        },
    )
    account = _account(equity_orders=(_owner_sell(),))
    assert _settle_owner_liquidations(tmp_path, account) == ()


# ---------- legacy twin terminal classification ----------


def _seed_staged_twin(repository_root: Path) -> str:
    staged = append_record(
        paper_twin_path(repository_root),
        "paper_twin_staged",
        {"intent_id": "entry-1", "symbol": "GOOGL", "paper_only": True},
    )
    return str(staged["record_hash"])


def test_legacy_twin_without_snapshot_is_terminally_classified(tmp_path: Path) -> None:
    twin_hash = _seed_staged_twin(tmp_path)
    _seed_filled_buy(tmp_path, twin_hash=twin_hash)

    appended = _complete_legacy_twin_observations(tmp_path)
    assert len(appended) == 1
    payload = appended[0]["payload"]
    assert payload["terminally_unobservable"] is True
    assert payload["result_bearing"] is False
    assert (
        payload["paper_twin_execution_status"]
        == "unobservable_legacy_order_predates_quote_snapshot"
    )
    # idempotent: second pass appends nothing
    assert _complete_legacy_twin_observations(tmp_path) == ()


def test_gate_reports_legacy_twin_separately_not_missing(tmp_path: Path) -> None:
    twin_hash = _seed_staged_twin(tmp_path)
    _seed_filled_buy(tmp_path, twin_hash=twin_hash)
    live_record = read_ledger(ledger_path(tmp_path))[-1]
    append_record(
        paper_twin_path(tmp_path),
        "paper_twin_linked",
        {"intent_id": "entry-1", "live_record_hash": str(live_record["record_hash"])},
    )
    append_record(
        ledger_path(tmp_path),
        "live_order_status_observed",
        {
            "order_id": "order-1",
            "status": "filled",
            "filled_at": "2026-07-20T15:00:00+00:00",
            "filled_quantity": 1.1,
            "average_fill_price": 180.0,
        },
    )

    before = _live_ledger_evidence(tmp_path)
    assert before["paper_twin_result_evidence_green"] is False
    assert before["missing_twin_result_order_ids"] == ["order-1"]

    _complete_legacy_twin_observations(tmp_path)
    after = _live_ledger_evidence(tmp_path)
    assert after["missing_twin_result_order_ids"] == []
    assert after["twin_result_unobservable_legacy_order_ids"] == ["order-1"]
    assert after["paper_twin_result_evidence_green"] is True
    assert after["placed_orders_reconciled"] is True
