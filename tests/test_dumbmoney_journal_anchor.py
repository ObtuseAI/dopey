from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dopey_live.dumbmoney_authority import canonical_json_bytes
from dopey_live.dumbmoney_command_feed import (
    CommandFeedHttpRequest,
    CommandFeedHttpResponse,
)
from dopey_live.dumbmoney_journal_anchor import (
    ANCHOR_BODY_SCHEMA,
    ANCHOR_CHECKPOINT_SCHEMA,
    ANCHOR_RESPONSE_SCHEMA,
    CoreJournalAnchorClient,
    JournalAnchorError,
)

NOW = datetime(2026, 7, 26, 22, 0, 0, tzinfo=UTC)
ACCOUNT_HASH = hashlib.sha256(b"dopey-account").hexdigest()
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC_KEY = PRIVATE_KEY.public_key().public_bytes_raw()
SIGNER_KEY_ID = hashlib.sha256(PUBLIC_KEY).hexdigest()
ZERO_DIGEST = "0" * 64


def _z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _hash(value: str | dict[str, Any]) -> str:
    material = (
        value.encode("utf-8") if isinstance(value, str) else canonical_json_bytes(value)
    )
    return hashlib.sha256(material).hexdigest()


def _signature(value: dict[str, Any]) -> str:
    return (
        base64.urlsafe_b64encode(PRIVATE_KEY.sign(canonical_json_bytes(value)))
        .decode("ascii")
        .rstrip("=")
    )


