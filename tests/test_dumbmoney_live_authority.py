from __future__ import annotations

import base64
import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dopey_live.dumbmoney_authority import (
    DumbMoneyAuthorityContext,
    DumbMoneyAuthorityError,
    account_open_risk_cents,
    authorize_intent,
    authorized_settled_cash_usd,
    canonical_json_bytes,
    verify_signed_capital_envelope,
    _urlsafe_b64decode,
)
from dopey_live.ledger import (
    LiveBranchLedgerError,
    activate_dumbmoney_fence,
    append_record,
    assert_current_dumbmoney_fence,
    ledger_path,
    read_ledger,
)
from dopey_live.models import (
    AccountSnapshot,
    GatewayCancelResult,
    LiveExecutionIntent,
)
from dopey_live.robinhood_gateway import (
    McpToolCallEvidence,
    RobinhoodAgenticGateway,
    RobinhoodCancellationAmbiguousError,
    RobinhoodGatewayError,
    _canonical_raw_broker_item,
    _gateway_cancel_result,
    _validated_equity_position,
)
from dopey_live.service import (
    _poll_ambiguous_placement_history,
    _run_cancel_only_degraded,
    _witnessed_daily_loss_cents,
)
from dopey_live.signals import LiveSignalError, validate_option_entry_for_execution
from operator_tools import operator_live_branch


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "dumbmoney" / "signed-capital-envelope.v1.json"
)
NEGATIVE_CAP_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "dumbmoney"
    / "capital-envelope-cap-order-negative.v1.json"
)
FIXTURE_FILE_SHA256 = "b0fe2fa0261b2dc36e4043e8c33b91b1016676e04a25e4b4d5bd66eea0c9079a"
NOW = datetime(2099, 1, 1, 0, 0, 30, tzinfo=timezone.utc)


def _fixture() -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    public_key = base64.urlsafe_b64decode(
        fixture["public_key_base64url"]
        + "=" * (-len(fixture["public_key_base64url"]) % 4)
    )
    return fixture["envelope"], public_key, fixture


def _account(
    *,
    orders: tuple[dict[str, Any], ...] = (),
    positions: tuple[dict[str, Any], ...] = (),
) -> AccountSnapshot:
    return AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=100.0,
        total_equity_usd=100.0,
        equity_positions=positions,
        option_positions=(),
        recent_equity_orders=orders,
        recent_option_orders=(),
        equity_order_history_complete=True,
        option_order_history_complete=True,
        error="",
        account_hash="c" * 64,
    )


def _equity_intent(
    *,
    notional_usd: float = 1.0,
    quantity: float = 0.01,
    promotion_hash: str | None = None,
    passport_hash: str | None = None,
) -> LiveExecutionIntent:
    return LiveExecutionIntent(
        intent_id="intent-1",
        instrument="equity",
        symbol="ACME",
        side="buy",
        order_type="limit",
        limit_price=100.0,
        time_in_force="day",
        extended_hours=False,
        notional_usd=notional_usd,
        quantity=quantity,
        source_as_of_date="2098-12-31",
        source_hash="a" * 64,
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
        reason_codes=("fixture",),
        promotion_hash=(
            promotion_hash
            or str(_fixture()[0]["body"].get("promotion_hashes", ["b" * 64])[0])
        ),
        passport_hash=(
            passport_hash
            or str(_fixture()[0]["body"].get("passport_hashes", ["b" * 64])[0])
        ),
    )


