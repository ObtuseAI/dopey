from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

import pytest

from dopey_dashboard.live_branch_state import build_live_branch_state
from dopey_equity_swing.leveraged_etf import (
    LEVERAGED_ETF_CATALOG,
    build_leveraged_etf_swing_plans,
    validate_leveraged_etf_catalog,
)
from dopey_live.control import (
    CONTROL_CONFIRMATION,
    LiveBranchControlError,
    load_live_branch_control,
    set_live_branch_enabled,
    set_options_execution_enabled,
)
from dopey_live.ledger import (
    LiveBranchLedgerError,
    OPERATOR_LOCK_RECOVERY_CONFIRMATION,
    OPERATOR_RECONCILIATION_CONFIRMATION,
    append_record,
    intent_already_submitted,
    ledger_path,
    paper_twin_path,
    read_ledger,
    reconcile_submission_after_operator_verification,
    recover_stale_ledger_lock_after_operator_verification,
    reserve_intent,
    write_latest_cycle,
)
from dopey_live.models import (
    EQUITY_SNAPSHOT_SOURCE,
    AccountSnapshot,
    EquityExecutionSnapshot,
    EquityQuoteSnapshot,
    LiveExecutionIntent,
)
from dopey_live.robinhood_gateway import (
    DISABLED_CODEX_FEATURES,
    McpToolCallEvidence,
    RobinhoodGatewayError,
    RobinhoodPlacementAmbiguousError,
    _attest_account_scope,
    _attest_equity_execution_snapshot,
    _attest_order_history_results,
    _attest_order_call,
    _canonical_raw_broker_item,
    _codex_exec_command,
    _gateway_order_result,
    _mcp_transcript,
    _validated_equity_position,
    _validated_order,
)
from dopey_live.service import (
    _build_exit_intents,
    _day_trade_blocker,
    _open_live_positions,
    _order_history_blocker,
    _position_ownership_blocker,
    _reconcile_live_order_statuses,
    _robinhood_stock_submission_state,
    run_live_branch_cycle,
)
from dopey_live.signals import (
    LiveSignalError,
    MAX_EQUITY_QUOTE_AGE_SECONDS,
    MAX_STOCK_ENTRY_GROSS_ALLOCATION_FRACTION,
    MAX_STOCK_RISK_PER_POSITION_FRACTION,
    MAX_STOCK_SINGLE_NAME_ALLOCATION_FRACTION,
    _calibration_source_hashes,
    _canonical_summary_hash,
    _champion_source_hashes,
    _option_quote_matches_market_session,
    _thesis_has_complete_earnings_evidence,
    _reproducibility_hash,
    _stable_summary_hash,
    build_entry_intents,
    prepare_equity_entry_for_execution,
    research_maturity_blockers,
)
from dopey_validation.live_pivot_release_gate import _live_ledger_evidence
from operator_tools import operator_live_branch


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_research_maturity(path: Path, ready: bool) -> None:
    observed_at = datetime.now(timezone.utc).isoformat()
    champion_path = (
        path
        / "artifacts"
        / "dopey"
        / "champion_hardening"
        / "public_champion_hardening_gate_v1_summary.json"
    )
    champion: dict[str, object] = {
        "artifact_type": "public_champion_hardening_gate_v1_summary",
        "public_champion_hardening_gate_version": (
            "dopey-public-champion-hardening-gate-v1"
        ),
        "hardened_champion_count": 1 if ready else 0,
        "generated_utc": observed_at,
        "source_artifact_hashes": _champion_source_hashes(champion_path),
    }
    champion["summary_hash"] = _stable_summary_hash(champion)
    nightly: dict[str, object] = {
        "artifact_type": "nightly_effectiveness_report",
        "finished_at_utc": observed_at,
        "verdict": "all_green" if ready else "inconclusive_fixture",
        "suite_green": ready,
        "stack_stability": {"green": ready},
        "fitness_determinism": {"deterministic": ready},
    }
    nightly["summary_hash"] = _stable_summary_hash(nightly)
    calibration_path = (
        path
        / "artifacts"
        / "dopey"
        / "vnext"
        / "cross_sectional_operational"
        / "calibration_summary.json"
    )
    calibration: dict[str, object] = {
        "artifact_type": "vnext_probability_calibration_summary",
        "calibration_version": "dopey-vnext-calibration-v2",
        "observed_at": observed_at,
        "calibration_sample_sufficient": ready,
        "promotion_allowed": ready,
        "source_evidence_hashes": _calibration_source_hashes(calibration_path),
    }
    calibration["reproducibility_hash"] = _canonical_summary_hash(calibration)
    release: dict[str, object] = {
        "artifact_type": "live_pivot_release_gate",
        "release_gate_version": "dopey-live-pivot-release-gate-v1",
        "release_status": "release_ready" if ready else "release_blocked",
        "live_blocked": not ready,
        "checks": {
            "hardened_champion_available": ready,
            "full_nightly_validation_green": ready,
        },
    }
    release["reproducibility_hash"] = _reproducibility_hash(release)
    action: dict[str, object] = {
        "artifact_type": "action_readiness_gate",
        "gate_semantics": (
            "necessary_not_sufficient_human_operator_review_always_required"
        ),
        "action_ready": ready,
        "readiness_status": (
            "action_ready_pending_human_review" if ready else "not_action_ready"
        ),
        "strategy_promotion_allowed": ready,
        "live_pivot_release_gate": release,
    }
    action["reproducibility_hash"] = _reproducibility_hash(action)
    payloads = {
        path
        / "artifacts"
        / "dopey"
        / "broker_readiness"
        / "action_readiness_gate.json": action,
        path
        / "artifacts"
        / "dopey"
        / "broker_readiness"
        / "live_pivot_release_gate.json": release,
        calibration_path: calibration,
        champion_path: champion,
        path / "artifacts" / "dopey" / "nightly" / "nightly_latest.json": nightly,
    }
    for artifact_path, payload in payloads.items():
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _mcp_call(
    call_id: str,
    tool: str,
    arguments: dict[str, object],
    result: dict[str, object] | list[object],
) -> McpToolCallEvidence:
    return McpToolCallEvidence(
        call_id=call_id,
        tool=tool,
        arguments=arguments,
        result={"content": [], "structured_content": result},
    )


def _attested_limit_order_calls(
    intent: LiveExecutionIntent,
) -> tuple[McpToolCallEvidence, McpToolCallEvidence]:
    exact_order: dict[str, object] = {
        "account_id": "agentic-account-id",
        "symbol": intent.symbol,
        "side": intent.side,
        "order_type": intent.order_type,
        "time_in_force": intent.time_in_force,
        "notional_usd": intent.notional_usd,
        "quantity": intent.quantity,
        "limit_price": intent.limit_price,
    }
    review = _mcp_call(
        "review-1",
        "review_equity_order",
        exact_order,
        {**exact_order, "review_succeeded": True},
    )
    place = _mcp_call(
        "place-1",
        "place_equity_order",
        exact_order,
        {
            **exact_order,
            "placed": True,
            "order_id": "broker-order-1",
            "status": "queued",
            "filled_quantity": 0.0,
            "average_fill_price": 0.0,
        },
    )
    return review, place