def _signed_anchor(
    body: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    unsigned = {
        "schema": "dumbmoney.signed-envelope.v1",
        "source_id": "dumbmoney-core",
        "source_sequence": 1,
        "correlation_id": "journal-anchor:dopey_robinhood:test-journal",
        "causation_id": None,
        "nonce": _hash("anchor-event-nonce"),
        "not_before": _z(observed_at),
        "expires_at": _z(observed_at + timedelta(seconds=120)),
        "body_schema": ANCHOR_BODY_SCHEMA,
        "body_digest": _hash(body),
        "body": body,
        "signature_algorithm": "Ed25519",
        "signer_key_id": SIGNER_KEY_ID,
    }
    envelope = {**unsigned, "event_id": _hash(unsigned)}
    envelope["signature"] = _signature(envelope)
    return envelope


def _response(
    request: dict[str, Any],
    *,
    observed_at: datetime = NOW,
) -> dict[str, Any]:
    identity = {
        "schema": ANCHOR_BODY_SCHEMA,
        "venue": "dopey_robinhood",
        "account_hash": request["account_hash"],
        "journal_name": request["journal_name"],
        "journal_schema": request["journal_schema"],
        "journal_stream_id": request["journal_stream_id"],
        "journal_sequence": request["journal_sequence"],
        "journal_head_sha256": request["journal_head_sha256"],
        "previous_anchor_body_digest": ZERO_DIGEST,
    }
    body = {
        **identity,
        "anchor_id": _hash(identity),
        "anchored_at": _z(observed_at),
    }
    envelope = _signed_anchor(body, observed_at)
    event_material = {
        "global_sequence": 1,
        "event_id": envelope["event_id"],
        "source_id": envelope["source_id"],
        "source_sequence": envelope["source_sequence"],
        "signer_key_id": envelope["signer_key_id"],
        "nonce": envelope["nonce"],
        "event_schema": envelope["body_schema"],
        "observed_at": _z(observed_at),
        "received_at": _z(observed_at),
        "correlation_id": envelope["correlation_id"],
        "causation_id": envelope["causation_id"],
        "payload_digest": envelope["body_digest"],
        "previous_source_digest": ZERO_DIGEST,
        "previous_global_digest": ZERO_DIGEST,
    }
    event_digest = _hash(event_material)
    checkpoint = {
        "schema": ANCHOR_CHECKPOINT_SCHEMA,
        "cell_id": "dopey_robinhood",
        "request_nonce": request["request_nonce"],
        "account_hash": request["account_hash"],
        "journal_name": request["journal_name"],
        "journal_schema": request["journal_schema"],
        "journal_stream_id": request["journal_stream_id"],
        "journal_sequence": request["journal_sequence"],
        "journal_head_sha256": request["journal_head_sha256"],
        "anchor_body_digest": envelope["body_digest"],
        "anchor_event_digest": event_digest,
        "reused": False,
        "observed_at": _z(observed_at),
    }
    return {
        "schema": ANCHOR_RESPONSE_SCHEMA,
        "cell_id": "dopey_robinhood",
        "request_nonce": request["request_nonce"],
        "observed_at": _z(observed_at),
        "reused": False,
        "anchor_envelope": envelope,
        "ledger_proof": {
            "schema": "dumbmoney.ledger-event-proof.v1",
            **event_material,
            "event_digest": event_digest,
        },
        "checkpoint": checkpoint,
        "checkpoint_signature": {
            "algorithm": "Ed25519",
            "signer_key_id": SIGNER_KEY_ID,
            "signature": _signature(checkpoint),
        },
    }


class _Transport:
    def __init__(self, mutate: Any = None, *, status: int = 200) -> None:
        self.mutate = mutate
        self.status = status
        self.calls: list[CommandFeedHttpRequest] = []

    def __call__(
        self,
        request: CommandFeedHttpRequest,
    ) -> CommandFeedHttpResponse:
        self.calls.append(request)
        assert request.body is not None
        payload = _response(json.loads(request.body))
        if self.mutate is not None:
            self.mutate(payload)
        return CommandFeedHttpResponse(
            status=self.status,
            headers={"Content-Type": "application/json"},
            body=canonical_json_bytes(payload),
        )


def _client(transport: Any, now: datetime = NOW) -> CoreJournalAnchorClient:
    return CoreJournalAnchorClient(
        base_url="http://127.0.0.1:49152",
        transport=transport,
        cell_token_provider=lambda: "t" * 64,
        trusted_core_public_key=PUBLIC_KEY,
        expected_account_hash=ACCOUNT_HASH,
        request_nonce_fn=lambda: _hash("request-nonce"),
        now_fn=lambda: now,
    )


def test_exact_core_anchor_checkpoint_and_proof_are_accepted() -> None:
    transport = _Transport()
    client = _client(transport)
    head = _hash("journal-head")

    result = client.anchor(
        journal_name="live-branch-ledger",
        journal_schema="dopey-live-branch-ledger-v1",
        journal_sequence=7,
        journal_head_sha256=head,
    )

    assert result.journal_sequence == 7
    assert result.journal_head_sha256 == head
    assert len(transport.calls) == 1
    request = transport.calls[0]
    assert request.method == "POST"
    assert request.url.endswith("/v1/cells/dopey_robinhood/journal-heads:anchor")
    assert request.headers["Authorization"] == f"Bearer {'t' * 64}"


def test_tampered_checkpoint_and_rejected_anchor_fail_closed() -> None:
    def tamper(payload: dict[str, Any]) -> None:
        payload["checkpoint"]["journal_sequence"] = 6

    with pytest.raises(JournalAnchorError, match="signature is invalid"):
        _client(_Transport(tamper)).anchor(
            journal_name="live-branch-ledger",
            journal_schema="dopey-live-branch-ledger-v1",
            journal_sequence=7,
            journal_head_sha256=_hash("journal-head"),
        )

    with pytest.raises(JournalAnchorError, match="Core rejected"):
        _client(_Transport(status=409)).anchor(
            journal_name="command-feed",
            journal_schema="dopey.dumbmoney-command-feed-state.v1",
            journal_sequence=0,
            journal_head_sha256=ZERO_DIGEST,
        )


def test_zero_sequence_and_head_must_move_together() -> None:
    client = _client(_Transport())

    with pytest.raises(JournalAnchorError, match="zero must exactly bind"):
        client.anchor(
            journal_name="command-feed",
            journal_schema="dopey.dumbmoney-command-feed-state.v1",
            journal_sequence=0,
            journal_head_sha256=_hash("not-zero"),
        )