def test_blunder_signed_fixture_cross_validates_byte_for_byte() -> None:
    envelope, public_key, fixture = _fixture()
    signing_payload = {
        key: value for key, value in envelope.items() if key != "signature"
    }

    assert hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest() == (
        FIXTURE_FILE_SHA256
    )
    assert hashlib.sha256(canonical_json_bytes(signing_payload)).hexdigest() == (
        "97f8ecdf0d6b48b310c06cdeb37654fb171f4fa62bf91b427965191643d7ee1e"
    )
    assert fixture["signing_payload_sha256"] == (
        "97f8ecdf0d6b48b310c06cdeb37654fb171f4fa62bf91b427965191643d7ee1e"
    )
    assert envelope["body_digest"] == (
        "fcf86b4c257c0fea9ba65051366b76738563598d4217c4950ef3cf63ed1927d0"
    )
    assert envelope["event_id"] == (
        "95fd19cc7bcbc89fe3c7985ee04d502704344b2f09c1eb6dce575b41c0ae579c"
    )
    assert envelope["body"]["promotion_hashes"] == ["f" * 64]
    assert envelope["body"]["authorized_instruments"] == ["equity:ACME"]
    authority = verify_signed_capital_envelope(
        envelope,
        public_key,
        NOW,
        "c" * 64,
    )

    assert authority.event_id == envelope["event_id"]
    assert authority.envelope.venue == "dopey_robinhood"
    assert authority.envelope.fencing_generation == 7


def test_signed_envelope_rejects_tamper_expiry_and_wrong_account() -> None:
    envelope, public_key, _ = _fixture()
    tampered = json.loads(json.dumps(envelope))
    tampered["body"]["max_order_risk_cents"] = 200

    with pytest.raises(DumbMoneyAuthorityError, match="body digest mismatch"):
        verify_signed_capital_envelope(tampered, public_key, NOW, "c" * 64)
    with pytest.raises(DumbMoneyAuthorityError, match="not currently valid"):
        verify_signed_capital_envelope(
            envelope,
            public_key,
            datetime(2099, 1, 1, 0, 1, tzinfo=timezone.utc),
            "c" * 64,
        )
    with pytest.raises(DumbMoneyAuthorityError, match="different account"):
        verify_signed_capital_envelope(envelope, public_key, NOW, "d" * 64)


def test_authority_file_requires_strict_canonical_json(tmp_path: Path) -> None:
    envelope, public_key, _ = _fixture()
    envelope_path = tmp_path / "capital-envelope.json"
    public_key_path = tmp_path / "core.pub"
    envelope_path.write_bytes(canonical_json_bytes(envelope))
    public_key_path.write_bytes(public_key)

    context = DumbMoneyAuthorityContext.from_files(
        envelope_path,
        public_key_path,
        "c" * 64,
    )

    assert context.signed_envelope == envelope
    assert context.trusted_public_key == public_key


@pytest.mark.parametrize(
    "raw, match",
    [
        (
            b'{"schema":"first","schema":"second"}',
            "duplicate JSON key",
        ),
        (
            b'{"body":{"schema":"first","schema":"second"}}',
            "duplicate JSON key",
        ),
        (
            b'{"value":NaN}',
            "non-finite JSON number",
        ),
        (
            b'{"value":Infinity}',
            "non-finite JSON number",
        ),
        (
            b'{"value":1e9999}',
            "non-finite JSON number",
        ),
        (
            b'{"value":1.5}',
            "float outside the signed integer domain",
        ),
    ],
)
def test_authority_file_rejects_ambiguous_json(
    tmp_path: Path,
    raw: bytes,
    match: str,
) -> None:
    envelope_path = tmp_path / "capital-envelope.json"
    public_key_path = tmp_path / "core.pub"
    envelope_path.write_bytes(raw)
    public_key_path.write_bytes(b"x" * 32)

    with pytest.raises(DumbMoneyAuthorityError, match=match):
        DumbMoneyAuthorityContext.from_files(
            envelope_path,
            public_key_path,
            "c" * 64,
        )


def test_authority_file_rejects_noncanonical_bytes(tmp_path: Path) -> None:
    envelope, public_key, _ = _fixture()
    envelope_path = tmp_path / "capital-envelope.json"
    public_key_path = tmp_path / "core.pub"
    envelope_path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    public_key_path.write_bytes(public_key)

    with pytest.raises(DumbMoneyAuthorityError, match="exact canonical JSON bytes"):
        DumbMoneyAuthorityContext.from_files(
            envelope_path,
            public_key_path,
            "c" * 64,
        )