def _equity_intent() -> LiveExecutionIntent:
    return LiveExecutionIntent(
        intent_id="entry-1",
        instrument="equity",
        symbol="ACME",
        side="buy",
        order_type="market",
        limit_price=0.0,
        time_in_force="day",
        extended_hours=False,
        notional_usd=1_000.0,
        quantity=0.0,
        source_as_of_date="2026-07-17",
        source_hash="a" * 64,
        thesis_direction="bullish",
        analysis_symbol="ACME",
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


def _equity_execution_snapshot(observed_at: str) -> EquityExecutionSnapshot:
    quote = EquityQuoteSnapshot(
        symbol="ACME",
        bid_price=100.10,
        ask_price=100.20,
        last_price=100.15,
        observed_at=observed_at,
        tradable=True,
    )
    return EquityExecutionSnapshot(
        execution_quote=quote,
        analysis_quote=quote,
        source=EQUITY_SNAPSHOT_SOURCE,
    )


def _earnings_evidence(as_of_date: str) -> dict[str, object]:
    return {
        "snapshot_date": as_of_date,
        "snapshot_sha256": "e" * 64,
        "snapshot_symbol_count": 1,
        "symbol_covered": True,
        "next_earnings_date": "2026-08-05",
        "source_labels": ["fixture_frontier_calendar"],
        "status": "frontier_aligned_symbol_event_observed",
        "live_candidate_event_gate_passed": True,
    }


def _mstr_bearish_thesis() -> dict[str, object]:
    return {
        "symbol": "MSTR",
        "as_of_date": "2026-07-20",
        "thesis_status": "actionable_shadow_thesis",
        "direction": "bearish",
        "trade_intent": "long_put",
        "setup_quality_score": 0.8,
        "reward_risk_ratio": 2.0,
        "equity_bullish_score": 0.2,
        "equity_bearish_score": 0.8,
        "entry_reference_price": 100.0,
        "invalidation_price": 110.0,
        "target_price": 80.0,
        "expected_hold_trading_days": 10,
        "reason_codes": ["fixture"],
        "strategy_promotion_allowed": True,
        "not_edge_evidence": False,
        "earnings_evidence": _earnings_evidence("2026-07-20"),
        "technical_confirmation": {
            "technical_status": "complete",
            "bearish_score": 0.8,
        },
        "structure_reference": {"multi_timeframe_direction": "bearish"},
    }


class AmbiguousPlacementGateway:
    """Connector fixture that loses the broker result after one placement attempt."""

    def __init__(self, account: AccountSnapshot) -> None:
        self._account = account
        self.snapshot_call_count = 0
        self.placement_call_count = 0

    def get_account_snapshot(self) -> AccountSnapshot:
        return self._account

    def get_equity_execution_snapshot(
        self,
        intent: LiveExecutionIntent,
    ) -> EquityExecutionSnapshot:
        assert intent.instrument == "equity"
        assert intent.side == "buy"
        self.snapshot_call_count += 1
        return _equity_execution_snapshot("2026-07-21T15:00:00+00:00")

    def place_order(
        self,
        intent: LiveExecutionIntent,
        paper_twin_record_hash: str,
    ) -> NoReturn:
        self.placement_call_count += 1
        raise RobinhoodPlacementAmbiguousError(
            "fixture accepted-or-timeout: "
            f"intent_id={intent.intent_id}, paper_twin_record_hash={paper_twin_record_hash}"
        )


def test_user_scoped_options_gate_starts_off_and_is_reversible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with pytest.raises(LiveBranchControlError, match="control is missing"):
        load_live_branch_control()

    armed = set_live_branch_enabled(True, CONTROL_CONFIRMATION)
    assert armed.live_branch_enabled is True
    assert armed.stock_execution_enabled is True
    assert armed.options_execution_enabled is False
    assert armed.owner_authorization_id.startswith("machine:")

    enabled = set_options_execution_enabled(True, CONTROL_CONFIRMATION)
    assert enabled.options_execution_enabled is True
    disabled = set_options_execution_enabled(False, CONTROL_CONFIRMATION)
    assert disabled.options_execution_enabled is False

    disarmed = set_live_branch_enabled(False, CONTROL_CONFIRMATION)
    assert disarmed.live_branch_enabled is False
    assert disarmed.stock_execution_enabled is False


def test_stock_allocator_uses_full_capital_base_with_stop_risk_and_exposure_caps(
    tmp_path: Path,
) -> None:
    _write_research_maturity(tmp_path, True)
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [
            {
                "symbol": "ACME",
                "as_of_date": "2026-07-17",
                "thesis_status": "actionable_shadow_thesis",
                "direction": "bullish",
                "trade_intent": "long_call",
                "setup_quality_score": 0.8,
                "reward_risk_ratio": 2.0,
                "equity_bullish_score": 0.8,
                "equity_bearish_score": 0.2,
                "entry_reference_price": 100.0,
                "invalidation_price": 90.0,
                "target_price": 120.0,
                "expected_hold_trading_days": 10,
                "reason_codes": ["fixture"],
                "strategy_promotion_allowed": True,
                "not_edge_evidence": False,
                "earnings_evidence": _earnings_evidence("2026-07-17"),
            }
        ],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )
    intents = build_entry_intents(
        tmp_path,
        12_345.67,
        date(2026, 7, 20),
        True,
        False,
        frozenset(),
    )
    assert len(intents) == 1
    assert intents[0].instrument == "equity"
    assert intents[0].symbol == "ACME"
    assert intents[0].notional_usd == 617.28
    loss_at_invalidation = intents[0].notional_usd * 0.10
    assert loss_at_invalidation <= 12_345.67 * MAX_STOCK_RISK_PER_POSITION_FRACTION
    assert intents[0].notional_usd <= (
        12_345.67 * MAX_STOCK_SINGLE_NAME_ALLOCATION_FRACTION
    )
    assert sum(intent.notional_usd for intent in intents) <= (
        12_345.67 * MAX_STOCK_ENTRY_GROSS_ALLOCATION_FRACTION
    )


def test_plain_equity_entry_path_excludes_leveraged_etf_trade_symbols(
    tmp_path: Path,
) -> None:
    _write_research_maturity(tmp_path, True)
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "equity_swing_theses.jsonl",
        [
            {
                "symbol": "TQQQ",
                "as_of_date": "2026-07-17",
                "thesis_status": "actionable_shadow_thesis",
                "direction": "bullish",
                "trade_intent": "long_equity",
                "setup_quality_score": 0.8,
                "reward_risk_ratio": 2.0,
                "equity_bullish_score": 0.8,
                "equity_bearish_score": 0.2,
                "entry_reference_price": 100.0,
                "invalidation_price": 90.0,
                "target_price": 120.0,
                "expected_hold_trading_days": 10,
                "reason_codes": ["fixture"],
                "strategy_promotion_allowed": True,
                "not_edge_evidence": False,
                "earnings_evidence": _earnings_evidence("2026-07-17"),
            }
        ],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )

    intents = build_entry_intents(
        tmp_path,
        10_000.0,
        date(2026, 7, 20),
        True,
        False,
        frozenset(),
    )

    assert intents == ()


def test_earnings_evidence_contract_is_fail_closed() -> None:
    complete = {
        "as_of_date": "2026-07-20",
        "earnings_evidence": _earnings_evidence("2026-07-20"),
    }
    assert _thesis_has_complete_earnings_evidence(complete) is True

    unresolved_evidence = {
        **_earnings_evidence("2026-07-20"),
        "status": "unresolved_symbol_absence",
        "live_candidate_event_gate_passed": False,
    }
    assert (
        _thesis_has_complete_earnings_evidence(
            {**complete, "earnings_evidence": unresolved_evidence}
        )
        is False
    )
    assert (
        _thesis_has_complete_earnings_evidence(
            {
                **complete,
                "earnings_evidence": {
                    **_earnings_evidence("2026-07-19"),
                    "snapshot_sha256": "not-a-sha256",
                },
            }
        )
        is False
    )


