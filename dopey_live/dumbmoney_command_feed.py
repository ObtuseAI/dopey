"""Authenticated, pull-only DumbMoney Core command delivery for DOPEY.

Importing this module starts no thread, listener, timer, or network request.
The supervising process must inject both the cell bearer-token provider and a
single-request transport into :func:`poll_once`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Final, Iterator, Mapping, Protocol
from urllib.parse import urlencode, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .dumbmoney_authority import (
    CAPITAL_ENVELOPE_SCHEMA,
    DESIRED_MODE_SCHEMA,
    DOPEY_VENUE,
    KILL_STATE_SCHEMA,
    DumbMoneyAuthorityContext,
    DumbMoneyAuthorityError,
    VerifiedCapitalAuthority,
    VerifiedDesiredMode,
    VerifiedKillState,
    _decode_public_key,
    _sha256_text,
    _urlsafe_b64decode,
    _utc_timestamp,
    canonical_json_bytes,
    verify_signed_control_envelope,
)
from .ledger import artifact_root

COMMAND_PAGE_SCHEMA: Final[str] = "dumbmoney.cell-command-page.v1"
COMMAND_CHECKPOINT_SCHEMA: Final[str] = "dumbmoney.cell-command-checkpoint.v1"
LEDGER_EVENT_PROOF_SCHEMA: Final[str] = "dumbmoney.ledger-event-proof.v1"
COMMAND_STATE_SCHEMA: Final[str] = "dopey.dumbmoney-command-feed-state.v1"
GENESIS_DIGEST: Final[str] = "0" * 64
DEFAULT_PAGE_LIMIT: Final[int] = 250
MAXIMUM_PAGE_LIMIT: Final[int] = 1000
MAXIMUM_RESPONSE_BYTES: Final[int] = 1_048_576
MAXIMUM_PAGE_CLOCK_SKEW: Final[timedelta] = timedelta(seconds=60)
MAXIMUM_KILL_CHANGED_AT_FUTURE_SKEW: Final[timedelta] = timedelta(seconds=5)
VALID_REQUIRED_ACTIONS: Final[frozenset[str]] = frozenset(
    {"APPLY_SIGNED_CONTROLS", "PAUSE_NEW_RISK", "CANCEL_AND_RECONCILE"}
)
COMMAND_PAGE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "request_nonce",
        "observed_at",
        "after_sequence",
        "after_digest",
        "next_sequence",
        "next_digest",
        "ledger_head_sequence",
        "ledger_head_digest",
        "has_more",
        "required_action",
        "commands",
        "checkpoint",
        "checkpoint_signature",
    }
)
COMMAND_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "global_sequence",
        "event_id",
        "event_digest",
        "body_schema",
        "valid_now",
        "transport_window_current",
        "authority_effect",
        "ledger_proof",
        "envelope",
    }
)
ORDERED_COMMAND_FIELDS: Final[frozenset[str]] = COMMAND_FIELDS - {"envelope"}
COMMAND_CHECKPOINT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "request_nonce",
        "after_sequence",
        "after_digest",
        "ordered_commands",
        "next_sequence",
        "next_digest",
        "ledger_head_sequence",
        "ledger_head_digest",
        "observed_at",
        "required_action",
    }
)
CHECKPOINT_SIGNATURE_FIELDS: Final[frozenset[str]] = frozenset(
    {"algorithm", "signer_key_id", "signature"}
)
LEDGER_EVENT_PROOF_FIELDS: Final[frozenset[str]] = frozenset(
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
VALID_AUTHORITY_EFFECTS: Final[frozenset[str]] = frozenset(
    {"APPLY_FAIL_CLOSED", "APPLY_POSITIVE", "HISTORICAL_ONLY"}
)
COMMAND_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "cell_id",
        "next_sequence",
        "next_digest",
        "kill_envelope",
        "desired_mode_envelope",
        "capital_envelope",
        "updated_at",
    }
)


class DumbMoneyCommandFeedError(RuntimeError):
    """Raised internally when the command feed cannot advance safely."""


@dataclass(frozen=True)
class CommandFeedHttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    timeout_seconds: float
    body: bytes | None = None


@dataclass(frozen=True)
class CommandFeedHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class CommandFeedTransport(Protocol):
    def __call__(
        self,
        request: CommandFeedHttpRequest,
    ) -> CommandFeedHttpResponse: ...


@dataclass(frozen=True)
class DumbMoneyCommandFeedClient:
    """Injected, side-effect-free-until-called command-feed binding."""

    base_url: str
    cell_bearer_provider: Callable[[], str]
    trusted_public_key: bytes
    trusted_operator_public_keys: Mapping[str, bytes]
    expected_account_hash: str
    state_path: Path
    transport: CommandFeedTransport
    limit: int = DEFAULT_PAGE_LIMIT
    timeout_seconds: float = 5.0

    def poll_once(self, now_utc: datetime) -> DumbMoneyCommandDispatch:
        return poll_once(
            base_url=self.base_url,
            cell_bearer_provider=self.cell_bearer_provider,
            trusted_public_key=self.trusted_public_key,
            trusted_operator_public_keys=self.trusted_operator_public_keys,
            expected_account_hash=self.expected_account_hash,
            state_path=self.state_path,
            transport=self.transport,
            now_utc=now_utc,
            limit=self.limit,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True)
class DumbMoneyCommandDispatch:
    """Controls safe to hand to one Live Branch cycle."""

    desired_mode: str
    kill_active: bool
    allow_new_risk: bool
    capital_authority: DumbMoneyAuthorityContext | None
    fail_closed_reason: str
    required_action: str
    caught_up: bool
    next_sequence: int
    next_digest: str
    applied_event_ids: tuple[str, ...]

    def evidence(self) -> dict[str, Any]:
        return {
            "desired_mode": self.desired_mode,
            "kill_active": self.kill_active,
            "allow_new_risk": self.allow_new_risk,
            "capital_authority_present": self.capital_authority is not None,
            "fail_closed_reason": self.fail_closed_reason,
            "required_action": self.required_action,
            "caught_up": self.caught_up,
            "next_sequence": self.next_sequence,
            "next_digest": self.next_digest,
            "applied_event_ids": list(self.applied_event_ids),
        }


@dataclass(frozen=True)
class _CommandState:
    next_sequence: int = 0
    next_digest: str = GENESIS_DIGEST
    kill_envelope: dict[str, Any] | None = None
    desired_mode_envelope: dict[str, Any] | None = None
    capital_envelope: dict[str, Any] | None = None
    updated_at: str = "1970-01-01T00:00:00Z"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMMAND_STATE_SCHEMA,
            "cell_id": DOPEY_VENUE,
            "next_sequence": self.next_sequence,
            "next_digest": self.next_digest,
            "kill_envelope": self.kill_envelope,
            "desired_mode_envelope": self.desired_mode_envelope,
            "capital_envelope": self.capital_envelope,
            "updated_at": self.updated_at,
        }


def command_feed_state_path(repository_root: Path) -> Path:
    return artifact_root(repository_root) / "dumbmoney_command_feed_state.json"


def command_feed_head(state_path: Path) -> tuple[int, str]:
    """Return one integrity-checked persisted cursor for Core anchoring."""

    state = _read_state(state_path.resolve())
    return state.next_sequence, state.next_digest


def _format_utc(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    rendered = utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds")
    return rendered.replace("+00:00", "Z")


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DumbMoneyCommandFeedError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DumbMoneyCommandFeedError(f"{label} must be a nonnegative integer")
    return value


def _digest(value: Any, label: str) -> str:
    try:
        return _sha256_text(value, label)
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyCommandFeedError(str(error)) from error


def _trusted_keyring(
    trusted_public_key: bytes,
    trusted_operator_public_keys: Mapping[str, bytes],
) -> tuple[bytes, dict[str, bytes]]:
    try:
        core_key = _decode_public_key(trusted_public_key)
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyCommandFeedError("pinned Core public key is invalid") from error
    core_key_id = hashlib.sha256(core_key).hexdigest()
    if (
        not isinstance(trusted_operator_public_keys, Mapping)
        or not 1 <= len(trusted_operator_public_keys) <= 16
    ):
        raise DumbMoneyCommandFeedError(
            "trusted operator public-key set must contain 1 to 16 keys"
        )
    operator_keys: dict[str, bytes] = {}
    for raw_key_id, raw_key in trusted_operator_public_keys.items():
        key_id = _digest(raw_key_id, "trusted operator key ID")
        try:
            public_key = _decode_public_key(raw_key)
        except DumbMoneyAuthorityError as error:
            raise DumbMoneyCommandFeedError(
                f"trusted operator public key is invalid: key_id={key_id}"
            ) from error
        if hashlib.sha256(public_key).hexdigest() != key_id:
            raise DumbMoneyCommandFeedError(
                f"trusted operator key ID does not bind its key: key_id={key_id}"
            )
        if key_id == core_key_id:
            raise DumbMoneyCommandFeedError(
                "Core checkpoint key and operator command keys must be disjoint"
            )
        operator_keys[key_id] = public_key
    return core_key, operator_keys


def _command_public_key(
    envelope: Mapping[str, Any],
    body_schema: str,
    core_public_key: bytes,
    operator_public_keys: Mapping[str, bytes],
) -> bytes:
    signer_key_id = _digest(
        envelope.get("signer_key_id"),
        "command signer_key_id",
    )
    core_key_id = hashlib.sha256(core_public_key).hexdigest()
    if body_schema == CAPITAL_ENVELOPE_SCHEMA:
        if signer_key_id != core_key_id:
            raise DumbMoneyCommandFeedError(
                "CapitalEnvelopeV1 command is not signed by pinned Core"
            )
        return core_public_key
    if body_schema in {DESIRED_MODE_SCHEMA, KILL_STATE_SCHEMA}:
        public_key = operator_public_keys.get(signer_key_id)
        if public_key is None:
            raise DumbMoneyCommandFeedError(
                "operator control command signer is outside the sealed operator key set"
            )
        return public_key
    raise DumbMoneyCommandFeedError(
        f"command body schema is unsupported: {body_schema}"
    )


def _verify_checkpoint_signature(
    checkpoint: Mapping[str, Any],
    signature_payload: Mapping[str, Any],
    core_public_key: bytes,
) -> None:
    _exact_fields(
        checkpoint,
        COMMAND_CHECKPOINT_FIELDS,
        "command checkpoint",
    )
    _exact_fields(
        signature_payload,
        CHECKPOINT_SIGNATURE_FIELDS,
        "command checkpoint signature",
    )
    if checkpoint.get("schema") != COMMAND_CHECKPOINT_SCHEMA:
        raise DumbMoneyCommandFeedError("command checkpoint schema is unsupported")
    if signature_payload.get("algorithm") != "Ed25519":
        raise DumbMoneyCommandFeedError(
            "command checkpoint signature algorithm is unsupported"
        )
    expected_key_id = hashlib.sha256(core_public_key).hexdigest()
    if signature_payload.get("signer_key_id") != expected_key_id:
        raise DumbMoneyCommandFeedError("command checkpoint signer is not pinned Core")
    try:
        signature = _urlsafe_b64decode(str(signature_payload.get("signature", "")))
        if len(signature) != 64:
            raise ValueError("Ed25519 signature must be 64 bytes")
        Ed25519PublicKey.from_public_bytes(core_public_key).verify(
            signature,
            canonical_json_bytes(dict(checkpoint)),
        )
    except (InvalidSignature, ValueError) as error:
        raise DumbMoneyCommandFeedError(
            "command checkpoint signature is invalid"
        ) from error


def _exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        raise DumbMoneyCommandFeedError(
            f"{label} schema mismatch: missing={missing}, unknown={unknown}"
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DumbMoneyCommandFeedError(f"duplicate JSON key is prohibited: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise DumbMoneyCommandFeedError(f"non-finite JSON value is prohibited: {value}")


def _validate_json_domain(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DumbMoneyCommandFeedError(f"{path} contains a non-finite number")
        raise DumbMoneyCommandFeedError(
            f"{path} contains a float outside the signed integer domain"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_domain(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DumbMoneyCommandFeedError(f"{path} contains a non-string object key")
        for key, item in value.items():
            _validate_json_domain(item, f"{path}.{key}")
        return
    raise DumbMoneyCommandFeedError(
        f"{path} contains unsupported JSON type {type(value).__name__}"
    )


def _loads_strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DumbMoneyCommandFeedError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise DumbMoneyCommandFeedError(f"{label} root must be an object")
    _validate_json_domain(value)
    return value


def _validated_ledger_proof(
    raw_proof: Any,
    command: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(raw_proof, dict):
        raise DumbMoneyCommandFeedError("command ledger_proof must be an object")
    _exact_fields(raw_proof, LEDGER_EVENT_PROOF_FIELDS, "ledger event proof")
    if raw_proof.get("schema") != LEDGER_EVENT_PROOF_SCHEMA:
        raise DumbMoneyCommandFeedError("ledger event proof schema is unsupported")
    global_sequence = _positive_int(
        raw_proof.get("global_sequence"),
        "ledger proof global_sequence",
    )
    source_sequence = _positive_int(
        raw_proof.get("source_sequence"),
        "ledger proof source_sequence",
    )
    event_id = _digest(raw_proof.get("event_id"), "ledger proof event_id")
    signer_key_id = _digest(
        raw_proof.get("signer_key_id"),
        "ledger proof signer_key_id",
    )
    payload_digest = _digest(
        raw_proof.get("payload_digest"),
        "ledger proof payload_digest",
    )
    _digest(
        raw_proof.get("previous_source_digest"),
        "ledger proof previous_source_digest",
    )
    _digest(
        raw_proof.get("previous_global_digest"),
        "ledger proof previous_global_digest",
    )
    event_digest = _digest(
        raw_proof.get("event_digest"),
        "ledger proof event_digest",
    )
    for field in ("source_id", "nonce", "event_schema"):
        value = raw_proof.get(field)
        if not isinstance(value, str) or not value:
            raise DumbMoneyCommandFeedError(f"ledger proof {field} must be nonempty")
    correlation_id = raw_proof.get("correlation_id")
    if not isinstance(correlation_id, str) or not correlation_id:
        raise DumbMoneyCommandFeedError("ledger proof correlation_id must be nonempty")
    causation_id = raw_proof.get("causation_id")
    if causation_id is not None:
        _digest(causation_id, "ledger proof causation_id")
    try:
        observed_at = _utc_timestamp(
            raw_proof.get("observed_at"),
            "ledger proof observed_at",
        )
        received_at = _utc_timestamp(
            raw_proof.get("received_at"),
            "ledger proof received_at",
        )
        envelope_not_before = _utc_timestamp(
            envelope.get("not_before"),
            "ledger proof envelope not_before",
        )
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyCommandFeedError(str(error)) from error
    if observed_at != max(received_at, envelope_not_before):
        raise DumbMoneyCommandFeedError(
            "ledger proof observed_at does not match ledger receipt semantics"
        )
    if (source_sequence == 1) is not (
        raw_proof["previous_source_digest"] == GENESIS_DIGEST
    ):
        raise DumbMoneyCommandFeedError(
            "ledger proof source-chain genesis semantics are invalid"
        )
    if (global_sequence == 1) is not (
        raw_proof["previous_global_digest"] == GENESIS_DIGEST
    ):
        raise DumbMoneyCommandFeedError(
            "ledger proof global-chain genesis semantics are invalid"
        )
    event_core = {
        key: value
        for key, value in raw_proof.items()
        if key not in {"schema", "event_digest"}
    }
    recomputed = hashlib.sha256(canonical_json_bytes(event_core)).hexdigest()
    if recomputed != event_digest:
        raise DumbMoneyCommandFeedError("ledger proof event_digest does not recompute")
    duplicate_bindings = (
        (global_sequence, command.get("global_sequence"), "global_sequence"),
        (event_id, command.get("event_id"), "event_id"),
        (event_digest, command.get("event_digest"), "event_digest"),
        (raw_proof["event_schema"], command.get("body_schema"), "body_schema"),
        (event_id, envelope.get("event_id"), "envelope event_id"),
        (raw_proof["source_id"], envelope.get("source_id"), "source_id"),
        (
            source_sequence,
            envelope.get("source_sequence"),
            "source_sequence",
        ),
        (
            signer_key_id,
            envelope.get("signer_key_id"),
            "signer_key_id",
        ),
        (raw_proof["nonce"], envelope.get("nonce"), "nonce"),
        (
            raw_proof["event_schema"],
            envelope.get("body_schema"),
            "event_schema",
        ),
        (
            correlation_id,
            envelope.get("correlation_id"),
            "correlation_id",
        ),
        (causation_id, envelope.get("causation_id"), "causation_id"),
        (
            payload_digest,
            envelope.get("body_digest"),
            "payload_digest",
        ),
    )
    for observed, expected, label in duplicate_bindings:
        if observed != expected:
            raise DumbMoneyCommandFeedError(f"ledger proof {label} binding mismatch")
    return dict(raw_proof)


def _validate_command_projection(
    command: Mapping[str, Any],
    verified: VerifiedCapitalAuthority | VerifiedDesiredMode | VerifiedKillState,
    now_utc: datetime,
) -> None:
    transport_current = False
    envelope = command["envelope"]
    try:
        wrapper_not_before = _utc_timestamp(
            envelope.get("not_before"),
            "command envelope not_before",
        )
        wrapper_expires = _utc_timestamp(
            envelope.get("expires_at"),
            "command envelope expires_at",
        )
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyCommandFeedError(str(error)) from error
    now = now_utc.astimezone(timezone.utc)
    transport_current = wrapper_not_before <= now < wrapper_expires
    if isinstance(verified, VerifiedCapitalAuthority):
        body_not_before = _utc_timestamp(
            verified.envelope.not_before,
            "capital body not_before",
        )
        body_expires = _utc_timestamp(
            verified.envelope.expires_at,
            "capital body expires_at",
        )
        body_current = body_not_before <= now < body_expires
        positive_grant = True
    elif isinstance(verified, VerifiedDesiredMode):
        body_not_before = _utc_timestamp(
            verified.desired_mode.not_before,
            "desired mode body not_before",
        )
        body_expires = _utc_timestamp(
            verified.desired_mode.expires_at,
            "desired mode body expires_at",
        )
        body_current = body_not_before <= now < body_expires
        positive_grant = verified.desired_mode.mode == "LIVE"
    else:
        changed_at = _utc_timestamp(
            verified.kill_state.changed_at,
            "kill state changed_at",
        )
        body_current = changed_at <= now + MAXIMUM_KILL_CHANGED_AT_FUTURE_SKEW
        positive_grant = not verified.kill_state.active
    valid_now = transport_current and body_current
    expected_effect = (
        "APPLY_FAIL_CLOSED"
        if not positive_grant
        else "APPLY_POSITIVE"
        if valid_now
        else "HISTORICAL_ONLY"
    )
    if command.get("transport_window_current") is not transport_current:
        raise DumbMoneyCommandFeedError(
            "command transport_window_current projection mismatch"
        )
    if command.get("valid_now") is not valid_now:
        raise DumbMoneyCommandFeedError("command valid_now projection mismatch")
    if command.get("authority_effect") != expected_effect:
        raise DumbMoneyCommandFeedError("command authority_effect projection mismatch")


def _validated_loopback_origin(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as error:
        raise DumbMoneyCommandFeedError(
            "DumbMoney Core URL has an invalid port"
        ) from error
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65_535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DumbMoneyCommandFeedError(
            "DumbMoney Core command feed must use an exact "
            "http://127.0.0.1:<port> origin"
        )
    return f"http://127.0.0.1:{port}"


def _cell_bearer(provider: Callable[[], str]) -> str:
    try:
        value = provider()
    except Exception as error:
        raise DumbMoneyCommandFeedError(
            f"cell bearer provider failed: {type(error).__name__}"
        ) from error
    if (
        not isinstance(value, str)
        or not 32 <= len(value) <= 4096
        or any(character.isspace() or ord(character) < 33 for character in value)
    ):
        raise DumbMoneyCommandFeedError(
            "cell bearer must be an injected high-entropy non-whitespace string"
        )
    return value


def _state_from_payload(payload: dict[str, Any]) -> _CommandState:
    _exact_fields(payload, COMMAND_STATE_FIELDS, "command state")
    if payload.get("schema") != COMMAND_STATE_SCHEMA:
        raise DumbMoneyCommandFeedError("command state schema is unsupported")
    if payload.get("cell_id") != DOPEY_VENUE:
        raise DumbMoneyCommandFeedError("command state targets another cell")
    next_sequence = _nonnegative_int(
        payload.get("next_sequence"),
        "command state next_sequence",
    )
    next_digest = _digest(
        payload.get("next_digest"),
        "command state next_digest",
    )
    if next_sequence == 0 and next_digest != GENESIS_DIGEST:
        raise DumbMoneyCommandFeedError(
            "bootstrap command cursor must use the zero digest"
        )
    for field in (
        "kill_envelope",
        "desired_mode_envelope",
        "capital_envelope",
    ):
        value = payload.get(field)
        if value is not None and (
            not isinstance(value, dict)
            or not all(isinstance(key, str) for key in value)
        ):
            raise DumbMoneyCommandFeedError(
                f"command state {field} must be an object or null"
            )
    updated_at = str(payload.get("updated_at", ""))
    try:
        _utc_timestamp(updated_at, "command state updated_at")
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyCommandFeedError(str(error)) from error
    return _CommandState(
        next_sequence=next_sequence,
        next_digest=next_digest,
        kill_envelope=payload.get("kill_envelope"),
        desired_mode_envelope=payload.get("desired_mode_envelope"),
        capital_envelope=payload.get("capital_envelope"),
        updated_at=updated_at,
    )


def _read_state(path: Path) -> _CommandState:
    if not path.exists():
        return _CommandState()
    if not path.is_file():
        raise DumbMoneyCommandFeedError("command state path is not a file")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DumbMoneyCommandFeedError("command state is unreadable") from error
    if len(raw) > MAXIMUM_RESPONSE_BYTES:
        raise DumbMoneyCommandFeedError("command state exceeds its size ceiling")
    return _state_from_payload(_loads_strict_json(raw, "command state"))


def _write_state(path: Path, state: _CommandState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            state.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


@contextmanager
def _exclusive_state_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise DumbMoneyCommandFeedError(
            "command feed state is locked by another poller"
        ) from error
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _response_content_type(headers: Mapping[str, str]) -> str:
    return next(
        (
            str(value).lower()
            for name, value in headers.items()
            if str(name).lower() == "content-type"
        ),
        "",
    )


def _current_persisted_control(
    envelope: dict[str, Any] | None,
    core_public_key: bytes,
    operator_public_keys: Mapping[str, bytes],
    expected_account_hash: str,
    now_utc: datetime,
) -> VerifiedCapitalAuthority | VerifiedDesiredMode | VerifiedKillState | None:
    if envelope is None:
        return None
    body_schema = str(envelope.get("body_schema", ""))
    public_key = _command_public_key(
        envelope,
        body_schema,
        core_public_key,
        operator_public_keys,
    )
    return verify_signed_control_envelope(
        envelope,
        public_key,
        now_utc,
        expected_account_hash,
        enforce_current_window=True,
    )


def _historical_persisted_control(
    envelope: dict[str, Any] | None,
    core_public_key: bytes,
    operator_public_keys: Mapping[str, bytes],
    expected_account_hash: str,
    now_utc: datetime,
) -> VerifiedCapitalAuthority | VerifiedDesiredMode | VerifiedKillState | None:
    if envelope is None:
        return None
    body_schema = str(envelope.get("body_schema", ""))
    public_key = _command_public_key(
        envelope,
        body_schema,
        core_public_key,
        operator_public_keys,
    )
    return verify_signed_control_envelope(
        envelope,
        public_key,
        now_utc,
        expected_account_hash,
        enforce_current_window=False,
    )


def _fail_closed(
    state: _CommandState,
    reason: str,
    *,
    kill_active: bool = True,
    required_action: str = "FAIL_CLOSED",
    caught_up: bool = False,
    applied_event_ids: tuple[str, ...] = (),
) -> DumbMoneyCommandDispatch:
    return DumbMoneyCommandDispatch(
        desired_mode="PAUSED",
        kill_active=kill_active,
        allow_new_risk=False,
        capital_authority=None,
        fail_closed_reason=reason,
        required_action=required_action,
        caught_up=caught_up,
        next_sequence=state.next_sequence,
        next_digest=state.next_digest,
        applied_event_ids=applied_event_ids,
    )


def _validated_page(
    payload: dict[str, Any],
    state: _CommandState,
    now_utc: datetime,
    limit: int,
    core_public_key: bytes,
    expected_request_nonce: str,
) -> tuple[
    int,
    str,
    bool,
    str,
    tuple[dict[str, Any], ...],
]:
    _exact_fields(payload, COMMAND_PAGE_FIELDS, "command page")
    if payload.get("schema") != COMMAND_PAGE_SCHEMA:
        raise DumbMoneyCommandFeedError("command page schema is unsupported")
    raw_checkpoint = payload.get("checkpoint")
    raw_checkpoint_signature = payload.get("checkpoint_signature")
    if not isinstance(raw_checkpoint, dict) or not isinstance(
        raw_checkpoint_signature,
        dict,
    ):
        raise DumbMoneyCommandFeedError(
            "command page checkpoint and signature must be objects"
        )
    _verify_checkpoint_signature(
        raw_checkpoint,
        raw_checkpoint_signature,
        core_public_key,
    )
    checkpoint_bindings = {
        "cell_id": payload.get("cell_id"),
        "request_nonce": payload.get("request_nonce"),
        "observed_at": payload.get("observed_at"),
        "after_sequence": payload.get("after_sequence"),
        "after_digest": payload.get("after_digest"),
        "next_sequence": payload.get("next_sequence"),
        "next_digest": payload.get("next_digest"),
        "ledger_head_sequence": payload.get("ledger_head_sequence"),
        "ledger_head_digest": payload.get("ledger_head_digest"),
        "required_action": payload.get("required_action"),
    }
    if any(
        raw_checkpoint.get(field) != value
        for field, value in checkpoint_bindings.items()
    ):
        raise DumbMoneyCommandFeedError(
            "signed checkpoint does not bind command page metadata"
        )
    if payload.get("cell_id") != DOPEY_VENUE:
        raise DumbMoneyCommandFeedError("command page targets another cell")
    request_nonce = _digest(
        payload.get("request_nonce"),
        "command page request_nonce",
    )
    if request_nonce != expected_request_nonce:
        raise DumbMoneyCommandFeedError(
            "command page request_nonce does not match this poll"
        )
    if payload.get("after_sequence") != state.next_sequence:
        raise DumbMoneyCommandFeedError("command page sequence gap or rollback")
    if payload.get("after_digest") != state.next_digest:
        raise DumbMoneyCommandFeedError("command page starting digest mismatch")
    next_sequence = _nonnegative_int(
        payload.get("next_sequence"),
        "command page next_sequence",
    )
    if (
        next_sequence < state.next_sequence
        or next_sequence - state.next_sequence > limit
    ):
        raise DumbMoneyCommandFeedError("command page sequence advance is invalid")
    next_digest = _digest(
        payload.get("next_digest"),
        "command page next_digest",
    )
    ledger_head = _nonnegative_int(
        payload.get("ledger_head_sequence"),
        "command page ledger_head_sequence",
    )
    ledger_head_digest = _digest(
        payload.get("ledger_head_digest"),
        "command page ledger_head_digest",
    )
    if next_sequence > ledger_head:
        raise DumbMoneyCommandFeedError(
            "command page cursor is ahead of the ledger head"
        )
    if next_sequence == ledger_head and next_digest != ledger_head_digest:
        raise DumbMoneyCommandFeedError(
            "caught-up page cursor does not bind the ledger head digest"
        )
    has_more = payload.get("has_more")
    if not isinstance(has_more, bool) or has_more is not (next_sequence < ledger_head):
        raise DumbMoneyCommandFeedError("command page has_more is inconsistent")
    if next_sequence == state.next_sequence and next_digest != state.next_digest:
        raise DumbMoneyCommandFeedError("stationary command cursor changed its digest")
    required_action = str(payload.get("required_action", ""))
    if required_action not in VALID_REQUIRED_ACTIONS:
        raise DumbMoneyCommandFeedError("command page required_action is unsupported")
    try:
        observed_at = _utc_timestamp(
            payload.get("observed_at"),
            "command page observed_at",
        )
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyCommandFeedError(str(error)) from error
    now = now_utc.astimezone(timezone.utc)
    if abs(now - observed_at) > MAXIMUM_PAGE_CLOCK_SKEW:
        raise DumbMoneyCommandFeedError(
            "command page observed_at is stale or future-dated"
        )
    raw_commands = payload.get("commands")
    if not isinstance(raw_commands, list) or len(raw_commands) > limit:
        raise DumbMoneyCommandFeedError("command page commands must be a bounded array")
    ordered_commands = raw_checkpoint.get("ordered_commands")
    if not isinstance(ordered_commands, list) or len(ordered_commands) != len(
        raw_commands
    ):
        raise DumbMoneyCommandFeedError(
            "signed checkpoint ordered_commands does not match the page"
        )
    commands: list[dict[str, Any]] = []
    previous_sequence = state.next_sequence
    previous_event_digest = state.next_digest
    event_ids: set[str] = set()
    event_digests: set[str] = set()
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, dict):
            raise DumbMoneyCommandFeedError(
                f"command page command {index} must be an object"
            )
        _exact_fields(raw_command, COMMAND_FIELDS, f"command {index}")
        global_sequence = _positive_int(
            raw_command.get("global_sequence"),
            f"command {index} global_sequence",
        )
        prior_sequence = previous_sequence
        if not previous_sequence < global_sequence <= next_sequence:
            raise DumbMoneyCommandFeedError(
                "command global sequences are duplicated, reordered, "
                "or outside the page"
            )
        event_id = _digest(raw_command.get("event_id"), f"command {index} event_id")
        event_digest = _digest(
            raw_command.get("event_digest"),
            f"command {index} event_digest",
        )
        if event_id in event_ids or event_digest in event_digests:
            raise DumbMoneyCommandFeedError(
                "command page repeats an event identity or digest"
            )
        event_ids.add(event_id)
        event_digests.add(event_digest)
        if not isinstance(raw_command.get("valid_now"), bool):
            raise DumbMoneyCommandFeedError(
                "command valid_now projection must be a boolean"
            )
        if not isinstance(
            raw_command.get("transport_window_current"),
            bool,
        ):
            raise DumbMoneyCommandFeedError(
                "command transport_window_current projection must be a boolean"
            )
        if raw_command.get("authority_effect") not in VALID_AUTHORITY_EFFECTS:
            raise DumbMoneyCommandFeedError(
                "command authority_effect projection is unsupported"
            )
        envelope = raw_command.get("envelope")
        if not isinstance(envelope, dict):
            raise DumbMoneyCommandFeedError(
                f"command {index} envelope must be an object"
            )
        if envelope.get("event_id") != event_id:
            raise DumbMoneyCommandFeedError(
                f"command {index} event_id does not bind its envelope"
            )
        if envelope.get("body_schema") != raw_command.get("body_schema"):
            raise DumbMoneyCommandFeedError(
                f"command {index} body_schema does not bind its envelope"
            )
        proof = _validated_ledger_proof(
            raw_command.get("ledger_proof"),
            raw_command,
            envelope,
        )
        if (
            global_sequence == state.next_sequence + 1
            and proof["previous_global_digest"] != state.next_digest
        ):
            raise DumbMoneyCommandFeedError(
                "first contiguous ledger proof does not bind the request cursor"
            )
        if (
            commands
            and global_sequence == prior_sequence + 1
            and proof["previous_global_digest"] != previous_event_digest
        ):
            raise DumbMoneyCommandFeedError(
                "contiguous ledger proofs do not form a global hash chain"
            )
        ordered_command = ordered_commands[index]
        if not isinstance(ordered_command, dict):
            raise DumbMoneyCommandFeedError(
                "signed checkpoint ordered command must be an object"
            )
        _exact_fields(
            ordered_command,
            ORDERED_COMMAND_FIELDS,
            f"checkpoint ordered command {index}",
        )
        projected = {
            key: value for key, value in raw_command.items() if key != "envelope"
        }
        if ordered_command != projected:
            raise DumbMoneyCommandFeedError(
                "signed checkpoint ordered command projection mismatch"
            )
        commands.append(dict(raw_command))
        previous_sequence = global_sequence
        previous_event_digest = event_digest
    if commands and commands[-1]["global_sequence"] == next_sequence:
        if commands[-1]["event_digest"] != next_digest:
            raise DumbMoneyCommandFeedError(
                "command page terminal event digest does not bind the next cursor"
            )
    return next_sequence, next_digest, has_more, required_action, tuple(commands)


def _apply_commands(
    state: _CommandState,
    commands: tuple[dict[str, Any], ...],
    core_public_key: bytes,
    operator_public_keys: Mapping[str, bytes],
    expected_account_hash: str,
    now_utc: datetime,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    tuple[str, ...],
]:
    historical_kill = _historical_persisted_control(
        state.kill_envelope,
        core_public_key,
        operator_public_keys,
        expected_account_hash,
        now_utc,
    )
    historical_mode = _historical_persisted_control(
        state.desired_mode_envelope,
        core_public_key,
        operator_public_keys,
        expected_account_hash,
        now_utc,
    )
    historical_capital = _historical_persisted_control(
        state.capital_envelope,
        core_public_key,
        operator_public_keys,
        expected_account_hash,
        now_utc,
    )
    if historical_kill is not None and not isinstance(
        historical_kill,
        VerifiedKillState,
    ):
        raise DumbMoneyCommandFeedError("persisted kill control has the wrong schema")
    if historical_mode is not None and not isinstance(
        historical_mode,
        VerifiedDesiredMode,
    ):
        raise DumbMoneyCommandFeedError("persisted mode control has the wrong schema")
    if historical_capital is not None and not isinstance(
        historical_capital,
        VerifiedCapitalAuthority,
    ):
        raise DumbMoneyCommandFeedError(
            "persisted capital control has the wrong schema"
        )
    kill_envelope = state.kill_envelope
    desired_envelope = state.desired_mode_envelope
    capital_envelope = state.capital_envelope
    kill_generation = (
        historical_kill.kill_state.generation if historical_kill is not None else 0
    )
    mode_revision = (
        historical_mode.desired_mode.revision if historical_mode is not None else 0
    )
    capital_generation = (
        historical_capital.envelope.fencing_generation
        if historical_capital is not None
        else 0
    )
    applied_event_ids: list[str] = []
    for command in commands:
        envelope = dict(command["envelope"])
        body_schema = str(command["body_schema"])
        try:
            public_key = _command_public_key(
                envelope,
                body_schema,
                core_public_key,
                operator_public_keys,
            )
            verified = verify_signed_control_envelope(
                envelope,
                public_key,
                now_utc,
                expected_account_hash,
                enforce_current_window=False,
            )
        except DumbMoneyAuthorityError as error:
            raise DumbMoneyCommandFeedError(
                f"signed command verification failed: {error}"
            ) from error
        _validate_command_projection(command, verified, now_utc)
        if isinstance(verified, VerifiedKillState):
            if body_schema != KILL_STATE_SCHEMA:
                raise DumbMoneyCommandFeedError("verified kill schema mismatch")
            if verified.kill_state.generation != kill_generation + 1:
                raise DumbMoneyCommandFeedError("KillStateV1 generation gap or replay")
            kill_generation = verified.kill_state.generation
            kill_envelope = envelope
        elif isinstance(verified, VerifiedDesiredMode):
            if body_schema != DESIRED_MODE_SCHEMA:
                raise DumbMoneyCommandFeedError("verified desired-mode schema mismatch")
            if verified.desired_mode.revision != mode_revision + 1:
                raise DumbMoneyCommandFeedError("DesiredModeV1 revision gap or replay")
            mode_revision = verified.desired_mode.revision
            desired_envelope = envelope
        elif isinstance(verified, VerifiedCapitalAuthority):
            if body_schema != CAPITAL_ENVELOPE_SCHEMA:
                raise DumbMoneyCommandFeedError("verified capital schema mismatch")
            if verified.envelope.fencing_generation != capital_generation + 1:
                raise DumbMoneyCommandFeedError(
                    "CapitalEnvelopeV1 fencing generation gap or replay"
                )
            capital_generation = verified.envelope.fencing_generation
            capital_envelope = envelope
        else:  # pragma: no cover - closed by the verifier union
            raise DumbMoneyCommandFeedError("unsupported verified command")
        applied_event_ids.append(verified.event_id)
    return (
        kill_envelope,
        desired_envelope,
        capital_envelope,
        tuple(applied_event_ids),
    )


def _dispatch_from_state(
    state: _CommandState,
    core_public_key: bytes,
    operator_public_keys: Mapping[str, bytes],
    expected_account_hash: str,
    now_utc: datetime,
    *,
    required_action: str,
    caught_up: bool,
    applied_event_ids: tuple[str, ...],
) -> DumbMoneyCommandDispatch:
    try:
        kill = _current_persisted_control(
            state.kill_envelope,
            core_public_key,
            operator_public_keys,
            expected_account_hash,
            now_utc,
        )
    except DumbMoneyAuthorityError:
        _historical_persisted_control(
            state.kill_envelope,
            core_public_key,
            operator_public_keys,
            expected_account_hash,
            now_utc,
        )
        return _fail_closed(
            state,
            "kill_control_stale_or_future",
            # A previously authenticated active kill is durable. An expired
            # inactive projection is no longer positive evidence that kill is
            # clear, so unknown also resolves to the risk-reducing state.
            kill_active=True,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    if kill is None or not isinstance(kill, VerifiedKillState):
        return _fail_closed(
            state,
            "verified_kill_state_missing",
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    if kill.kill_state.active:
        return _fail_closed(
            state,
            "signed_global_kill_active",
            kill_active=True,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    try:
        desired = _current_persisted_control(
            state.desired_mode_envelope,
            core_public_key,
            operator_public_keys,
            expected_account_hash,
            now_utc,
        )
        capital = _current_persisted_control(
            state.capital_envelope,
            core_public_key,
            operator_public_keys,
            expected_account_hash,
            now_utc,
        )
    except DumbMoneyAuthorityError:
        return _fail_closed(
            state,
            "mode_or_capital_control_stale_future_or_invalid",
            kill_active=False,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    if desired is None or not isinstance(desired, VerifiedDesiredMode):
        return _fail_closed(
            state,
            "verified_desired_mode_missing",
            kill_active=False,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    if desired.desired_mode.mode != "LIVE":
        dispatch = _fail_closed(
            state,
            f"desired_mode_{desired.desired_mode.mode.lower()}",
            kill_active=False,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
        return DumbMoneyCommandDispatch(
            **{
                **dispatch.__dict__,
                "desired_mode": desired.desired_mode.mode,
            }
        )
    if capital is None or not isinstance(capital, VerifiedCapitalAuthority):
        return _fail_closed(
            state,
            "verified_capital_authority_missing",
            kill_active=False,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    policy_epochs = {
        kill.kill_state.policy_epoch,
        desired.desired_mode.policy_epoch,
        capital.envelope.policy_epoch,
    }
    if len(policy_epochs) != 1:
        return _fail_closed(
            state,
            "control_policy_epoch_mismatch",
            kill_active=False,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    if not caught_up:
        return _fail_closed(
            state,
            "command_feed_not_caught_up",
            kill_active=False,
            required_action=required_action,
            caught_up=False,
            applied_event_ids=applied_event_ids,
        )
    if required_action != "APPLY_SIGNED_CONTROLS":
        return _fail_closed(
            state,
            f"core_required_action_{required_action.lower()}",
            kill_active=False,
            required_action=required_action,
            caught_up=caught_up,
            applied_event_ids=applied_event_ids,
        )
    authority = DumbMoneyAuthorityContext(
        signed_envelope=dict(state.capital_envelope or {}),
        trusted_public_key=core_public_key,
        expected_account_hash=expected_account_hash,
    )
    return DumbMoneyCommandDispatch(
        desired_mode="LIVE",
        kill_active=False,
        allow_new_risk=True,
        capital_authority=authority,
        fail_closed_reason="",
        required_action=required_action,
        caught_up=True,
        next_sequence=state.next_sequence,
        next_digest=state.next_digest,
        applied_event_ids=applied_event_ids,
    )


def poll_once(
    *,
    base_url: str,
    cell_bearer_provider: Callable[[], str],
    trusted_public_key: bytes,
    trusted_operator_public_keys: Mapping[str, bytes],
    expected_account_hash: str,
    state_path: Path,
    transport: CommandFeedTransport,
    now_utc: datetime,
    limit: int = DEFAULT_PAGE_LIMIT,
    timeout_seconds: float = 5.0,
) -> DumbMoneyCommandDispatch:
    """Fetch, verify, persist, and dispatch at most one bounded command page."""

    if now_utc.tzinfo is None:
        return _fail_closed(_CommandState(), "poll_clock_is_timezone_naive")
    try:
        origin = _validated_loopback_origin(base_url)
        core_public_key, operator_public_keys = _trusted_keyring(
            trusted_public_key,
            trusted_operator_public_keys,
        )
        account_hash = _sha256_text(
            expected_account_hash,
            "expected_account_hash",
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAXIMUM_PAGE_LIMIT
        ):
            raise DumbMoneyCommandFeedError(
                "command page limit must be between 1 and 1000"
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or not 0.1 <= float(timeout_seconds) <= 30.0
        ):
            raise DumbMoneyCommandFeedError(
                "command transport timeout must be between 0.1 and 30 seconds"
            )
        resolved_state_path = state_path.resolve()
    except (DumbMoneyAuthorityError, DumbMoneyCommandFeedError, OSError) as error:
        return _fail_closed(
            _CommandState(),
            f"feed_configuration_invalid:{type(error).__name__}",
        )
    try:
        with _exclusive_state_lock(resolved_state_path):
            state = _read_state(resolved_state_path)
            try:
                token = _cell_bearer(cell_bearer_provider)
                try:
                    raw_request_nonce = secrets.token_hex(32)
                except Exception as error:
                    raise DumbMoneyCommandFeedError(
                        "cryptographic request nonce generation failed"
                    ) from error
                request_nonce = _digest(
                    raw_request_nonce,
                    "command request_nonce",
                )
                query = urlencode(
                    {
                        "after": state.next_sequence,
                        "cursor": state.next_digest,
                        "limit": limit,
                        "request_nonce": request_nonce,
                    }
                )
                request = CommandFeedHttpRequest(
                    method="GET",
                    url=(f"{origin}/v1/cells/{DOPEY_VENUE}/commands?{query}"),
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    timeout_seconds=float(timeout_seconds),
                )
                try:
                    response = transport(request)
                except Exception as error:
                    return _fail_closed(
                        state,
                        f"command_transport_failure:{type(error).__name__}",
                    )
                if not isinstance(response, CommandFeedHttpResponse):
                    return _fail_closed(
                        state,
                        "command_transport_response_invalid",
                    )
                if isinstance(response.status, bool) or not isinstance(
                    response.status, int
                ):
                    return _fail_closed(state, "command_transport_status_invalid")
                if response.status in {401, 403}:
                    return _fail_closed(state, "cell_bearer_authentication_failed")
                if response.status == 409:
                    return _fail_closed(state, "command_cursor_rejected")
                if response.status != 200:
                    return _fail_closed(
                        state,
                        f"command_http_status_{response.status}",
                    )
                if not isinstance(response.body, bytes):
                    return _fail_closed(state, "command_response_body_not_bytes")
                if len(response.body) > MAXIMUM_RESPONSE_BYTES:
                    return _fail_closed(state, "command_response_too_large")
                if not _response_content_type(response.headers).startswith(
                    "application/json"
                ):
                    return _fail_closed(
                        state,
                        "command_response_content_type_invalid",
                    )
                page = _loads_strict_json(response.body, "command page")
                (
                    next_sequence,
                    next_digest,
                    has_more,
                    required_action,
                    commands,
                ) = _validated_page(
                    page,
                    state,
                    now_utc,
                    limit,
                    core_public_key,
                    request_nonce,
                )
                (
                    kill_envelope,
                    desired_envelope,
                    capital_envelope,
                    applied_event_ids,
                ) = _apply_commands(
                    state,
                    commands,
                    core_public_key,
                    operator_public_keys,
                    account_hash,
                    now_utc,
                )
                advanced = _CommandState(
                    next_sequence=next_sequence,
                    next_digest=next_digest,
                    kill_envelope=kill_envelope,
                    desired_mode_envelope=desired_envelope,
                    capital_envelope=capital_envelope,
                    updated_at=_format_utc(now_utc),
                )
                _write_state(resolved_state_path, advanced)
                return _dispatch_from_state(
                    advanced,
                    core_public_key,
                    operator_public_keys,
                    account_hash,
                    now_utc,
                    required_action=required_action,
                    caught_up=not has_more,
                    applied_event_ids=applied_event_ids,
                )
            except (
                DumbMoneyAuthorityError,
                DumbMoneyCommandFeedError,
                OSError,
            ) as error:
                return _fail_closed(
                    state,
                    f"command_page_rejected:{error}",
                    kill_active=True,
                )
    except (DumbMoneyCommandFeedError, OSError) as error:
        return _fail_closed(
            _CommandState(),
            f"command_state_unavailable:{error}",
        )