def test_monotonic_fence_survives_local_lock_reacquisition(tmp_path: Path) -> None:
    activate_dumbmoney_fence(
        tmp_path,
        "e" * 64,
        "1" * 64,
        "2" * 64,
        7,
        1,
    )
    activate_dumbmoney_fence(
        tmp_path,
        "e" * 64,
        "1" * 64,
        "2" * 64,
        7,
        1,
    )
    assert_current_dumbmoney_fence(
        tmp_path,
        "e" * 64,
        "1" * 64,
        "2" * 64,
        7,
        1,
    )

    with pytest.raises(LiveBranchLedgerError, match="newer generation"):
        activate_dumbmoney_fence(
            tmp_path,
            "f" * 64,
            "2" * 64,
            "3" * 64,
            6,
            1,
        )
    with pytest.raises(LiveBranchLedgerError, match="reused"):
        activate_dumbmoney_fence(
            tmp_path,
            "e" * 64,
            "9" * 64,
            "2" * 64,
            7,
            1,
        )
    with pytest.raises(LiveBranchLedgerError, match="reused"):
        activate_dumbmoney_fence(
            tmp_path,
            "e" * 64,
            "1" * 64,
            "8" * 64,
            7,
            1,
        )

    activate_dumbmoney_fence(
        tmp_path,
        "f" * 64,
        "3" * 64,
        "4" * 64,
        8,
        2,
    )
    with pytest.raises(LiveBranchLedgerError, match="no longer"):
        assert_current_dumbmoney_fence(
            tmp_path,
            "e" * 64,
            "1" * 64,
            "2" * 64,
            7,
            1,
        )


def test_capital_intersects_settled_cash_open_risk_and_order_limit() -> None:
    envelope, public_key, _ = _fixture()
    authority = verify_signed_capital_envelope(envelope, public_key, NOW, "c" * 64)
    account = _account()

    assert authorized_settled_cash_usd(authority, account, 100.0, 0) == 3.0
    assert authorize_intent(authority, account, _equity_intent(), 0) == 100

    with pytest.raises(DumbMoneyAuthorityError, match="max_order_risk"):
        authorize_intent(
            authority,
            account,
            _equity_intent(notional_usd=2.0, quantity=0.02),
            0,
        )
    exposed = _account(
        positions=(
            {
                "symbol": "ACME",
                "quantity": 1.0,
                "average_cost": 2.5,
                "market_price": 2.5,
                "market_value": 2.5,
                "unrealized_pnl": 0.0,
            },
        )
    )
    assert account_open_risk_cents(exposed) == 250
    assert authorized_settled_cash_usd(authority, exposed, 100.0, 0) == 0.5


def test_intent_requires_exact_instrument_promotion_and_daily_loss_headroom() -> None:
    envelope, public_key, _ = _fixture()
    authority = verify_signed_capital_envelope(envelope, public_key, NOW, "c" * 64)
    intent = _equity_intent()

    assert authorize_intent(authority, _account(), intent, 200) == 100
    with pytest.raises(DumbMoneyAuthorityError, match="daily-loss capacity"):
        authorize_intent(authority, _account(), intent, 201)
    with pytest.raises(DumbMoneyAuthorityError, match="daily-loss capacity"):
        authorize_intent(authority, _account(), intent, 299)
    with pytest.raises(DumbMoneyAuthorityError, match="promotion hash"):
        authorize_intent(
            authority,
            _account(),
            replace(intent, promotion_hash="e" * 64),
            0,
        )
    with pytest.raises(DumbMoneyAuthorityError, match="passport hash"):
        authorize_intent(
            authority,
            _account(),
            replace(intent, passport_hash="e" * 64),
            0,
        )
    with pytest.raises(DumbMoneyAuthorityError, match="exact broker instrument"):
        authorize_intent(
            authority,
            _account(),
            replace(
                intent,
                symbol="OTHER",
                analysis_symbol="OTHER",
            ),
            0,
        )