def test_equity_entry_requires_fresh_typed_quote_and_becomes_exact_limit() -> None:
    now_utc = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)
    snapshot = _equity_execution_snapshot(now_utc.isoformat())

    prepared = prepare_equity_entry_for_execution(
        _equity_intent(),
        snapshot,
        now_utc,
        10_000.0,
    )

    assert prepared.order_type == "limit"
    assert prepared.limit_price == 100.20
    assert prepared.execution_snapshot == snapshot
    assert prepared.notional_usd < _equity_intent().notional_usd
    assert "price_collared_limit_order" in prepared.reason_codes

    stale_observed_at = (
        now_utc - timedelta(seconds=MAX_EQUITY_QUOTE_AGE_SECONDS + 1.0)
    ).isoformat()
    with pytest.raises(LiveSignalError, match="quote is stale"):
        prepare_equity_entry_for_execution(
            _equity_intent(),
            _equity_execution_snapshot(stale_observed_at),
            now_utc,
            10_000.0,
        )


def test_robinhood_codex_command_is_read_only_and_capability_minimized(
    tmp_path: Path,
) -> None:
    command = _codex_exec_command(
        "codex.exe",
        str(tmp_path),
        tmp_path / "result.json",
        ("get_portfolio", "get_accounts", "get_accounts"),
    )

    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--json" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    for feature in DISABLED_CODEX_FEATURES:
        assert ["--disable", feature] in [
            command[index : index + 2] for index in range(len(command) - 1)
        ]
    config_values = [
        command[index + 1] for index, value in enumerate(command[:-1]) if value == "-c"
    ]
    assert config_values == [
        'mcp_servers.robinhood-trading.url="https://agent.robinhood.com/mcp/trading"',
        'mcp_servers.robinhood-trading.enabled_tools=["get_accounts","get_portfolio"]',
        'mcp_servers.robinhood-trading.default_tools_approval_mode="writes"',
        'mcp_servers.robinhood-trading.tools.get_accounts.approval_mode="approve"',
        'mcp_servers.robinhood-trading.tools.get_portfolio.approval_mode="approve"',
    ]


def test_machine_readable_mcp_transcript_requires_complete_lifecycle() -> None:
    arguments = {"account_id": "agentic-account-id"}
    result = {
        "content": [],
        "structured_content": {"buying_power": "1000.00"},
    }
    events = (
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {
            "type": "item.started",
            "item": {
                "id": "call-1",
                "type": "mcp_tool_call",
                "server": "robinhood-trading",
                "tool": "get_portfolio",
                "arguments": arguments,
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "call-1",
                "type": "mcp_tool_call",
                "server": "robinhood-trading",
                "tool": "get_portfolio",
                "arguments": arguments,
                "result": result,
                "error": None,
                "status": "completed",
            },
        },
        {"type": "turn.completed", "usage": {}},
    )
    transcript = "\n".join(json.dumps(event) for event in events)

    calls = _mcp_transcript(transcript)

    assert len(calls) == 1
    assert calls[0].tool == "get_portfolio"
    with pytest.raises(RobinhoodGatewayError, match="start/completion sets differ"):
        _mcp_transcript(
            "\n".join(
                json.dumps(event)
                for event in events
                if event.get("type") != "item.completed"
            )
        )


def test_agentic_account_mapping_is_bound_to_every_scoped_call() -> None:
    get_accounts = _mcp_call(
        "accounts-1",
        "get_accounts",
        {},
        {
            "data": {
                "accounts": [
                    {
                        "nickname": "Primary individual",
                        "account_number": "primary-account-id",
                        "brokerage_account_type": "individual",
                    },
                    {
                        "nickname": "Agentic",
                        "account_number": "agentic-account-id",
                        "brokerage_account_type": "individual",
                    },
                ]
            }
        },
    )
    portfolio = _mcp_call(
        "portfolio-1",
        "get_portfolio",
        {"account_number": "agentic-account-id"},
        {
            "data": {
                "buying_power": {"buying_power": "1000.00"},
                "total_value": "1000.00",
            }
        },
    )

    attestation = _attest_account_scope(
        (get_accounts, portfolio),
        ("get_portfolio",),
    )

    assert attestation.account_label == "Agentic"
    assert attestation.account_type == "individual"
    with pytest.raises(RobinhoodGatewayError, match="labeled Agentic account"):
        _attest_account_scope(
            (
                get_accounts,
                replace(
                    portfolio,
                    arguments={"account_number": "primary-account-id"},
                ),
            ),
            ("get_portfolio",),
        )


def test_live_order_envelope_attests_history_and_canonical_fields() -> None:
    raw_order: dict[str, object] = {
        "id": "broker-order-1",
        "symbol": "GOOGL",
        "side": "sell",
        "state": "filled",
        "created_at": "2026-07-20T03:43:04.815114Z",
        "last_transaction_at": "2026-07-20T13:30:00.862Z",
        "cumulative_quantity": "0.570255",
        "average_price": "345.631100",
    }
    equity_orders = _mcp_call(
        "equity-orders-1",
        "get_equity_orders",
        {"account_number": "agentic-account-id", "limit": 1000},
        {"data": {"orders": [raw_order]}},
    )
    option_orders = _mcp_call(
        "option-orders-1",
        "get_option_orders",
        {"account_number": "agentic-account-id", "limit": 1000},
        {"data": {"orders": []}},
    )

    assert _attest_order_history_results((equity_orders, option_orders)) == (
        True,
        True,
    )
    canonical = _canonical_raw_broker_item(raw_order, "equity_order")
    assert canonical["order_id"] == "broker-order-1"
    assert canonical["status"] == "filled"
    assert canonical["filled_quantity"] == "0.570255"
    assert canonical["average_fill_price"] == "345.631100"
    assert canonical["market_date"] == "2026-07-20"


def test_equity_snapshot_is_bound_to_mcp_request_arguments_and_results() -> None:
    intent = _equity_intent()
    snapshot = _equity_execution_snapshot("2026-07-21T15:00:00+00:00")
    quote_result = {
        "quotes": [
            {
                "symbol": "ACME",
                "bid_price": "100.10",
                "ask_price": "100.20",
                "last_price": "100.15",
                "observed_at": "2026-07-21T15:00:00+00:00",
            }
        ]
    }
    quote_call = _mcp_call(
        "quote-1",
        "get_equity_quotes",
        {"symbols": ["ACME"]},
        quote_result,
    )
    tradability_call = _mcp_call(
        "tradability-1",
        "get_equity_tradability",
        {"symbols": ["ACME"]},
        {"results": [{"symbol": "ACME", "tradable": True}]},
    )

    _attest_equity_execution_snapshot(
        (quote_call, tradability_call),
        intent,
        snapshot,
    )

    mismatched_quote = replace(
        quote_call,
        result={
            "content": [],
            "structured_content": {
                "quotes": [{**quote_result["quotes"][0], "ask_price": "100.21"}]
            },
        },
    )
    with pytest.raises(RobinhoodGatewayError, match="differs from the MCP response"):
        _attest_equity_execution_snapshot(
            (mismatched_quote, tradability_call),
            intent,
            snapshot,
        )


@pytest.mark.parametrize(
    "malformed_position",
    [
        "not-an-object",
        {"symbol": "ACME", "quantity": 1.0},
        {
            "symbol": "ACME",
            "quantity": -1.0,
            "average_cost": 100.0,
            "market_price": 100.0,
            "market_value": 100.0,
            "unrealized_pnl": 0.0,
        },
    ],
)
def test_broker_position_items_never_drop_or_accept_malformed_values(
    malformed_position: object,
) -> None:
    with pytest.raises(RobinhoodGatewayError):
        _validated_equity_position(malformed_position, 0)


