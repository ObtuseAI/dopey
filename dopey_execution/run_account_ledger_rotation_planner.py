"""Write offline account-ledger and PDT-safe rotation planner artifacts."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from dopey_options.run_zero_dte_outcome_replay import ZERO_DTE_REPLAY_OUTCOMES_PATH, run_zero_dte_outcome_replay
from dopey_options.run_zero_dte_risk_model import run_zero_dte_risk_model
from dopey_options.zero_dte_decision_engine import evaluate_zero_dte_candidate
from dopey_options.zero_dte_risk_model import ZeroDTERiskInput
from dopey_options.zero_dte_risk_thresholds import load_default_zero_dte_risk_thresholds

from .account_ledger import (
    PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH,
    ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH,
    account_ledger_summary,
    add_open_position,
    close_position,
    create_paper_account_ledger,
    write_account_ledger_artifacts,
)
from .day_trade_policy import default_day_trade_policy
from .execution_intent import ExecutionIntent
from .paper_broker import PaperBroker
from .pdt_safe_policy import default_pdt_safe_policy
from .rotation_planner import build_rotation_plan, ledger_with_rotation_plan, write_rotation_plan_artifacts


REPO_ROOT = Path(__file__).resolve().parent.parent
PAPER_ALLOCATION_PLAN_PATH = REPO_ROOT / "artifacts" / "dopey" / "allocation" / "paper_allocation_plan.json"


def run_account_ledger_rotation_planner() -> dict:
    zero_dte_risk_result = run_zero_dte_risk_model()
    zero_dte_replay_result = run_zero_dte_outcome_replay()
    trade_date = "2026-07-03"
    prior_date = "2026-07-02"
    policy = default_day_trade_policy()
    pdt_policy = default_pdt_safe_policy()
    ledger = create_paper_account_ledger("dopey-paper-account-fixture", policy)

    open_call_today = _intent("acct-call-today", "long_call", "buy", "buy_to_open", trade_date, "call", "2026-07-17")
    open_put_yesterday = _intent("acct-put-yesterday", "long_put", "buy", "buy_to_open", prior_date, "put", "2026-07-17")
    call_open_result = add_open_position(ledger, open_call_today, policy)
    ledger = call_open_result.ledger
    put_open_result = add_open_position(ledger, open_put_yesterday, policy)
    ledger = put_open_result.ledger

    same_day_close = _intent("acct-call-close-same", "long_call", "sell", "sell_to_close", trade_date, "call", "2026-07-17")
    same_day_close.related_open_position_id = open_call_today.position_id or open_call_today.intent_id
    same_day_close_result = close_position(ledger, same_day_close, policy)
    ledger = same_day_close_result.ledger

    next_day_close = _intent("acct-put-close-next", "long_put", "sell", "sell_to_close", trade_date, "put", "2026-07-17")
    next_day_close.related_open_position_id = open_put_yesterday.position_id or open_put_yesterday.intent_id
    next_day_close_result = close_position(ledger, next_day_close, policy)
    ledger = next_day_close_result.ledger

    new_entry = _intent("rotation-new-put", "long_put", "buy", "buy_to_open", trade_date, "put", "2026-07-24")
    plan = build_rotation_plan(
        ledger,
        [new_entry],
        [same_day_close],
        policy,
        {"entry_allowed": True},
        {"entry_allowed": True},
        {"rotation-new-put": 0.91},
    )
    ledger = ledger_with_rotation_plan(ledger, plan)

    zero_dte_rejected = add_open_position(
        ledger,
        _intent("zero-dte-missing-liquidity", "long_call", "buy", "buy_to_open", trade_date, "call", trade_date, zero_dte=True, liquidity=False, risk=True, lifecycle="zero_dte_special_lifecycle", zero_dte_risk_decision=_zero_dte_decision("zero-dte-missing-liquidity", "blocked_liquidity")),
        policy,
    )
    zero_dte_open = add_open_position(
        ledger,
        _intent("zero-dte-open", "long_call", "buy", "buy_to_open", trade_date, "call", trade_date, zero_dte=True, liquidity=True, risk=True, lifecycle="zero_dte_special_lifecycle", zero_dte_risk_decision=_zero_dte_decision("zero-dte-open", "approved_for_paper_open"), zero_dte_replay_feedback=_latest_zero_dte_replay_feedback("approved_survived_fixture")),
        policy,
    )
    zero_dte_close_intent = _intent("zero-dte-close", "long_call", "sell", "sell_to_close", trade_date, "call", trade_date, zero_dte=True, liquidity=True, risk=True, lifecycle="zero_dte_expiry_managed", reason="expiry_window", zero_dte_risk_decision=_zero_dte_decision("zero-dte-open", "approved_for_paper_open"))
    zero_dte_close_intent.related_open_position_id = "zero-dte-open"
    zero_dte_close = close_position(zero_dte_open.ledger, zero_dte_close_intent, policy)

    broker_ledger: list[dict] = []
    broker = PaperBroker(ledger=broker_ledger)
    broker_open = broker.place_order(_intent("broker-ledger-open", "long_call", "buy", "buy_to_open", trade_date, "call", "2026-07-17"))
    broker_close_same = _intent("broker-ledger-close-same", "long_call", "sell", "sell_to_close", trade_date, "call", "2026-07-17")
    broker_close_same.related_open_position_id = "broker-ledger-open"
    broker_close_result = broker.place_order(broker_close_same)

    paths = write_account_ledger_artifacts(ledger, policy, pdt_policy)
    paths.update(write_rotation_plan_artifacts(plan))
    zero_proof = {
        "artifact_type": "zero_dte_account_lifecycle_proof",
        "zero_dte_rejected": zero_dte_rejected.to_dict(),
        "zero_dte_open": zero_dte_open.to_dict(),
        "zero_dte_close": zero_dte_close.to_dict(),
        "zero_dte_replay_feedback": _latest_zero_dte_replay_feedback("approved_survived_fixture"),
        "paper_only": True,
        "live_blocked": True,
    }
    zero_proof["reproducibility_hash"] = _stable_hash(zero_proof)
    _append_jsonl(ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH, zero_proof)
    broker_proof = {
        "artifact_type": "paperbroker_account_ledger_proof",
        "broker_open": broker_open,
        "broker_same_day_close": broker_close_result,
        "account_ledger": broker.account_ledger.to_dict(),
        "broker_log": broker_ledger,
        "paper_only": True,
        "live_blocked": True,
    }
    broker_proof["reproducibility_hash"] = _stable_hash(broker_proof)
    _append_jsonl(PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH, broker_proof)
    paths["zero_dte_account_lifecycle_proof"] = str(ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH)
    paths["paperbroker_account_ledger_proof"] = str(PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH)

    allocation_context = _allocation_context()
    result = {
        "account_ledger_rotation_planner_status": "ok",
        "mode": "RESEARCH",
        "paper_only": True,
        "live_blocked": True,
        "allocation_context": allocation_context,
        "account_ledger_summary": account_ledger_summary(ledger, trade_date),
        "same_day_close_result": same_day_close_result.to_dict(),
        "next_day_close_result": next_day_close_result.to_dict(),
        "rotation_plan": {**plan.to_dict(), "allocation_context": allocation_context},
        "zero_dte_risk_model": zero_dte_risk_result,
        "zero_dte_outcome_replay": zero_dte_replay_result,
        "artifact_paths": paths,
    }
    result["reproducibility_hash"] = _stable_hash(result)
    return result


def _allocation_context() -> dict:
    if not PAPER_ALLOCATION_PLAN_PATH.exists():
        return _default_allocation_context(False, {})
    payload = json.loads(PAPER_ALLOCATION_PLAN_PATH.read_text(encoding="utf-8"))
    return _default_allocation_context(True, payload)


def _default_allocation_context(loaded: bool, plan: dict) -> dict:
    risk_summary = plan.get("risk_summary", {}) if isinstance(plan.get("risk_summary", {}), dict) else {}
    strategy_units = plan.get("allocation_by_strategy_type", {}) if isinstance(plan.get("allocation_by_strategy_type", {}), dict) else {}
    return {
        "artifact_type": "paper_allocation_context",
        "allocation_plan_loaded": loaded,
        "allocator_role": "advisory_paper_attention_only",
        "paper_attention_priority_available": loaded,
        "delayed_rotation_reserves_advisory_only": True,
        "allocator_can_force_same_day_close": False,
        "paper_broker_override_allowed": False,
        "paperbroker_role": "policy_executor_not_allocator",
        "plan_id": str(plan.get("plan_id", "")),
        "opportunity_count": int(plan.get("opportunity_count", 0)),
        "allocated_count": int(plan.get("allocated_count", 0)),
        "delayed_rotation_count": int(plan.get("delayed_rotation_count", 0)),
        "zero_dte_paper_premium_risk_units": float(risk_summary.get("zero_dte_paper_premium_risk_units", 0.0)),
        "swing_paper_premium_risk_units": float(risk_summary.get("swing_paper_premium_risk_units", 0.0)),
        "strategy_priority_units": strategy_units,
        "paper_only": True,
        "live_blocked": True,
    }


def _intent(
    intent_id: str,
    structure: str,
    side: str,
    order_action: str,
    trade_date: str,
    option_type: str,
    expiry: str,
    zero_dte: bool = False,
    liquidity: bool = False,
    risk: bool = False,
    lifecycle: str = "normal_hold",
    reason: str = "",
    zero_dte_risk_decision: dict | None = None,
    zero_dte_replay_feedback: dict | None = None,
) -> ExecutionIntent:
    strike = 500.0 if option_type == "call" else 495.0
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": f"SPY_{option_type}_{strike}_{expiry}", "option_type": option_type, "expiry": expiry, "strike": strike, "dte": 0 if zero_dte else 14}],
        max_loss=1.0,
        target_profit=2.0,
        order_action=order_action,
        trade_date=trade_date,
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state=lifecycle,
        zero_dte=zero_dte,
        liquidity_approved=liquidity,
        risk_cap_approved=risk,
        reason_code=reason,
        zero_dte_risk_decision=zero_dte_risk_decision or {},
        zero_dte_replay_feedback=zero_dte_replay_feedback or {},
    )


def _zero_dte_decision(candidate_id: str, expected: str) -> dict:
    thresholds = load_default_zero_dte_risk_thresholds()
    base = {
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
        "explicit_thesis": "fixture trend and proof stack justify temporary same-day convexity exposure",
        "explicit_exit_or_expiry_plan": "expiry-managed close only with explicit risk reason and no normal churn",
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
    if expected == "blocked_liquidity":
        base["liquidity_score"] = 0.40
        base["volume"] = 100
        base["open_interest"] = 120
    return evaluate_zero_dte_candidate(ZeroDTERiskInput.from_dict(base), thresholds).to_dict()


def _append_jsonl(path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def _stable_hash(record: dict) -> str:
    encoded = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _latest_zero_dte_replay_feedback(outcome_type: str) -> dict:
    if not ZERO_DTE_REPLAY_OUTCOMES_PATH.exists():
        return {}
    for line in ZERO_DTE_REPLAY_OUTCOMES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("outcome_type") == outcome_type:
            return {
                "replay_id": record.get("replay_id", ""),
                "candidate_id": record.get("candidate_id", ""),
                "outcome_type": record.get("outcome_type", ""),
                "risk_model_alignment": record.get("risk_model_alignment", ""),
                "threshold_feedback": record.get("threshold_feedback", []),
                "recursive_improvement_tags": record.get("recursive_improvement_tags", []),
                "advisory_only": True,
                "auto_approval_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
    return {}


def main() -> int:
    print(json.dumps(run_account_ledger_rotation_planner(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