def test_sell_requires_exact_fresh_long_inventory_and_cannot_oversell() -> None:
    envelope, public_key, _ = _fixture()
    authority = verify_signed_capital_envelope(envelope, public_key, NOW, "c" * 64)
    exit_intent = replace(
        _equity_intent(quantity=1.0),
        side="sell",
        notional_usd=0.0,
    )
    holding = {
        "symbol": "ACME",
        "quantity": 1.0,
        "average_cost": 100.0,
        "market_price": 99.0,
        "market_value": 99.0,
        "unrealized_pnl": -1.0,
    }

    assert (
        authorize_intent(
            authority,
            _account(positions=(holding,)),
            exit_intent,
            None,
        )
        == 0
    )
    with pytest.raises(DumbMoneyAuthorityError, match="matching long"):
        authorize_intent(authority, _account(), exit_intent, None)
    with pytest.raises(DumbMoneyAuthorityError, match="oversell"):
        authorize_intent(
            authority,
            _account(positions=(holding,)),
            replace(exit_intent, quantity=1.01),
            None,
        )
    active_sell = {
        "order_id": "sell-open",
        "symbol": "ACME",
        "side": "sell",
        "status": "open",
        "market_date": "2099-01-01",
        "submitted_at": "2099-01-01T00:00:00Z",
        "filled_at": "",
        "filled_quantity": 0.0,
        "average_fill_price": 0.0,
    }
    with pytest.raises(DumbMoneyAuthorityError, match="active sell"):
        authorize_intent(
            authority,
            _account(orders=(active_sell,), positions=(holding,)),
            exit_intent,
            None,
        )


def test_daily_loss_and_existing_entry_order_fail_closed() -> None:
    envelope, public_key, _ = _fixture()
    authority = verify_signed_capital_envelope(envelope, public_key, NOW, "c" * 64)

    with pytest.raises(DumbMoneyAuthorityError, match="daily loss is required"):
        authorized_settled_cash_usd(authority, _account(), 100.0, None)
    with pytest.raises(DumbMoneyAuthorityError, match="max_daily_loss"):
        authorize_intent(authority, _account(), _equity_intent(), 300)

    active_entry = {
        "order_id": "open-buy",
        "symbol": "OTHER",
        "side": "buy",
        "status": "open",
        "market_date": "2099-01-01",
        "submitted_at": "2099-01-01T00:00:00+00:00",
        "filled_at": "",
        "filled_quantity": 0.0,
        "average_fill_price": 0.0,
    }
    with pytest.raises(DumbMoneyAuthorityError, match="active entry order"):
        authorize_intent(
            authority,
            _account(orders=(active_entry,)),
            _equity_intent(),
            0,
        )


def test_option_position_risk_uses_multiplier_and_rejects_missing_evidence() -> None:
    option_position = {
        "symbol": "ACME",
        "contract_id": "option-1",
        "quantity": 2.0,
        "average_cost": 1.25,
        "market_price": 1.0,
        "market_value": 200.0,
        "unrealized_pnl": -50.0,
    }
    account = AccountSnapshot(
        **{
            **_account().to_dict(),
            "option_positions": (option_position,),
        }
    )
    assert account_open_risk_cents(account) == 25_000

    incomplete = AccountSnapshot(
        **{
            **_account().to_dict(),
            "option_positions": (
                {
                    "symbol": "ACME",
                    "contract_id": "option-1",
                    "quantity": 1.0,
                },
            ),
        }
    )
    with pytest.raises(DumbMoneyAuthorityError, match="complete finite risk"):
        account_open_risk_cents(incomplete)