@pytest.mark.parametrize(
    "malformed_order",
    [
        7,
        {"order_id": "order-1"},
        {
            "order_id": "order-1",
            "symbol": "ACME",
            "side": "buy",
            "status": "filled",
            "submitted_at": "2026-07-21T14:30:00+00:00",
            "filled_at": "2026-07-21T14:31:00+00:00",
            "filled_quantity": 0.0,
            "average_fill_price": 100.0,
            "market_date": "2026-07-21",
        },
    ],
)
def test_broker_history_items_never_drop_or_accept_malformed_values(
    malformed_order: object,
) -> None:
    with pytest.raises(RobinhoodGatewayError):
        _validated_order(malformed_order, 0, False)


def test_order_result_rejects_unattested_exact_limit() -> None:
    intent = replace(
        _equity_intent(),
        order_type="limit",
        limit_price=100.20,
    )
    review, place = _attested_limit_order_calls(intent)
    mismatched_place = replace(
        place,
        arguments={**place.arguments, "limit_price": 100.21},
    )
    payload = {
        "order_history_complete": True,
        "review_succeeded": True,
        "placed": True,
        "order_id": "broker-order-1",
        "status": "queued",
        "filled_quantity": 0.0,
        "average_fill_price": 0.0,
        "submitted_at": "2026-07-21T14:30:00+00:00",
        "filled_at": "",
        "warnings": [],
        "error": "",
    }

    with pytest.raises(
        RobinhoodPlacementAmbiguousError,
        match="does not prove the exact typed intent",
    ):
        _gateway_order_result(
            payload,
            "review_equity_order",
            "place_equity_order",
            intent,
            (review, mismatched_place),
            "agentic-account-id",
        )


def test_order_result_requires_review_before_place() -> None:
    intent = replace(
        _equity_intent(),
        order_type="limit",
        limit_price=100.20,
    )
    review, place = _attested_limit_order_calls(intent)
    payload = {
        "order_history_complete": True,
        "review_succeeded": True,
        "placed": True,
        "order_id": "broker-order-1",
        "status": "queued",
        "filled_quantity": 0.0,
        "average_fill_price": 0.0,
        "submitted_at": "2026-07-21T14:30:00+00:00",
        "filled_at": "",
        "warnings": [],
        "error": "",
    }

    with pytest.raises(
        RobinhoodPlacementAmbiguousError,
        match="before its exact review",
    ):
        _gateway_order_result(
            payload,
            "review_equity_order",
            "place_equity_order",
            intent,
            (place, review),
            "agentic-account-id",
    )


def test_option_quote_must_be_from_the_execution_market_session() -> None:
    market_date = date(2026, 7, 20)

    assert (
        _option_quote_matches_market_session(
            {"quote_observed_at": "2026-07-20T15:30:00+00:00"},
            market_date,
        )
        is True
    )
    assert (
        _option_quote_matches_market_session(
            {"quote_observed_at": "2026-07-17T15:30:00+00:00"},
            market_date,
        )
        is False
    )
    assert (
        _option_quote_matches_market_session(
            {"quote_observed_at": "2026-07-20T15:30:00"},
            market_date,
        )
        is False
    )


def test_stock_allocator_rejects_stale_source_thesis(tmp_path: Path) -> None:
    _write_research_maturity(tmp_path, True)
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [
            {
                "symbol": "ACME",
                "as_of_date": "2026-07-16",
                "thesis_status": "actionable_shadow_thesis",
                "direction": "bullish",
                "trade_intent": "long_call",
                "setup_quality_score": 0.8,
                "reward_risk_ratio": 2.0,
                "equity_bullish_score": 0.8,
                "equity_bearish_score": 0.2,
                "entry_reference_price": 100.0,
                "invalidation_price": 90.0,
                "target_price": 120.0,
                "expected_hold_trading_days": 10,
                "reason_codes": ["fixture"],
                "strategy_promotion_allowed": True,
                "not_edge_evidence": False,
                "earnings_evidence": _earnings_evidence("2026-07-16"),
            }
        ],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )

    intents = build_entry_intents(
        tmp_path,
        12_345.67,
        date(2026, 7, 20),
        True,
        False,
        frozenset(),
    )

    assert intents == ()


def test_mstz_entry_and_exit_use_mstr_chart_authority(tmp_path: Path) -> None:
    _write_research_maturity(tmp_path, True)
    thesis = _mstr_bearish_thesis()
    history = {
        "MSTR": [
            {
                "date": "2026-07-20",
                "open": 101.0,
                "high": 102.0,
                "low": 98.0,
                "close": 100.0,
                "adjusted_close": 100.0,
                "volume": 1_000_000,
            }
        ]
    }
    plans = build_leveraged_etf_swing_plans([thesis], history)
    mstz = next(plan for plan in plans if plan["trade_symbol"] == "MSTZ")
    mstu = next(plan for plan in plans if plan["trade_symbol"] == "MSTU")
    assert mstz["plan_status"] == "actionable_shadow_leveraged_etf_plan"
    assert mstz["analysis_symbol"] == "MSTR"
    assert mstz["position_construction"] == "long_shares"
    assert mstz["direct_short_sale_allowed"] is False
    assert mstz["expected_hold_trading_days"] == 5
    assert mstu["plan_status"] == "no_trade_exposure_direction_mismatch"
    mstz = {
        **mstz,
        "strategy_promotion_allowed": True,
        "not_edge_evidence": False,
    }

    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [thesis],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "leveraged_etf_swing_plans.jsonl",
        [mstz, mstu],
    )
    thesis_without_earnings = {
        key: value for key, value in thesis.items() if key != "earnings_evidence"
    }
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [thesis_without_earnings],
    )
    assert (
        build_entry_intents(
            tmp_path,
            10_000.0,
            date(2026, 7, 21),
            True,
            False,
            frozenset(),
        )
        == ()
    )
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [thesis],
    )
    intents = build_entry_intents(
        tmp_path,
        10_000.0,
        date(2026, 7, 21),
        True,
        False,
        frozenset(),
    )
    assert len(intents) == 1
    opened = intents[0]
    assert opened.symbol == "MSTZ"
    assert opened.analysis_symbol == "MSTR"
    assert opened.thesis_direction == "bearish"
    assert opened.daily_reset is True
    assert opened.notional_usd == 1_000.0
    assert (
        build_entry_intents(
            tmp_path,
            10_000.0,
            date(2026, 7, 21),
            True,
            False,
            frozenset({"MSTZ"}),
        )
        == ()
    )
    assert (
        build_entry_intents(
            tmp_path,
            10_000.0,
            date(2026, 7, 21),
            True,
            False,
            frozenset({"MSTU"}),
        )
        == ()
    )

    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": opened.intent_id,
            "instrument": opened.instrument,
            "symbol": opened.symbol,
            "side": opened.side,
            "market_date": "2026-07-20",
            "order_id": "mstz-order-1",
            "status": "filled",
            "filled_quantity": 10.0,
            "placed": True,
            "intent": opened.to_dict(),
        },
    )
    history_path = tmp_path / "dopey_data" / "history" / "raw" / "MSTR.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
        "2026-07-21,MSTR,82,83,79,80,80,1000000,fixture\n",
        encoding="utf-8",
    )
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_000.0,
        equity_positions=(
            {
                "symbol": "MSTZ",
                "quantity": 10.0,
                "average_cost": 30.0,
                "market_price": 30.0,
            },
        ),
        option_positions=(),
        recent_equity_orders=(),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )
    exits = _build_exit_intents(tmp_path, account, date(2026, 7, 21))
    assert len(exits) == 1
    assert exits[0].symbol == "MSTZ"
    assert exits[0].analysis_symbol == "MSTR"
    assert "underlying_chart_target_reached" in exits[0].reason_codes


