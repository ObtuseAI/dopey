from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dopey_live.dumbmoney_authority import (
    VerifiedCapitalAuthority,
    canonical_json_bytes,
    verify_signed_capital_envelope,
)
from dopey_live.dumbmoney_command_feed import (
    CommandFeedHttpRequest,
    CommandFeedHttpResponse,
)
from dopey_live.dumbmoney_contract_feed import (
    CONTRACT_RESOLUTION_CHECKPOINT_SCHEMA,
    CONTRACT_RESOLUTION_SCHEMA,
    DumbMoneyContractResolverClient,
)
from dopey_live.dumbmoney_promotion import (
    ALPHA_PASSPORT_SCHEMA,
    PROMOTION_CERTIFICATE_SCHEMA,
    DumbMoneyPromotionError,
)
from dopey_live.models import LiveExecutionIntent


NOW = datetime(2099, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
ACCOUNT_HASH = "c" * 64
STRATEGY_HASH = "a" * 64
ZERO_DIGEST = "0" * 64


def _format_utc(value: datetime) -> str:
    rendered = value.astimezone(timezone.utc).isoformat(
        timespec="microseconds" if value.microsecond else "seconds"
    )
    return rendered.replace("+00:00", "Z")


def _sign_envelope(
    private_key: Ed25519PrivateKey,
    body: dict[str, Any],
    *,
    source_id: str,
    source_sequence: int,
    not_before: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    public_key = private_key.public_key().public_bytes_raw()
    unsigned: dict[str, Any] = {
        "schema": "dumbmoney.signed-envelope.v1",
        "source_id": source_id,
        "source_sequence": source_sequence,
        "correlation_id": "promotion-fixture",
        "causation_id": None,
        "nonce": f"{source_id}-nonce-{source_sequence}",
        "not_before": _format_utc(not_before),
        "expires_at": _format_utc(expires_at),
        "body_schema": body["schema"],
        "body_digest": hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
        "body": body,
        "signature_algorithm": "Ed25519",
        "signer_key_id": hashlib.sha256(public_key).hexdigest(),
    }
    unsigned["event_id"] = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    signature = private_key.sign(canonical_json_bytes(unsigned))
    return {
        **unsigned,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def _passport_body() -> dict[str, Any]:
    return {
        "schema": ALPHA_PASSPORT_SCHEMA,
        "passport_id": "passport-dopey-1",
        "strategy_lineage_id": "lineage-dopey-1",
        "venue": "dopey_robinhood",
        "strategy_hash": STRATEGY_HASH,
        "artifact_hashes": ["1" * 64],
        "evidence_verdict_hashes": ["2" * 64],
        "intended_instruments": ["equity:ACME"],
        "maximum_loss_cents": 100,
        "evidence_class": "FORWARD",
        "created_at": _format_utc(NOW - timedelta(days=1)),
        "expires_at": _format_utc(NOW + timedelta(days=1)),
    }


def _promotion_body(
    passport_digest: str,
    *,
    stage: str = "EXPLORATORY_LIVE",
) -> dict[str, Any]:
    return {
        "schema": PROMOTION_CERTIFICATE_SCHEMA,
        "certificate_id": "promotion-dopey-1",
        "passport_digest": passport_digest,
        "verdict_digests": ["3" * 64],
        "stage": stage,
        "venue": "dopey_robinhood",
        "instruments": ["equity:ACME"],
        "maximum_loss_cents": 100,
        "rollback_triggers": ["AMBIGUOUS_OUTCOME", "KILL_ACTIVE"],
        "policy_epoch": 1,
        "not_before": _format_utc(NOW - timedelta(days=1)),
        "expires_at": _format_utc(NOW + timedelta(days=1)),
    }


def _capital_body(
    passport_digest: str,
    promotion_digest: str,
) -> dict[str, Any]:
    return {
        "schema": "dumbmoney.capital-envelope.v1",
        "envelope_id": "e" * 64,
        "mandate_id": "d" * 64,
        "venue": "dopey_robinhood",
        "account_hash": ACCOUNT_HASH,
        "strategy_hashes": [STRATEGY_HASH],
        "passport_hashes": [passport_digest],
        "promotion_hashes": [promotion_digest],
        "authorized_instruments": ["equity:ACME"],
        "authorized_mode": "LIVE",
        "max_order_risk_cents": 100,
        "max_open_risk_cents": 1250,
        "max_correlated_risk_cents": 300,
        "max_daily_loss_cents": 300,
        "max_open_orders": 5,
        "fencing_generation": 7,
        "policy_epoch": 1,
        "not_before": _format_utc(NOW),
        "expires_at": _format_utc(NOW + timedelta(seconds=60)),
    }


def _intent() -> LiveExecutionIntent:
    return LiveExecutionIntent(
        intent_id="intent-1",
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
        reason_codes=("resolver-fixture",),
    )


def _ledger_proof(
    envelope: dict[str, Any],
    *,
    global_sequence: int,
) -> dict[str, Any]:
    received_at = NOW - timedelta(seconds=1)
    observed_at = max(
        received_at,
        datetime.fromisoformat(envelope["not_before"].replace("Z", "+00:00")),
    )
    proof: dict[str, Any] = {
        "schema": "dumbmoney.ledger-event-proof.v1",
        "global_sequence": global_sequence,
        "event_id": envelope["event_id"],
        "source_id": envelope["source_id"],
        "source_sequence": envelope["source_sequence"],
        "signer_key_id": envelope["signer_key_id"],
        "nonce": envelope["nonce"],
        "event_schema": envelope["body_schema"],
        "observed_at": _format_utc(observed_at),
        "received_at": _format_utc(received_at),
        "correlation_id": envelope["correlation_id"],
        "causation_id": envelope["causation_id"],
        "payload_digest": envelope["body_digest"],
        "previous_source_digest": ZERO_DIGEST,
        "previous_global_digest": (ZERO_DIGEST if global_sequence == 1 else "9" * 64),
    }
    proof["event_digest"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in proof.items() if key != "schema"}
        )
    ).hexdigest()
    return proof


def _resolution(
    core_key: Ed25519PrivateKey,
    envelope: dict[str, Any],
    request_nonce: str,
    capital_digest: str,
    authority_state: dict[str, Any],
    *,
    global_sequence: int,
    eligible: bool = True,
) -> dict[str, Any]:
    proof = _ledger_proof(envelope, global_sequence=global_sequence)
    checkpoint: dict[str, Any] = {
        "schema": CONTRACT_RESOLUTION_CHECKPOINT_SCHEMA,
        "cell_id": "dopey_robinhood",
        "request_nonce": request_nonce,
        "requested_body_digest": envelope["body_digest"],
        "capital_envelope_digest": capital_digest,
        "fencing_generation": 7,
        "observed_at": _format_utc(NOW),
        "contract_schema": envelope["body_schema"],
        "transport_window_current": True,
        "body_window_current": True,
        "eligible_live_input": eligible,
        "authority_state": authority_state,
        "ledger_proof": proof,
        "envelope": envelope,
    }
    public_key = core_key.public_key().public_bytes_raw()
    signature = core_key.sign(canonical_json_bytes(checkpoint))
    return {
        "schema": CONTRACT_RESOLUTION_SCHEMA,
        **{key: value for key, value in checkpoint.items() if key != "schema"},
        "checkpoint": checkpoint,
        "checkpoint_signature": {
            "algorithm": "Ed25519",
            "signer_key_id": hashlib.sha256(public_key).hexdigest(),
            "signature": base64.urlsafe_b64encode(signature)
            .decode("ascii")
            .rstrip("="),
        },
    }


def _resign_resolution(
    response: dict[str, Any],
    core_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    signature = core_key.sign(canonical_json_bytes(response["checkpoint"]))
    response["checkpoint_signature"]["signature"] = (
        base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    )
    return response


def _authority_state(
    authority: VerifiedCapitalAuthority,
    *,
    passport_event_digest: str,
    promotion_event_digest: str,
    evaluator_key_ids: tuple[str, str],
) -> dict[str, Any]:
    return {
        "schema": "dumbmoney.cell-authority-state.v1",
        "evaluated_at": _format_utc(NOW),
        "authority_valid_until": _format_utc(NOW + timedelta(seconds=30)),
        "policy_epoch": authority.envelope.policy_epoch,
        "mandate_id": authority.envelope.mandate_id,
        "mandate_event_digest": "4" * 64,
        "kill_clear": True,
        "kill_generation": 1,
        "kill_event_digest": "5" * 64,
        "desired_mode": "LIVE",
        "desired_mode_revision": 1,
        "desired_mode_event_digest": "6" * 64,
        "capital_envelope_digest": authority.body_digest,
        "capital_event_digest": "7" * 64,
        "fencing_generation": authority.envelope.fencing_generation,
        "strategy_hash": authority.envelope.strategy_hashes[0],
        "passport_digest": authority.envelope.passport_hashes[0],
        "passport_event_digest": passport_event_digest,
        "promotion_digest": authority.envelope.promotion_hashes[0],
        "promotion_event_digest": promotion_event_digest,
        "verdicts": [
            {
                "verdict_digest": "8" * 64,
                "verdict_event_digest": "a" * 64,
                "verdict_id": "verdict-integrity-1",
                "court": "integrity",
                "decision": "PASS",
                "signer_key_id": evaluator_key_ids[0],
                "evaluated_at": _format_utc(NOW - timedelta(seconds=5)),
                "expires_at": _format_utc(NOW + timedelta(seconds=45)),
                "transport_expires_at": _format_utc(NOW + timedelta(seconds=45)),
            },
            {
                "verdict_digest": "b" * 64,
                "verdict_event_digest": "c" * 64,
                "verdict_id": "verdict-statistics-1",
                "court": "statistics",
                "decision": "PASS",
                "signer_key_id": evaluator_key_ids[1],
                "evaluated_at": _format_utc(NOW - timedelta(seconds=5)),
                "expires_at": _format_utc(NOW + timedelta(seconds=45)),
                "transport_expires_at": _format_utc(NOW + timedelta(seconds=45)),
            },
        ],
        "ledger_head_sequence": 2,
        "ledger_head_digest": promotion_event_digest,
    }


class ResolutionTransport:
    def __init__(
        self,
        core_key: Ed25519PrivateKey,
        authority: VerifiedCapitalAuthority,
        envelopes: dict[str, dict[str, Any]],
        evaluator_key_ids: tuple[str, str],
        *,
        response_mutator: Any = None,
    ) -> None:
        self.core_key = core_key
        self.authority = authority
        self.envelopes = envelopes
        self.evaluator_key_ids = evaluator_key_ids
        self.response_mutator = response_mutator
        self.requests: list[CommandFeedHttpRequest] = []

    def __call__(self, request: CommandFeedHttpRequest) -> CommandFeedHttpResponse:
        self.requests.append(request)
        parsed = urlsplit(request.url)
        digest = parsed.path.rsplit("/", 1)[-1]
        query = parse_qs(parsed.query)
        assert query["capital_envelope_digest"] == [self.authority.body_digest]
        nonce = query["request_nonce"][0]
        envelope = self.envelopes[digest]
        passport_envelope = self.envelopes[self.authority.envelope.passport_hashes[0]]
        promotion_envelope = self.envelopes[self.authority.envelope.promotion_hashes[0]]
        authority_state = _authority_state(
            self.authority,
            passport_event_digest=_ledger_proof(
                passport_envelope,
                global_sequence=1,
            )["event_digest"],
            promotion_event_digest=_ledger_proof(
                promotion_envelope,
                global_sequence=2,
            )["event_digest"],
            evaluator_key_ids=self.evaluator_key_ids,
        )
        response = _resolution(
            self.core_key,
            envelope,
            nonce,
            self.authority.body_digest,
            authority_state,
            global_sequence=(
                1 if envelope["body_schema"] == ALPHA_PASSPORT_SCHEMA else 2
            ),
        )
        if self.response_mutator is not None:
            response = self.response_mutator(response)
            response = _resign_resolution(response, self.core_key)
        return CommandFeedHttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(response, separators=(",", ":")).encode("utf-8"),
        )


def _runtime(
    *,
    promotion_signer: str = "promoter",
    stage: str = "EXPLORATORY_LIVE",
    response_mutator: Any = None,
) -> tuple[
    DumbMoneyContractResolverClient,
    VerifiedCapitalAuthority,
    ResolutionTransport,
]:
    core_key = Ed25519PrivateKey.generate()
    promoter_key = Ed25519PrivateKey.generate()
    research_key = Ed25519PrivateKey.generate()
    evaluator_key_1 = Ed25519PrivateKey.generate()
    evaluator_key_2 = Ed25519PrivateKey.generate()
    passport = _sign_envelope(
        research_key,
        _passport_body(),
        source_id="research",
        source_sequence=1,
        not_before=NOW - timedelta(seconds=10),
        expires_at=NOW + timedelta(minutes=10),
    )
    signing_key = research_key if promotion_signer == "research" else promoter_key
    promotion = _sign_envelope(
        signing_key,
        _promotion_body(passport["body_digest"], stage=stage),
        source_id="promoter",
        source_sequence=1,
        not_before=NOW - timedelta(seconds=10),
        expires_at=NOW + timedelta(minutes=10),
    )
    capital = _sign_envelope(
        core_key,
        _capital_body(passport["body_digest"], promotion["body_digest"]),
        source_id="dumbmoney-core",
        source_sequence=1,
        not_before=NOW,
        expires_at=NOW + timedelta(seconds=60),
    )
    core_public = core_key.public_key().public_bytes_raw()
    authority = verify_signed_capital_envelope(
        capital,
        core_public,
        NOW,
        ACCOUNT_HASH,
    )
    transport = ResolutionTransport(
        core_key,
        authority,
        {
            passport["body_digest"]: passport,
            promotion["body_digest"]: promotion,
        },
        (
            hashlib.sha256(evaluator_key_1.public_key().public_bytes_raw()).hexdigest(),
            hashlib.sha256(evaluator_key_2.public_key().public_bytes_raw()).hexdigest(),
        ),
        response_mutator=response_mutator,
    )
    promoter_public = promoter_key.public_key().public_bytes_raw()
    research_public = research_key.public_key().public_bytes_raw()
    evaluator_public_1 = evaluator_key_1.public_key().public_bytes_raw()
    evaluator_public_2 = evaluator_key_2.public_key().public_bytes_raw()
    client = DumbMoneyContractResolverClient(
        base_url="http://127.0.0.1:8765",
        cell_bearer_provider=lambda: "cell-token-from-credential-manager",
        trusted_core_public_key=core_public,
        trusted_promoter_public_keys={
            hashlib.sha256(promoter_public).hexdigest(): promoter_public,
        },
        trusted_research_public_keys={
            hashlib.sha256(research_public).hexdigest(): research_public,
        },
        trusted_evaluator_public_keys={
            hashlib.sha256(evaluator_public_1).hexdigest(): evaluator_public_1,
            hashlib.sha256(evaluator_public_2).hexdigest(): evaluator_public_2,
        },
        transport=transport,
    )
    return client, authority, transport


def test_nonce_and_fence_bound_resolver_hydrates_exact_lineage() -> None:
    client, authority, transport = _runtime()

    intent, binding = client.bind_intent(authority, _intent(), NOW)

    assert intent.passport_hash == authority.envelope.passport_hashes[0]
    assert intent.promotion_hash == authority.envelope.promotion_hashes[0]
    assert binding.strategy_hash == STRATEGY_HASH
    assert binding.capital_body_digest == authority.body_digest
    assert binding.capital_fencing_generation == 7
    assert len(transport.requests) == 2
    nonces = [
        parse_qs(urlsplit(request.url).query)["request_nonce"][0]
        for request in transport.requests
    ]
    assert len(set(nonces)) == 2
    assert all(len(nonce) == 64 for nonce in nonces)
    assert all(
        request.headers["Authorization"] == "Bearer cell-token-from-credential-manager"
        for request in transport.requests
    )


def test_resolver_rejects_caller_supplied_or_wrong_role_lineage() -> None:
    client, authority, _ = _runtime()
    with pytest.raises(DumbMoneyPromotionError, match="supplied its own"):
        client.bind_intent(
            authority,
            replace(_intent(), promotion_hash=authority.envelope.promotion_hashes[0]),
            NOW,
        )

    wrong_role_client, wrong_role_authority, _ = _runtime(promotion_signer="research")
    with pytest.raises(DumbMoneyPromotionError, match="sealed promoter"):
        wrong_role_client.bind_intent(wrong_role_authority, _intent(), NOW)


def test_resolver_rejects_nonlive_stage_even_if_projection_lies() -> None:
    client, authority, _ = _runtime(stage="PAPER")

    with pytest.raises(
        DumbMoneyPromotionError,
        match="stage is not live-authorizing|live-eligibility projection",
    ):
        client.bind_intent(authority, _intent(), NOW)


def test_resolver_rejects_response_transplanted_across_capital_fence() -> None:
    def mutate(response: dict[str, Any]) -> dict[str, Any]:
        response["capital_envelope_digest"] = "8" * 64
        return response

    client, authority, _ = _runtime(response_mutator=mutate)

    with pytest.raises(
        DumbMoneyPromotionError,
        match="checkpoint does not bind|active capital envelope",
    ):
        client.bind_intent(authority, _intent(), NOW)


def test_resolver_rejects_expired_authority_state() -> None:
    def mutate(response: dict[str, Any]) -> dict[str, Any]:
        response["authority_state"]["authority_valid_until"] = _format_utc(
            NOW - timedelta(seconds=1)
        )
        return response

    client, authority, _ = _runtime(response_mutator=mutate)

    with pytest.raises(
        DumbMoneyPromotionError,
        match="authority_state is stale",
    ):
        client.bind_intent(authority, _intent(), NOW)


def test_resolver_rejects_unsealed_authority_verdict_signer() -> None:
    def mutate(response: dict[str, Any]) -> dict[str, Any]:
        response["authority_state"]["verdicts"][0]["signer_key_id"] = "f" * 64
        return response

    client, authority, _ = _runtime(response_mutator=mutate)

    with pytest.raises(
        DumbMoneyPromotionError,
        match="verdict signer is not sealed",
    ):
        client.bind_intent(authority, _intent(), NOW)


def test_resolver_rejects_contract_proof_outside_authority_state() -> None:
    def mutate(response: dict[str, Any]) -> dict[str, Any]:
        if response["contract_schema"] == PROMOTION_CERTIFICATE_SCHEMA:
            response["authority_state"]["promotion_event_digest"] = "f" * 64
        return response

    client, authority, _ = _runtime(response_mutator=mutate)

    with pytest.raises(
        DumbMoneyPromotionError,
        match="proof event digest",
    ):
        client.bind_intent(authority, _intent(), NOW)


def test_resolver_rejects_authority_state_change_between_lineage_reads() -> None:
    calls = 0

    def mutate(response: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            state = response["authority_state"]
            state["ledger_head_sequence"] = 3
            state["ledger_head_digest"] = "f" * 64
        return response

    client, authority, _ = _runtime(response_mutator=mutate)

    with pytest.raises(
        DumbMoneyPromotionError,
        match="one authority state",
    ):
        client.bind_intent(authority, _intent(), NOW)