def _signed_capital_body(
    body: dict[str, Any],
    wrapper_not_before: str,
    wrapper_expires_at: str,
) -> tuple[dict[str, Any], bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    unsigned: dict[str, Any] = {
        "schema": "dumbmoney.signed-envelope.v1",
        "source_id": "dumbmoney-core",
        "source_sequence": 1,
        "correlation_id": "window-test",
        "causation_id": None,
        "nonce": "window-test-1",
        "not_before": wrapper_not_before,
        "expires_at": wrapper_expires_at,
        "body_schema": "dumbmoney.capital-envelope.v1",
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
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }, public_key


def _signed_envelope_for_window(
    wrapper_not_before: str,
    wrapper_expires_at: str,
    body_not_before: str,
    body_expires_at: str,
) -> tuple[dict[str, Any], bytes]:
    body = {
        **_fixture()[0]["body"],
        "not_before": body_not_before,
        "expires_at": body_expires_at,
        "account_hash": "c" * 64,
    }
    return _signed_capital_body(
        body,
        wrapper_not_before,
        wrapper_expires_at,
    )


def test_capital_envelope_cap_order_negative_fixture_fails_closed() -> None:
    fixture = json.loads(NEGATIVE_CAP_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_schema"] == (
        "dopey.dumbmoney-capital-envelope-negative-cases.v1"
    )
    cases = fixture["cases"]
    assert [case["name"] for case in cases] == [
        "max_order_exceeds_max_correlated",
        "max_correlated_exceeds_max_open",
    ]
    for case in cases:
        body = {
            **_fixture()[0]["body"],
            **case["overrides"],
        }
        envelope, public_key = _signed_capital_body(
            body,
            "2099-01-01T00:00:00Z",
            "2099-01-01T00:01:00Z",
        )
        with pytest.raises(
            DumbMoneyAuthorityError,
            match=str(case["expected_error"]),
        ):
            verify_signed_capital_envelope(
                envelope,
                public_key,
                NOW,
                "c" * 64,
            )


def test_capital_envelope_rejects_mix_and_match_lineage_sets() -> None:
    body = {
        **_fixture()[0]["body"],
        "strategy_hashes": ["a" * 64, "b" * 64],
        "passport_hashes": ["c" * 64, "d" * 64],
        "promotion_hashes": ["e" * 64, "f" * 64],
    }
    envelope, public_key = _signed_capital_body(
        body,
        "2099-01-01T00:00:00Z",
        "2099-01-01T00:01:00Z",
    )

    with pytest.raises(
        DumbMoneyAuthorityError,
        match="exactly one bound strategy/passport/promotion tuple",
    ):
        verify_signed_capital_envelope(
            envelope,
            public_key,
            NOW,
            "c" * 64,
        )


def test_signature_encoding_and_authority_window_are_canonical_and_short() -> None:
    envelope, _, _ = _fixture()
    signature = envelope["signature"]
    with pytest.raises(ValueError, match="canonical"):
        _urlsafe_b64decode(signature[:-1] + "x")

    wider, public_key = _signed_envelope_for_window(
        "2099-01-01T00:00:00Z",
        "2099-01-01T00:02:00Z",
        "2099-01-01T00:00:00Z",
        "2099-01-01T00:02:00Z",
    )
    with pytest.raises(DumbMoneyAuthorityError, match="60-second"):
        verify_signed_capital_envelope(wider, public_key, NOW, "c" * 64)

    mismatched, public_key = _signed_envelope_for_window(
        "2099-01-01T00:00:00Z",
        "2099-01-01T00:01:00Z",
        "2099-01-01T00:00:01Z",
        "2099-01-01T00:01:00Z",
    )
    with pytest.raises(DumbMoneyAuthorityError, match="must match exactly"):
        verify_signed_capital_envelope(mismatched, public_key, NOW, "c" * 64)


def test_daily_loss_is_derived_from_attributed_fee_bearing_broker_fills(
    tmp_path: Path,
) -> None:
    buy = _equity_intent(notional_usd=100.0, quantity=1.0)
    sell = replace(
        buy,
        intent_id="intent-sell",
        side="sell",
        notional_usd=0.0,
        quantity=1.0,
    )
    for order_id, intent in (("buy-1", buy), ("sell-1", sell)):
        append_record(
            ledger_path(tmp_path),
            "live_order_result",
            {
                "intent_id": intent.intent_id,
                "instrument": intent.instrument,
                "symbol": intent.symbol,
                "side": intent.side,
                "market_date": "2099-01-01",
                "intent": intent.to_dict(),
                "placed": True,
                "order_id": order_id,
                "status": "filled",
                "filled_quantity": 1.0,
                "average_fill_price": 100.0 if intent.side == "buy" else 98.0,
            },
        )
    broker_orders = (
        {
            "order_id": "buy-1",
            "symbol": "ACME",
            "side": "buy",
            "status": "filled",
            "market_date": "2099-01-01",
            "submitted_at": "2099-01-01T00:00:10+00:00",
            "filled_at": "2099-01-01T00:00:11+00:00",
            "filled_quantity": 1.0,
            "average_fill_price": 100.0,
            "fees_usd": 0.10,
        },
        {
            "order_id": "sell-1",
            "symbol": "ACME",
            "side": "sell",
            "status": "filled",
            "market_date": "2099-01-01",
            "submitted_at": "2099-01-01T00:00:20+00:00",
            "filled_at": "2099-01-01T00:00:21+00:00",
            "filled_quantity": 1.0,
            "average_fill_price": 98.0,
            "fees_usd": 0.10,
        },
    )
    assert (
        _witnessed_daily_loss_cents(
            tmp_path,
            _account(orders=broker_orders),
            "2099-01-01",
        )
        == 220
    )
    losing_and_winning_positions = (
        {
            "symbol": "LOSS",
            "quantity": 1.0,
            "average_cost": 10.0,
            "market_price": 5.0,
            "market_value": 5.0,
            "unrealized_pnl": -5.0,
        },
        {
            "symbol": "GAIN",
            "quantity": 1.0,
            "average_cost": 10.0,
            "market_price": 20.0,
            "market_value": 20.0,
            "unrealized_pnl": 10.0,
        },
    )
    assert (
        _witnessed_daily_loss_cents(
            tmp_path,
            _account(orders=broker_orders, positions=losing_and_winning_positions),
            "2099-01-01",
        )
        == 720
    )
    missing_unrealized = (
        {
            "symbol": "LOSS",
            "quantity": 1.0,
            "average_cost": 10.0,
            "market_price": 5.0,
            "market_value": 5.0,
        },
    )
    with pytest.raises(DumbMoneyAuthorityError, match="unrealized PnL"):
        _witnessed_daily_loss_cents(
            tmp_path,
            _account(orders=broker_orders, positions=missing_unrealized),
            "2099-01-01",
        )

    missing_fee = tuple(
        {key: value for key, value in order.items() if key != "fees_usd"}
        for order in broker_orders
    )
    with pytest.raises(DumbMoneyAuthorityError, match="fee observation"):
        _witnessed_daily_loss_cents(
            tmp_path,
            _account(orders=missing_fee),
            "2099-01-01",
        )


def test_raw_broker_position_cannot_fabricate_missing_unrealized_pnl() -> None:
    canonical = _canonical_raw_broker_item(
        {
            "symbol": "ACME",
            "quantity": 1.0,
            "average_cost": 100.0,
            "market_price": 99.0,
            "market_value": 99.0,
        },
        "equity_position",
    )

    assert "unrealized_pnl" not in canonical
    with pytest.raises(RobinhoodGatewayError, match="unrealized_pnl"):
        _validated_equity_position(canonical, 0)


def test_gateway_final_guard_denies_before_external_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = object.__new__(RobinhoodAgenticGateway)
    gateway._write_timeout_seconds = 30
    run_calls: list[str] = []

    def unexpected_run(*_args: Any, **_kwargs: Any) -> None:
        run_calls.append("called")
        raise AssertionError("external process must not start")

    monkeypatch.setattr(gateway, "_run", unexpected_run)
    exit_intent = replace(
        _equity_intent(quantity=1.0),
        side="sell",
        notional_usd=0.0,
    )

    with pytest.raises(RobinhoodGatewayError, match="kill became active"):
        gateway.place_order(
            exit_intent,
            "a" * 64,
            pre_submit_guard=lambda: (_ for _ in ()).throw(
                RobinhoodGatewayError("kill became active")
            ),
        )
    with pytest.raises(
        RobinhoodGatewayError,
        match="insufficient remaining validity",
    ):
        gateway.place_order(
            exit_intent,
            "a" * 64,
            pre_submit_guard=lambda: datetime.now(timezone.utc) + timedelta(seconds=35),
        )

    assert run_calls == []


def test_strict_operator_rejects_execute_without_full_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["operator_live_branch", "--dumbmoney-strict", "--execute"],
    )

    with pytest.raises(SystemExit) as error:
        operator_live_branch.main()

    assert error.value.code == 2