def test_expanded_leveraged_etf_catalog_is_paired_unique_and_chart_backed() -> None:
    counts = validate_leveraged_etf_catalog(LEVERAGED_ETF_CATALOG)
    assert counts == {
        "pair_count": 48,
        "product_count": 96,
        "analysis_symbol_count": 43,
    }
    trade_symbols = {spec["trade_symbol"] for spec in LEVERAGED_ETF_CATALOG}
    assert {
        "MSTU",
        "MSTZ",
        "TSLL",
        "TSLS",
        "AAPU",
        "AAPD",
        "NVDU",
        "NVDD",
        "TQQQ",
        "SQQQ",
        "URTY",
        "SRTY",
        "BITU",
        "SBIT",
        "BOIL",
        "KOLD",
    } <= trade_symbols
    repository_root = Path(__file__).resolve().parent.parent
    manifest = json.loads(
        (
            repository_root / "dopey_data" / "history" / "history_dataset_manifest.json"
        ).read_text(encoding="utf-8")
    )
    pinned_symbols = {
        str(symbol)
        for record in manifest["data_files"]
        for symbol in record.get("symbols", [])
    }
    analysis_symbols = {spec["analysis_symbol"] for spec in LEVERAGED_ETF_CATALOG}
    assert analysis_symbols <= pinned_symbols


def test_one_x_inverse_pair_routes_and_equivalent_products_do_not_duplicate(
    tmp_path: Path,
) -> None:
    _write_research_maturity(tmp_path, True)
    tsla_thesis = {
        **_mstr_bearish_thesis(),
        "symbol": "TSLA",
    }
    tsla_history = {
        "TSLA": [
            {
                "date": "2026-07-20",
                "open": 101.0,
                "high": 102.0,
                "low": 98.0,
                "close": 100.0,
                "adjusted_close": 100.0,
                "volume": 1_000_000,
            }
        ]
    }
    tsla_plans = build_leveraged_etf_swing_plans([tsla_thesis], tsla_history)
    tsls = next(plan for plan in tsla_plans if plan["trade_symbol"] == "TSLS")
    assert tsls["plan_status"] == "actionable_shadow_leveraged_etf_plan"
    assert tsls["daily_leverage_multiple"] == -1.0
    assert tsls["max_notional_fraction"] == 0.1

    spy_thesis = {
        **_mstr_bearish_thesis(),
        "symbol": "SPY",
    }
    spy_history = {
        "SPY": [
            {
                "date": "2026-07-20",
                "open": 101.0,
                "high": 102.0,
                "low": 98.0,
                "close": 100.0,
                "adjusted_close": 100.0,
                "volume": 1_000_000,
            }
        ]
    }
    spy_plans = build_leveraged_etf_swing_plans([spy_thesis], spy_history)
    actionable_spy = [
        plan
        for plan in spy_plans
        if plan["analysis_symbol"] == "SPY"
        and plan["plan_status"] == "actionable_shadow_leveraged_etf_plan"
    ]
    assert {plan["trade_symbol"] for plan in actionable_spy} == {"SPXS", "SPXU", "SDS"}
    tsls = {
        **tsls,
        "strategy_promotion_allowed": True,
        "not_edge_evidence": False,
    }
    actionable_spy = [
        {
            **plan,
            "strategy_promotion_allowed": True,
            "not_edge_evidence": False,
        }
        for plan in actionable_spy
    ]

    source_theses = [tsla_thesis, spy_thesis]
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        source_theses,
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "leveraged_etf_swing_plans.jsonl",
        [tsls, *actionable_spy],
    )
    intents = build_entry_intents(
        tmp_path,
        20_000.0,
        date(2026, 7, 21),
        True,
        False,
        frozenset(),
    )
    assert {intent.symbol for intent in intents} == {"TSLS", "SPXS"}
    assert len({intent.analysis_symbol for intent in intents}) == 2


def test_no_same_session_round_trip_and_next_session_exit(tmp_path: Path) -> None:
    opened = _equity_intent()
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": opened.intent_id,
            "instrument": opened.instrument,
            "symbol": opened.symbol,
            "side": opened.side,
            "market_date": "2026-07-20",
            "order_id": "broker-order-1",
            "status": "filled",
            "filled_quantity": 10.0,
            "placed": True,
            "intent": opened.to_dict(),
        },
    )
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_200.0,
        equity_positions=(
            {
                "symbol": "ACME",
                "quantity": 10.0,
                "market_price": 115.0,
            },
        ),
        option_positions=(),
        recent_equity_orders=(),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )
    assert _build_exit_intents(tmp_path, account, date(2026, 7, 20)) == ()
    exits = _build_exit_intents(tmp_path, account, date(2026, 7, 21))
    assert len(exits) == 1
    assert exits[0].side == "sell"
    assert exits[0].quantity == 10.0
    assert "target_price_reached" in exits[0].reason_codes


def test_broker_history_blocks_manual_same_session_stock_round_trip() -> None:
    exit_intent = LiveExecutionIntent(**{**_equity_intent().to_dict(), "side": "sell"})
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_000.0,
        equity_positions=(),
        option_positions=(),
        recent_equity_orders=(
            {
                "symbol": "ACME",
                "side": "buy",
                "status": "filled",
                "market_date": "2026-07-20",
            },
        ),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )
    assert (
        _day_trade_blocker(account, exit_intent, "2026-07-20")
        == "broker_history_same_session_round_trip_blocked"
    )
    assert _day_trade_blocker(account, exit_intent, "2026-07-21") == ""


def test_order_history_guard_fails_closed_on_missing_prior_session_live_order(
    tmp_path: Path,
) -> None:
    opened = _equity_intent()
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": opened.intent_id,
            "instrument": opened.instrument,
            "symbol": opened.symbol,
            "side": opened.side,
            "market_date": "2026-07-20",
            "order_id": "broker-order-1",
            "status": "queued",
            "placed": True,
            "intent": opened.to_dict(),
        },
    )
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_000.0,
        equity_positions=(),
        option_positions=(),
        recent_equity_orders=(),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )
    assert (
        _order_history_blocker(tmp_path, account, "2026-07-21", False)
        == "broker_history_missing_nonterminal_local_live_order"
    )


def test_live_position_requires_observed_fill_and_reconciliation_is_idempotent(
    tmp_path: Path,
) -> None:
    opened = _equity_intent()
    twin = append_record(
        paper_twin_path(tmp_path),
        "paper_twin_staged",
        {
            "intent": opened.to_dict(),
            "paper_only": True,
            "live_twin": True,
        },
    )
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": opened.intent_id,
            "instrument": opened.instrument,
            "symbol": opened.symbol,
            "side": opened.side,
            "market_date": "2026-07-20",
            "order_id": "broker-order-1",
            "status": "queued",
            "placed": True,
            "paper_twin_record_hash": twin["record_hash"],
            "intent": opened.to_dict(),
        },
    )
    assert _open_live_positions(tmp_path) == {}
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_000.0,
        equity_positions=({"symbol": "ACME", "quantity": 10.0, "market_price": 100.0},),
        option_positions=(),
        recent_equity_orders=(
            {
                "order_id": "broker-order-1",
                "symbol": "ACME",
                "side": "buy",
                "status": "filled",
                "market_date": "2026-07-20",
                "submitted_at": "2026-07-20T13:30:00+00:00",
                "filled_at": "2026-07-20T13:30:01+00:00",
                "filled_quantity": 10.0,
                "average_fill_price": 100.0,
            },
        ),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )

    first = _reconcile_live_order_statuses(tmp_path, account)
    second = _reconcile_live_order_statuses(tmp_path, account)

    assert len(first) == 1
    assert second == ()
    assert set(_open_live_positions(tmp_path)) == {"equity|ACME|"}
    twin_outcome = read_ledger(paper_twin_path(tmp_path))[-1]
    assert twin_outcome["event_type"] == "paper_twin_outcome_observed"
    assert twin_outcome["payload"]["paper_twin_outcome_status"] == (
        "paper_twin_observed_terminal_live_order"
    )
    assert twin_outcome["payload"]["observed_live_filled_quantity"] == 10.0
    assert twin_outcome["payload"]["paper_filled_quantity"] is None
    assert twin_outcome["payload"]["no_fill_inferred"] is True


