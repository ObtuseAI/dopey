"""Core-backed rollback detection for Dopey's venue-local state stores."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .dumbmoney_authority import (
    DOPEY_VENUE,
    IDENTIFIER_PATTERN,
    DumbMoneyAuthorityError,
    _decode_public_key,
    _exact_fields,
    _loads_strict_signed_json,
    _sha256_text,
    _urlsafe_b64decode,
    _utc_timestamp,
    _verify_signed_wrapper,
    canonical_json_bytes,
)
from .dumbmoney_command_feed import (
    CommandFeedHttpRequest,
    CommandFeedHttpResponse,
    CommandFeedTransport,
)

ANCHOR_REQUEST_SCHEMA: Final[str] = "dumbmoney.cell-journal-anchor-request.v1"
ANCHOR_RESPONSE_SCHEMA: Final[str] = "dumbmoney.cell-journal-anchor-response.v1"
ANCHOR_CHECKPOINT_SCHEMA: Final[str] = "dumbmoney.cell-journal-anchor-checkpoint.v1"
ANCHOR_BODY_SCHEMA: Final[str] = "dumbmoney.cell-journal-head-anchor.v1"
LEDGER_PROOF_SCHEMA: Final[str] = "dumbmoney.ledger-event-proof.v1"
CORE_SOURCE_ID: Final[str] = "dumbmoney-core"
ZERO_DIGEST: Final[str] = "0" * 64
MAXIMUM_RESPONSE_BYTES: Final[int] = 524_288
MAXIMUM_RESPONSE_AGE: Final[timedelta] = timedelta(seconds=30)
MAXIMUM_CLOCK_SKEW: Final[timedelta] = timedelta(seconds=5)
MAXIMUM_ANCHOR_TTL: Final[timedelta] = timedelta(seconds=120)
_RESPONSE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "request_nonce",
        "observed_at",
        "reused",
        "anchor_envelope",
        "ledger_proof",
        "checkpoint",
        "checkpoint_signature",
    }
)
_CHECKPOINT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "request_nonce",
        "account_hash",
        "journal_name",
        "journal_schema",
        "journal_stream_id",
        "journal_sequence",
        "journal_head_sha256",
        "anchor_body_digest",
        "anchor_event_digest",
        "reused",
        "observed_at",
    }
)
_SIGNATURE_FIELDS: Final[frozenset[str]] = frozenset(
    {"algorithm", "signer_key_id", "signature"}
)
_ANCHOR_BODY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "anchor_id",
        "venue",
        "account_hash",
        "journal_name",
        "journal_schema",
        "journal_stream_id",
        "journal_sequence",
        "journal_head_sha256",
        "previous_anchor_body_digest",
        "anchored_at",
    }
)
_LEDGER_PROOF_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "global_sequence",
        "event_id",
        "source_id",
        "source_sequence",
        "signer_key_id",
        "nonce",
        "event_schema",
        "observed_at",
        "received_at",
        "correlation_id",
        "causation_id",
        "payload_digest",
        "previous_source_digest",
        "previous_global_digest",
        "event_digest",
    }
)


class JournalAnchorError(RuntimeError):
    """A Core anchor, signature, or monotonicity check failed closed."""


@dataclass(frozen=True)
class VerifiedJournalAnchor:
    journal_name: str
    journal_sequence: int
    journal_head_sha256: str
    anchor_body_digest: str
    anchor_event_digest: str
    reused: bool
    observed_at: str


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JournalAnchorError(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result == 0:
        raise JournalAnchorError(f"{label} must be positive")
    return result


def _digest(value: Any, label: str) -> str:
    try:
        return _sha256_text(value, label)
    except DumbMoneyAuthorityError as error:
        raise JournalAnchorError(str(error)) from error


def _timestamp(value: Any, label: str) -> datetime:
    try:
        return _utc_timestamp(value, label)
    except DumbMoneyAuthorityError as error:
        raise JournalAnchorError(str(error)) from error


def _strict_response(body: bytes) -> dict[str, Any]:
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAXIMUM_RESPONSE_BYTES:
        raise JournalAnchorError("Core anchor response size is invalid")
    try:
        return _loads_strict_signed_json(
            body,
            "Core anchor response",
            require_canonical_bytes=False,
        )
    except DumbMoneyAuthorityError as error:
        raise JournalAnchorError(str(error)) from error


class CoreJournalAnchorClient:
    """Publish exact local heads and verify Core's durable signed receipt."""

    def __init__(
        self,
        *,
        base_url: str,
        transport: CommandFeedTransport,
        cell_token_provider: Callable[[], str],
        trusted_core_public_key: bytes,
        expected_account_hash: str,
        request_nonce_fn: Callable[[], str] = lambda: secrets.token_hex(32),
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        parsed = urlsplit(base_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise JournalAnchorError("Core anchor base URL port is invalid") from error
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or port is None
            or not 1024 <= port <= 65_535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise JournalAnchorError(
                "Core anchor base URL must be literal loopback HTTP"
            )
        try:
            self._core_public_key = _decode_public_key(trusted_core_public_key)
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError("pinned Core public key is invalid") from error
        self._core_key_id = hashlib.sha256(self._core_public_key).hexdigest()
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._cell_token_provider = cell_token_provider
        self._account_hash = _digest(
            expected_account_hash,
            "expected_account_hash",
        )
        self._request_nonce_fn = request_nonce_fn
        self._now_fn = now_fn
        self._last_nonce: str | None = None

    def stream_id(self, journal_name: str) -> str:
        if not isinstance(journal_name, str) or not IDENTIFIER_PATTERN.fullmatch(
            journal_name
        ):
            raise JournalAnchorError("journal_name must be a canonical identifier")
        return _hash(
            {
                "schema": "dopey.journal-anchor-stream.v1",
                "cell_id": DOPEY_VENUE,
                "account_hash": self._account_hash,
                "journal_name": journal_name,
            }
        )

    def _verify_checkpoint(
        self,
        checkpoint: Any,
        signature: Any,
    ) -> dict[str, Any]:
        if not isinstance(checkpoint, dict):
            raise JournalAnchorError("Core anchor checkpoint must be an object")
        try:
            _exact_fields(
                checkpoint,
                _CHECKPOINT_FIELDS,
                "Core anchor checkpoint",
            )
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError(str(error)) from error
        if not isinstance(signature, dict):
            raise JournalAnchorError(
                "Core anchor checkpoint signature must be an object"
            )
        try:
            _exact_fields(
                signature,
                _SIGNATURE_FIELDS,
                "Core anchor checkpoint signature",
            )
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError(str(error)) from error
        if (
            signature.get("algorithm") != "Ed25519"
            or signature.get("signer_key_id") != self._core_key_id
        ):
            raise JournalAnchorError(
                "Core anchor checkpoint signature identity mismatch"
            )
        try:
            raw_signature = _urlsafe_b64decode(str(signature.get("signature", "")))
            if len(raw_signature) != 64:
                raise ValueError("Ed25519 signature must be 64 bytes")
            Ed25519PublicKey.from_public_bytes(self._core_public_key).verify(
                raw_signature,
                canonical_json_bytes(checkpoint),
            )
        except (InvalidSignature, ValueError) as error:
            raise JournalAnchorError(
                "Core anchor checkpoint signature is invalid"
            ) from error
        return dict(checkpoint)

    @staticmethod
    def _verify_ledger_proof(
        proof: Any,
        *,
        signed: Any,
        observed_at: datetime,
    ) -> dict[str, Any]:
        if not isinstance(proof, dict):
            raise JournalAnchorError("anchor ledger proof must be an object")
        try:
            _exact_fields(proof, _LEDGER_PROOF_FIELDS, "anchor ledger proof")
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError(str(error)) from error
        if proof.get("schema") != LEDGER_PROOF_SCHEMA:
            raise JournalAnchorError("anchor ledger proof schema is unsupported")
        global_sequence = _positive_int(
            proof.get("global_sequence"),
            "ledger proof global_sequence",
        )
        source_sequence = _positive_int(
            proof.get("source_sequence"),
            "ledger proof source_sequence",
        )
        received_at = _timestamp(
            proof.get("received_at"),
            "ledger proof received_at",
        )
        record_observed = _timestamp(
            proof.get("observed_at"),
            "ledger proof observed_at",
        )
        if received_at > observed_at or record_observed != max(
            received_at,
            signed.not_before_utc,
        ):
            raise JournalAnchorError("anchor ledger proof observation semantics differ")
        previous_global = _digest(
            proof.get("previous_global_digest"),
            "ledger proof previous_global_digest",
        )
        previous_source = _digest(
            proof.get("previous_source_digest"),
            "ledger proof previous_source_digest",
        )
        if (global_sequence == 1) != (previous_global == ZERO_DIGEST):
            raise JournalAnchorError(
                "anchor ledger proof global predecessor is invalid"
            )
        if (source_sequence == 1) != (previous_source == ZERO_DIGEST):
            raise JournalAnchorError(
                "anchor ledger proof source predecessor is invalid"
            )
        expected = {
            "event_id": signed.event_id,
            "source_id": signed.source_id,
            "source_sequence": signed.source_sequence,
            "signer_key_id": signed.signer_key_id,
            "event_schema": signed.body_schema,
            "payload_digest": signed.body_digest,
        }
        for field, expected_value in expected.items():
            if proof.get(field) != expected_value:
                raise JournalAnchorError(
                    f"anchor ledger proof {field} differs from envelope"
                )
        event_digest = _digest(
            proof.get("event_digest"),
            "ledger proof event_digest",
        )
        material = {
            key: value
            for key, value in proof.items()
            if key not in {"schema", "event_digest"}
        }
        if _hash(material) != event_digest:
            raise JournalAnchorError("anchor ledger proof digest is invalid")
        return dict(proof)

    def anchor(
        self,
        *,
        journal_name: str,
        journal_schema: str,
        journal_sequence: int,
        journal_head_sha256: str,
    ) -> VerifiedJournalAnchor:
        if (
            not isinstance(journal_name, str)
            or not IDENTIFIER_PATTERN.fullmatch(journal_name)
            or not isinstance(journal_schema, str)
            or not IDENTIFIER_PATTERN.fullmatch(journal_schema)
        ):
            raise JournalAnchorError(
                "journal name and schema must be canonical identifiers"
            )
        sequence = _nonnegative_int(journal_sequence, "journal_sequence")
        head = _digest(journal_head_sha256, "journal_head_sha256")
        if (sequence == 0) != (head == ZERO_DIGEST):
            raise JournalAnchorError(
                "journal sequence zero must exactly bind the zero head"
            )
        stream_id = self.stream_id(journal_name)
        nonce = _digest(self._request_nonce_fn(), "request_nonce")
        if nonce == self._last_nonce:
            raise JournalAnchorError("journal anchor nonce generator repeated a nonce")
        self._last_nonce = nonce
        request = {
            "schema": ANCHOR_REQUEST_SCHEMA,
            "cell_id": DOPEY_VENUE,
            "account_hash": self._account_hash,
            "journal_name": journal_name,
            "journal_schema": journal_schema,
            "journal_stream_id": stream_id,
            "journal_sequence": sequence,
            "journal_head_sha256": head,
            "request_nonce": nonce,
        }
        token = self._cell_token_provider()
        if (
            not isinstance(token, str)
            or not token
            or token != token.strip()
            or any(character.isspace() for character in token)
        ):
            raise JournalAnchorError("cell token is not a canonical secret")
        try:
            response = self._transport(
                CommandFeedHttpRequest(
                    method="POST",
                    url=(
                        f"{self._base_url}/v1/cells/{DOPEY_VENUE}/journal-heads:anchor"
                    ),
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout_seconds=5.0,
                    body=canonical_json_bytes(request),
                )
            )
        except Exception as error:
            raise JournalAnchorError(
                f"journal anchor transport failed:{type(error).__name__}"
            ) from error
        finally:
            token = ""
        if not isinstance(response, CommandFeedHttpResponse) or response.status != 200:
            raise JournalAnchorError("Core rejected the journal head anchor")
        content_type = next(
            (
                str(value).split(";", 1)[0].strip().lower()
                for name, value in response.headers.items()
                if str(name).lower() == "content-type"
            ),
            "",
        )
        if content_type != "application/json":
            raise JournalAnchorError("Core anchor response content type is invalid")
        payload = _strict_response(response.body)
        try:
            _exact_fields(payload, _RESPONSE_FIELDS, "Core anchor response")
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError(str(error)) from error
        if (
            payload.get("schema") != ANCHOR_RESPONSE_SCHEMA
            or payload.get("cell_id") != DOPEY_VENUE
            or payload.get("request_nonce") != nonce
            or not isinstance(payload.get("reused"), bool)
        ):
            raise JournalAnchorError("Core anchor response fields or identity mismatch")
        checkpoint = self._verify_checkpoint(
            payload.get("checkpoint"),
            payload.get("checkpoint_signature"),
        )
        observed_at = _timestamp(
            payload.get("observed_at"),
            "anchor response observed_at",
        )
        now = self._now_fn()
        if now.tzinfo is None or now.utcoffset() is None:
            raise JournalAnchorError("journal anchor clock must be timezone-aware")
        now = now.astimezone(UTC)
        if (
            observed_at > now + MAXIMUM_CLOCK_SKEW
            or now - observed_at > MAXIMUM_RESPONSE_AGE
        ):
            raise JournalAnchorError("Core anchor response is not current")
        expected_checkpoint = {
            "schema": ANCHOR_CHECKPOINT_SCHEMA,
            "cell_id": DOPEY_VENUE,
            "request_nonce": nonce,
            "account_hash": self._account_hash,
            "journal_name": journal_name,
            "journal_schema": journal_schema,
            "journal_stream_id": stream_id,
            "journal_sequence": sequence,
            "journal_head_sha256": head,
            "anchor_body_digest": checkpoint.get("anchor_body_digest"),
            "anchor_event_digest": checkpoint.get("anchor_event_digest"),
            "reused": payload["reused"],
            "observed_at": payload["observed_at"],
        }
        if checkpoint != expected_checkpoint:
            raise JournalAnchorError("Core anchor checkpoint differs from the request")
        envelope = payload.get("anchor_envelope")
        if not isinstance(envelope, dict):
            raise JournalAnchorError("Core journal anchor envelope must be an object")
        try:
            signed = _verify_signed_wrapper(
                envelope,
                self._core_public_key,
                observed_at,
                enforce_current_window=False,
            )
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError(
                "Core journal anchor envelope is invalid"
            ) from error
        if (
            signed.source_id != CORE_SOURCE_ID
            or signed.body_schema != ANCHOR_BODY_SCHEMA
            or signed.expires_at_utc - signed.not_before_utc > MAXIMUM_ANCHOR_TTL
        ):
            raise JournalAnchorError(
                "Core journal anchor envelope authority is invalid"
            )
        body = signed.body
        try:
            _exact_fields(body, _ANCHOR_BODY_FIELDS, "journal anchor body")
        except DumbMoneyAuthorityError as error:
            raise JournalAnchorError(str(error)) from error
        anchored_at = _timestamp(
            body.get("anchored_at"),
            "anchor body anchored_at",
        )
        if (
            body.get("venue") != DOPEY_VENUE
            or body.get("account_hash") != self._account_hash
            or body.get("journal_name") != journal_name
            or body.get("journal_schema") != journal_schema
            or body.get("journal_stream_id") != stream_id
            or body.get("journal_sequence") != sequence
            or body.get("journal_head_sha256") != head
            or anchored_at > observed_at
        ):
            raise JournalAnchorError("journal anchor body differs from the local head")
        previous = _digest(
            body.get("previous_anchor_body_digest"),
            "previous_anchor_body_digest",
        )
        identity = {
            "schema": ANCHOR_BODY_SCHEMA,
            "venue": DOPEY_VENUE,
            "account_hash": self._account_hash,
            "journal_name": journal_name,
            "journal_schema": journal_schema,
            "journal_stream_id": stream_id,
            "journal_sequence": sequence,
            "journal_head_sha256": head,
            "previous_anchor_body_digest": previous,
        }
        if body.get("anchor_id") != _hash(identity):
            raise JournalAnchorError("journal anchor identity is invalid")
        proof = self._verify_ledger_proof(
            payload.get("ledger_proof"),
            signed=signed,
            observed_at=observed_at,
        )
        for field in ("nonce", "correlation_id", "causation_id"):
            if proof.get(field) != envelope.get(field):
                raise JournalAnchorError(
                    f"anchor ledger proof {field} differs from envelope"
                )
        body_digest = _digest(
            checkpoint.get("anchor_body_digest"),
            "checkpoint anchor_body_digest",
        )
        event_digest = _digest(
            checkpoint.get("anchor_event_digest"),
            "checkpoint anchor_event_digest",
        )
        if (
            body_digest != signed.body_digest
            or body_digest != proof.get("payload_digest")
            or event_digest != proof.get("event_digest")
        ):
            raise JournalAnchorError(
                "journal anchor checkpoint proof binding is invalid"
            )
        return VerifiedJournalAnchor(
            journal_name=journal_name,
            journal_sequence=sequence,
            journal_head_sha256=head,
            anchor_body_digest=body_digest,
            anchor_event_digest=event_digest,
            reused=bool(payload["reused"]),
            observed_at=str(payload["observed_at"]),
        )


__all__ = [
    "ANCHOR_BODY_SCHEMA",
    "ANCHOR_CHECKPOINT_SCHEMA",
    "ANCHOR_REQUEST_SCHEMA",
    "ANCHOR_RESPONSE_SCHEMA",
    "CoreJournalAnchorClient",
    "JournalAnchorError",
    "VerifiedJournalAnchor",
]
