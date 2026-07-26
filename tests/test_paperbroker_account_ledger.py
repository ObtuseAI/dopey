from __future__ import annotations

import pytest

from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_options.zero_dte_decision_engine import evaluate_zero_dte_candidate
from dopey_options.zero_dte_risk_model import ZeroDTERiskInput
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds


def _approved_zero_dte_decision(intent_id: str) -> dict:
    record = {
        "candidate_id": intent_id,
        "underlying": "SPY_FIXTURE",
        "option_type": "call",
        "expiry": "2026-07-03",
        "trade_date": "2026-07-03",
        "strike": 500.0,
        "moneyness": 1.0,
        "bid": 1.98,
        "ask": 2.04,
        "mid": 2.01,
        "spread_pct": 0.029,
        "volume": 6200,
        "open_interest": 8500,
        "implied_volatility": 0.38,
        "iv_rank_fixture": 0.42,
        "delta": 0.48,
        "gamma": 0.032,
        "theta": -0.08,
        "vega": 0.08,
        "liquidity_score": 0.86,
        "slippage_score": 0.14,
        "event_risk_score": 0.18,
        "regime_score": 0.78,
        "trend_score": 0.86,
        "reversal_score": 0.25,
        "macro_risk_score": 0.2,
        "proof_score": 0.84,
        "signal_confidence": 0.82,
        "expected_hold_minutes": 90,
        "explicit_thesis": "fixture thesis",
        "explicit_exit_or_expiry_plan": "expiry-managed close only with reason",
        "paper_only": True,
        "live_blocked": True,
        "order_action": "buy_to_open",
        "structure_type": "long_call",
        "defined_risk": True,
        "later_expiry_alternative_available": False,
        "expiry_managed_only_requested": False,
        "special_close_requested": False,
        "special_close_reason": "",
    }
    return evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(record), load_default_zero_dte_risk_thresholds()).to_dict()


def _intent(intent_id: str, structure: str, side: str, action: str, date: str, option_type: str, live: bool = False, zero: bool = False, lifecycle: str = "normal_hold", reason: str = "", liquidity: bool = False, risk: bool = False) -> ExecutionIntent:
    expiry = date if zero else "2026-07-17"
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": f"SPY_{option_type}_{intent_id}", "option_type": option_type, "expiry": expiry, "strike": 500.0, "dte": 0 if zero else 14}],
        max_loss=1.0,
        order_action=action,
        trade_date=date,
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state=lifecycle,
        live_allowed=live,
        zero_dte=zero,
        reason_code=reason,
        liquidity_approved=liquidity,
        risk_cap_approved=risk,
        zero_dte_risk_decision=_approved_zero_dte_decision(intent_id) if zero and liquidity and risk else {},
    )


def test_paper_broker_writes_position_to_account_ledger():
    broker = PaperBroker()
    assert broker.place_order(_intent("open", "long_call", "buy", "buy_to_open", "2026-07-03", "call"))["ok"]
    assert broker.account_ledger.positions[0].position_id == "open"


def test_paper_broker_rejects_same_day_normal_close():
    broker = PaperBroker()
    broker.place_order(_intent("open", "long_call", "buy", "buy_to_open", "2026-07-03", "call"))
    close = _intent("close", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "open"
    assert broker.place_order(close)["reason_code"] == "same_day_round_trip_rejected"


def test_paper_broker_allows_next_day_sell_to_close():
    broker = PaperBroker()
    broker.place_order(_intent("open", "long_put", "buy", "buy_to_open", "2026-07-02", "put"))
    close = _intent("close", "long_put", "sell", "sell_to_close", "2026-07-03", "put")
    close.related_open_position_id = "open"
    assert broker.place_order(close)["ok"]


def test_paper_broker_rejects_close_without_open_position():
    close = _intent("missing", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "missing-open"
    assert PaperBroker().place_order(close)["reason_code"] == "close_without_open_position_rejected"


def test_paper_broker_rejects_live_order_with_account_ledger():
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(_intent("live", "long_call", "buy", "buy_to_open", "2026-07-03", "call", live=True))


def test_paper_broker_records_day_trade_policy_rejection():
    broker = PaperBroker()
    broker.place_order(_intent("open", "long_call", "buy", "buy_to_open", "2026-07-03", "call"))
    close = _intent("close", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "open"
    broker.place_order(close)
    assert broker.account_ledger.day_trade_events[-1].rejection_reason == "same_day_round_trip_rejected"


def test_paper_broker_records_zero_dte_lifecycle_state():
    broker = PaperBroker()
    result = broker.place_order(_intent("z-open", "long_call", "buy", "buy_to_open", "2026-07-03", "call", zero=True, lifecycle="zero_dte_special_lifecycle", liquidity=True, risk=True))
    assert result["ok"]
    assert broker.account_ledger.positions[0].lifecycle_state == "zero_dte_open"