def test_release_gate_requires_independent_result_bearing_paper_execution(
    tmp_path: Path,
) -> None:
    intent = _equity_intent()
    twin = append_record(
        paper_twin_path(tmp_path),
        "paper_twin_staged",
        {"intent": intent.to_dict(), "paper_only": True, "live_twin": True},
    )
    live = append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": intent.intent_id,
            "order_id": "broker-order-1",
            "placed": True,
            "status": "queued",
            "paper_twin_record_hash": twin["record_hash"],
            "intent": intent.to_dict(),
        },
    )
    append_record(
        paper_twin_path(tmp_path),
        "paper_twin_linked",
        {
            "intent_id": intent.intent_id,
            "live_record_hash": live["record_hash"],
            "paper_only": True,
            "live_twin": True,
        },
    )

    linkage_only = _live_ledger_evidence(tmp_path)
    assert linkage_only["paper_twin_linkage_green"] is True
    assert linkage_only["paper_twin_result_evidence_green"] is False
    assert linkage_only["missing_twin_result_order_ids"] == ["broker-order-1"]

    append_record(
        paper_twin_path(tmp_path),
        "paper_twin_execution_observed",
        {
            "intent_id": intent.intent_id,
            "paper_twin_record_hash": twin["record_hash"],
            "paper_twin_execution_status": "independent_quote_observation_complete",
            "paper_fill_status": "simulated_filled",
            "paper_filled_quantity": 1.0,
            "paper_average_fill_price": 100.2,
            "market_observation_source": EQUITY_SNAPSHOT_SOURCE,
            "market_observed_at": "2026-07-21T15:00:00+00:00",
            "result_bearing": True,
            "independent_of_live_result": True,
            "paper_only": True,
        },
    )

    result_bearing = _live_ledger_evidence(tmp_path)
    assert result_bearing["paper_twin_result_evidence_green"] is True
    assert result_bearing["missing_twin_result_order_ids"] == []


def test_live_ledger_detects_tampering(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    append_record(path, "fixture", {"value": 1})
    text = path.read_text(encoding="utf-8").replace('"value": 1', '"value": 2')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(LiveBranchLedgerError, match="hash chain mismatch"):
        read_ledger(path)


def test_robinhood_stock_submission_window_opens_sunday_evening() -> None:
    open_state, market_date, regular_open = _robinhood_stock_submission_state(
        datetime(2026, 7, 20, 3, 30, tzinfo=timezone.utc)
    )
    assert open_state is True
    assert market_date == "2026-07-20"
    assert regular_open is False


def test_research_maturity_gate_blocks_unproven_live_entries(tmp_path: Path) -> None:
    _write_research_maturity(tmp_path, False)
    thesis = {
        "symbol": "ACME",
        "as_of_date": "2026-07-20",
        "thesis_status": "actionable_shadow_thesis",
        "direction": "bullish",
        "trade_intent": "long_call",
        "setup_quality_score": 0.8,
        "reward_risk_ratio": 2.0,
        "equity_bullish_score": 0.8,
        "equity_bearish_score": 0.2,
        "entry_reference_price": 100.0,
        "invalidation_price": 90.0,
        "target_price": 120.0,
        "expected_hold_trading_days": 10,
        "strategy_promotion_allowed": True,
        "not_edge_evidence": False,
        "earnings_evidence": _earnings_evidence("2026-07-20"),
        "reason_codes": ["fixture"],
    }
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [thesis],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )

    assert research_maturity_blockers(tmp_path) == (
        "action_readiness_gate_not_ready",
        "action_readiness_status_not_ready",
        "strategy_promotion_not_allowed",
        "live_pivot_release_not_ready",
        "live_pivot_release_still_blocked",
        "forward_calibration_sample_insufficient",
        "forward_calibration_promotion_not_allowed",
    )
    assert (
        build_entry_intents(
            tmp_path,
            10_000.0,
            date(2026, 7, 21),
            True,
            False,
            frozenset(),
        )
        == ()
    )


def test_research_maturity_gate_rejects_stale_or_unbound_green_artifacts(
    tmp_path: Path,
) -> None:
    _write_research_maturity(tmp_path, True)
    release_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "broker_readiness"
        / "live_pivot_release_gate.json"
    )
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release["checks"]["hardened_champion_available"] = False
    release_path.write_text(json.dumps(release), encoding="utf-8")

    blockers = research_maturity_blockers(tmp_path)

    assert "live_pivot_release_hash_invalid" in blockers
    assert "action_release_binding_invalid" in blockers
    assert "release_champion_binding_invalid" in blockers

    _write_research_maturity(tmp_path, True)
    calibration_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "vnext"
        / "cross_sectional_operational"
        / "calibration_summary.json"
    )
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    calibration["observed_at"] = "2020-01-01T00:00:00+00:00"
    calibration_path.write_text(json.dumps(calibration), encoding="utf-8")

    assert "forward_calibration_stale" in research_maturity_blockers(tmp_path)

    _write_research_maturity(tmp_path, True)
    source_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "champion_hardening"
        / "public_champion_decay_alerts_v1.jsonl"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("{}\n", encoding="utf-8")

    assert (
        "champion_hardening_source_binding_invalid"
        in research_maturity_blockers(tmp_path)
    )

    _write_research_maturity(tmp_path, True)
    calibration_source_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "vnext"
        / "cross_sectional_operational"
        / "forward_predictions.jsonl"
    )
    calibration_source_path.write_text("{}\n", encoding="utf-8")

    assert (
        "forward_calibration_source_binding_invalid"
        in research_maturity_blockers(tmp_path)
    )

    _write_research_maturity(tmp_path, True)
    nightly_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "nightly"
        / "nightly_latest.json"
    )
    nightly = json.loads(nightly_path.read_text(encoding="utf-8"))
    nightly["suite_green"] = False
    nightly_path.write_text(json.dumps(nightly), encoding="utf-8")

    assert "nightly_hash_invalid" in research_maturity_blockers(tmp_path)


def test_actionable_shadow_thesis_requires_strategy_promotion(tmp_path: Path) -> None:
    _write_research_maturity(tmp_path, True)
    thesis = {
        "symbol": "ACME",
        "as_of_date": "2026-07-20",
        "thesis_status": "actionable_shadow_thesis",
        "direction": "bullish",
        "trade_intent": "long_call",
        "setup_quality_score": 0.8,
        "reward_risk_ratio": 2.0,
        "equity_bullish_score": 0.8,
        "equity_bearish_score": 0.2,
        "entry_reference_price": 100.0,
        "invalidation_price": 90.0,
        "target_price": 120.0,
        "expected_hold_trading_days": 10,
        "strategy_promotion_allowed": False,
        "not_edge_evidence": True,
        "earnings_evidence": _earnings_evidence("2026-07-20"),
        "reason_codes": ["fixture"],
    }
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [thesis],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )

    assert (
        build_entry_intents(
            tmp_path,
            10_000.0,
            date(2026, 7, 21),
            True,
            False,
            frozenset(),
        )
        == ()
    )