def test_operator_rejects_plain_execute_before_gateway_or_model_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway_calls: list[bool] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["operator_live_branch", "--execute"],
    )
    monkeypatch.setattr(
        operator_live_branch,
        "default_gateway",
        lambda: gateway_calls.append(True),
    )

    with pytest.raises(SystemExit) as error:
        operator_live_branch.main()

    assert error.value.code == 2
    assert gateway_calls == []


def test_programmatic_legacy_execute_rejected_before_gateway_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway_calls: list[bool] = []
    monkeypatch.setattr(
        operator_live_branch,
        "default_gateway",
        lambda: gateway_calls.append(True),
    )

    with pytest.raises(RuntimeError, match="Legacy operator execution is disabled"):
        operator_live_branch._run_with_crash_tombstone(True)

    assert gateway_calls == []


def test_cancel_result_is_bound_to_exact_account_and_order() -> None:
    call = McpToolCallEvidence(
        call_id="cancel-1",
        tool="cancel_equity_order",
        arguments={"account_id": "agentic-account", "order_id": "order-1"},
        result={
            "structured_content": {
                "order_id": "order-1",
                "status": "cancel_requested",
            }
        },
    )
    result = _gateway_cancel_result(
        {
            "cancel_requested": True,
            "order_id": "order-1",
            "status": "cancel_requested",
            "warnings": [],
            "error": "",
        },
        "cancel_equity_order",
        "order-1",
        (call,),
        "agentic-account",
    )
    assert result.cancel_requested is True

    with pytest.raises(
        RobinhoodCancellationAmbiguousError,
        match="exact Agentic order",
    ):
        _gateway_cancel_result(
            {
                "cancel_requested": True,
                "order_id": "order-1",
                "status": "cancel_requested",
                "warnings": [],
                "error": "",
            },
            "cancel_equity_order",
            "order-1",
            (
                McpToolCallEvidence(
                    call_id="cancel-2",
                    tool="cancel_equity_order",
                    arguments={
                        "account_id": "other-account",
                        "order_id": "order-1",
                    },
                    result=call.result,
                ),
            ),
            "agentic-account",
        )


