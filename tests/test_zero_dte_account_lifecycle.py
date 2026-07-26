from __future__ import annotations

from dopey_execution.account_ledger import add_open_position, close_position, create_paper_account_ledger
from dopey_execution.day_trade_policy import default_day_trade_policy
from dopey_execution.execution_intent import ExecutionIntent
from dopey_options.zero_dte_decision_engine import evaluate_zero_dte_candidate
from dopey_options.zero_dte_risk_model import ZeroDTERiskInput
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds


def _policy():
    return default_day_trade_policy()


def _approved_risk_decision(candidate_id: str) -> dict:
    record = {
        "candidate_id": candidate_id,
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


def _intent(intent_id: str, side: str, action: str, liquidity: bool, risk: bool, lifecycle: str, reason: str = "", risk_decision: dict | None = None) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure="long_call",
        legs=[{"side": side, "symbol": f"SPY_0DTE_{intent_id}", "option_type": "call", "expiry": "2026-07-03", "strike": 500.0, "dte": 0}],
        max_loss=1.0,
        order_action=action,
        trade_date="2026-07-03",
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state=lifecycle,
        zero_dte=True,
        liquidity_approved=liquidity,
        risk_cap_approved=risk,
        reason_code=reason,
        zero_dte_risk_decision=risk_decision or _approved_risk_decision(intent_id),
    )


def test_zero_dte_open_requires_special_lifecycle():
    result = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z", "buy", "buy_to_open", True, True, "normal_hold"), _policy())
    assert "zero_dte_requires_special_lifecycle" in result.reason_codes


def test_zero_dte_missing_liquidity_rejected():
    result = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z-liq", "buy", "buy_to_open", False, True, "zero_dte_special_lifecycle"), _policy())
    assert any("liquidity" in reason for reason in result.reason_codes)


def test_zero_dte_missing_risk_cap_rejected():
    result = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z-risk", "buy", "buy_to_open", True, False, "zero_dte_special_lifecycle"), _policy())
    assert any("risk" in reason for reason in result.reason_codes)


def test_zero_dte_special_close_missing_reason_rejected():
    ledger = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z-open", "buy", "buy_to_open", True, True, "zero_dte_special_lifecycle"), _policy()).ledger
    close = _intent("z-close", "sell", "sell_to_close", True, True, "zero_dte_expiry_managed")
    close.related_open_position_id = "z-open"
    assert "zero_dte_special_close_requires_explicit_reason_code" in close_position(ledger, close, _policy()).reason_codes


def test_zero_dte_special_close_with_all_approvals_allowed():
    ledger = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z-open", "buy", "buy_to_open", True, True, "zero_dte_special_lifecycle"), _policy()).ledger
    close = _intent("z-close-ok", "sell", "sell_to_close", True, True, "zero_dte_expiry_managed", "expiry_window")
    close.related_open_position_id = "z-open"
    assert close_position(ledger, close, _policy()).accepted


def test_zero_dte_lifecycle_recorded_separately_from_normal_day_trade():
    ledger = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z-open", "buy", "buy_to_open", True, True, "zero_dte_special_lifecycle"), _policy()).ledger
    assert ledger.positions[0].zero_dte is True


def test_zero_dte_expiry_managed_state_written():
    ledger = add_open_position(create_paper_account_ledger("zero", _policy()), _intent("z-open", "buy", "buy_to_open", True, True, "zero_dte_special_lifecycle"), _policy()).ledger
    close = _intent("z-close-ok", "sell", "sell_to_close", True, True, "zero_dte_expiry_managed", "expiry_window")
    close.related_open_position_id = "z-open"
    result = close_position(ledger, close, _policy())
    assert result.ledger.positions[0].lifecycle_state == "zero_dte_special_close_allowed"