def test_intent_reservation_blocks_reentry_until_definitive_nonplacement(
    tmp_path: Path,
) -> None:
    intent = _equity_intent()
    payload = {"intent": intent.to_dict(), "market_date": "2026-07-21"}
    assert reserve_intent(tmp_path, intent.intent_id, payload) is True
    assert reserve_intent(tmp_path, intent.intent_id, payload) is False
    assert intent_already_submitted(tmp_path, intent.intent_id) is True

    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": intent.intent_id,
            "placed": False,
            "status": "blocked_review_rejected",
            "intent": intent.to_dict(),
        },
    )

    assert intent_already_submitted(tmp_path, intent.intent_id) is False
    assert reserve_intent(tmp_path, intent.intent_id, payload) is True


def test_ambiguous_submission_remains_fail_closed(tmp_path: Path) -> None:
    intent = _equity_intent()
    payload = {"intent": intent.to_dict(), "market_date": "2026-07-21"}
    assert reserve_intent(tmp_path, intent.intent_id, payload) is True
    append_record(
        ledger_path(tmp_path),
        "live_order_submission_ambiguous",
        {
            "intent_id": intent.intent_id,
            "placed": None,
            "status": "ambiguous_submission_manual_reconciliation_required",
        },
    )

    assert intent_already_submitted(tmp_path, intent.intent_id) is True
    assert reserve_intent(tmp_path, intent.intent_id, payload) is False


def test_operator_verified_reconciliation_resolves_without_broker_inference(
    tmp_path: Path,
) -> None:
    intent = _equity_intent()
    assert reserve_intent(
        tmp_path,
        intent.intent_id,
        {"intent": intent.to_dict(), "market_date": "2026-07-21"},
    )

    record = reconcile_submission_after_operator_verification(
        tmp_path,
        intent.intent_id,
        False,
        "",
        "verified_not_placed",
        0.0,
        0.0,
        "broker-history-export:2026-07-21T15:30Z",
        OPERATOR_RECONCILIATION_CONFIRMATION,
    )

    assert record["event_type"] == "live_order_result"
    assert record["payload"]["operator_reconciled"] is True
    assert record["payload"]["automatic_broker_inference_used"] is False
    assert intent_already_submitted(tmp_path, intent.intent_id) is False
    with pytest.raises(
        LiveBranchLedgerError,
        match="not an unresolved submission",
    ):
        reconcile_submission_after_operator_verification(
            tmp_path,
            intent.intent_id,
            False,
            "",
            "verified_not_placed",
            0.0,
            0.0,
            "broker-history-export:duplicate",
            OPERATOR_RECONCILIATION_CONFIRMATION,
        )


def test_operator_can_recover_only_a_stale_dead_pid_ledger_lock(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "ledger_path": str(path.resolve()),
                "process_id": 2_147_483_647,
                "locked_utc": "2026-07-21T14:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    record = recover_stale_ledger_lock_after_operator_verification(
        tmp_path,
        "live",
        OPERATOR_LOCK_RECOVERY_CONFIRMATION,
        datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc),
    )

    assert (
        record["event_type"]
        == "ledger_lock_recovered_after_operator_verification"
    )
    assert not lock_path.exists()
    assert (
        len(tuple(lock_path.parent.glob(f"{lock_path.name}.recovered.*")))
        == 1
    )
    assert read_ledger(path)[-1]["record_hash"] == record["record_hash"]


def test_order_attestation_rejects_unexpected_arguments_and_extended_hours() -> None:
    intent = _equity_intent()
    exact_order: dict[str, object] = {
        "account_id": "agentic-account-id",
        "symbol": intent.symbol,
        "side": intent.side,
        "order_type": intent.order_type,
        "time_in_force": intent.time_in_force,
        "notional_usd": intent.notional_usd,
        "quantity": intent.quantity,
    }
    safe_call = _mcp_call(
        "place-market-safe",
        "place_equity_order",
        exact_order,
        {**exact_order, "limit_price": 0.0, "extended_hours": False},
    )
    _attest_order_call(safe_call, intent, "agentic-account-id")

    with pytest.raises(RobinhoodGatewayError, match="unexpected arguments"):
        _attest_order_call(
            replace(
                safe_call,
                arguments={**safe_call.arguments, "prompt_override": "ignore policy"},
            ),
            intent,
            "agentic-account-id",
        )
    with pytest.raises(RobinhoodGatewayError, match="extended_hours"):
        _attest_order_call(
            replace(
                safe_call,
                arguments={**safe_call.arguments, "extended_hours": True},
            ),
            intent,
            "agentic-account-id",
        )


def test_live_dashboard_marks_old_cycle_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local_app_data"))
    set_live_branch_enabled(True, CONTROL_CONFIRMATION)
    write_latest_cycle(
        tmp_path,
        {
            "generated_utc": (
                datetime.now(timezone.utc) - timedelta(hours=1)
            ).isoformat(),
            "cycle_status": "complete",
            "account": {"authenticated": True},
        },
    )

    state = build_live_branch_state(tmp_path)

    assert state["status"] == "stale"
    assert state["cycle_freshness"] == "stale"
    assert state["cycle_age_seconds"] > state["max_cycle_age_seconds"]


