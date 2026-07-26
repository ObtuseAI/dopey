from __future__ import annotations

from dopey_execution.account_ledger import add_open_position, create_paper_account_ledger
from dopey_execution.day_trade_policy import default_day_trade_policy
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.rotation_planner import build_rotation_plan, rotation_plan_hash


def _policy():
    return default_day_trade_policy()


def _intent(intent_id: str, structure: str, side: str, action: str, date: str, option_type: str, live: bool = False) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": f"SPY_{option_type}_{intent_id}", "option_type": option_type, "expiry": "2026-07-17", "strike": 500.0, "dte": 14}],
        max_loss=1.0,
        order_action=action,
        trade_date=date,
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state="normal_hold",
        live_allowed=live,
    )


def _ledger_with_today_call():
    ledger = create_paper_account_ledger("rotation-test", _policy())
    return add_open_position(ledger, _intent("today-call", "long_call", "buy", "buy_to_open", "2026-07-03", "call"), _policy()).ledger


def test_rotation_planner_allows_new_compliant_entry():
    plan = build_rotation_plan(_ledger_with_today_call(), [_intent("new-put", "long_put", "buy", "buy_to_open", "2026-07-03", "put")], [], _policy(), {"entry_allowed": True}, {"entry_allowed": True}, {})
    assert plan.allowed_entries[0].candidate_id == "new-put"


def test_rotation_planner_blocks_same_day_close():
    close = _intent("close-today", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "today-call"
    plan = build_rotation_plan(_ledger_with_today_call(), [], [close], _policy(), {}, {}, {})
    assert plan.blocked_actions[0].decision_type == "blocked_same_day_round_trip"


def test_rotation_planner_creates_delayed_exit_plan():
    close = _intent("close-delay", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "today-call"
    plan = build_rotation_plan(_ledger_with_today_call(), [], [close], _policy(), {}, {}, {})
    assert plan.delayed_exits[0].earliest_exit_date == "2026-07-06"


def test_rotation_planner_allows_rotation_after_next_day_close():
    ledger = create_paper_account_ledger("rotation-next", _policy())
    ledger = add_open_position(ledger, _intent("old-call", "long_call", "buy", "buy_to_open", "2026-07-02", "call"), _policy()).ledger
    close = _intent("close-old", "long_call", "sell", "sell_to_close", "2026-07-03", "call")
    close.related_open_position_id = "old-call"
    plan = build_rotation_plan(ledger, [_intent("new-put", "long_put", "buy", "buy_to_open", "2026-07-03", "put")], [close], _policy(), {}, {}, {})
    assert {decision.decision_type for decision in plan.decisions} >= {"close_allowed", "open_allowed"}


def test_rotation_planner_blocks_unsupported_spread():
    plan = build_rotation_plan(_ledger_with_today_call(), [_intent("spread", "vertical", "buy", "buy_to_open", "2026-07-03", "call")], [], _policy(), {}, {}, {})
    assert plan.blocked_actions[0].decision_type == "blocked_policy_violation"


def test_rotation_planner_blocks_sell_to_open():
    plan = build_rotation_plan(_ledger_with_today_call(), [_intent("short", "long_call", "sell", "sell_to_open", "2026-07-03", "call")], [], _policy(), {}, {}, {})
    assert "sell_to_open_rejected" in plan.blocked_actions[0].reason_codes


def test_rotation_planner_blocks_live_path():
    plan = build_rotation_plan(_ledger_with_today_call(), [_intent("live", "long_call", "buy", "buy_to_open", "2026-07-03", "call", live=True)], [], _policy(), {}, {}, {})
    assert plan.blocked_actions[0].decision_type == "blocked_live_path"


def test_rotation_plan_hash_is_deterministic():
    plan_one = build_rotation_plan(_ledger_with_today_call(), [_intent("new-put", "long_put", "buy", "buy_to_open", "2026-07-03", "put")], [], _policy(), {}, {}, {})
    plan_two = build_rotation_plan(_ledger_with_today_call(), [_intent("new-put", "long_put", "buy", "buy_to_open", "2026-07-03", "put")], [], _policy(), {}, {}, {})
    assert rotation_plan_hash(plan_one) == rotation_plan_hash(plan_two)
