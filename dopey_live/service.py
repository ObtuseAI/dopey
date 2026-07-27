"""Orchestrate one deterministic Live Branch cycle."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .control import LiveBranchControl, load_live_branch_control
from .dumbmoney_command_feed import DumbMoneyCommandDispatch
from .dumbmoney_authority import (
    DumbMoneyAuthorityContext,
    DumbMoneyAuthorityError,
    VerifiedCapitalAuthority,
    authorize_intent,
    authorized_settled_cash_usd,
)
from .dumbmoney_promotion import (
    PromotionAuthorityResolver,
    VerifiedPromotionBinding,
)
from .ledger import (
    LiveBranchLedgerError,
    activate_dumbmoney_fence,
    append_record,
    assert_current_dumbmoney_fence,
    artifact_root,
    ledger_path,
    paper_twin_path,
    read_ledger,
    reserve_intent,
    write_latest_cycle,
)
from .models import (
    AccountSnapshot,
    LiveExecutionIntent,
    live_execution_intent_from_dict,
)
from .robinhood_gateway import (
    RobinhoodAgenticGateway,
    RobinhoodAuthRequiredError,
    RobinhoodCancellationAmbiguousError,
    RobinhoodConsentRequiredError,
    RobinhoodGatewayError,
    RobinhoodPlacementAmbiguousError,
    consent_remediation,
    reauth_remediation,
)
from .settlement import SettlementModelError, estimate_settled_funds
from .signals import (
    LiveSignalError,
    build_entry_intents,
    prepare_equity_entry_for_execution,
    research_maturity_blockers,
    validate_option_entry_for_execution,
)


NEW_YORK = ZoneInfo("America/New_York")
ACTIVE_ORDER_STATUSES = frozenset(
    {"queued", "pending", "open", "confirmed", "partially_filled"}
)
TERMINAL_ORDER_STATUSES = frozenset(
    {"filled", "cancelled", "canceled", "rejected", "expired", "failed", "voided"}
)
RECOGNIZED_ORDER_STATUSES = ACTIVE_ORDER_STATUSES | TERMINAL_ORDER_STATUSES
MAX_ORDER_INTENTS_PER_CYCLE = 1
DUMBMONEY_KILL_FILENAME = "DUMBMONEY_KILL.v1"
DUMBMONEY_HISTORY_POLL_LIMIT = 3


def _regular_market_state(now_utc: datetime) -> tuple[bool, str]:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    calendar = xcals.get_calendar("XNYS")
    minute = now_utc.astimezone(timezone.utc).replace(second=0, microsecond=0)
    session = (
        calendar.minute_to_session(minute, direction="none")
        if calendar.is_open_on_minute(minute)
        else None
    )
    return (session is not None, "" if session is None else str(session.date()))


def _robinhood_stock_submission_state(now_utc: datetime) -> tuple[bool, str, bool]:
    regular_open, regular_date = _regular_market_state(now_utc)
    now_et = now_utc.astimezone(NEW_YORK)
    weekday = now_et.weekday()
    local_time = now_et.time()
    if weekday == 5:
        return False, "", regular_open
    if weekday == 6:
        if local_time.hour < 20:
            return False, "", regular_open
        return True, (now_et.date() + timedelta(days=1)).isoformat(), regular_open
    if weekday == 4 and local_time.hour >= 20:
        return False, "", regular_open
    if local_time.hour >= 20:
        return True, (now_et.date() + timedelta(days=1)).isoformat(), regular_open
    return True, regular_date or now_et.date().isoformat(), regular_open


def _base_cycle(now_utc: datetime) -> dict[str, Any]:
    return {
        "artifact_type": "dopey_live_branch_cycle",
        "schema_version": "dopey-live-branch-cycle-v1",
        "generated_utc": now_utc.isoformat(),
        "mode": "LIVE",
        "paper_twin_required": True,
        "no_day_trading_enforced": True,
        "account_identifiers_redacted": True,
    }


def _paper_twin_outcome_payload(
    intent_id: str,
    paper_twin_record_hash: str,
    live_record_hash: str,
    live_order_status: str,
    live_order_placed: bool | None,
    observed_live_filled_quantity: float | None,
    observed_live_average_fill_price: float | None,
) -> dict[str, Any]:
    if live_order_placed is None:
        outcome_status = "paper_twin_quarantined_ambiguous_live_submission"
    elif live_order_placed is False:
        outcome_status = "paper_twin_not_submitted_live_order_blocked"
    elif live_order_status in ACTIVE_ORDER_STATUSES:
        outcome_status = "paper_twin_pending_nonterminal_live_order"
    else:
        outcome_status = "paper_twin_observed_terminal_live_order"
    return {
        "intent_id": intent_id,
        "paper_twin_record_hash": paper_twin_record_hash,
        "live_record_hash": live_record_hash,
        "live_order_status": live_order_status,
        "live_order_placed": live_order_placed,
        "observed_live_filled_quantity": observed_live_filled_quantity,
        "observed_live_average_fill_price": observed_live_average_fill_price,
        "paper_twin_outcome_status": outcome_status,
        "paper_fill_status": "not_simulated",
        "paper_filled_quantity": None,
        "paper_average_fill_price": None,
        "no_fill_inferred": True,
        "result_bearing": False,
        "independent_of_live_result": False,
        "comparison_only": True,
        "paper_only": True,
        "live_twin": True,
    }


def _paper_twin_execution_payload(
    intent: LiveExecutionIntent,
    paper_twin_record_hash: str,
) -> dict[str, Any]:
    snapshot = intent.execution_snapshot
    base = {
        "intent_id": intent.intent_id,
        "paper_twin_record_hash": paper_twin_record_hash,
        "instrument": intent.instrument,
        "symbol": intent.symbol,
        "side": intent.side,
        "limit_price": intent.limit_price,
        "paper_only": True,
        "live_twin": True,
        "independent_of_live_result": True,
        "simulation_model_version": "dopey-paper-twin-marketable-limit-v1",
    }
    if intent.instrument != "equity" or intent.side != "buy" or snapshot is None:
        return {
            **base,
            "paper_twin_execution_status": "unobserved_no_independent_quote_snapshot",
            "paper_fill_status": "not_simulated",
            "paper_filled_quantity": None,
            "paper_average_fill_price": None,
            "market_observation_source": "",
            "market_observed_at": "",
            "result_bearing": False,
        }
    quote = snapshot.execution_quote
    marketable = intent.limit_price >= quote.ask_price
    filled_quantity = (
        (
            intent.quantity
            if intent.quantity > 0.0
            else round(intent.notional_usd / quote.ask_price, 8)
        )
        if marketable
        else 0.0
    )
    if marketable and filled_quantity <= 0.0:
        raise ValueError(
            "Paper twin marketable equity order has no positive simulated quantity: "
            f"intent_id={intent.intent_id}, notional={intent.notional_usd}, "
            f"ask={quote.ask_price}"
        )
    return {
        **base,
        "paper_twin_execution_status": "independent_quote_observation_complete",
        "paper_fill_status": "simulated_filled"
        if marketable
        else "simulated_not_filled",
        "paper_filled_quantity": filled_quantity,
        "paper_average_fill_price": quote.ask_price if marketable else None,
        "market_observation_source": snapshot.source,
        "market_observed_at": quote.observed_at,
        "observed_bid_price": quote.bid_price,
        "observed_ask_price": quote.ask_price,
        "result_bearing": True,
    }


def _append_paper_twin_execution_observation(
    repository_root: Path,
    intent: LiveExecutionIntent,
    paper_twin_record_hash: str,
) -> dict[str, Any]:
    return append_record(
        paper_twin_path(repository_root),
        "paper_twin_execution_observed",
        _paper_twin_execution_payload(intent, paper_twin_record_hash),
    )


def _append_paper_twin_outcome(
    repository_root: Path,
    intent_id: str,
    paper_twin_record_hash: str,
    live_record_hash: str,
    live_order_status: str,
    live_order_placed: bool | None,
    observed_live_filled_quantity: float | None,
    observed_live_average_fill_price: float | None,
) -> dict[str, Any]:
    return append_record(
        paper_twin_path(repository_root),
        "paper_twin_outcome_observed",
        _paper_twin_outcome_payload(
            intent_id,
            paper_twin_record_hash,
            live_record_hash,
            live_order_status,
            live_order_placed,
            observed_live_filled_quantity,
            observed_live_average_fill_price,
        ),
    )


def _complete_legacy_twin_observations(
    repository_root: Path,
) -> tuple[dict[str, Any], ...]:
    """Terminally classify twins that can never bear an independent result.

    Orders placed before execution-snapshot capture existed serialized no
    review-time quote, so no independent paper-twin result can ever be
    produced for them - not now, not later. Record that fact once as an
    explicit terminal observation; the release gate reports these separately
    instead of carrying a permanently unfixable missing-result blocker. For a
    post-capability order whose intent DOES carry its snapshot but whose
    observation is missing (crash between placement and observation append),
    this appends the real result-bearing observation instead.
    """
    live_records = read_ledger(ledger_path(repository_root))
    twin_ledger = paper_twin_path(repository_root)
    twin_records = read_ledger(twin_ledger)
    observed_twin_hashes = {
        str(record["payload"].get("paper_twin_record_hash", ""))
        for record in twin_records
        if record.get("event_type") == "paper_twin_execution_observed"
        and isinstance(record.get("payload"), dict)
    }
    appended: list[dict[str, Any]] = []
    for record in live_records:
        if record.get("event_type") != "live_order_result":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("placed") is not True:
            continue
        twin_hash = str(payload.get("paper_twin_record_hash", ""))
        if not twin_hash or twin_hash in observed_twin_hashes:
            continue
        raw_intent = payload.get("intent")
        if not isinstance(raw_intent, dict):
            continue
        intent = live_execution_intent_from_dict(raw_intent)
        if intent.execution_snapshot is not None:
            appended.append(
                _append_paper_twin_execution_observation(
                    repository_root, intent, twin_hash
                )
            )
            observed_twin_hashes.add(twin_hash)
            continue
        observation = {
            "intent_id": intent.intent_id,
            "paper_twin_record_hash": twin_hash,
            "instrument": intent.instrument,
            "symbol": intent.symbol,
            "side": intent.side,
            "paper_twin_execution_status": (
                "unobservable_legacy_order_predates_quote_snapshot"
            ),
            "paper_fill_status": "not_simulated",
            "paper_filled_quantity": None,
            "paper_average_fill_price": None,
            "market_observation_source": "",
            "market_observed_at": "",
            "result_bearing": False,
            "terminally_unobservable": True,
            "paper_only": True,
            "live_twin": True,
            "independent_of_live_result": True,
        }
        appended.append(
            append_record(twin_ledger, "paper_twin_execution_observed", observation)
        )
        observed_twin_hashes.add(twin_hash)
    return tuple(appended)


def _position_key(intent: LiveExecutionIntent) -> str:
    contract_key = str(intent.option_contract.get("contract_symbol_key", ""))
    return f"{intent.instrument}|{intent.symbol}|{contract_key}"


def _filled_quantity(payload: dict[str, Any], context: str) -> float:
    try:
        quantity = float(payload.get("filled_quantity", 0.0))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Filled quantity must be numeric: context={context}, value={payload.get('filled_quantity')!r}"
        ) from error
    if not math.isfinite(quantity) or quantity < 0.0:
        raise ValueError(
            f"Filled quantity must be finite and nonnegative: context={context}, value={quantity}"
        )
    return quantity


def _open_live_positions(
    repository_root: Path,
) -> dict[str, tuple[LiveExecutionIntent, str, float]]:
    records = read_ledger(ledger_path(repository_root))
    order_states: dict[str, tuple[LiveExecutionIntent, str, str, float]] = {}
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = str(record.get("event_type", ""))
        order_id = str(payload.get("order_id", ""))
        if not order_id:
            continue
        if event_type == "live_order_result" and payload.get("placed") is True:
            raw_intent = payload.get("intent")
            if not isinstance(raw_intent, dict):
                raise ValueError(
                    f"Placed live order is missing a typed intent: order_id={order_id}"
                )
            intent = live_execution_intent_from_dict(raw_intent)
            order_states[order_id] = (
                intent,
                str(payload.get("market_date", "")),
                str(payload.get("status", "")).lower(),
                _filled_quantity(payload, f"live_order_result:{order_id}"),
            )
            continue
        if event_type == "live_order_status_observed" and order_id in order_states:
            intent, market_date, _, prior_filled_quantity = order_states[order_id]
            observed_filled_quantity = _filled_quantity(
                payload,
                f"live_order_status_observed:{order_id}",
            )
            order_states[order_id] = (
                intent,
                market_date,
                str(payload.get("status", "")).lower(),
                max(prior_filled_quantity, observed_filled_quantity),
            )
    opened: dict[str, tuple[LiveExecutionIntent, str, float]] = {}
    for intent, market_date, status, quantity in order_states.values():
        if status not in {"filled", "partially_filled"} or quantity <= 0.0:
            continue
        key = _position_key(intent)
        if intent.side == "buy":
            prior = opened.get(key)
            if prior is None:
                opened[key] = (intent, market_date, quantity)
            else:
                opened[key] = (prior[0], prior[1], prior[2] + quantity)
        elif intent.side == "sell":
            prior = opened.get(key)
            if prior is None:
                continue
            remaining_quantity = prior[2] - quantity
            if remaining_quantity <= 0.0:
                opened.pop(key, None)
            else:
                opened[key] = (prior[0], prior[1], remaining_quantity)
    # Owner-initiated liquidations (sold directly in the brokerage app, outside
    # DOPEY) reduce local attribution once settled by evidence - see
    # _settle_owner_liquidations. Subtraction order vs system sells does not
    # matter: both only ever subtract nonnegative quantities.
    for record in records:
        if (
            str(record.get("event_type", ""))
            != "live_position_owner_liquidation_observed"
        ):
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        key = str(payload.get("position_key", ""))
        prior = opened.get(key)
        if prior is None:
            continue
        try:
            liquidated_quantity = float(payload.get("liquidated_quantity", 0.0))
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Owner liquidation record has a non-numeric quantity: "
                f"position_key={key}"
            ) from error
        if not math.isfinite(liquidated_quantity) or liquidated_quantity <= 0.0:
            raise ValueError(
                "Owner liquidation record quantity must be finite and positive: "
                f"position_key={key}, value={liquidated_quantity}"
            )
        remaining_quantity = prior[2] - liquidated_quantity
        if remaining_quantity <= 0.0:
            opened.pop(key, None)
        else:
            opened[key] = (prior[0], prior[1], remaining_quantity)
    return opened


def _reconcile_live_order_statuses(
    repository_root: Path,
    account: AccountSnapshot,
) -> tuple[dict[str, Any], ...]:
    path = ledger_path(repository_root)
    records = read_ledger(path)
    existing_observations = {
        (
            str(record["payload"].get("order_id", "")),
            str(record["payload"].get("status", "")).lower(),
            str(record["payload"].get("filled_at", "")),
            str(record["payload"].get("filled_quantity", "")),
        )
        for record in records
        if record.get("event_type") == "live_order_status_observed"
        and isinstance(record.get("payload"), dict)
    }
    broker_orders = (*account.recent_equity_orders, *account.recent_option_orders)
    broker_by_order_id = {
        str(order.get("order_id", order.get("id", ""))): order
        for order in broker_orders
        if str(order.get("order_id", order.get("id", "")))
    }
    appended: list[dict[str, Any]] = []
    for record in records:
        if record.get("event_type") != "live_order_result":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("placed") is not True:
            continue
        order_id = str(payload.get("order_id", ""))
        broker_order = broker_by_order_id.get(order_id)
        if not order_id or broker_order is None:
            continue
        status = str(broker_order.get("status", "")).lower()
        filled_at = str(broker_order.get("filled_at", ""))
        filled_quantity = _filled_quantity(
            broker_order,
            f"broker_order:{order_id}",
        )
        observation_key = (order_id, status, filled_at, str(filled_quantity))
        if not status or observation_key in existing_observations:
            continue
        observation = {
            "intent_id": str(payload.get("intent_id", "")),
            "instrument": str(payload.get("instrument", "")),
            "symbol": str(payload.get("symbol", "")),
            "side": str(payload.get("side", "")),
            "market_date": str(
                broker_order.get("market_date", payload.get("market_date", ""))
            ),
            "order_id": order_id,
            "status": status,
            "submitted_at": str(broker_order.get("submitted_at", "")),
            "filled_at": filled_at,
            "filled_quantity": filled_quantity,
            "average_fill_price": float(broker_order.get("average_fill_price", 0.0)),
            "account_identifiers_redacted": True,
        }
        live_observation_record = append_record(
            path,
            "live_order_status_observed",
            observation,
        )
        paper_twin_record_hash = str(payload.get("paper_twin_record_hash", ""))
        if paper_twin_record_hash:
            _append_paper_twin_outcome(
                repository_root,
                str(payload.get("intent_id", "")),
                paper_twin_record_hash,
                str(live_observation_record["record_hash"]),
                status,
                True,
                filled_quantity,
                float(broker_order.get("average_fill_price", 0.0)),
            )
        appended.append(observation)
        existing_observations.add(observation_key)
    return tuple(appended)


def _weekday_age(open_date: date, current_date: date) -> int:
    age = 0
    cursor = open_date
    while cursor < current_date:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            age += 1
    return age


def _matching_position(
    intent: LiveExecutionIntent, account: AccountSnapshot
) -> dict[str, Any] | None:
    positions = (
        account.equity_positions
        if intent.instrument == "equity"
        else account.option_positions
    )
    for position in positions:
        if str(position.get("symbol", "")).upper() != intent.symbol:
            continue
        if intent.instrument == "option":
            intent_contract_id = str(intent.option_contract.get("contract_id", ""))
            position_contract_id = str(position.get("contract_id", ""))
            if not intent_contract_id or intent_contract_id != position_contract_id:
                continue
            return position
        return position
    return None


def _settle_owner_liquidations(
    repository_root: Path,
    account: AccountSnapshot,
) -> tuple[dict[str, Any], ...]:
    """Explain broker-missing positions via owner-initiated sell fills.

    The owner may sell any position directly in the brokerage app at any
    time. A locally attributed position that is gone (or short) broker-side is
    settled - instead of hard-blocking every future cycle - ONLY when
    owner-side sell fills (broker orders that are not in our ledger) cover the
    missing quantity since the position opened. The settlement is an
    append-only, hash-chained ledger event carrying the broker evidence; an
    unexplained disappearance still blocks the cycle via
    _position_ownership_blocker. Equity only: an owner-sold option position
    stays a hard blocker (no owner-sell model for options).
    """
    path = ledger_path(repository_root)
    records = read_ledger(path)
    system_order_ids = {
        str(record["payload"].get("order_id", ""))
        for record in records
        if record.get("event_type") == "live_order_result"
        and isinstance(record.get("payload"), dict)
    }
    appended: list[dict[str, Any]] = []
    for key, (intent, opened_market_date, owned_quantity) in _open_live_positions(
        repository_root
    ).items():
        if intent.instrument != "equity":
            continue
        position = _matching_position(intent, account)
        if position is None:
            missing_quantity = owned_quantity
        else:
            try:
                account_quantity = float(position.get("quantity", 0.0))
            except (TypeError, ValueError):
                continue  # malformed broker data: leave for the blocker
            if not math.isfinite(account_quantity):
                continue
            if account_quantity >= owned_quantity:
                continue  # intact
            missing_quantity = owned_quantity - max(account_quantity, 0.0)
        evidence_ids: list[str] = []
        covered_quantity = 0.0
        for order in account.recent_equity_orders:
            order_id = str(order.get("order_id", ""))
            if not order_id or order_id in system_order_ids:
                continue
            if str(order.get("symbol", "")).strip().upper() != intent.symbol.upper():
                continue
            if str(order.get("side", "")).strip().lower() != "sell":
                continue
            if str(order.get("status", "")).strip().lower() not in {
                "filled",
                "partially_filled",
            }:
                continue
            if str(order.get("market_date", "")) < opened_market_date:
                continue
            evidence_ids.append(order_id)
            covered_quantity += _filled_quantity(order, f"owner_sell:{order_id}")
        if covered_quantity + 1e-9 < missing_quantity:
            continue  # unexplained: the ownership blocker will fire, honestly
        payload = {
            "position_key": key,
            "intent_id": intent.intent_id,
            "instrument": intent.instrument,
            "symbol": intent.symbol,
            "liquidated_quantity": missing_quantity,
            "opened_market_date": opened_market_date,
            "evidence_broker_order_ids": sorted(evidence_ids),
            "evidence_sold_quantity": covered_quantity,
            "classification": "owner_initiated_liquidation_observed_in_broker_history",
            "account_identifiers_redacted": True,
        }
        appended.append(
            append_record(path, "live_position_owner_liquidation_observed", payload)
        )
    return tuple(appended)


def _position_ownership_blocker(
    repository_root: Path,
    account: AccountSnapshot,
) -> str:
    for opened, _, owned_quantity in _open_live_positions(repository_root).values():
        position = _matching_position(opened, account)
        if position is None:
            return "broker_position_missing_locally_attributed_quantity"
        try:
            account_quantity = float(position.get("quantity", 0.0))
        except (TypeError, ValueError):
            return "broker_position_quantity_invalid"
        if not math.isfinite(account_quantity) or account_quantity < owned_quantity:
            return "broker_position_below_locally_attributed_quantity"
    return ""


def _latest_analysis_close(
    repository_root: Path,
    analysis_symbol: str,
    market_date: date,
) -> float | None:
    path = (
        repository_root.resolve()
        / "dopey_data"
        / "history"
        / "raw"
        / f"{analysis_symbol}.csv"
    )
    if not path.exists():
        return None
    latest_date: date | None = None
    latest_close = 0.0
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("symbol", "")).upper() != analysis_symbol:
                continue
            try:
                row_date = date.fromisoformat(str(row.get("date", "")))
                close = float(row.get("close", 0.0))
            except (TypeError, ValueError):
                continue
            if row_date > market_date or not math.isfinite(close) or close <= 0.0:
                continue
            if latest_date is None or row_date > latest_date:
                latest_date = row_date
                latest_close = close
    if latest_date is None or _weekday_age(latest_date, market_date) > 1:
        return None
    return latest_close


def _exit_trigger(
    intent: LiveExecutionIntent,
    position: dict[str, Any],
    age: int,
    analysis_price: float | None,
) -> str:
    try:
        mark = float(position.get("market_price", 0.0))
    except (TypeError, ValueError):
        return ""
    if mark <= 0.0:
        return ""
    if intent.daily_reset:
        if age >= intent.maximum_holding_sessions > 0:
            return "leveraged_etf_maximum_holding_window_complete"
        try:
            average_cost = float(position.get("average_cost", 0.0))
        except (TypeError, ValueError):
            average_cost = 0.0
        if average_cost > 0.0 and mark <= average_cost * 0.80:
            return "leveraged_etf_emergency_execution_drawdown"
        if analysis_price is None or analysis_price <= 0.0:
            return ""
        if intent.thesis_direction == "bullish":
            if (
                intent.analysis_invalidation_price > 0.0
                and analysis_price <= intent.analysis_invalidation_price
            ):
                return "underlying_chart_invalidation_reached"
            if (
                intent.analysis_target_price > 0.0
                and analysis_price >= intent.analysis_target_price
            ):
                return "underlying_chart_target_reached"
        elif intent.thesis_direction == "bearish":
            if (
                intent.analysis_invalidation_price > 0.0
                and analysis_price >= intent.analysis_invalidation_price
            ):
                return "underlying_chart_invalidation_reached"
            if (
                intent.analysis_target_price > 0.0
                and analysis_price <= intent.analysis_target_price
            ):
                return "underlying_chart_target_reached"
        return ""
    if intent.instrument == "equity":
        if intent.invalidation_price > 0.0 and mark <= intent.invalidation_price:
            return "invalidation_price_reached"
        if intent.target_price > 0.0 and mark >= intent.target_price:
            return "target_price_reached"
    else:
        if mark <= intent.reference_price * 0.5:
            return "long_premium_half_value_exit"
        if mark >= intent.reference_price * 2.0:
            return "long_premium_double_value_exit"
    if (
        intent.expected_hold_trading_days > 0
        and age >= intent.expected_hold_trading_days
    ):
        return "expected_holding_window_complete"
    return ""


def _build_exit_intents(
    repository_root: Path,
    account: AccountSnapshot,
    market_date: date,
) -> tuple[LiveExecutionIntent, ...]:
    exits: list[LiveExecutionIntent] = []
    for opened, opened_date_text, owned_quantity in _open_live_positions(
        repository_root
    ).values():
        if not opened_date_text:
            continue
        opened_date = date.fromisoformat(opened_date_text)
        if market_date <= opened_date:
            continue
        position = _matching_position(opened, account)
        if position is None:
            continue
        age = _weekday_age(opened_date, market_date)
        analysis_price = (
            _latest_analysis_close(repository_root, opened.analysis_symbol, market_date)
            if opened.daily_reset
            else None
        )
        trigger = _exit_trigger(opened, position, age, analysis_price)
        if not trigger:
            continue
        if owned_quantity <= 0.0:
            continue
        option_contract = dict(opened.option_contract)
        if opened.instrument == "option":
            option_contract["order_action"] = "sell_to_close"
            option_contract["limit_price"] = float(position.get("market_price", 0.0))
        source_hash = hashlib.sha256(
            json.dumps(
                {"opened_intent": opened.to_dict(), "trigger": trigger},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        intent_id = hashlib.sha256(
            f"{opened.instrument}|sell|{opened.symbol}|{market_date.isoformat()}|{source_hash}".encode(
                "utf-8"
            )
        ).hexdigest()
        exits.append(
            LiveExecutionIntent(
                intent_id=intent_id,
                instrument=opened.instrument,
                symbol=opened.symbol,
                side="sell",
                order_type="market" if opened.instrument == "equity" else "limit",
                limit_price=(
                    0.0
                    if opened.instrument == "equity"
                    else float(option_contract.get("limit_price", 0.0))
                ),
                time_in_force="day",
                extended_hours=False,
                notional_usd=0.0,
                quantity=owned_quantity,
                source_as_of_date=opened.source_as_of_date,
                source_hash=source_hash,
                thesis_direction=opened.thesis_direction,
                analysis_symbol=opened.analysis_symbol,
                analysis_relationship=opened.analysis_relationship,
                analysis_reference_price=opened.analysis_reference_price,
                analysis_invalidation_price=opened.analysis_invalidation_price,
                analysis_target_price=opened.analysis_target_price,
                daily_leverage_multiple=opened.daily_leverage_multiple,
                daily_reset=opened.daily_reset,
                maximum_holding_sessions=opened.maximum_holding_sessions,
                reference_price=opened.reference_price,
                invalidation_price=opened.invalidation_price,
                target_price=opened.target_price,
                expected_hold_trading_days=opened.expected_hold_trading_days,
                execution_snapshot=None,
                option_contract=option_contract,
                reason_codes=(
                    *opened.reason_codes,
                    trigger,
                    "next_session_or_later_exit",
                ),
            )
        )
    return tuple(sorted(exits, key=lambda intent: (intent.instrument, intent.symbol)))


def _order_matches_intent(order: dict[str, Any], intent: LiveExecutionIntent) -> bool:
    if str(order.get("symbol", "")).upper() != intent.symbol:
        return False
    if intent.instrument == "equity":
        return True
    contract = intent.option_contract
    order_contract_id = str(order.get("contract_id", ""))
    intent_contract_id = str(contract.get("contract_id", ""))
    if order_contract_id and intent_contract_id:
        return order_contract_id == intent_contract_id
    return (
        str(order.get("expiry", "")) == str(contract.get("expiry", ""))
        and str(order.get("option_type", "")) == str(contract.get("option_type", ""))
        and float(order.get("strike", 0.0)) == float(contract.get("strike", 0.0))
    )


def _day_trade_blocker(
    account: AccountSnapshot,
    intent: LiveExecutionIntent,
    market_date: str,
) -> str:
    orders = (
        account.recent_equity_orders
        if intent.instrument == "equity"
        else account.recent_option_orders
    )
    opposite_side = "sell" if intent.side == "buy" else "buy"
    active_statuses = {
        "filled",
        "partially_filled",
        "queued",
        "pending",
        "open",
        "confirmed",
    }
    for order in orders:
        status = str(order.get("status", "")).lower()
        side = str(order.get("side", "")).lower()
        if str(order.get("market_date", "")) != market_date:
            continue
        if side != opposite_side or status not in active_statuses:
            continue
        if _order_matches_intent(order, intent):
            return "broker_history_same_session_round_trip_blocked"
    return ""


def _order_history_blocker(
    repository_root: Path,
    account: AccountSnapshot,
    market_date: str,
    options_execution_enabled: bool,
) -> str:
    if not market_date:
        return "market_date_missing_for_order_history_reconciliation"
    if not account.equity_order_history_complete:
        return "equity_order_history_incomplete"
    records = read_ledger(ledger_path(repository_root))
    unresolved_by_intent: dict[str, bool] = {}
    local_order_ids: set[str] = set()
    observed_status_by_order_id: dict[str, str] = {}
    placed_records: list[dict[str, Any]] = []
    local_option_evidence = bool(account.option_positions)
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = str(record.get("event_type", ""))
        intent_id = str(payload.get("intent_id", ""))
        if intent_id and event_type in {
            "live_order_submission_reserved",
            "live_order_submission_started",
            "live_order_submission_ambiguous",
        }:
            unresolved_by_intent[intent_id] = True
        elif intent_id and event_type == "live_order_result":
            unresolved_by_intent[intent_id] = False
        order_id = str(payload.get("order_id", ""))
        if event_type == "live_order_status_observed" and order_id:
            observed_status_by_order_id[order_id] = str(
                payload.get("status", "")
            ).lower()
        if event_type != "live_order_result" or payload.get("placed") is not True:
            if event_type == "live_position_owner_liquidation_observed":
                evidence_order_ids = payload.get("evidence_broker_order_ids", [])
                if isinstance(evidence_order_ids, list):
                    local_order_ids.update(
                        str(value) for value in evidence_order_ids if str(value).strip()
                    )
            continue
        placed_records.append(payload)
        if order_id:
            local_order_ids.add(order_id)
        raw_intent = payload.get("intent")
        if isinstance(raw_intent, dict) and raw_intent.get("instrument") == "option":
            local_option_evidence = True
    if (
        options_execution_enabled or local_option_evidence
    ) and not account.option_order_history_complete:
        return "option_order_history_incomplete"
    broker_orders = (*account.recent_equity_orders, *account.recent_option_orders)
    broker_by_order_id: dict[str, dict[str, Any]] = {}
    for order in broker_orders:
        order_id = str(order.get("order_id", order.get("id", "")))
        if not order_id:
            return "broker_history_order_missing_order_id"
        if not str(order.get("market_date", "")):
            return "broker_history_order_missing_market_date"
        status = str(order.get("status", "")).lower()
        if status not in RECOGNIZED_ORDER_STATUSES:
            return "broker_history_order_status_unrecognized"
        if order_id in broker_by_order_id:
            return "broker_history_duplicate_order_id"
        broker_by_order_id[order_id] = order
    for payload in placed_records:
        raw_intent = payload.get("intent")
        if not isinstance(raw_intent, dict):
            return "local_live_order_missing_typed_intent"
        try:
            intent = live_execution_intent_from_dict(raw_intent)
        except (TypeError, ValueError):
            return "local_live_order_invalid_typed_intent"
        local_order_id = str(payload.get("order_id", ""))
        if not local_order_id:
            return "local_live_order_missing_broker_order_id"
        broker_orders = (
            account.recent_equity_orders
            if intent.instrument == "equity"
            else account.recent_option_orders
        )
        matched = next(
            (
                order
                for order in broker_orders
                if local_order_id == str(order.get("order_id", order.get("id", "")))
            ),
            None,
        )
        if matched is not None:
            continue
        latest_status = observed_status_by_order_id.get(
            local_order_id,
            str(payload.get("status", "")).lower(),
        )
        if latest_status not in TERMINAL_ORDER_STATUSES:
            return "broker_history_missing_nonterminal_local_live_order"
    if any(unresolved_by_intent.values()):
        return "local_live_order_submission_unresolved"
    orphan_order_ids = sorted(set(broker_by_order_id) - local_order_ids)
    if orphan_order_ids:
        return "broker_history_contains_unattributed_order"
    return ""


def dumbmoney_kill_path(repository_root: Path) -> Path:
    return artifact_root(repository_root) / DUMBMONEY_KILL_FILENAME


def _active_attributed_orders(
    repository_root: Path,
    account: AccountSnapshot,
) -> tuple[tuple[str, str], ...]:
    instruments_by_order_id: dict[str, str] = {}
    for record in read_ledger(ledger_path(repository_root)):
        if record.get("event_type") not in {
            "live_order_result",
            "live_order_submission_ambiguous",
        }:
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        is_definite_placement = (
            record.get("event_type") == "live_order_result"
            and payload.get("placed") is True
        )
        is_attributed_ambiguous_dispatch = (
            record.get("event_type") == "live_order_submission_ambiguous"
            and payload.get("in_flight_authority_revoked") is True
        )
        if not (is_definite_placement or is_attributed_ambiguous_dispatch):
            continue
        order_id = str(payload.get("order_id", "")).strip()
        instrument = str(payload.get("instrument", "")).strip()
        if order_id and instrument in {"equity", "option"}:
            instruments_by_order_id[order_id] = instrument
    active: list[tuple[str, str]] = []
    for instrument, orders in (
        ("equity", account.recent_equity_orders),
        ("option", account.recent_option_orders),
    ):
        for order in orders:
            order_id = str(order.get("order_id", "")).strip()
            status = str(order.get("status", "")).strip().lower()
            if (
                order_id
                and status in ACTIVE_ORDER_STATUSES
                and instruments_by_order_id.get(order_id) == instrument
            ):
                active.append((instrument, order_id))
    return tuple(sorted(set(active)))


def _run_cancel_only_degraded(
    repository_root: Path,
    gateway: RobinhoodAgenticGateway,
    account: AccountSnapshot,
    now_utc: datetime,
    reason: str,
    request_cancellation: bool,
    *,
    effective_kill_active: bool | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    current_account = account
    targets = _active_attributed_orders(repository_root, current_account)
    if request_cancellation:
        for instrument, order_id in targets:
            append_record(
                ledger_path(repository_root),
                "dumbmoney_cancel_started",
                {
                    "instrument": instrument,
                    "order_id": order_id,
                    "reason": reason,
                    "new_exposure_allowed": False,
                },
            )
            outcome: dict[str, Any]
            try:
                cancellation = gateway.cancel_order(instrument, order_id)
            except RobinhoodCancellationAmbiguousError as error:
                outcome = {
                    "instrument": instrument,
                    "order_id": order_id,
                    "cancel_requested": None,
                    "status": "ambiguous_cancel_history_poll_required",
                    "error": str(error),
                }
                append_record(
                    ledger_path(repository_root),
                    "dumbmoney_cancel_ambiguous",
                    outcome,
                )
            except RobinhoodGatewayError as error:
                outcome = {
                    "instrument": instrument,
                    "order_id": order_id,
                    "cancel_requested": False,
                    "status": "cancel_gateway_blocked",
                    "error": str(error),
                }
                append_record(
                    ledger_path(repository_root),
                    "dumbmoney_cancel_blocked",
                    outcome,
                )
            else:
                outcome = {
                    "instrument": instrument,
                    "order_id": order_id,
                    **cancellation.to_dict(),
                }
                append_record(
                    ledger_path(repository_root),
                    "dumbmoney_cancel_result",
                    outcome,
                )
            attempts.append(outcome)
    poll_count = 0
    poll_errors: list[str] = []
    for _ in range(DUMBMONEY_HISTORY_POLL_LIMIT if request_cancellation else 1):
        poll_count += 1
        try:
            current_account = gateway.get_account_snapshot()
        except RobinhoodGatewayError as error:
            poll_errors.append(f"{type(error).__name__}: {error}")
            continue
        _reconcile_live_order_statuses(repository_root, current_account)
        if not _active_attributed_orders(repository_root, current_account):
            break
    unresolved = _active_attributed_orders(repository_root, current_account)
    return {
        "cycle_status": "cancel_only_degraded",
        "authority_state": "CANCEL_ONLY_DEGRADED",
        "cancel_only_reason": reason,
        "new_exposure_allowed": False,
        "kill_active": (
            dumbmoney_kill_path(repository_root).is_file()
            if effective_kill_active is None
            else (
                effective_kill_active or dumbmoney_kill_path(repository_root).is_file()
            )
        ),
        "cancel_requested": request_cancellation,
        "cancel_target_count": len(targets),
        "cancel_attempts": attempts,
        "history_poll_count": poll_count,
        "history_poll_errors": poll_errors,
        "unresolved_attributed_orders": [
            {"instrument": instrument, "order_id": order_id}
            for instrument, order_id in unresolved
        ],
        "account": current_account.to_dict(),
        "orders": [],
    }


def _required_exact_number(
    order: dict[str, Any],
    fields: tuple[str, ...],
    expected: float,
) -> bool:
    values = [order[field] for field in fields if field in order]
    if not values:
        return False
    try:
        return len({float(value) for value in values}) == 1 and math.isclose(
            float(values[0]),
            expected,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    except (TypeError, ValueError):
        return False


def _exact_ambiguous_history_match(
    order: dict[str, Any],
    intent: LiveExecutionIntent,
    market_date: str,
    attempted_at: datetime,
) -> bool:
    if (
        str(order.get("symbol", "")).upper() != intent.symbol
        or str(order.get("side", "")).lower() != intent.side
        or str(order.get("market_date", "")) != market_date
    ):
        return False
    try:
        submitted_at = datetime.fromisoformat(
            str(order.get("submitted_at", "")).replace("Z", "+00:00")
        )
    except ValueError:
        return False
    if (
        submitted_at.tzinfo is None
        or abs((submitted_at - attempted_at).total_seconds()) > 300
    ):
        return False
    if str(order.get("order_type", "")).lower() != intent.order_type:
        return False
    if str(order.get("time_in_force", "")).lower() != intent.time_in_force:
        return False
    if intent.order_type != "market" and not _required_exact_number(
        order,
        ("limit", "limit_price"),
        intent.limit_price,
    ):
        return False
    if intent.quantity > 0.0:
        if not _required_exact_number(
            order,
            ("asset_quantity", "quantity", "share_quantity", "shares"),
            intent.quantity,
        ):
            return False
    elif not _required_exact_number(
        order,
        ("amount", "dollar_amount", "notional", "notional_usd"),
        intent.notional_usd,
    ):
        return False
    return _order_matches_intent(order, intent)


def _witnessed_daily_loss_cents(
    repository_root: Path,
    account: AccountSnapshot,
    market_date: str,
) -> int:
    """Derive a conservative daily loss from complete broker history + local lineage.

    A filled order without explicit broker fee evidence, local attribution, or
    enough prior long inventory makes the baseline unknowable and therefore
    blocks new exposure.
    """
    if (
        not market_date
        or not account.equity_order_history_complete
        or not account.option_order_history_complete
    ):
        raise DumbMoneyAuthorityError(
            "Complete broker order history is required for daily-loss authority"
        )
    intents_by_order_id: dict[str, LiveExecutionIntent] = {}
    for record in read_ledger(ledger_path(repository_root)):
        if record.get("event_type") != "live_order_result":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("placed") is not True:
            continue
        order_id = str(payload.get("order_id", "")).strip()
        raw_intent = payload.get("intent")
        if not order_id or not isinstance(raw_intent, dict):
            raise DumbMoneyAuthorityError(
                "Placed local order lacks broker identity or typed intent"
            )
        try:
            intents_by_order_id[order_id] = live_execution_intent_from_dict(raw_intent)
        except (TypeError, ValueError) as error:
            raise DumbMoneyAuthorityError(
                "Placed local order has an invalid typed intent"
            ) from error
    broker_orders = [
        *account.recent_equity_orders,
        *account.recent_option_orders,
    ]
    try:
        broker_orders.sort(
            key=lambda order: (
                datetime.fromisoformat(
                    str(order.get("submitted_at", "")).replace("Z", "+00:00")
                ),
                str(order.get("order_id", "")),
            )
        )
    except ValueError as error:
        raise DumbMoneyAuthorityError(
            "Broker order history has an invalid submission timestamp"
        ) from error
    lots: dict[str, list[list[float]]] = {}
    daily_pnl_usd = 0.0
    for order in broker_orders:
        status = str(order.get("status", "")).lower()
        if status not in {"filled", "partially_filled"}:
            continue
        order_id = str(order.get("order_id", "")).strip()
        intent = intents_by_order_id.get(order_id)
        if intent is None:
            raise DumbMoneyAuthorityError(
                "Filled broker order is not attributed to a typed local intent"
            )
        if str(
            order.get("side", "")
        ).lower() != intent.side or not _order_matches_intent(order, intent):
            raise DumbMoneyAuthorityError(
                "Broker fill identity conflicts with its typed local intent"
            )
        try:
            quantity = float(order.get("filled_quantity", 0.0))
            average_price = float(order.get("average_fill_price", 0.0))
        except (TypeError, ValueError) as error:
            raise DumbMoneyAuthorityError(
                "Broker fill economics are invalid"
            ) from error
        fee_values = [order[field] for field in ("fees_usd", "fees") if field in order]
        if len(fee_values) != 1:
            raise DumbMoneyAuthorityError(
                "Filled broker order lacks one explicit fee observation"
            )
        try:
            fee_usd = float(fee_values[0])
        except (TypeError, ValueError) as error:
            raise DumbMoneyAuthorityError("Broker fill fee is invalid") from error
        if (
            not math.isfinite(quantity)
            or not math.isfinite(average_price)
            or not math.isfinite(fee_usd)
            or quantity <= 0.0
            or average_price <= 0.0
            or fee_usd < 0.0
        ):
            raise DumbMoneyAuthorityError(
                "Broker fill quantity, price, and fee must be finite and bounded"
            )
        key = _position_key(intent)
        multiplier = 100.0 if intent.instrument == "option" else 1.0
        if intent.side == "buy":
            lots.setdefault(key, []).append([quantity, average_price])
            if str(order.get("market_date", "")) == market_date:
                daily_pnl_usd -= fee_usd
            continue
        remaining = quantity
        realized = -fee_usd
        position_lots = lots.setdefault(key, [])
        while remaining > 1e-9 and position_lots:
            lot_quantity, lot_price = position_lots[0]
            consumed = min(remaining, lot_quantity)
            realized += (average_price - lot_price) * consumed * multiplier
            remaining -= consumed
            lot_quantity -= consumed
            if lot_quantity <= 1e-9:
                position_lots.pop(0)
            else:
                position_lots[0][0] = lot_quantity
        if remaining > 1e-9:
            raise DumbMoneyAuthorityError(
                "Broker sell fill exceeds witnessed long inventory"
            )
        if str(order.get("market_date", "")) == market_date:
            daily_pnl_usd += realized
    if not math.isfinite(daily_pnl_usd):
        raise DumbMoneyAuthorityError("Witnessed daily PnL is not finite")
    unrealized_loss_usd = 0.0
    for position in (*account.equity_positions, *account.option_positions):
        try:
            quantity = float(position.get("quantity", 0.0))
            unrealized_pnl = float(position["unrealized_pnl"])
        except (KeyError, TypeError, ValueError) as error:
            raise DumbMoneyAuthorityError(
                "Nonzero broker position lacks witnessed unrealized PnL"
            ) from error
        if not math.isfinite(quantity) or not math.isfinite(unrealized_pnl):
            raise DumbMoneyAuthorityError(
                "Broker position unrealized PnL evidence is not finite"
            )
        if quantity != 0.0:
            unrealized_loss_usd += max(0.0, -unrealized_pnl)
    realized_loss_cents = max(0, math.ceil(-daily_pnl_usd * 100.0 - 1e-9))
    unrealized_loss_cents = math.ceil(unrealized_loss_usd * 100.0 - 1e-9)
    return realized_loss_cents + unrealized_loss_cents


def _poll_ambiguous_placement_history(
    repository_root: Path,
    gateway: RobinhoodAgenticGateway,
    intent: LiveExecutionIntent,
    market_date: str,
    attempted_at: datetime,
    paper_twin_record_hash: str,
) -> tuple[dict[str, Any] | None, AccountSnapshot | None, int]:
    known_order_ids = {
        str(record.get("payload", {}).get("order_id", ""))
        for record in read_ledger(ledger_path(repository_root))
        if isinstance(record.get("payload"), dict)
        and str(record.get("payload", {}).get("order_id", ""))
    }
    candidates: dict[str, dict[str, Any]] = {}
    latest_account: AccountSnapshot | None = None
    poll_errors: list[str] = []
    poll_count = 0
    for poll_index in range(1, DUMBMONEY_HISTORY_POLL_LIMIT + 1):
        poll_count = poll_index
        try:
            latest_account = gateway.get_account_snapshot()
        except RobinhoodGatewayError as error:
            poll_errors.append(f"{type(error).__name__}: {error}")
            continue
        orders = (
            latest_account.recent_equity_orders
            if intent.instrument == "equity"
            else latest_account.recent_option_orders
        )
        for order in orders:
            order_id = str(order.get("order_id", "")).strip()
            if (
                order_id
                and order_id not in known_order_ids
                and _exact_ambiguous_history_match(
                    order,
                    intent,
                    market_date,
                    attempted_at,
                )
            ):
                candidates[order_id] = order
        append_record(
            ledger_path(repository_root),
            "dumbmoney_ambiguous_history_poll",
            {
                "intent_id": intent.intent_id,
                "poll_index": poll_index,
                "candidate_order_ids": sorted(candidates),
                "candidate_count": len(candidates),
                "history_complete": (
                    latest_account.equity_order_history_complete
                    if intent.instrument == "equity"
                    else latest_account.option_order_history_complete
                ),
            },
        )
    if latest_account is None or len(candidates) != 1:
        if poll_errors:
            append_record(
                ledger_path(repository_root),
                "dumbmoney_ambiguous_history_poll_failed",
                {
                    "intent_id": intent.intent_id,
                    "poll_error_count": len(poll_errors),
                    "errors": poll_errors,
                },
            )
        return None, latest_account, poll_count
    order = next(iter(candidates.values()))
    history_complete = (
        latest_account.equity_order_history_complete
        if intent.instrument == "equity"
        else latest_account.option_order_history_complete
    )
    if not history_complete:
        return None, latest_account, poll_count
    payload = {
        "intent_id": intent.intent_id,
        "instrument": intent.instrument,
        "symbol": intent.symbol,
        "side": intent.side,
        "market_date": market_date,
        "paper_twin_record_hash": paper_twin_record_hash,
        "intent": intent.to_dict(),
        "review_succeeded": True,
        "placed": True,
        "order_id": str(order["order_id"]),
        "status": str(order.get("status", "")).lower(),
        "filled_quantity": _filled_quantity(
            order,
            f"ambiguous_history_order:{order['order_id']}",
        ),
        "average_fill_price": float(order.get("average_fill_price", 0.0)),
        "submitted_at": str(order.get("submitted_at", "")),
        "filled_at": str(order.get("filled_at", "")),
        "warnings": ["automatically_reconciled_from_exact_complete_broker_history"],
        "error": "",
        "observed_tools": ["get_accounts", "get_equity_orders", "get_option_orders"],
        "automatic_history_reconciled": True,
        "placement_retried": False,
    }
    reconciliation_record = append_record(
        ledger_path(repository_root),
        "live_order_result",
        payload,
    )
    return (
        {
            **payload,
            "automatic_history_record_hash": reconciliation_record["record_hash"],
        },
        latest_account,
        poll_count,
    )


def run_live_branch_cycle(
    repository_root: Path,
    gateway: RobinhoodAgenticGateway,
    now_utc: datetime,
    execute_orders: bool,
    *,
    dumbmoney_authority: DumbMoneyAuthorityContext | None = None,
    dumbmoney_controls: DumbMoneyCommandDispatch | None = None,
    dumbmoney_control_refresh: (
        Callable[[datetime], DumbMoneyCommandDispatch] | None
    ) = None,
    dumbmoney_promotion_resolver: PromotionAuthorityResolver | None = None,
    authority_clock: Callable[[], datetime] | None = None,
    live_branch_control: LiveBranchControl | None = None,
) -> dict[str, Any]:
    control = (
        live_branch_control
        if live_branch_control is not None
        else load_live_branch_control()
    )
    if dumbmoney_authority is not None and dumbmoney_controls is not None:
        result = {
            **_base_cycle(now_utc),
            "dumbmoney_authority_enabled": False,
            "dumbmoney_command_feed": dumbmoney_controls.evidence(),
            "cycle_status": "blocked_dumbmoney_control_source_conflict",
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    if dumbmoney_control_refresh is not None and dumbmoney_controls is None:
        result = {
            **_base_cycle(now_utc),
            "dumbmoney_authority_enabled": False,
            "dumbmoney_command_feed": None,
            "cycle_status": "blocked_dumbmoney_control_refresh_without_snapshot",
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    effective_authority = (
        dumbmoney_controls.capital_authority
        if dumbmoney_controls is not None
        else dumbmoney_authority
    )
    dumbmoney_configured = (
        dumbmoney_controls is not None or dumbmoney_authority is not None
    )
    feed_kill_active = (
        dumbmoney_controls.kill_active if dumbmoney_controls is not None else False
    )
    local_kill_active = (
        dumbmoney_configured and dumbmoney_kill_path(repository_root).is_file()
    )
    effective_kill_active = feed_kill_active or local_kill_active
    feed_blocks_new_risk = (
        dumbmoney_controls is not None and not dumbmoney_controls.allow_new_risk
    )
    feed_refresh_missing = (
        execute_orders
        and dumbmoney_controls is not None
        and dumbmoney_controls.allow_new_risk
        and dumbmoney_control_refresh is None
    )
    feed_blocks_new_risk = feed_blocks_new_risk or feed_refresh_missing
    base = {
        **_base_cycle(now_utc),
        "dumbmoney_authority_enabled": effective_authority is not None,
        "dumbmoney_command_feed": (
            dumbmoney_controls.evidence() if dumbmoney_controls is not None else None
        ),
    }
    kill_requested = dumbmoney_configured and (
        effective_kill_active or feed_blocks_new_risk
    )
    if not control.live_branch_enabled and not kill_requested:
        result = {**base, "cycle_status": "disabled_by_owner_control", "orders": []}
        write_latest_cycle(repository_root, result)
        return result
    submission_window_open, market_date, regular_market_open = (
        _robinhood_stock_submission_state(now_utc)
    )
    try:
        account = gateway.get_account_snapshot()
    except RobinhoodConsentRequiredError as error:
        result = {
            **base,
            "cycle_status": "blocked_robinhood_interactive_consent_required",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "error": str(error),
            "operator_remediation": consent_remediation(),
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    except RobinhoodAuthRequiredError as error:
        result = {
            **base,
            "cycle_status": "blocked_robinhood_auth_required",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "error": str(error),
            "operator_remediation": reauth_remediation(),
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    except RobinhoodGatewayError as error:
        result = {
            **base,
            "cycle_status": "blocked_robinhood_account_validation_failed",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "error": str(error),
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    if not account.authenticated:
        result = {
            **base,
            "cycle_status": "blocked_robinhood_account_not_authenticated",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "account": account.to_dict(),
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    if dumbmoney_controls is not None and effective_kill_active:
        degraded = _run_cancel_only_degraded(
            repository_root,
            gateway,
            account,
            now_utc,
            (
                dumbmoney_controls.fail_closed_reason
                or "dumbmoney_command_feed_kill_active"
            ),
            True,
            effective_kill_active=True,
        )
        result = {**base, **degraded}
        write_latest_cycle(repository_root, result)
        return result
    if dumbmoney_controls is not None and feed_blocks_new_risk:
        degraded = _run_cancel_only_degraded(
            repository_root,
            gateway,
            account,
            now_utc,
            (
                "dumbmoney_command_feed_refresh_missing_at_broker_sink"
                if feed_refresh_missing
                else dumbmoney_controls.fail_closed_reason
                or "dumbmoney_command_feed_paused"
            ),
            False,
            effective_kill_active=False,
        )
        result = {**base, **degraded}
        write_latest_cycle(repository_root, result)
        return result
    verified_authority: VerifiedCapitalAuthority | None = None
    if effective_authority is not None:
        try:
            verified_authority = effective_authority.verify(
                now_utc,
                account.account_hash,
            )
            activate_dumbmoney_fence(
                repository_root,
                verified_authority.envelope.envelope_id,
                verified_authority.event_id,
                verified_authority.body_digest,
                verified_authority.envelope.fencing_generation,
                verified_authority.envelope.policy_epoch,
            )
        except (DumbMoneyAuthorityError, LiveBranchLedgerError, ValueError) as error:
            degraded = _run_cancel_only_degraded(
                repository_root,
                gateway,
                account,
                now_utc,
                f"capital_authority_invalid:{error}",
                dumbmoney_kill_path(repository_root).is_file(),
                effective_kill_active=effective_kill_active,
            )
            result = {**base, **degraded}
            write_latest_cycle(repository_root, result)
            return result
    reconciled_orders = _reconcile_live_order_statuses(repository_root, account)
    legacy_twin_observations = _complete_legacy_twin_observations(repository_root)
    owner_liquidation_settlements = _settle_owner_liquidations(
        repository_root,
        account,
    )
    history_blocker = _order_history_blocker(
        repository_root,
        account,
        market_date,
        control.options_execution_enabled,
    )
    if (
        verified_authority is not None
        and dumbmoney_kill_path(repository_root).is_file()
    ):
        degraded = _run_cancel_only_degraded(
            repository_root,
            gateway,
            account,
            now_utc,
            "dumbmoney_kill_active",
            True,
            effective_kill_active=True,
        )
        result = {
            **base,
            **degraded,
            "capital_authority": verified_authority.evidence(),
            "reconciled_order_status_count": len(reconciled_orders),
        }
        write_latest_cycle(repository_root, result)
        return result
    if not execute_orders or not regular_market_open:
        result = {
            **base,
            "cycle_status": (
                "preflight_blocked_order_history"
                if execute_orders is False and history_blocker
                else "preflight_complete"
                if execute_orders is False
                else "market_closed_monitoring_blocked_order_history"
                if history_blocker
                else "market_closed_monitoring_complete"
            ),
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "account": account.to_dict(),
            "stock_execution_enabled": control.stock_execution_enabled,
            "options_execution_enabled": control.options_execution_enabled,
            "reconciled_order_status_count": len(reconciled_orders),
            "order_history_blocker": history_blocker,
            "capital_authority": (
                verified_authority.evidence()
                if verified_authority is not None
                else None
            ),
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    unresolved_submission_present = (
        history_blocker == "local_live_order_submission_unresolved"
    )
    if verified_authority is not None and history_blocker:
        degraded = _run_cancel_only_degraded(
            repository_root,
            gateway,
            account,
            now_utc,
            f"order_history_blocker:{history_blocker}",
            False,
        )
        result = {
            **base,
            **degraded,
            "capital_authority": verified_authority.evidence(),
            "order_history_blocker": history_blocker,
            "reconciled_order_status_count": len(reconciled_orders),
        }
        write_latest_cycle(repository_root, result)
        return result
    if history_blocker and not unresolved_submission_present:
        result = {
            **base,
            "cycle_status": "blocked_order_history_incomplete",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "account": account.to_dict(),
            "stock_execution_enabled": control.stock_execution_enabled,
            "options_execution_enabled": control.options_execution_enabled,
            "reconciled_order_status_count": len(reconciled_orders),
            "blocker": history_blocker,
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    ownership_blocker = _position_ownership_blocker(repository_root, account)
    if ownership_blocker:
        result = {
            **base,
            "cycle_status": "blocked_position_ownership_reconciliation",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "account": account.to_dict(),
            "stock_execution_enabled": control.stock_execution_enabled,
            "options_execution_enabled": control.options_execution_enabled,
            "reconciled_order_status_count": len(reconciled_orders),
            "blocker": ownership_blocker,
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    # CASH ACCOUNT: entries are sized against SETTLED funds only, never raw
    # buying power (which can include unsettled T+1 sale proceeds). Buying
    # exclusively with settled cash makes a system-caused good-faith violation
    # impossible no matter when the owner or an exit intent later sells.
    try:
        settled_funds = estimate_settled_funds(
            account,
            now_utc.astimezone(NEW_YORK).date(),
        )
    except SettlementModelError as error:
        result = {
            **base,
            "cycle_status": "blocked_settlement_model_invalid_broker_data",
            "market_open": regular_market_open,
            "market_date": market_date,
            "regular_market_open": regular_market_open,
            "robinhood_24_hour_submission_window": submission_window_open,
            "account": account.to_dict(),
            "error": str(error),
            "orders": [],
        }
        write_latest_cycle(repository_root, result)
        return result
    entry_cash_usd = settled_funds.spendable_settled_usd
    witnessed_daily_loss_cents: int | None = None
    if verified_authority is not None:
        try:
            witnessed_daily_loss_cents = _witnessed_daily_loss_cents(
                repository_root,
                account,
                market_date,
            )
            entry_cash_usd = authorized_settled_cash_usd(
                verified_authority,
                account,
                settled_funds.spendable_settled_usd,
                witnessed_daily_loss_cents,
            )
        except DumbMoneyAuthorityError as error:
            degraded = _run_cancel_only_degraded(
                repository_root,
                gateway,
                account,
                now_utc,
                f"capital_allocation_blocked:{error}",
                False,
            )
            result = {
                **base,
                **degraded,
                "capital_authority": verified_authority.evidence(),
            }
            write_latest_cycle(repository_root, result)
            return result
    all_exit_intents = _build_exit_intents(
        repository_root,
        account,
        now_utc.astimezone(NEW_YORK).date(),
    )
    try:
        maturity_blockers = research_maturity_blockers(repository_root)
    except LiveSignalError as error:
        maturity_blockers = (f"research_maturity_artifact_invalid:{error}",)
    all_entry_intents = (
        ()
        if maturity_blockers or unresolved_submission_present
        else build_entry_intents(
            repository_root,
            entry_cash_usd,
            now_utc.astimezone(NEW_YORK).date(),
            control.stock_execution_enabled,
            control.options_execution_enabled and regular_market_open,
            frozenset(
                str(position.get("symbol", "")).upper()
                for position in account.equity_positions
                if str(position.get("symbol", ""))
            ),
        )
    )
    exit_intents = tuple(
        intent
        for intent in all_exit_intents
        if intent.instrument == "equity"
        or (regular_market_open and control.options_execution_enabled)
    )
    entry_intents = tuple(
        intent
        for intent in all_entry_intents
        if intent.instrument == "equity" or regular_market_open
    )
    intents = (*exit_intents, *entry_intents)
    intents_to_process = intents[:MAX_ORDER_INTENTS_PER_CYCLE]
    outcomes: list[dict[str, Any]] = []
    for candidate_intent in intents_to_process:
        intent = candidate_intent
        blocked_payload: dict[str, Any]
        promotion_binding: VerifiedPromotionBinding | None = None
        day_trade_blocker = _day_trade_blocker(account, intent, market_date)
        if day_trade_blocker:
            blocked_payload = {
                "intent_id": intent.intent_id,
                "instrument": intent.instrument,
                "symbol": intent.symbol,
                "side": intent.side,
                "market_date": market_date,
                "status": "blocked_no_day_trade",
                "reason": day_trade_blocker,
                "intent": intent.to_dict(),
            }
            append_record(
                ledger_path(repository_root), "day_trade_guard_block", blocked_payload
            )
            outcomes.append(blocked_payload)
            continue
        if intent.instrument == "equity" and intent.side == "buy":
            try:
                execution_snapshot = gateway.get_equity_execution_snapshot(intent)
                intent = prepare_equity_entry_for_execution(
                    intent,
                    execution_snapshot,
                    now_utc,
                    entry_cash_usd,
                )
            except (LiveSignalError, RobinhoodGatewayError) as error:
                blocked_payload = {
                    "intent_id": intent.intent_id,
                    "instrument": intent.instrument,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "market_date": market_date,
                    "status": "blocked_equity_execution_snapshot_invalid",
                    "reason": str(error),
                    "intent": intent.to_dict(),
                }
                append_record(
                    ledger_path(repository_root),
                    "equity_execution_preflight_block",
                    blocked_payload,
                )
                outcomes.append(blocked_payload)
                continue
        if intent.instrument == "option" and intent.side == "buy":
            try:
                validate_option_entry_for_execution(intent, now_utc)
            except LiveSignalError as error:
                blocked_payload = {
                    "intent_id": intent.intent_id,
                    "instrument": intent.instrument,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "market_date": market_date,
                    "status": "blocked_option_execution_snapshot_invalid",
                    "reason": str(error),
                    "intent": intent.to_dict(),
                }
                append_record(
                    ledger_path(repository_root),
                    "option_execution_preflight_block",
                    blocked_payload,
                )
                outcomes.append(blocked_payload)
                continue
        capital_authority_evidence: dict[str, Any] | None = None
        if verified_authority is not None:
            try:
                if intent.side == "buy":
                    if dumbmoney_promotion_resolver is None:
                        raise DumbMoneyAuthorityError(
                            "authenticated DumbMoney promotion resolver is absent"
                        )
                    intent, promotion_binding = (
                        dumbmoney_promotion_resolver.bind_intent(
                            verified_authority,
                            intent,
                            now_utc,
                        )
                    )
                authorize_intent(
                    verified_authority,
                    account,
                    intent,
                    witnessed_daily_loss_cents,
                )
            except DumbMoneyAuthorityError as error:
                blocked_payload = {
                    "intent_id": intent.intent_id,
                    "instrument": intent.instrument,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "market_date": market_date,
                    "status": "blocked_dumbmoney_capital_envelope",
                    "reason": str(error),
                    "intent": intent.to_dict(),
                }
                append_record(
                    ledger_path(repository_root),
                    "dumbmoney_capital_preflight_block",
                    blocked_payload,
                )
                outcomes.append(blocked_payload)
                continue
            capital_authority_evidence = {
                **verified_authority.evidence(),
                "promotion_binding": (
                    promotion_binding.evidence()
                    if promotion_binding is not None
                    else None
                ),
            }
        reserved = reserve_intent(
            repository_root,
            intent.intent_id,
            {
                "instrument": intent.instrument,
                "symbol": intent.symbol,
                "side": intent.side,
                "market_date": market_date,
                "intent": intent.to_dict(),
                "capital_authority": capital_authority_evidence,
            },
        )
        if not reserved:
            outcomes.append(
                {
                    "intent_id": intent.intent_id,
                    "status": "skipped_idempotent_live_order",
                }
            )
            continue
        twin = append_record(
            paper_twin_path(repository_root),
            "paper_twin_staged",
            {
                "intent": intent.to_dict(),
                "market_date": market_date,
                "status": "simulated_pending_live_result",
                "paper_only": True,
                "live_twin": True,
            },
        )
        paper_twin_execution = _append_paper_twin_execution_observation(
            repository_root,
            intent,
            str(twin["record_hash"]),
        )
        pre_submit_guard: Callable[[], datetime] | None = None
        if verified_authority is not None and effective_authority is not None:
            try:
                sink_now = (
                    authority_clock()
                    if authority_clock is not None
                    else datetime.now(timezone.utc)
                )
                sink_authority = effective_authority.verify(
                    sink_now,
                    account.account_hash,
                )
                if sink_authority.event_id != verified_authority.event_id:
                    raise DumbMoneyAuthorityError(
                        "Capital authority changed during the execution cycle"
                    )
                assert_current_dumbmoney_fence(
                    repository_root,
                    sink_authority.envelope.envelope_id,
                    sink_authority.event_id,
                    sink_authority.body_digest,
                    sink_authority.envelope.fencing_generation,
                    sink_authority.envelope.policy_epoch,
                )
                sink_account = gateway.get_account_snapshot()
                if (
                    not sink_account.authenticated
                    or sink_account.account_hash != account.account_hash
                ):
                    raise DumbMoneyAuthorityError(
                        "Broker-sink account attestation changed during execution"
                    )
                sink_daily_loss_cents = _witnessed_daily_loss_cents(
                    repository_root,
                    sink_account,
                    market_date,
                )
                if intent.side == "buy":
                    if (
                        dumbmoney_promotion_resolver is None
                        or promotion_binding is None
                    ):
                        raise DumbMoneyAuthorityError(
                            "authenticated DumbMoney promotion binding is absent"
                        )
                    intent, promotion_binding = (
                        dumbmoney_promotion_resolver.bind_intent(
                            sink_authority,
                            intent,
                            sink_now,
                            expected_binding=promotion_binding,
                        )
                    )
                authorize_intent(
                    sink_authority,
                    sink_account,
                    intent,
                    sink_daily_loss_cents,
                )
                if intent.instrument == "option" and intent.side == "buy":
                    validate_option_entry_for_execution(intent, sink_now)
                account = sink_account
                capital_authority_evidence = {
                    **sink_authority.evidence(),
                    "verified_again_at_broker_sink": True,
                    "verified_at": sink_now.astimezone(timezone.utc).isoformat(),
                    "witnessed_daily_loss_cents": sink_daily_loss_cents,
                    "promotion_binding": (
                        promotion_binding.evidence()
                        if promotion_binding is not None
                        else None
                    ),
                }

                def final_broker_sink_guard(
                    *,
                    expected_event_id: str = sink_authority.event_id,
                    expected_envelope_id: str = (sink_authority.envelope.envelope_id),
                    expected_body_digest: str = sink_authority.body_digest,
                    expected_generation: int = (
                        sink_authority.envelope.fencing_generation
                    ),
                    expected_policy_epoch: int = (sink_authority.envelope.policy_epoch),
                    expected_account_hash: str = sink_account.account_hash,
                    guarded_intent: LiveExecutionIntent = intent,
                    expected_promotion_binding: (
                        VerifiedPromotionBinding | None
                    ) = promotion_binding,
                ) -> datetime:
                    guard_now = (
                        authority_clock()
                        if authority_clock is not None
                        else datetime.now(timezone.utc)
                    )
                    if dumbmoney_kill_path(repository_root).is_file():
                        raise RobinhoodGatewayError(
                            "Local DumbMoney kill became active before broker submission"
                        )
                    if dumbmoney_controls is not None and (
                        dumbmoney_controls.kill_active
                        or not dumbmoney_controls.allow_new_risk
                    ):
                        raise RobinhoodGatewayError(
                            "DumbMoney command controls deny broker submission"
                        )
                    try:
                        refreshed_context = effective_authority
                        if dumbmoney_control_refresh is not None:
                            try:
                                refreshed_controls = dumbmoney_control_refresh(
                                    guard_now
                                )
                            except Exception as error:
                                raise DumbMoneyAuthorityError(
                                    "DumbMoney command refresh failed closed: "
                                    f"{type(error).__name__}"
                                ) from error
                            if not isinstance(
                                refreshed_controls,
                                DumbMoneyCommandDispatch,
                            ):
                                raise DumbMoneyAuthorityError(
                                    "DumbMoney command refresh returned an "
                                    "unsupported control snapshot"
                                )
                            if (
                                refreshed_controls.kill_active
                                or not refreshed_controls.allow_new_risk
                                or refreshed_controls.capital_authority is None
                            ):
                                raise DumbMoneyAuthorityError(
                                    "Refreshed DumbMoney command controls deny "
                                    "broker submission"
                                )
                            refreshed_context = refreshed_controls.capital_authority
                        if refreshed_context is None:
                            raise DumbMoneyAuthorityError(
                                "Final DumbMoney capital authority is absent"
                            )
                        guarded_authority = refreshed_context.verify(
                            guard_now,
                            expected_account_hash,
                        )
                        guarded_identity = (
                            guarded_authority.envelope.envelope_id,
                            guarded_authority.event_id,
                            guarded_authority.body_digest,
                            guarded_authority.envelope.fencing_generation,
                            guarded_authority.envelope.policy_epoch,
                        )
                        expected_identity = (
                            expected_envelope_id,
                            expected_event_id,
                            expected_body_digest,
                            expected_generation,
                            expected_policy_epoch,
                        )
                        if guarded_identity != expected_identity:
                            raise DumbMoneyAuthorityError(
                                "Capital authority changed before broker submission"
                            )
                        assert_current_dumbmoney_fence(
                            repository_root,
                            guarded_authority.envelope.envelope_id,
                            guarded_authority.event_id,
                            guarded_authority.body_digest,
                            guarded_authority.envelope.fencing_generation,
                            guarded_authority.envelope.policy_epoch,
                        )
                        guarded_binding = expected_promotion_binding
                        if guarded_intent.side == "buy":
                            if (
                                dumbmoney_promotion_resolver is None
                                or expected_promotion_binding is None
                            ):
                                raise DumbMoneyAuthorityError(
                                    "Final authenticated promotion binding is absent"
                                )
                            _, guarded_binding = (
                                dumbmoney_promotion_resolver.bind_intent(
                                    guarded_authority,
                                    guarded_intent,
                                    guard_now,
                                    expected_binding=expected_promotion_binding,
                                )
                            )
                        authorize_intent(
                            guarded_authority,
                            sink_account,
                            guarded_intent,
                            sink_daily_loss_cents,
                        )
                        if (
                            guarded_intent.instrument == "option"
                            and guarded_intent.side == "buy"
                        ):
                            validate_option_entry_for_execution(
                                guarded_intent,
                                guard_now,
                            )
                        capital_deadline = datetime.fromisoformat(
                            guarded_authority.envelope.expires_at.replace(
                                "Z",
                                "+00:00",
                            )
                        )
                        if guarded_binding is None:
                            return capital_deadline
                        promotion_deadline = datetime.fromisoformat(
                            guarded_binding.expires_at.replace("Z", "+00:00")
                        )
                        return min(capital_deadline, promotion_deadline)
                    except (
                        DumbMoneyAuthorityError,
                        LiveBranchLedgerError,
                        LiveSignalError,
                    ) as error:
                        raise RobinhoodGatewayError(
                            "Final DumbMoney broker-sink guard denied submission: "
                            f"{error}"
                        ) from error

                pre_submit_guard = final_broker_sink_guard
            except (
                DumbMoneyAuthorityError,
                LiveBranchLedgerError,
                LiveSignalError,
                RobinhoodGatewayError,
            ) as error:
                blocked_payload = {
                    "intent_id": intent.intent_id,
                    "instrument": intent.instrument,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "market_date": market_date,
                    "paper_twin_record_hash": twin["record_hash"],
                    "paper_twin_execution_record_hash": paper_twin_execution[
                        "record_hash"
                    ],
                    "intent": intent.to_dict(),
                    "capital_authority": capital_authority_evidence,
                    "review_succeeded": False,
                    "placed": False,
                    "order_id": "",
                    "status": "blocked_dumbmoney_broker_sink_authority",
                    "warnings": [],
                    "error": str(error),
                    "observed_tools": [],
                }
                live_record = append_record(
                    ledger_path(repository_root),
                    "live_order_result",
                    blocked_payload,
                )
                _append_paper_twin_outcome(
                    repository_root,
                    intent.intent_id,
                    str(twin["record_hash"]),
                    str(live_record["record_hash"]),
                    "blocked_dumbmoney_broker_sink_authority",
                    False,
                    None,
                    None,
                )
                outcomes.append(blocked_payload)
                continue
        append_record(
            ledger_path(repository_root),
            "live_order_submission_started",
            {
                "intent_id": intent.intent_id,
                "instrument": intent.instrument,
                "symbol": intent.symbol,
                "side": intent.side,
                "market_date": market_date,
                "paper_twin_record_hash": twin["record_hash"],
                "paper_twin_execution_record_hash": paper_twin_execution["record_hash"],
                "intent": intent.to_dict(),
                "capital_authority": capital_authority_evidence,
            },
        )
        if pre_submit_guard is not None:
            append_record(
                ledger_path(repository_root),
                "dumbmoney_order_dispatching",
                {
                    "intent_id": intent.intent_id,
                    "instrument": intent.instrument,
                    "symbol": intent.symbol,
                    "market_date": market_date,
                    "status": "DISPATCHING",
                    "external_write_boundary": (
                        "single_at_most_once_deterministic_robinhood_place_call"
                    ),
                    "placement_retries_allowed": 0,
                    "capital_authority": capital_authority_evidence,
                },
            )
        try:
            if pre_submit_guard is None:
                order_result = gateway.place_order(
                    intent,
                    str(twin["record_hash"]),
                )
            else:
                order_result = gateway.place_order(
                    intent,
                    str(twin["record_hash"]),
                    pre_submit_guard=pre_submit_guard,
                )
            in_flight_revocation_error = ""
            if pre_submit_guard is not None:
                try:
                    pre_submit_guard()
                except RobinhoodGatewayError as error:
                    in_flight_revocation_error = str(error)
            if in_flight_revocation_error:
                ambiguous_payload = {
                    "intent_id": intent.intent_id,
                    "instrument": intent.instrument,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "market_date": market_date,
                    "paper_twin_record_hash": twin["record_hash"],
                    "paper_twin_execution_record_hash": paper_twin_execution[
                        "record_hash"
                    ],
                    "intent": intent.to_dict(),
                    "review_succeeded": order_result.review_succeeded,
                    "placed": None,
                    "order_id": order_result.order_id,
                    "status": "ambiguous_in_flight_authority_revoked",
                    "warnings": list(order_result.warnings),
                    "error": in_flight_revocation_error,
                    "observed_tools": list(order_result.observed_tools),
                    "capital_authority": capital_authority_evidence,
                    "placement_retried": False,
                    "in_flight_authority_revoked": True,
                    "broker_result_before_revocation_detection": (
                        order_result.to_dict()
                    ),
                }
                ambiguous_record = append_record(
                    ledger_path(repository_root),
                    "live_order_submission_ambiguous",
                    ambiguous_payload,
                )
                cancel_reconciliation: dict[str, Any]
                try:
                    revocation_account = gateway.get_account_snapshot()
                except RobinhoodGatewayError as error:
                    cancel_reconciliation = {
                        "cycle_status": "cancel_only_degraded",
                        "authority_state": "CANCEL_ONLY_DEGRADED",
                        "cancel_only_reason": (
                            "in_flight_authority_revoked_account_poll_failed"
                        ),
                        "new_exposure_allowed": False,
                        "kill_active": True,
                        "cancel_requested": False,
                        "history_poll_errors": [str(error)],
                        "orders": [],
                    }
                else:
                    cancel_reconciliation = _run_cancel_only_degraded(
                        repository_root,
                        gateway,
                        revocation_account,
                        datetime.now(timezone.utc),
                        "in_flight_authority_revoked",
                        True,
                        effective_kill_active=True,
                    )
                    account = AccountSnapshot(**cancel_reconciliation["account"])
                _append_paper_twin_outcome(
                    repository_root,
                    intent.intent_id,
                    str(twin["record_hash"]),
                    str(ambiguous_record["record_hash"]),
                    "ambiguous_in_flight_authority_revoked",
                    None,
                    None,
                    None,
                )
                outcomes.append(
                    {
                        **ambiguous_payload,
                        "cancel_reconciliation": cancel_reconciliation,
                    }
                )
                continue
        except RobinhoodPlacementAmbiguousError as error:
            ambiguous_payload = {
                "intent_id": intent.intent_id,
                "instrument": intent.instrument,
                "symbol": intent.symbol,
                "side": intent.side,
                "market_date": market_date,
                "paper_twin_record_hash": twin["record_hash"],
                "paper_twin_execution_record_hash": paper_twin_execution["record_hash"],
                "intent": intent.to_dict(),
                "review_succeeded": False,
                "placed": None,
                "order_id": "",
                "status": "ambiguous_submission_manual_reconciliation_required",
                "warnings": [],
                "error": str(error),
                "observed_tools": [],
                "capital_authority": capital_authority_evidence,
                "placement_retried": False,
            }
            ambiguous_record = append_record(
                ledger_path(repository_root),
                "live_order_submission_ambiguous",
                ambiguous_payload,
            )
            append_record(
                paper_twin_path(repository_root),
                "paper_twin_linked",
                {
                    "intent_id": intent.intent_id,
                    "live_record_hash": ambiguous_record["record_hash"],
                    "live_order_placed": None,
                    "live_order_status": "ambiguous_submission_manual_reconciliation_required",
                    "paper_only": True,
                    "live_twin": True,
                },
            )
            _append_paper_twin_outcome(
                repository_root,
                intent.intent_id,
                str(twin["record_hash"]),
                str(ambiguous_record["record_hash"]),
                "ambiguous_submission_manual_reconciliation_required",
                None,
                None,
                None,
            )
            reconciled_payload: dict[str, Any] | None = None
            history_poll_count = 0
            if verified_authority is not None:
                reconciled_payload, polled_account, history_poll_count = (
                    _poll_ambiguous_placement_history(
                        repository_root,
                        gateway,
                        intent,
                        market_date,
                        sink_now,
                        str(twin["record_hash"]),
                    )
                )
                if polled_account is not None:
                    account = polled_account
            if reconciled_payload is None:
                outcomes.append(
                    {
                        **ambiguous_payload,
                        "automatic_history_poll_count": history_poll_count,
                        "authority_state": (
                            "CANCEL_ONLY_DEGRADED"
                            if verified_authority is not None
                            else "LEGACY_MANUAL_RECONCILIATION"
                        ),
                    }
                )
            else:
                _append_paper_twin_outcome(
                    repository_root,
                    intent.intent_id,
                    str(twin["record_hash"]),
                    str(reconciled_payload["automatic_history_record_hash"]),
                    str(reconciled_payload["status"]),
                    True,
                    float(reconciled_payload["filled_quantity"]),
                    float(reconciled_payload["average_fill_price"]),
                )
                outcomes.append(reconciled_payload)
            continue
        except RobinhoodGatewayError as error:
            blocked_payload = {
                "intent_id": intent.intent_id,
                "instrument": intent.instrument,
                "symbol": intent.symbol,
                "side": intent.side,
                "market_date": market_date,
                "paper_twin_record_hash": twin["record_hash"],
                "paper_twin_execution_record_hash": paper_twin_execution["record_hash"],
                "intent": intent.to_dict(),
                "review_succeeded": False,
                "placed": False,
                "order_id": "",
                "status": "blocked_robinhood_order_gateway_failed",
                "warnings": [],
                "error": str(error),
                "observed_tools": [],
            }
            live_record = append_record(
                ledger_path(repository_root),
                "live_order_result",
                blocked_payload,
            )
            append_record(
                paper_twin_path(repository_root),
                "paper_twin_linked",
                {
                    "intent_id": intent.intent_id,
                    "live_record_hash": live_record["record_hash"],
                    "live_order_placed": False,
                    "live_order_status": "blocked_robinhood_order_gateway_failed",
                    "paper_only": True,
                    "live_twin": True,
                },
            )
            _append_paper_twin_outcome(
                repository_root,
                intent.intent_id,
                str(twin["record_hash"]),
                str(live_record["record_hash"]),
                "blocked_robinhood_order_gateway_failed",
                False,
                None,
                None,
            )
            outcomes.append(blocked_payload)
            continue
        live_payload = {
            "intent_id": intent.intent_id,
            "instrument": intent.instrument,
            "symbol": intent.symbol,
            "side": intent.side,
            "market_date": market_date,
            "paper_twin_record_hash": twin["record_hash"],
            "paper_twin_execution_record_hash": paper_twin_execution["record_hash"],
            "intent": intent.to_dict(),
            **order_result.to_dict(),
        }
        live_record = append_record(
            ledger_path(repository_root), "live_order_result", live_payload
        )
        append_record(
            paper_twin_path(repository_root),
            "paper_twin_linked",
            {
                "intent_id": intent.intent_id,
                "live_record_hash": live_record["record_hash"],
                "live_order_placed": order_result.placed,
                "live_order_status": order_result.status,
                "paper_only": True,
                "live_twin": True,
            },
        )
        _append_paper_twin_outcome(
            repository_root,
            intent.intent_id,
            str(twin["record_hash"]),
            str(live_record["record_hash"]),
            order_result.status,
            order_result.placed,
            order_result.filled_quantity,
            order_result.average_fill_price,
        )
        outcomes.append(live_payload)
    blocked_order_count = sum(
        str(outcome.get("status", "")).startswith(("blocked_", "ambiguous_"))
        for outcome in outcomes
    )
    dumbmoney_cancel_only = verified_authority is not None and any(
        outcome.get("authority_state") == "CANCEL_ONLY_DEGRADED"
        or outcome.get("status") == "ambiguous_in_flight_authority_revoked"
        for outcome in outcomes
    )
    result = {
        **base,
        "cycle_status": (
            "cancel_only_degraded"
            if dumbmoney_cancel_only
            else "complete_exits_only_unresolved_submission_entries_blocked"
            if unresolved_submission_present and exit_intents
            else "blocked_unresolved_submission_no_exit_intents"
            if unresolved_submission_present
            else "complete_with_blocked_orders"
            if blocked_order_count
            else "complete_research_entries_blocked"
            if maturity_blockers
            else "complete"
        ),
        "market_open": regular_market_open,
        "market_date": market_date,
        "regular_market_open": regular_market_open,
        "robinhood_24_hour_submission_window": submission_window_open,
        "account": account.to_dict(),
        "stock_execution_enabled": control.stock_execution_enabled,
        "options_execution_enabled": control.options_execution_enabled,
        "use_full_available_balance": control.use_full_available_balance,
        "settled_funds": settled_funds.to_dict(),
        "dumbmoney_authorized_entry_cash_usd": (
            entry_cash_usd if verified_authority is not None else None
        ),
        "witnessed_daily_loss_cents": witnessed_daily_loss_cents,
        "capital_authority": (
            verified_authority.evidence() if verified_authority is not None else None
        ),
        "authority_state": (
            "CANCEL_ONLY_DEGRADED"
            if dumbmoney_cancel_only
            else "ACTIVE"
            if verified_authority is not None
            else "LEGACY_DISABLED"
        ),
        "reconciled_order_status_count": len(reconciled_orders),
        "legacy_twin_observation_count": len(legacy_twin_observations),
        "owner_liquidation_settlement_count": len(owner_liquidation_settlements),
        "research_entry_gate_blockers": list(maturity_blockers),
        "research_entries_enabled": (
            not maturity_blockers and not unresolved_submission_present
        ),
        "order_history_blocker": history_blocker,
        "blocked_order_count": blocked_order_count,
        "candidate_intent_count": len(intents),
        "processed_intent_count": len(intents_to_process),
        "deferred_intent_count": len(intents) - len(intents_to_process),
        "max_order_intents_per_cycle": MAX_ORDER_INTENTS_PER_CYCLE,
        "exit_intent_count": len(exit_intents),
        "entry_intent_count": len(entry_intents),
        "orders": outcomes,
    }
    write_latest_cycle(repository_root, result)
    return result


def default_gateway() -> RobinhoodAgenticGateway:
    return RobinhoodAgenticGateway(
        subprocess.run,
        60,
        write_timeout_seconds=30,
    )