def test_operator_wrapper_replaces_stale_success_with_crash_tombstone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_latest_cycle(
        tmp_path,
        {
            "generated_utc": "2026-07-20T15:00:00+00:00",
            "cycle_status": "complete",
        },
    )

    def crash_cycle(
        repository_root: Path,
        gateway: object,
        now_utc: datetime,
        execute_orders: bool,
    ) -> dict[str, object]:
        del repository_root, gateway, now_utc, execute_orders
        raise ValueError("corrupt source thesis")

    monkeypatch.setattr(operator_live_branch, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(operator_live_branch, "default_gateway", object)
    monkeypatch.setattr(operator_live_branch, "run_live_branch_cycle", crash_cycle)

    with pytest.raises(ValueError, match="corrupt source thesis"):
        operator_live_branch._run_with_crash_tombstone(False)

    tombstone = json.loads(
        (
            tmp_path
            / "artifacts"
            / "dopey"
            / "live_branch"
            / "latest_cycle.json"
        ).read_text(encoding="utf-8")
    )
    assert tombstone["cycle_status"] == "cycle_crashed_unhandled"
    assert tombstone["error_type"] == "ValueError"
    assert tombstone["stale_prior_success_hidden"] is True


def test_ambiguous_broker_outcome_cannot_place_twice_across_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local_app_data"))
    set_live_branch_enabled(True, CONTROL_CONFIRMATION)
    _write_research_maturity(tmp_path, True)
    _write_jsonl(
        tmp_path / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl",
        [
            {
                "symbol": "ACME",
                "as_of_date": "2026-07-20",
                "thesis_status": "actionable_shadow_thesis",
                "direction": "bullish",
                "trade_intent": "long_call",
                "setup_quality_score": 0.8,
                "reward_risk_ratio": 2.0,
                "equity_bullish_score": 0.8,
                "equity_bearish_score": 0.2,
                "entry_reference_price": 100.0,
                "invalidation_price": 90.0,
                "target_price": 120.0,
                "expected_hold_trading_days": 10,
                "strategy_promotion_allowed": True,
                "not_edge_evidence": False,
                "earnings_evidence": _earnings_evidence("2026-07-20"),
                "reason_codes": ["fixture"],
            }
        ],
    )
    _write_jsonl(
        tmp_path
        / "artifacts"
        / "dopey"
        / "equity_swing"
        / "strategic_option_contracts.jsonl",
        [],
    )
    gateway = AmbiguousPlacementGateway(
        AccountSnapshot(
            authenticated=True,
            account_type="individual",
            buying_power_usd=1_000.0,
            total_equity_usd=1_000.0,
            equity_positions=(),
            option_positions=(),
            recent_equity_orders=(),
            recent_option_orders=(),
            equity_order_history_complete=True,
            option_order_history_complete=True,
            error="",
        )
    )
    now_utc = datetime(2026, 7, 21, 15, 0, tzinfo=timezone.utc)

    first = run_live_branch_cycle(tmp_path, gateway, now_utc, True)
    second = run_live_branch_cycle(tmp_path, gateway, now_utc, True)

    assert gateway.snapshot_call_count == 1
    assert gateway.placement_call_count == 1
    assert first["cycle_status"] == "complete_with_blocked_orders"
    assert first["orders"][0]["status"] == (
        "ambiguous_submission_manual_reconciliation_required"
    )
    assert second["cycle_status"] == "blocked_unresolved_submission_no_exit_intents"
    assert (
        second["order_history_blocker"]
        == "local_live_order_submission_unresolved"
    )
    twin_records = read_ledger(paper_twin_path(tmp_path))
    paper_execution = next(
        record
        for record in twin_records
        if record["event_type"] == "paper_twin_execution_observed"
    )
    assert paper_execution["payload"]["result_bearing"] is True
    assert paper_execution["payload"]["independent_of_live_result"] is True
    assert paper_execution["payload"]["paper_fill_status"] == "simulated_filled"
    assert paper_execution["payload"]["paper_filled_quantity"] > 0.0
    assert paper_execution["payload"]["paper_average_fill_price"] == 100.2
    twin_outcome = twin_records[-1]
    assert twin_outcome["event_type"] == "paper_twin_outcome_observed"
    assert twin_outcome["payload"]["paper_twin_outcome_status"] == (
        "paper_twin_quarantined_ambiguous_live_submission"
    )
    assert twin_outcome["payload"]["live_order_placed"] is None
    assert twin_outcome["payload"]["paper_fill_status"] == "not_simulated"
    assert twin_outcome["payload"]["no_fill_inferred"] is True
    assert twin_outcome["payload"]["result_bearing"] is False
    assert twin_outcome["payload"]["comparison_only"] is True


def test_order_history_guard_blocks_unattributed_broker_order(tmp_path: Path) -> None:
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_000.0,
        equity_positions=(),
        option_positions=(),
        recent_equity_orders=(
            {
                "order_id": "manual-order-1",
                "symbol": "ACME",
                "side": "buy",
                "status": "filled",
                "market_date": "2026-07-21",
            },
        ),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )

    assert (
        _order_history_blocker(tmp_path, account, "2026-07-21", False)
        == "broker_history_contains_unattributed_order"
    )


def test_exit_quantity_is_capped_to_dopey_attributed_fill(tmp_path: Path) -> None:
    opened = _equity_intent()
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": opened.intent_id,
            "instrument": opened.instrument,
            "symbol": opened.symbol,
            "side": opened.side,
            "market_date": "2026-07-20",
            "order_id": "broker-order-1",
            "status": "filled",
            "filled_quantity": 4.0,
            "placed": True,
            "intent": opened.to_dict(),
        },
    )
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=1_200.0,
        equity_positions=({"symbol": "ACME", "quantity": 10.0, "market_price": 115.0},),
        option_positions=(),
        recent_equity_orders=(),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )

    assert _position_ownership_blocker(tmp_path, account) == ""
    exits = _build_exit_intents(tmp_path, account, date(2026, 7, 21))
    assert len(exits) == 1
    assert exits[0].quantity == 4.0


def test_position_ownership_blocks_when_account_quantity_is_too_small(
    tmp_path: Path,
) -> None:
    opened = _equity_intent()
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": opened.intent_id,
            "instrument": opened.instrument,
            "symbol": opened.symbol,
            "side": opened.side,
            "market_date": "2026-07-20",
            "order_id": "broker-order-1",
            "status": "filled",
            "filled_quantity": 10.0,
            "placed": True,
            "intent": opened.to_dict(),
        },
    )
    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=0.0,
        total_equity_usd=500.0,
        equity_positions=({"symbol": "ACME", "quantity": 5.0, "market_price": 100.0},),
        option_positions=(),
        recent_equity_orders=(),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
    )

    assert (
        _position_ownership_blocker(tmp_path, account)
        == "broker_position_below_locally_attributed_quantity"
    )


@pytest.mark.parametrize(
    ("overrides", "error_match"),
    [
        ({"review_succeeded": False}, "successful_review"),
        ({"order_id": ""}, "broker_order_id"),
        ({"status": "mystery"}, "recognized_placed_status"),
        ({"status": "filled", "filled_quantity": 0.0}, "positive_filled_quantity"),
    ],
)
def test_gateway_rejects_contradictory_placed_results(
    overrides: dict[str, object],
    error_match: str,
) -> None:
    intent = replace(
        _equity_intent(),
        order_type="limit",
        limit_price=100.20,
    )
    calls = _attested_limit_order_calls(intent)
    payload: dict[str, object] = {
        "order_history_complete": True,
        "review_succeeded": True,
        "placed": True,
        "order_id": "broker-order-1",
        "status": "queued",
        "filled_quantity": 0.0,
        "average_fill_price": 0.0,
        "submitted_at": "2026-07-21T14:30:00+00:00",
        "filled_at": "",
        "warnings": [],
        "error": "",
        "observed_tools": ["review_equity_order", "place_equity_order"],
        "observed_tool_call_counts": {
            "review_equity_order": 1,
            "place_equity_order": 1,
        },
    }
    payload.update(overrides)

    with pytest.raises(RobinhoodPlacementAmbiguousError, match=error_match):
        _gateway_order_result(
            payload,
            "review_equity_order",
            "place_equity_order",
            intent,
            calls,
            "agentic-account-id",
        )


def test_gateway_accepts_definitive_pretrade_abstention() -> None:
    intent = replace(
        _equity_intent(),
        order_type="limit",
        limit_price=100.20,
    )
    result = _gateway_order_result(
        {
            "order_history_complete": True,
            "review_succeeded": False,
            "placed": False,
            "order_id": "",
            "status": "blocked_not_tradable",
            "filled_quantity": 0.0,
            "average_fill_price": 0.0,
            "submitted_at": "",
            "filled_at": "",
            "warnings": [],
            "error": "instrument is not tradable",
            "observed_tools": [],
            "observed_tool_call_counts": {},
        },
        "review_equity_order",
        "place_equity_order",
        intent,
        (),
        "agentic-account-id",
    )

    assert result.placed is False
    assert result.status == "blocked_not_tradable"


def test_gateway_rejects_malformed_nonplaced_result() -> None:
    intent = replace(
        _equity_intent(),
        order_type="limit",
        limit_price=100.20,
    )
    with pytest.raises(RobinhoodGatewayError, match="omitted status"):
        _gateway_order_result(
            {
                "order_history_complete": True,
                "review_succeeded": False,
                "placed": False,
                "order_id": "",
                "status": "",
                "warnings": [],
                "error": "",
                "observed_tools": [],
                "observed_tool_call_counts": {},
            },
            "review_equity_order",
            "place_equity_order",
            intent,
            (),
            "agentic-account-id",
        )