class CancelGateway:
    def __init__(self) -> None:
        self.cancel_calls: list[tuple[str, str]] = []
        self.polls = 0

    def cancel_order(self, instrument: str, order_id: str) -> GatewayCancelResult:
        self.cancel_calls.append((instrument, order_id))
        return GatewayCancelResult(
            cancel_requested=True,
            order_id=order_id,
            status="cancel_requested",
            warnings=(),
            error="",
            observed_tools=("cancel_equity_order",),
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        self.polls += 1
        return _account(
            orders=(
                {
                    "order_id": "order-1",
                    "symbol": "ACME",
                    "side": "buy",
                    "status": "canceled",
                    "market_date": "2099-01-01",
                    "submitted_at": "2099-01-01T00:00:30+00:00",
                    "filled_at": "",
                    "filled_quantity": 0.0,
                    "average_fill_price": 0.0,
                },
            )
        )


def test_kill_cancel_workflow_is_bounded_and_reconciles_history(tmp_path: Path) -> None:
    intent = _equity_intent()
    append_record(
        ledger_path(tmp_path),
        "live_order_result",
        {
            "intent_id": intent.intent_id,
            "instrument": "equity",
            "symbol": "ACME",
            "side": "buy",
            "market_date": "2099-01-01",
            "intent": intent.to_dict(),
            "placed": True,
            "order_id": "order-1",
            "status": "open",
            "filled_quantity": 0.0,
            "average_fill_price": 0.0,
        },
    )
    open_account = _account(
        orders=(
            {
                "order_id": "order-1",
                "symbol": "ACME",
                "side": "buy",
                "status": "open",
                "market_date": "2099-01-01",
                "submitted_at": "2099-01-01T00:00:30+00:00",
                "filled_at": "",
                "filled_quantity": 0.0,
                "average_fill_price": 0.0,
            },
        )
    )
    gateway = CancelGateway()

    result = _run_cancel_only_degraded(
        tmp_path,
        gateway,  # type: ignore[arg-type]
        open_account,
        NOW,
        "dumbmoney_kill_active",
        True,
    )

    assert result["cycle_status"] == "cancel_only_degraded"
    assert gateway.cancel_calls == [("equity", "order-1")]
    assert gateway.polls == 1
    assert result["unresolved_attributed_orders"] == []


class HistoryOnlyGateway:
    def __init__(self, account: AccountSnapshot) -> None:
        self.account = account
        self.poll_count = 0

    def get_account_snapshot(self) -> AccountSnapshot:
        self.poll_count += 1
        return self.account


def test_ambiguous_placement_polls_history_without_retrying_placement(
    tmp_path: Path,
) -> None:
    intent = _equity_intent()
    broker_order = {
        "order_id": "broker-1",
        "symbol": "ACME",
        "side": "buy",
        "status": "open",
        "market_date": "2099-01-01",
        "submitted_at": "2099-01-01T00:00:30+00:00",
        "filled_at": "",
        "filled_quantity": 0.0,
        "average_fill_price": 0.0,
        "order_type": "limit",
        "time_in_force": "day",
        "limit_price": 100.0,
        "quantity": 0.01,
    }
    gateway = HistoryOnlyGateway(_account(orders=(broker_order,)))

    reconciled, _, poll_count = _poll_ambiguous_placement_history(
        tmp_path,
        gateway,  # type: ignore[arg-type]
        intent,
        "2099-01-01",
        NOW,
        "paper-hash",
    )

    assert poll_count == 3
    assert gateway.poll_count == 3
    assert reconciled is not None
    assert reconciled["order_id"] == "broker-1"
    assert reconciled["placement_retried"] is False
    assert any(
        record["event_type"] == "live_order_result"
        for record in read_ledger(ledger_path(tmp_path))
    )


def test_option_entry_requires_fresh_quote_multiplier_expiry_and_exact_debit() -> None:
    intent = LiveExecutionIntent(
        **{
            **_equity_intent(notional_usd=125.0, quantity=1.0).to_dict(),
            "instrument": "option",
            "limit_price": 1.25,
            "option_contract": {
                "contract_id": "option-1",
                "expiry": "2099-01-15",
                "multiplier": 100,
                "maximum_loss_usd": 125.0,
                "quote_observed_at": "2099-01-01T00:00:00Z",
                "defined_risk": True,
                "order_action": "buy_to_open",
            },
        }
    )
    validate_option_entry_for_execution(intent, NOW)

    with pytest.raises(LiveSignalError, match="multiplier"):
        validate_option_entry_for_execution(
            LiveExecutionIntent(
                **{
                    **intent.to_dict(),
                    "option_contract": {**intent.option_contract, "multiplier": 10},
                }
            ),
            NOW,
        )
    with pytest.raises(LiveSignalError, match="freshness"):
        validate_option_entry_for_execution(
            intent,
            datetime(2099, 1, 1, 0, 2, tzinfo=timezone.utc),
        )
