"""Dopey paper broker: fully local simulated broker stub (logs to proof ledger, no live exec).

DOPEY-native. Simulates paper order preview + placement only. Never connects to a funded
account. Records every action to a proof ledger path (default in-memory list) so the autonomy
loop can audit paper activity.
"""
from __future__ import annotations

from .broker_interface import BrokerInterface
from .execution_intent import ExecutionIntent


class PaperBroker(BrokerInterface):
    def __init__(self, ledger=None, account_id: str = "dopey-paper-account", day_trade_policy=None):
        self.ledger = ledger  # optional append-only ledger (ProofLedger or list)
        self._orders: list[dict] = []
        # Restored active-trading-policy integration: the paper broker carries a
        # paper account ledger; intents that declare an order_action are routed
        # through the ledger's fail-closed open/close policy validation
        # (buy-to-open only, no same-day close except the zero-DTE special
        # lifecycle, close requires a matching open position).
        from .account_ledger import create_paper_account_ledger
        from .day_trade_policy import default_day_trade_policy

        self.day_trade_policy = day_trade_policy or default_day_trade_policy()
        self.account_ledger = create_paper_account_ledger(account_id, self.day_trade_policy)

    def get_capabilities(self) -> dict:
        return {
            "broker": "paper",
            "options_exec_supported": True,   # paper exec is supported
            "live": False,
            "funded": False,
            # restored expanded defined-risk PAPER structures (strangle / iron
            # condor / butterfly are simulated paper-only; still never live)
            "supported_structures": ["single", "vertical", "strangle", "iron_condor", "butterfly"],
            "defined_risk_only_default": True,
        }

    def get_account_snapshot(self) -> dict:
        return {"broker": "paper", "funded": False, "cash": 0.0, "positions": [], "paper": True}

    def get_option_chain(self, symbol: str) -> dict:
        return {"ok": False, "reason": "paper broker does not hold chain data in first pass", "symbol": symbol}

    def preview_order(self, intent: ExecutionIntent) -> dict:
        errs = intent.validate()
        if intent.live_allowed:
            errs.append("paper broker cannot preview a live_allowed intent")
        return {
            "preview": True,
            "paper": True,
            "valid": not errs,
            "errors": errs,
            "intent": intent.to_dict(),
            "estimated_fill": "simulated_paper_only",
            # The paper broker EXECUTES policy decisions; it does not select or
            # optimize trades (that is the research layer's job). This role
            # declaration is a standing envelope property - see the preflight
            # "paperbroker_policy_executor_not_optimizer_check" and the sibling
            # allocator's "policy_executor_not_allocator".
            "paper_broker_role": "policy_executor_not_optimizer",
        }

    def place_order(self, intent: ExecutionIntent) -> dict:
        errs = intent.validate()
        if intent.live_allowed:
            from .errors import LiveTradingDisabledError
            raise LiveTradingDisabledError("paper broker cannot place a live_allowed intent")
        if errs:
            return {"ok": False, "errors": errs}
        if intent.order_action:
            return self._place_active_policy_order(intent)
        order_id = f"paper-{len(self._orders)+1}"
        rec = {"order_id": order_id, "intent": intent.to_dict(), "status": "simulated_paper_filled", "paper": True}
        self._orders.append(rec)
        self._log(rec)
        return {"ok": True, "order_id": order_id, "paper": True, "status": "simulated_paper_filled"}

    # Most-specific-first ordering for the single surfaced reason_code: a
    # structural leg problem (a short leg can never be opened) explains a
    # rejection better than the derivative action-level codes the ledger
    # lists alongside it. All codes remain available in "errors".
    _REASON_CODE_PRIORITY = (
        "unsupported_short_option_leg",
        "ledger_rejects_non_call_put_option_type",
        "close_without_open_position_rejected",
        "same_day_round_trip_rejected",
        "zero_dte_",
        "blocked_live_path",
    )

    @classmethod
    def _primary_reason_code(cls, reason_codes: list[str]) -> str:
        for prefix in cls._REASON_CODE_PRIORITY:
            for code in reason_codes:
                if code.startswith(prefix):
                    return code
        return reason_codes[0] if reason_codes else ""

    @staticmethod
    def _post_action_policy_state(result) -> dict:
        """Truthful post-action lifecycle snapshot from the UPDATED ledger.

        For a close, result.position is the matched position BEFORE the close;
        the authoritative post-action state (paper_closed /
        zero_dte_special_close_allowed) lives on the updated ledger.
        """
        position_id = str(result.position.get("position_id", "")) if result.position else ""
        post = next(
            (p for p in result.ledger.positions if p.position_id == position_id),
            None,
        )
        state = post.to_dict() if post is not None else dict(result.position or {})
        return {
            "position_id": state.get("position_id", ""),
            "lifecycle_state": state.get("lifecycle_state", ""),
            "zero_dte": bool(state.get("zero_dte", False)),
            "close_status": state.get("close_status", ""),
            "same_day_close_blocked": bool(state.get("same_day_close_blocked", False)),
            "decision": result.decision,
            "paper_only": True,
            "live_blocked": True,
        }

    def _place_active_policy_order(self, intent: ExecutionIntent) -> dict:
        """Route an active-policy intent through the paper account ledger.

        Fail-closed: unknown order_actions and sell_to_open are rejected by the
        ledger validators; a close requires a matching open position and honors
        the no-same-day-close policy (zero-DTE special lifecycle excepted).
        """
        from .account_ledger import add_open_position, close_position
        from .position_lifecycle import ACTIVE_SELL_TO_CLOSE

        if intent.order_action in {ACTIVE_SELL_TO_CLOSE, "close"}:
            result = close_position(self.account_ledger, intent, self.day_trade_policy)
        else:
            result = add_open_position(self.account_ledger, intent, self.day_trade_policy)
        self.account_ledger = result.ledger
        order_id = f"paper-{len(self._orders)+1}"
        status = "simulated_paper_filled" if result.accepted else "rejected_by_account_ledger"
        reason_code = self._primary_reason_code(list(result.reason_codes))
        active_policy_state = self._post_action_policy_state(result)
        rec = {"order_id": order_id, "intent": intent.to_dict(), "status": status,
               "decision": result.decision, "reason_code": reason_code, "paper": True}
        self._orders.append(rec)
        self._log(rec)
        return {
            "ok": result.accepted,
            "errors": list(result.reason_codes),
            "order_id": order_id,
            "paper": True,
            "status": status,
            "decision": result.decision,
            "reason_code": reason_code,
            "active_policy_state": active_policy_state,
            "account_ledger_hash": getattr(result.ledger, "ledger_hash", ""),
            "position": result.position,
            "day_trade_event": result.day_trade_event,
        }

    def cancel_order(self, order_id: str) -> dict:
        return {"ok": True, "order_id": order_id, "paper": True, "status": "simulated_paper_canceled"}

    def _log(self, rec: dict) -> None:
        if self.ledger is None:
            return
        if isinstance(self.ledger, list):
            self.ledger.append(rec)
        elif hasattr(self.ledger, "append"):
            # ProofLedger expects a ProofEntry; here we just record a dict-shaped note
            try:
                self.ledger.append(rec)  # type: ignore[arg-type]
            except Exception:
                pass
