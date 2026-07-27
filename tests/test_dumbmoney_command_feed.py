from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import dopey_live.service as live_service
from dopey_live.dumbmoney_authority import (
    VerifiedCapitalAuthority,
    canonical_json_bytes,
)
from dopey_live.dumbmoney_command_feed import (
    CommandFeedHttpRequest,
    CommandFeedHttpResponse,
    poll_once,
)
from dopey_live.ledger import append_record, ledger_path, read_ledger
from dopey_live.dumbmoney_promotion import VerifiedPromotionBinding
from dopey_live.models import (
    AccountSnapshot,
    GatewayCancelResult,
    GatewayOrderResult,
    LiveExecutionIntent,
)
from dopey_live.service import run_live_branch_cycle


NOW = datetime(2099, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
ACCOUNT_HASH = "c" * 64
STRATEGY_HASH = "a" * 64
PASSPORT_HASH = "d" * 64
PROMOTION_HASH = "f" * 64
ZERO_DIGEST = "0" * 64
TEST_REQUEST_NONCE = "7" * 64


def _format_utc(value: datetime) -> str:
    rendered = value.astimezone(timezone.utc).isoformat(
        timespec="microseconds" if value.microsecond else "seconds"
    )
    return rendered.replace("+00:00", "Z")


def _sign(
    private_key: Ed25519PrivateKey,
    body: dict[str, Any],
    *,
    source_sequence: int,
    not_before: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    public_key = private_key.public_key().public_bytes_raw()
    unsigned: dict[str, Any] = {
        "schema": "dumbmoney.signed-envelope.v1",
        "source_id": "dumbmoney-core",
        "source_sequence": source_sequence,
        "correlation_id": "feed-test",
        "causation_id": None,
        "nonce": f"feed-test-{source_sequence}",
        "not_before": _format_utc(not_before),
        "expires_at": _format_utc(expires_at),
        "body_schema": body["schema"],
        "body_digest": hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
        "body": body,
        "signature_algorithm": "Ed25519",
        "signer_key_id": hashlib.sha256(public_key).hexdigest(),
    }
    event_material = dict(unsigned)
    unsigned["event_id"] = hashlib.sha256(
        canonical_json_bytes(event_material)
    ).hexdigest()
    signature = private_key.sign(canonical_json_bytes(unsigned))
    return {
        **unsigned,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def _kill_body(active: bool, generation: int = 1) -> dict[str, Any]:
    return {
        "schema": "dumbmoney.kill-state.v1",
        "active": active,
        "generation": generation,
        "reason": "feed test kill state",
        "changed_by": "owner",
        "policy_epoch": 1,
        "changed_at": _format_utc(NOW - timedelta(seconds=1)),
    }


def _mode_body(mode: str = "LIVE", revision: int = 1) -> dict[str, Any]:
    return {
        "schema": "dumbmoney.desired-mode.v1",
        "venue": "dopey_robinhood",
        "mode": mode,
        "revision": revision,
        "reason": "feed test desired mode",
        "policy_epoch": 1,
        "not_before": _format_utc(NOW - timedelta(seconds=5)),
        "expires_at": _format_utc(NOW + timedelta(minutes=10)),
    }


def _capital_body(generation: int = 1) -> dict[str, Any]:
    return {
        "schema": "dumbmoney.capital-envelope.v1",
        "envelope_id": hashlib.sha256(f"capital-{generation}".encode()).hexdigest(),
        "mandate_id": "9" * 64,
        "venue": "dopey_robinhood",
        "account_hash": ACCOUNT_HASH,
        "strategy_hashes": [STRATEGY_HASH],
        "passport_hashes": [PASSPORT_HASH],
        "promotion_hashes": [PROMOTION_HASH],
        "authorized_instruments": ["equity:ACME"],
        "authorized_mode": "LIVE",
        "max_order_risk_cents": 100,
        "max_open_risk_cents": 500,
        "max_correlated_risk_cents": 300,
        "max_daily_loss_cents": 300,
        "max_open_orders": 1,
        "fencing_generation": generation,
        "policy_epoch": 1,
        "not_before": _format_utc(NOW),
        "expires_at": _format_utc(NOW + timedelta(seconds=60)),
    }


def _command(
    envelope: dict[str, Any],
    global_sequence: int,
    *,
    valid_now: bool = True,
) -> dict[str, Any]:
    body = envelope["body"]
    positive_grant = (
        body["schema"] == "dumbmoney.capital-envelope.v1"
        or (body["schema"] == "dumbmoney.desired-mode.v1" and body["mode"] == "LIVE")
        or (body["schema"] == "dumbmoney.kill-state.v1" and body["active"] is False)
    )
    return {
        "global_sequence": global_sequence,
        "event_id": envelope["event_id"],
        "body_schema": envelope["body_schema"],
        "valid_now": valid_now,
        "transport_window_current": valid_now,
        "authority_effect": (
            "APPLY_FAIL_CLOSED"
            if not positive_grant
            else "APPLY_POSITIVE"
            if valid_now
            else "HISTORICAL_ONLY"
        ),
        "envelope": envelope,
    }


def _page(
    commands: list[dict[str, Any]],
    *,
    checkpoint_key: Ed25519PrivateKey,
    request_nonce: str = TEST_REQUEST_NONCE,
    after_sequence: int = 0,
    after_digest: str = ZERO_DIGEST,
    next_sequence: int | None = None,
    next_digest: str | None = None,
    ledger_head_sequence: int | None = None,
    required_action: str = "APPLY_SIGNED_CONTROLS",
) -> dict[str, Any]:
    projected_commands: list[dict[str, Any]] = []
    previous_global_digest = after_digest
    for command in commands:
        envelope = command["envelope"]
        proof: dict[str, Any] = {
            "schema": "dumbmoney.ledger-event-proof.v1",
            "global_sequence": command["global_sequence"],
            "event_id": envelope["event_id"],
            "source_id": envelope["source_id"],
            "source_sequence": envelope["source_sequence"],
            "signer_key_id": envelope["signer_key_id"],
            "nonce": envelope["nonce"],
            "event_schema": envelope["body_schema"],
            "observed_at": _format_utc(NOW),
            "received_at": _format_utc(NOW),
            "correlation_id": envelope["correlation_id"],
            "causation_id": envelope["causation_id"],
            "payload_digest": envelope["body_digest"],
            "previous_source_digest": (
                ZERO_DIGEST
                if envelope["source_sequence"] == 1
                else hashlib.sha256(
                    (
                        f"source-head-{envelope['source_id']}-"
                        f"{envelope['source_sequence'] - 1}"
                    ).encode()
                ).hexdigest()
            ),
            "previous_global_digest": previous_global_digest,
        }
        event_core = {key: value for key, value in proof.items() if key != "schema"}
        event_digest = hashlib.sha256(canonical_json_bytes(event_core)).hexdigest()
        proof["event_digest"] = event_digest
        projected = {
            **command,
            "event_digest": event_digest,
            "ledger_proof": proof,
        }
        projected_commands.append(projected)
        previous_global_digest = event_digest
    resolved_next = (
        next_sequence
        if next_sequence is not None
        else (
            int(projected_commands[-1]["global_sequence"])
            if projected_commands
            else after_sequence
        )
    )
    resolved_digest = (
        next_digest
        if next_digest is not None
        else (
            str(projected_commands[-1]["event_digest"])
            if projected_commands
            and projected_commands[-1]["global_sequence"] == resolved_next
            else after_digest
        )
    )
    head = ledger_head_sequence if ledger_head_sequence is not None else resolved_next
    head_digest = (
        resolved_digest
        if head == resolved_next
        else hashlib.sha256(f"ledger-head-{head}".encode()).hexdigest()
    )
    checkpoint = {
        "schema": "dumbmoney.cell-command-checkpoint.v1",
        "cell_id": "dopey_robinhood",
        "request_nonce": request_nonce,
        "after_sequence": after_sequence,
        "after_digest": after_digest,
        "ordered_commands": [
            {key: value for key, value in command.items() if key != "envelope"}
            for command in projected_commands
        ],
        "next_sequence": resolved_next,
        "next_digest": resolved_digest,
        "ledger_head_sequence": head,
        "ledger_head_digest": head_digest,
        "observed_at": _format_utc(NOW),
        "required_action": required_action,
    }
    signature = checkpoint_key.sign(canonical_json_bytes(checkpoint))
    checkpoint_public = checkpoint_key.public_key().public_bytes_raw()
    return {
        "schema": "dumbmoney.cell-command-page.v1",
        "cell_id": "dopey_robinhood",
        "request_nonce": request_nonce,
        "observed_at": _format_utc(NOW),
        "after_sequence": after_sequence,
        "after_digest": after_digest,
        "next_sequence": resolved_next,
        "next_digest": resolved_digest,
        "ledger_head_sequence": head,
        "ledger_head_digest": head_digest,
        "has_more": resolved_next < head,
        "required_action": required_action,
        "commands": projected_commands,
        "checkpoint": checkpoint,
        "checkpoint_signature": {
            "algorithm": "Ed25519",
            "signer_key_id": hashlib.sha256(checkpoint_public).hexdigest(),
            "signature": base64.urlsafe_b64encode(signature)
            .decode("ascii")
            .rstrip("="),
        },
    }


def _response(page: dict[str, Any], status: int = 200) -> CommandFeedHttpResponse:
    return CommandFeedHttpResponse(
        status=status,
        headers={"Content-Type": "application/json; charset=utf-8"},
        body=json.dumps(page, sort_keys=True, separators=(",", ":")).encode(),
    )


def _resign_checkpoint(
    page: dict[str, Any],
    checkpoint_key: Ed25519PrivateKey,
) -> None:
    signature = checkpoint_key.sign(canonical_json_bytes(page["checkpoint"]))
    public_key = checkpoint_key.public_key().public_bytes_raw()
    page["checkpoint_signature"] = {
        "algorithm": "Ed25519",
        "signer_key_id": hashlib.sha256(public_key).hexdigest(),
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


class QueueTransport:
    def __init__(
        self,
        *responses: CommandFeedHttpResponse | BaseException,
    ) -> None:
        self.responses = list(responses)
        self.requests: list[CommandFeedHttpRequest] = []

    def __call__(
        self,
        request: CommandFeedHttpRequest,
    ) -> CommandFeedHttpResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _poll(
    tmp_path: Path,
    transport: QueueTransport,
    core_public_key: bytes,
    operator_public_key: bytes,
    *,
    request_nonce: str = TEST_REQUEST_NONCE,
):
    operator_key_id = hashlib.sha256(operator_public_key).hexdigest()
    with patch(
        "dopey_live.dumbmoney_command_feed.secrets.token_hex",
        return_value=request_nonce,
    ):
        return poll_once(
            base_url="http://127.0.0.1:8765",
            cell_bearer_provider=(
                lambda: "dopey-cell-token-with-adequate-entropy-123456"
            ),
            trusted_public_key=core_public_key,
            trusted_operator_public_keys={
                operator_key_id: operator_public_key,
            },
            expected_account_hash=ACCOUNT_HASH,
            state_path=tmp_path / "command-state.json",
            transport=transport,
            now_utc=NOW,
        )


def test_mode_and_capital_dispatch_survive_restart_cursor(tmp_path: Path) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    kill = _sign(
        operator_key,
        _kill_body(False),
        source_sequence=1,
        not_before=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    mode = _sign(
        operator_key,
        _mode_body(),
        source_sequence=2,
        not_before=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    capital = _sign(
        core_key,
        _capital_body(),
        source_sequence=3,
        not_before=NOW,
        expires_at=NOW + timedelta(seconds=60),
    )
    commands = [
        _command(kill, 1),
        _command(mode, 2),
        _command(capital, 3),
    ]
    first_page = _page(commands, checkpoint_key=core_key)
    first_transport = QueueTransport(_response(first_page))

    first = _poll(
        tmp_path,
        first_transport,
        core_public_key,
        operator_public_key,
    )

    assert first.allow_new_risk is True
    assert first.desired_mode == "LIVE"
    assert first.kill_active is False
    assert first.capital_authority is not None
    assert (
        first.capital_authority.verify(NOW, ACCOUNT_HASH).event_id
        == (capital["event_id"])
    )
    assert first.next_sequence == 3
    request = first_transport.requests[0]
    assert request.method == "GET"
    assert request.headers["Authorization"].startswith("Bearer ")
    query = parse_qs(urlsplit(request.url).query)
    assert query == {
        "after": ["0"],
        "cursor": [ZERO_DIGEST],
        "limit": ["250"],
        "request_nonce": [TEST_REQUEST_NONCE],
    }

    second_page = _page(
        [],
        checkpoint_key=core_key,
        after_sequence=3,
        after_digest=first.next_digest,
        next_sequence=3,
        next_digest=first.next_digest,
    )
    second_transport = QueueTransport(_response(second_page))
    restarted = _poll(
        tmp_path,
        second_transport,
        core_public_key,
        operator_public_key,
    )

    assert restarted.allow_new_risk is True
    assert restarted.next_sequence == 3
    assert parse_qs(urlsplit(second_transport.requests[0].url).query)["after"] == ["3"]


@pytest.mark.parametrize(
    "case",
    ["checkpoint_signature", "ledger_proof"],
)
def test_checkpoint_and_ledger_proof_tamper_fail_closed(
    tmp_path: Path,
    case: str,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    kill = _sign(
        operator_key,
        _kill_body(True),
        source_sequence=1,
        not_before=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    page = _page(
        [_command(kill, 1)],
        checkpoint_key=core_key,
        required_action="CANCEL_AND_RECONCILE",
    )
    if case == "checkpoint_signature":
        page["checkpoint"]["required_action"] = "PAUSE_NEW_RISK"
    else:
        page["commands"][0]["ledger_proof"]["payload_digest"] = "e" * 64
        page["checkpoint"]["ordered_commands"][0]["ledger_proof"]["payload_digest"] = (
            "e" * 64
        )
        _resign_checkpoint(page, core_key)

    result = _poll(
        tmp_path,
        QueueTransport(_response(page)),
        core_public_key,
        operator_public_key,
    )

    assert result.allow_new_risk is False
    assert result.kill_active is True
    assert result.next_sequence == 0
    assert not (tmp_path / "command-state.json").exists()


def test_replayed_signed_page_under_different_request_nonce_fails_closed(
    tmp_path: Path,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    replayed_page = _page(
        [],
        checkpoint_key=core_key,
        request_nonce=TEST_REQUEST_NONCE,
        required_action="CANCEL_AND_RECONCILE",
    )
    transport = QueueTransport(_response(replayed_page))

    result = _poll(
        tmp_path,
        transport,
        core_key.public_key().public_bytes_raw(),
        operator_key.public_key().public_bytes_raw(),
        request_nonce="8" * 64,
    )

    assert result.allow_new_risk is False
    assert result.kill_active is True
    assert result.next_sequence == 0
    assert parse_qs(urlsplit(transport.requests[0].url).query)["request_nonce"] == [
        "8" * 64
    ]
    assert not (tmp_path / "command-state.json").exists()


@pytest.mark.parametrize("case", ["operator_control_by_core", "capital_by_operator"])
def test_command_schema_signer_role_mismatch_fails_closed(
    tmp_path: Path,
    case: str,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    if case == "operator_control_by_core":
        envelope = _sign(
            core_key,
            _kill_body(True),
            source_sequence=1,
            not_before=NOW - timedelta(seconds=5),
            expires_at=NOW + timedelta(minutes=10),
        )
        required_action = "CANCEL_AND_RECONCILE"
    else:
        envelope = _sign(
            operator_key,
            _capital_body(),
            source_sequence=1,
            not_before=NOW,
            expires_at=NOW + timedelta(seconds=60),
        )
        required_action = "PAUSE_NEW_RISK"
    page = _page(
        [_command(envelope, 1)],
        checkpoint_key=core_key,
        required_action=required_action,
    )

    result = _poll(
        tmp_path,
        QueueTransport(_response(page)),
        core_key.public_key().public_bytes_raw(),
        operator_key.public_key().public_bytes_raw(),
    )

    assert result.allow_new_risk is False
    assert result.kill_active is True
    assert result.next_sequence == 0
    assert not (tmp_path / "command-state.json").exists()


class KillGateway:
    def __init__(self, open_account: AccountSnapshot) -> None:
        self.account = open_account
        self.cancel_calls: list[tuple[str, str]] = []

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.account

    def cancel_order(
        self,
        instrument: str,
        order_id: str,
    ) -> GatewayCancelResult:
        self.cancel_calls.append((instrument, order_id))
        canceled_order = {
            **self.account.recent_equity_orders[0],
            "status": "canceled",
        }
        self.account = AccountSnapshot(
            **{
                **self.account.to_dict(),
                "recent_equity_orders": (canceled_order,),
            }
        )
        return GatewayCancelResult(
            cancel_requested=True,
            order_id=order_id,
            status="cancel_requested",
            warnings=(),
            error="",
            observed_tools=("cancel_equity_order",),
        )


def _account_with_open_order() -> AccountSnapshot:
    return AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=100.0,
        total_equity_usd=100.0,
        equity_positions=(),
        option_positions=(),
        recent_equity_orders=(
            {
                "order_id": "order-1",
                "symbol": "ACME",
                "side": "buy",
                "status": "open",
                "market_date": "2099-01-01",
                "submitted_at": "2099-01-01T00:00:00Z",
                "filled_at": "",
                "filled_quantity": 0.0,
                "average_fill_price": 0.0,
            },
        ),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
        account_hash=ACCOUNT_HASH,
    )


def _entry_intent() -> LiveExecutionIntent:
    return LiveExecutionIntent(
        intent_id="feed-race-entry",
        instrument="equity",
        symbol="ACME",
        side="buy",
        order_type="limit",
        limit_price=100.0,
        time_in_force="day",
        extended_hours=False,
        notional_usd=1.0,
        quantity=0.01,
        source_as_of_date="2098-12-31",
        source_hash=STRATEGY_HASH,
        thesis_direction="bullish",
        analysis_symbol="ACME",
        analysis_relationship="self",
        analysis_reference_price=100.0,
        analysis_invalidation_price=90.0,
        analysis_target_price=120.0,
        daily_leverage_multiple=1.0,
        daily_reset=False,
        maximum_holding_sessions=5,
        reference_price=100.0,
        invalidation_price=90.0,
        target_price=120.0,
        expected_hold_trading_days=5,
        execution_snapshot=None,
        option_contract={},
        reason_codes=("feed-race-fixture",),
        promotion_hash=PROMOTION_HASH,
        passport_hash=PASSPORT_HASH,
    )


class RevocationRaceGateway:
    def __init__(self, account: AccountSnapshot) -> None:
        self.account = account
        self.placement_calls = 0
        self.guard_calls = 0

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.account

    def get_equity_execution_snapshot(
        self,
        _intent: LiveExecutionIntent,
    ) -> object:
        return object()

    def place_order(
        self,
        _intent: LiveExecutionIntent,
        _paper_twin_record_hash: str,
        *,
        pre_submit_guard: Callable[[], datetime],
    ) -> GatewayOrderResult:
        pre_submit_guard()
        self.guard_calls += 1
        self.placement_calls += 1
        return GatewayOrderResult(
            review_succeeded=True,
            placed=True,
            order_id="broker-order-race-1",
            status="queued",
            filled_quantity=0.0,
            average_fill_price=0.0,
            submitted_at=_format_utc(NOW),
            filled_at="",
            warnings=(),
            error="",
            observed_tools=("review_equity_order", "place_equity_order"),
        )


class StaticPromotionResolver:
    def bind_intent(
        self,
        authority: VerifiedCapitalAuthority,
        intent: LiveExecutionIntent,
        _now_utc: datetime,
        *,
        expected_binding: VerifiedPromotionBinding | None = None,
    ) -> tuple[LiveExecutionIntent, VerifiedPromotionBinding]:
        binding = VerifiedPromotionBinding(
            strategy_hash=STRATEGY_HASH,
            passport_hash=PASSPORT_HASH,
            promotion_hash=PROMOTION_HASH,
            instrument_id="equity:ACME",
            maximum_loss_cents=100,
            policy_epoch=authority.envelope.policy_epoch,
            capital_envelope_id=authority.envelope.envelope_id,
            capital_event_id=authority.event_id,
            capital_body_digest=authority.body_digest,
            capital_fencing_generation=authority.envelope.fencing_generation,
            passport_event_id="4" * 64,
            promotion_event_id="5" * 64,
            passport_signer_key_id="6" * 64,
            promotion_signer_key_id="7" * 64,
            expires_at=authority.envelope.expires_at,
        )
        if expected_binding is not None:
            assert binding == expected_binding
        return intent, binding


def test_kill_arriving_during_atomic_write_is_ambiguous_and_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    initial_commands = [
        _command(
            _sign(
                operator_key,
                _kill_body(False),
                source_sequence=1,
                not_before=NOW - timedelta(seconds=5),
                expires_at=NOW + timedelta(minutes=10),
            ),
            1,
        ),
        _command(
            _sign(
                operator_key,
                _mode_body(),
                source_sequence=2,
                not_before=NOW - timedelta(seconds=5),
                expires_at=NOW + timedelta(minutes=10),
            ),
            2,
        ),
        _command(
            _sign(
                core_key,
                _capital_body(),
                source_sequence=3,
                not_before=NOW,
                expires_at=NOW + timedelta(seconds=60),
            ),
            3,
        ),
    ]
    initial = _poll(
        tmp_path,
        QueueTransport(_response(_page(initial_commands, checkpoint_key=core_key))),
        core_public_key,
        operator_public_key,
    )
    assert initial.allow_new_risk is True

    kill_during_write = _sign(
        operator_key,
        _kill_body(True, generation=2),
        source_sequence=4,
        not_before=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    refresh_transport = QueueTransport(
        _response(
            _page(
                [],
                checkpoint_key=core_key,
                after_sequence=3,
                after_digest=initial.next_digest,
                next_sequence=3,
                next_digest=initial.next_digest,
            )
        ),
        _response(
            _page(
                [_command(kill_during_write, 4)],
                checkpoint_key=core_key,
                after_sequence=3,
                after_digest=initial.next_digest,
                required_action="CANCEL_AND_RECONCILE",
            )
        ),
    )

    def refresh(_now_utc: datetime):
        return _poll(
            tmp_path,
            refresh_transport,
            core_public_key,
            operator_public_key,
        )

    account = AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=100.0,
        total_equity_usd=100.0,
        equity_positions=(),
        option_positions=(),
        recent_equity_orders=(),
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
        account_hash=ACCOUNT_HASH,
    )
    gateway = RevocationRaceGateway(account)
    intent = _entry_intent()
    monkeypatch.setattr(
        live_service,
        "load_live_branch_control",
        lambda: SimpleNamespace(
            live_branch_enabled=True,
            stock_execution_enabled=True,
            options_execution_enabled=False,
            use_full_available_balance=False,
        ),
    )
    monkeypatch.setattr(
        live_service,
        "_robinhood_stock_submission_state",
        lambda _now: (True, "2099-01-01", True),
    )
    monkeypatch.setattr(
        live_service,
        "research_maturity_blockers",
        lambda _root: (),
    )
    monkeypatch.setattr(
        live_service,
        "build_entry_intents",
        lambda *_args, **_kwargs: (intent,),
    )
    monkeypatch.setattr(
        live_service,
        "prepare_equity_entry_for_execution",
        lambda *_args, **_kwargs: intent,
    )

    missing_refresh = run_live_branch_cycle(
        tmp_path,
        gateway,  # type: ignore[arg-type]
        NOW,
        True,
        dumbmoney_controls=initial,
        authority_clock=lambda: NOW,
    )
    assert missing_refresh["new_exposure_allowed"] is False
    assert missing_refresh["cancel_only_reason"] == (
        "dumbmoney_command_feed_refresh_missing_at_broker_sink"
    )
    assert gateway.placement_calls == 0

    result = run_live_branch_cycle(
        tmp_path,
        gateway,  # type: ignore[arg-type]
        NOW,
        True,
        dumbmoney_controls=initial,
        dumbmoney_control_refresh=refresh,
        dumbmoney_promotion_resolver=StaticPromotionResolver(),
        authority_clock=lambda: NOW,
    )

    assert gateway.guard_calls == 1
    assert gateway.placement_calls == 1
    assert len(refresh_transport.requests) == 2
    assert result["orders"][0]["status"] == ("ambiguous_in_flight_authority_revoked")
    assert result["orders"][0]["placement_retried"] is False
    event_types = [
        str(record["event_type"]) for record in read_ledger(ledger_path(tmp_path))
    ]
    assert event_types.index("dumbmoney_order_dispatching") < event_types.index(
        "live_order_submission_ambiguous"
    )
    assert "live_order_result" not in event_types


def test_signed_kill_delivery_enters_existing_cancel_only_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    kill = _sign(
        operator_key,
        _kill_body(True),
        source_sequence=1,
        not_before=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    dispatch = _poll(
        tmp_path,
        QueueTransport(
            _response(
                _page(
                    [_command(kill, 1)],
                    checkpoint_key=core_key,
                    required_action="CANCEL_AND_RECONCILE",
                )
            )
        ),
        core_public_key,
        operator_public_key,
    )
    assert dispatch.kill_active is True
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": "intent-1",
            "instrument": "equity",
            "placed": True,
            "order_id": "order-1",
            "status": "open",
        },
    )
    monkeypatch.setattr(
        live_service,
        "load_live_branch_control",
        lambda: SimpleNamespace(live_branch_enabled=False),
    )
    monkeypatch.setattr(
        live_service,
        "_robinhood_stock_submission_state",
        lambda _now: (True, "2099-01-01", True),
    )
    gateway = KillGateway(_account_with_open_order())

    result = run_live_branch_cycle(
        tmp_path,
        gateway,  # type: ignore[arg-type]
        NOW,
        True,
        dumbmoney_controls=dispatch,
    )

    assert result["authority_state"] == "CANCEL_ONLY_DEGRADED"
    assert result["kill_active"] is True
    assert gateway.cancel_calls == [("equity", "order-1")]
    assert result["new_exposure_allowed"] is False


@pytest.mark.parametrize("case", ["tamper", "generation_gap"])
def test_tamper_and_generation_gap_do_not_advance_cursor(
    tmp_path: Path,
    case: str,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    generation = 2 if case == "generation_gap" else 1
    kill = _sign(
        operator_key,
        _kill_body(True, generation),
        source_sequence=1,
        not_before=NOW - timedelta(seconds=5),
        expires_at=NOW + timedelta(minutes=10),
    )
    if case == "tamper":
        kill["body"]["reason"] = "tampered"

    result = _poll(
        tmp_path,
        QueueTransport(
            _response(
                _page(
                    [_command(kill, 1)],
                    checkpoint_key=core_key,
                )
            )
        ),
        core_public_key,
        operator_public_key,
    )

    assert result.allow_new_risk is False
    assert result.kill_active is True
    assert result.next_sequence == 0
    assert not (tmp_path / "command-state.json").exists()


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (
            CommandFeedHttpResponse(
                status=401,
                headers={"Content-Type": "application/json"},
                body=b"{}",
            ),
            "authentication",
        ),
        (TimeoutError("fixture transport timeout"), "transport"),
    ],
)
def test_auth_and_transport_failure_are_fail_closed_unknown_kill(
    tmp_path: Path,
    response: CommandFeedHttpResponse | BaseException,
    reason: str,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    result = _poll(
        tmp_path,
        QueueTransport(response),
        core_key.public_key().public_bytes_raw(),
        operator_key.public_key().public_bytes_raw(),
    )

    assert result.allow_new_risk is False
    assert result.kill_active is True
    assert reason in result.fail_closed_reason
    assert result.next_sequence == 0


def test_expired_active_kill_bootstrap_advances_and_remains_active(
    tmp_path: Path,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    kill = _sign(
        operator_key,
        _kill_body(True),
        source_sequence=1,
        not_before=NOW - timedelta(minutes=10),
        expires_at=NOW - timedelta(minutes=5),
    )
    first_page = _page(
        [_command(kill, 1, valid_now=False)],
        checkpoint_key=core_key,
        required_action="CANCEL_AND_RECONCILE",
    )

    first = _poll(
        tmp_path,
        QueueTransport(_response(first_page)),
        core_public_key,
        operator_public_key,
    )

    assert first.next_sequence == 1
    assert first.kill_active is True
    assert first.allow_new_risk is False
    persisted = json.loads(
        (tmp_path / "command-state.json").read_text(encoding="utf-8")
    )
    assert persisted["next_sequence"] == 1
    assert persisted["kill_envelope"]["event_id"] == kill["event_id"]

    restart_page = _page(
        [],
        checkpoint_key=core_key,
        after_sequence=1,
        after_digest=first.next_digest,
        next_sequence=1,
        next_digest=first.next_digest,
        required_action="CANCEL_AND_RECONCILE",
    )
    restarted = _poll(
        tmp_path,
        QueueTransport(_response(restart_page)),
        core_public_key,
        operator_public_key,
    )
    assert restarted.kill_active is True
    assert restarted.next_sequence == 1


def test_page_omission_or_cursor_mismatch_never_reuses_positive_authority(
    tmp_path: Path,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    operator_key = Ed25519PrivateKey.generate()
    core_public_key = core_key.public_key().public_bytes_raw()
    operator_public_key = operator_key.public_key().public_bytes_raw()
    mismatched = _page(
        [],
        checkpoint_key=core_key,
        after_sequence=1,
        after_digest="1" * 64,
        next_sequence=1,
        next_digest="1" * 64,
    )

    result = _poll(
        tmp_path,
        QueueTransport(_response(mismatched)),
        core_public_key,
        operator_public_key,
    )

    assert result.allow_new_risk is False
    assert result.kill_active is True
    assert result.next_sequence == 0
