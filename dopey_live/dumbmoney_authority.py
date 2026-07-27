"""DumbMoney capital authority for the sovereign Robinhood venue cell.

The fund control plane can grant *less* authority than DOPEY's local controls,
never more.  The signed envelope is verified at allocation time and again at
the broker sink so an expired or superseded lease cannot be used after a slow
research or quote step.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .models import AccountSnapshot, LiveExecutionIntent


SIGNED_ENVELOPE_SCHEMA: Final[str] = "dumbmoney.signed-envelope.v1"
CAPITAL_ENVELOPE_SCHEMA: Final[str] = "dumbmoney.capital-envelope.v1"
DESIRED_MODE_SCHEMA: Final[str] = "dumbmoney.desired-mode.v1"
KILL_STATE_SCHEMA: Final[str] = "dumbmoney.kill-state.v1"
DOPEY_VENUE: Final[str] = "dopey_robinhood"
SIGNATURE_ALGORITHM: Final[str] = "Ed25519"
MAXIMUM_CAPITAL_ENVELOPE_TTL: Final[timedelta] = timedelta(seconds=60)
SHA256_HEX_LENGTH: Final[int] = 64
IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"
)
UTC_TIMESTAMP_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)
EQUITY_INSTRUMENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^equity:[A-Z0-9][A-Z0-9.-]{0,31}$"
)
OPTION_INSTRUMENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^option:[A-Z0-9][A-Z0-9.-]{0,31}:"
    r"[A-Za-z0-9][A-Za-z0-9._/-]{0,95}$"
)
SIGNED_ENVELOPE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "source_id",
        "source_sequence",
        "event_id",
        "correlation_id",
        "causation_id",
        "nonce",
        "not_before",
        "expires_at",
        "body_schema",
        "body_digest",
        "body",
        "signature_algorithm",
        "signer_key_id",
        "signature",
    }
)
CAPITAL_ENVELOPE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "envelope_id",
        "mandate_id",
        "venue",
        "account_hash",
        "strategy_hashes",
        "passport_hashes",
        "promotion_hashes",
        "authorized_instruments",
        "authorized_mode",
        "max_order_risk_cents",
        "max_open_risk_cents",
        "max_correlated_risk_cents",
        "max_daily_loss_cents",
        "max_open_orders",
        "fencing_generation",
        "policy_epoch",
        "not_before",
        "expires_at",
    }
)
DESIRED_MODE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "venue",
        "mode",
        "revision",
        "reason",
        "policy_epoch",
        "not_before",
        "expires_at",
    }
)
KILL_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "active",
        "generation",
        "reason",
        "changed_by",
        "policy_epoch",
        "changed_at",
    }
)
DESIRED_MODES: Final[frozenset[str]] = frozenset(
    {"READ_ONLY", "PAPER", "LIVE", "PAUSED"}
)


class DumbMoneyAuthorityError(RuntimeError):
    """Raised when global capital authority is absent, invalid, or exhausted."""


@dataclass(frozen=True)
class CapitalEnvelopeV1:
    schema: str
    envelope_id: str
    mandate_id: str
    venue: str
    account_hash: str
    strategy_hashes: tuple[str, ...]
    passport_hashes: tuple[str, ...]
    promotion_hashes: tuple[str, ...]
    authorized_instruments: tuple[str, ...]
    authorized_mode: str
    max_order_risk_cents: int
    max_open_risk_cents: int
    max_correlated_risk_cents: int
    max_daily_loss_cents: int
    max_open_orders: int
    fencing_generation: int
    policy_epoch: int
    not_before: str
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["strategy_hashes"] = list(self.strategy_hashes)
        payload["passport_hashes"] = list(self.passport_hashes)
        payload["promotion_hashes"] = list(self.promotion_hashes)
        payload["authorized_instruments"] = list(self.authorized_instruments)
        return payload


@dataclass(frozen=True)
class DesiredModeV1:
    schema: str
    venue: str
    mode: str
    revision: int
    reason: str
    policy_epoch: int
    not_before: str
    expires_at: str


@dataclass(frozen=True)
class KillStateV1:
    schema: str
    active: bool
    generation: int
    reason: str
    changed_by: str
    policy_epoch: int
    changed_at: str


@dataclass(frozen=True)
class VerifiedCapitalAuthority:
    envelope: CapitalEnvelopeV1
    event_id: str
    source_id: str
    source_sequence: int
    signer_key_id: str
    body_digest: str

    def evidence(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope.envelope_id,
            "mandate_id": self.envelope.mandate_id,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "source_sequence": self.source_sequence,
            "signer_key_id": self.signer_key_id,
            "body_digest": self.body_digest,
            "fencing_generation": self.envelope.fencing_generation,
            "policy_epoch": self.envelope.policy_epoch,
            "expires_at": self.envelope.expires_at,
        }


@dataclass(frozen=True)
class VerifiedDesiredMode:
    desired_mode: DesiredModeV1
    event_id: str
    source_id: str
    source_sequence: int
    signer_key_id: str
    body_digest: str
    not_before: str
    expires_at: str


@dataclass(frozen=True)
class VerifiedKillState:
    kill_state: KillStateV1
    event_id: str
    source_id: str
    source_sequence: int
    signer_key_id: str
    body_digest: str
    not_before: str
    expires_at: str


VerifiedControlEnvelope = (
    VerifiedCapitalAuthority | VerifiedDesiredMode | VerifiedKillState
)


@dataclass(frozen=True)
class DumbMoneyAuthorityContext:
    """Explicit opt-in authority inputs; constructing this does not arm DOPEY."""

    signed_envelope: dict[str, Any]
    trusted_public_key: bytes
    expected_account_hash: str

    @classmethod
    def from_files(
        cls,
        envelope_path: Path,
        public_key_path: Path,
        expected_account_hash: str,
    ) -> "DumbMoneyAuthorityContext":
        try:
            envelope_bytes = envelope_path.read_bytes()
        except OSError as error:
            raise DumbMoneyAuthorityError(
                f"Unable to read DumbMoney envelope: path={envelope_path}, error={error}"
            ) from error
        payload = _loads_strict_signed_json(
            envelope_bytes,
            "DumbMoney signed envelope",
            require_canonical_bytes=True,
        )
        try:
            encoded_key = public_key_path.read_bytes()
        except OSError as error:
            raise DumbMoneyAuthorityError(
                f"Unable to read DumbMoney public key: path={public_key_path}, error={error}"
            ) from error
        return cls(
            signed_envelope=dict(payload),
            trusted_public_key=_decode_public_key(encoded_key),
            expected_account_hash=_sha256_text(
                expected_account_hash,
                "expected_account_hash",
            ),
        )

    def verify(
        self,
        now_utc: datetime,
        observed_account_hash: str,
    ) -> VerifiedCapitalAuthority:
        if observed_account_hash != self.expected_account_hash:
            raise DumbMoneyAuthorityError(
                "Robinhood Agentic account hash does not match the pinned DumbMoney account"
            )
        return verify_signed_capital_envelope(
            self.signed_envelope,
            self.trusted_public_key,
            now_utc,
            self.expected_account_hash,
        )


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DumbMoneyAuthorityError(
            f"DumbMoney payload is not canonical-JSON encodable: {error}"
        ) from error


def _loads_strict_signed_json(
    raw: bytes,
    label: str,
    *,
    require_canonical_bytes: bool,
) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DumbMoneyAuthorityError(
                    f"{label} contains a duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise DumbMoneyAuthorityError(
            f"{label} contains a non-finite JSON number: {value}"
        )

    try:
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DumbMoneyAuthorityError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise DumbMoneyAuthorityError(f"{label} must be a JSON object")
    _validate_signed_json_domain(payload, label)
    if require_canonical_bytes and raw != canonical_json_bytes(payload):
        raise DumbMoneyAuthorityError(f"{label} must use exact canonical JSON bytes")
    return payload


def _validate_signed_json_domain(value: Any, label: str, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DumbMoneyAuthorityError(
                f"{label} {path} contains a non-finite JSON number"
            )
        raise DumbMoneyAuthorityError(
            f"{label} {path} contains a float outside the signed integer domain"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_signed_json_domain(item, label, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise DumbMoneyAuthorityError(
                f"{label} {path} contains a non-string object key"
            )
        for key, item in value.items():
            _validate_signed_json_domain(item, label, f"{path}.{key}")
        return
    raise DumbMoneyAuthorityError(
        f"{label} {path} contains unsupported JSON type {type(value).__name__}"
    )


def _decode_public_key(encoded: bytes) -> bytes:
    if len(encoded) == 32:
        return encoded
    stripped = encoded.strip()
    try:
        text = stripped.decode("ascii")
    except UnicodeDecodeError as error:
        raise DumbMoneyAuthorityError(
            "DumbMoney Ed25519 public key must be raw bytes, hex, or base64url"
        ) from error
    if len(text) == 64:
        try:
            decoded = bytes.fromhex(text)
        except ValueError:
            decoded = b""
        if len(decoded) == 32:
            return decoded
    try:
        decoded = _urlsafe_b64decode(text)
    except ValueError as error:
        raise DumbMoneyAuthorityError(
            "DumbMoney Ed25519 public key is not valid base64url"
        ) from error
    if len(decoded) != 32:
        raise DumbMoneyAuthorityError(
            f"DumbMoney Ed25519 public key must be 32 bytes: actual={len(decoded)}"
        )
    return decoded


def _urlsafe_b64decode(value: str) -> bytes:
    if (
        not value
        or "=" in value
        or not re.fullmatch(r"[A-Za-z0-9_-]+", value)
        or len(value) % 4 == 1
    ):
        raise ValueError("base64url must be unpadded")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise ValueError("invalid base64url") from error
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if canonical != value:
        raise ValueError("base64url is not canonical")
    return decoded


def _sha256_text(value: Any, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != SHA256_HEX_LENGTH:
        raise DumbMoneyAuthorityError(f"{label} must be lowercase sha256 hex")
    try:
        bytes.fromhex(normalized)
    except ValueError as error:
        raise DumbMoneyAuthorityError(
            f"{label} must be lowercase sha256 hex"
        ) from error
    if normalized != str(value):
        raise DumbMoneyAuthorityError(f"{label} must be canonical lowercase sha256 hex")
    return normalized


def account_hash(account_id: str) -> str:
    if not account_id:
        raise DumbMoneyAuthorityError("Robinhood Agentic account ID is missing")
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


def _utc_timestamp(value: Any, label: str) -> datetime:
    text = str(value)
    if not UTC_TIMESTAMP_PATTERN.fullmatch(text):
        raise DumbMoneyAuthorityError(
            f"{label} must be canonical RFC3339 UTC ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise DumbMoneyAuthorityError(
            f"{label} is not a valid RFC3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise DumbMoneyAuthorityError(f"{label} must use UTC")
    canonical = parsed.isoformat(
        timespec="microseconds" if parsed.microsecond else "seconds"
    ).replace("+00:00", "Z")
    if canonical != text:
        raise DumbMoneyAuthorityError(
            f"{label} must use canonical RFC3339 UTC precision"
        )
    return parsed


def _exact_fields(
    payload: dict[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing or unknown:
        raise DumbMoneyAuthorityError(
            f"{label} schema mismatch: missing={missing}, unknown={unknown}"
        )


def _positive_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DumbMoneyAuthorityError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DumbMoneyAuthorityError(f"{field} must be a nonnegative integer")
    return value


def _hash_array(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    values = payload.get(field)
    if not isinstance(values, list):
        raise DumbMoneyAuthorityError(f"{field} must be an array")
    normalized = tuple(_sha256_text(value, field) for value in values)
    if not normalized:
        raise DumbMoneyAuthorityError(f"{field} must be nonempty")
    if normalized != tuple(sorted(set(normalized))):
        raise DumbMoneyAuthorityError(f"{field} must be sorted and duplicate-free")
    return normalized


def _identifier_array(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    values = payload.get(field)
    if not isinstance(values, list):
        raise DumbMoneyAuthorityError(f"{field} must be an array")
    normalized = tuple(str(value) for value in values)
    if (
        not normalized
        or any(not IDENTIFIER_PATTERN.fullmatch(value) for value in normalized)
        or normalized != tuple(sorted(set(normalized)))
    ):
        raise DumbMoneyAuthorityError(
            f"{field} must be nonempty, canonical, sorted, and duplicate-free"
        )
    return normalized


def _capital_envelope(
    payload: dict[str, Any],
    expected_account_hash: str,
) -> CapitalEnvelopeV1:
    _exact_fields(payload, CAPITAL_ENVELOPE_FIELDS, "CapitalEnvelopeV1")
    if payload.get("schema") != CAPITAL_ENVELOPE_SCHEMA:
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 schema is unsupported")
    if payload.get("venue") != DOPEY_VENUE:
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 is not for dopey_robinhood")
    if payload.get("authorized_mode") != "LIVE":
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 does not authorize LIVE mode")
    envelope_id = _sha256_text(payload.get("envelope_id"), "envelope_id")
    mandate_id = _sha256_text(payload.get("mandate_id"), "mandate_id")
    account_digest = _sha256_text(payload.get("account_hash"), "account_hash")
    if account_digest != expected_account_hash:
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 targets a different account")
    max_order = _positive_int(payload, "max_order_risk_cents")
    max_open = _positive_int(payload, "max_open_risk_cents")
    max_correlated = _positive_int(payload, "max_correlated_risk_cents")
    max_daily_loss = _positive_int(payload, "max_daily_loss_cents")
    if not max_order <= max_correlated <= max_open:
        raise DumbMoneyAuthorityError(
            "CapitalEnvelopeV1 requires max_order_risk_cents <= "
            "max_correlated_risk_cents <= max_open_risk_cents"
        )
    not_before = str(payload.get("not_before", ""))
    expires_at = str(payload.get("expires_at", ""))
    if _utc_timestamp(expires_at, "body.expires_at") <= _utc_timestamp(
        not_before, "body.not_before"
    ):
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 validity interval is empty")
    authorized_instruments = _identifier_array(
        payload,
        "authorized_instruments",
    )
    unsupported_instruments = sorted(
        instrument_id
        for instrument_id in authorized_instruments
        if not (
            EQUITY_INSTRUMENT_ID_PATTERN.fullmatch(instrument_id)
            or OPTION_INSTRUMENT_ID_PATTERN.fullmatch(instrument_id)
        )
    )
    if unsupported_instruments:
        raise DumbMoneyAuthorityError(
            "CapitalEnvelopeV1 contains noncanonical exact Dopey instrument IDs: "
            f"{unsupported_instruments}"
        )
    strategy_hashes = _hash_array(payload, "strategy_hashes")
    passport_hashes = _hash_array(payload, "passport_hashes")
    promotion_hashes = _hash_array(payload, "promotion_hashes")
    if (
        len(strategy_hashes) != 1
        or len(passport_hashes) != 1
        or len(promotion_hashes) != 1
    ):
        raise DumbMoneyAuthorityError(
            "CapitalEnvelopeV1 must authorize exactly one bound "
            "strategy/passport/promotion tuple"
        )
    return CapitalEnvelopeV1(
        schema=CAPITAL_ENVELOPE_SCHEMA,
        envelope_id=envelope_id,
        mandate_id=mandate_id,
        venue=DOPEY_VENUE,
        account_hash=account_digest,
        strategy_hashes=strategy_hashes,
        passport_hashes=passport_hashes,
        promotion_hashes=promotion_hashes,
        authorized_instruments=authorized_instruments,
        authorized_mode="LIVE",
        max_order_risk_cents=max_order,
        max_open_risk_cents=max_open,
        max_correlated_risk_cents=max_correlated,
        max_daily_loss_cents=max_daily_loss,
        max_open_orders=_positive_int(payload, "max_open_orders"),
        fencing_generation=_positive_int(payload, "fencing_generation"),
        policy_epoch=_positive_int(payload, "policy_epoch"),
        not_before=not_before,
        expires_at=expires_at,
    )


@dataclass(frozen=True)
class _VerifiedSignedWrapper:
    body_schema: str
    body: dict[str, Any]
    event_id: str
    source_id: str
    source_sequence: int
    signer_key_id: str
    body_digest: str
    not_before: str
    expires_at: str
    not_before_utc: datetime
    expires_at_utc: datetime


def _verify_signed_wrapper(
    payload: dict[str, Any],
    trusted_public_key: bytes,
    now_utc: datetime,
    *,
    enforce_current_window: bool,
) -> _VerifiedSignedWrapper:
    if now_utc.tzinfo is None:
        raise DumbMoneyAuthorityError("Envelope verification requires aware now_utc")
    now = now_utc.astimezone(timezone.utc)
    _exact_fields(payload, SIGNED_ENVELOPE_FIELDS, "SignedEnvelopeV1")
    if payload.get("schema") != SIGNED_ENVELOPE_SCHEMA:
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 schema is unsupported")
    if payload.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise DumbMoneyAuthorityError(
            "SignedEnvelopeV1 signature algorithm is unsupported"
        )
    source_sequence = _positive_int(payload, "source_sequence")
    for field in ("source_id", "correlation_id", "nonce"):
        if not IDENTIFIER_PATTERN.fullmatch(str(payload.get(field, ""))):
            raise DumbMoneyAuthorityError(f"{field} is not a canonical identifier")
    causation_id = payload.get("causation_id")
    if causation_id is not None:
        _sha256_text(causation_id, "causation_id")
    body = payload.get("body")
    if not isinstance(body, dict) or not all(isinstance(key, str) for key in body):
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 body must be an object")
    body_schema = str(payload.get("body_schema", ""))
    if not IDENTIFIER_PATTERN.fullmatch(body_schema):
        raise DumbMoneyAuthorityError(
            "SignedEnvelopeV1 body_schema is not a canonical identifier"
        )
    if body.get("schema") != body_schema:
        raise DumbMoneyAuthorityError(
            "SignedEnvelopeV1 body_schema does not match embedded body"
        )
    body_digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    if payload.get("body_digest") != body_digest:
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 body digest mismatch")
    unsigned_event = dict(payload)
    unsigned_event.pop("signature", None)
    unsigned_event.pop("event_id", None)
    event_id = hashlib.sha256(canonical_json_bytes(unsigned_event)).hexdigest()
    if payload.get("event_id") != event_id:
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 event_id mismatch")
    public_key = _decode_public_key(trusted_public_key)
    signer_key_id = hashlib.sha256(public_key).hexdigest()
    if payload.get("signer_key_id") != signer_key_id:
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 signer_key_id mismatch")
    try:
        signature = _urlsafe_b64decode(str(payload.get("signature", "")))
        if len(signature) != 64:
            raise ValueError("Ed25519 signature must be 64 bytes")
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            canonical_json_bytes(
                {key: value for key, value in payload.items() if key != "signature"}
            ),
        )
    except (InvalidSignature, ValueError) as error:
        raise DumbMoneyAuthorityError(
            "SignedEnvelopeV1 signature is invalid"
        ) from error
    not_before = str(payload.get("not_before", ""))
    expires_at = str(payload.get("expires_at", ""))
    wrapper_not_before = _utc_timestamp(not_before, "not_before")
    wrapper_expires = _utc_timestamp(expires_at, "expires_at")
    if wrapper_expires <= wrapper_not_before:
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 validity interval is empty")
    if enforce_current_window and not wrapper_not_before <= now < wrapper_expires:
        raise DumbMoneyAuthorityError("SignedEnvelopeV1 is not currently valid")
    return _VerifiedSignedWrapper(
        body_schema=body_schema,
        body=dict(body),
        event_id=event_id,
        source_id=str(payload["source_id"]),
        source_sequence=source_sequence,
        signer_key_id=signer_key_id,
        body_digest=body_digest,
        not_before=not_before,
        expires_at=expires_at,
        not_before_utc=wrapper_not_before,
        expires_at_utc=wrapper_expires,
    )


def _verified_capital_from_wrapper(
    wrapper: _VerifiedSignedWrapper,
    now_utc: datetime,
    expected_account_hash: str,
    *,
    enforce_current_window: bool,
) -> VerifiedCapitalAuthority:
    if wrapper.body_schema != CAPITAL_ENVELOPE_SCHEMA:
        raise DumbMoneyAuthorityError(
            "SignedEnvelopeV1 body_schema is not capital authority"
        )
    now = now_utc.astimezone(timezone.utc)
    envelope = _capital_envelope(wrapper.body, expected_account_hash)
    body_not_before = _utc_timestamp(envelope.not_before, "body.not_before")
    body_expires = _utc_timestamp(envelope.expires_at, "body.expires_at")
    if enforce_current_window and not body_not_before <= now < body_expires:
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 is not currently valid")
    if (
        wrapper.not_before_utc != body_not_before
        or wrapper.expires_at_utc != body_expires
    ):
        raise DumbMoneyAuthorityError(
            "SignedEnvelopeV1 and CapitalEnvelopeV1 validity windows must match exactly"
        )
    if wrapper.expires_at_utc - wrapper.not_before_utc > MAXIMUM_CAPITAL_ENVELOPE_TTL:
        raise DumbMoneyAuthorityError(
            "Capital authority validity exceeds the local 60-second maximum"
        )
    return VerifiedCapitalAuthority(
        envelope=envelope,
        event_id=wrapper.event_id,
        source_id=wrapper.source_id,
        source_sequence=wrapper.source_sequence,
        signer_key_id=wrapper.signer_key_id,
        body_digest=wrapper.body_digest,
    )


def verify_signed_capital_envelope(
    payload: dict[str, Any],
    trusted_public_key: bytes,
    now_utc: datetime,
    expected_account_hash: str,
) -> VerifiedCapitalAuthority:
    wrapper = _verify_signed_wrapper(
        payload,
        trusted_public_key,
        now_utc,
        enforce_current_window=True,
    )
    return _verified_capital_from_wrapper(
        wrapper,
        now_utc,
        expected_account_hash,
        enforce_current_window=True,
    )


def _desired_mode(
    payload: dict[str, Any],
    now_utc: datetime,
    *,
    enforce_current_window: bool,
) -> DesiredModeV1:
    _exact_fields(payload, DESIRED_MODE_FIELDS, "DesiredModeV1")
    if payload.get("schema") != DESIRED_MODE_SCHEMA:
        raise DumbMoneyAuthorityError("DesiredModeV1 schema is unsupported")
    if payload.get("venue") != DOPEY_VENUE:
        raise DumbMoneyAuthorityError("DesiredModeV1 is not for dopey_robinhood")
    mode = str(payload.get("mode", ""))
    if mode not in DESIRED_MODES:
        raise DumbMoneyAuthorityError("DesiredModeV1 mode is unsupported")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise DumbMoneyAuthorityError("DesiredModeV1 reason must be nonempty")
    not_before = str(payload.get("not_before", ""))
    expires_at = str(payload.get("expires_at", ""))
    body_not_before = _utc_timestamp(not_before, "body.not_before")
    body_expires = _utc_timestamp(expires_at, "body.expires_at")
    if body_expires <= body_not_before:
        raise DumbMoneyAuthorityError("DesiredModeV1 validity interval is empty")
    now = now_utc.astimezone(timezone.utc)
    if enforce_current_window and not body_not_before <= now < body_expires:
        raise DumbMoneyAuthorityError("DesiredModeV1 is not currently valid")
    return DesiredModeV1(
        schema=DESIRED_MODE_SCHEMA,
        venue=DOPEY_VENUE,
        mode=mode,
        revision=_positive_int(payload, "revision"),
        reason=reason,
        policy_epoch=_positive_int(payload, "policy_epoch"),
        not_before=not_before,
        expires_at=expires_at,
    )


def _kill_state(
    payload: dict[str, Any],
    now_utc: datetime,
    *,
    enforce_current_window: bool,
) -> KillStateV1:
    _exact_fields(payload, KILL_STATE_FIELDS, "KillStateV1")
    if payload.get("schema") != KILL_STATE_SCHEMA:
        raise DumbMoneyAuthorityError("KillStateV1 schema is unsupported")
    active = payload.get("active")
    if not isinstance(active, bool):
        raise DumbMoneyAuthorityError("KillStateV1 active must be a boolean")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise DumbMoneyAuthorityError("KillStateV1 reason must be nonempty")
    changed_by = str(payload.get("changed_by", ""))
    if not IDENTIFIER_PATTERN.fullmatch(changed_by):
        raise DumbMoneyAuthorityError(
            "KillStateV1 changed_by is not a canonical identifier"
        )
    changed_at = str(payload.get("changed_at", ""))
    changed_at_utc = _utc_timestamp(changed_at, "body.changed_at")
    if enforce_current_window and changed_at_utc > now_utc.astimezone(timezone.utc):
        raise DumbMoneyAuthorityError("KillStateV1 changed_at is future-dated")
    return KillStateV1(
        schema=KILL_STATE_SCHEMA,
        active=active,
        generation=_positive_int(payload, "generation"),
        reason=reason,
        changed_by=changed_by,
        policy_epoch=_positive_int(payload, "policy_epoch"),
        changed_at=changed_at,
    )


def verify_signed_control_envelope(
    payload: dict[str, Any],
    trusted_public_key: bytes,
    now_utc: datetime,
    expected_account_hash: str,
    *,
    enforce_current_window: bool = True,
) -> VerifiedControlEnvelope:
    """Verify one Core command.

    ``enforce_current_window=False`` exists only so the command-feed recovery
    path can authenticate previously persisted generations. It must never be
    used to grant positive capital authority.
    """

    wrapper = _verify_signed_wrapper(
        payload,
        trusted_public_key,
        now_utc,
        enforce_current_window=enforce_current_window,
    )
    if wrapper.body_schema == CAPITAL_ENVELOPE_SCHEMA:
        return _verified_capital_from_wrapper(
            wrapper,
            now_utc,
            expected_account_hash,
            enforce_current_window=enforce_current_window,
        )
    if wrapper.body_schema == DESIRED_MODE_SCHEMA:
        desired = _desired_mode(
            wrapper.body,
            now_utc,
            enforce_current_window=enforce_current_window,
        )
        return VerifiedDesiredMode(
            desired_mode=desired,
            event_id=wrapper.event_id,
            source_id=wrapper.source_id,
            source_sequence=wrapper.source_sequence,
            signer_key_id=wrapper.signer_key_id,
            body_digest=wrapper.body_digest,
            not_before=wrapper.not_before,
            expires_at=wrapper.expires_at,
        )
    if wrapper.body_schema == KILL_STATE_SCHEMA:
        kill = _kill_state(
            wrapper.body,
            now_utc,
            enforce_current_window=enforce_current_window,
        )
        return VerifiedKillState(
            kill_state=kill,
            event_id=wrapper.event_id,
            source_id=wrapper.source_id,
            source_sequence=wrapper.source_sequence,
            signer_key_id=wrapper.signer_key_id,
            body_digest=wrapper.body_digest,
            not_before=wrapper.not_before,
            expires_at=wrapper.expires_at,
        )
    raise DumbMoneyAuthorityError(
        f"SignedEnvelopeV1 body_schema is unsupported: {wrapper.body_schema}"
    )


def account_open_risk_cents(account: AccountSnapshot) -> int:
    total_usd = 0.0
    for multiplier, positions in (
        (1.0, account.equity_positions),
        (100.0, account.option_positions),
    ):
        for position in positions:
            required = {"quantity", "average_cost", "market_value"}
            if not required <= set(position):
                raise DumbMoneyAuthorityError(
                    "Nonzero broker position lacks complete finite risk evidence"
                )
            try:
                market_value = abs(float(position.get("market_value", 0.0)))
                quantity = abs(float(position.get("quantity", 0.0)))
                average_cost = abs(float(position.get("average_cost", 0.0)))
            except (TypeError, ValueError) as error:
                raise DumbMoneyAuthorityError(
                    "Broker position risk fields are not numeric"
                ) from error
            cost_basis = quantity * average_cost * multiplier
            if not math.isfinite(market_value) or not math.isfinite(cost_basis):
                raise DumbMoneyAuthorityError("Broker position cost basis is invalid")
            position_risk = max(market_value, cost_basis)
            if quantity > 0.0 and position_risk <= 0.0:
                raise DumbMoneyAuthorityError(
                    "Nonzero broker position lacks positive risk evidence"
                )
            total_usd += position_risk
    if not math.isfinite(total_usd):
        raise DumbMoneyAuthorityError("Broker open risk is not finite")
    return math.ceil(total_usd * 100.0 - 1e-9)


def active_order_count(account: AccountSnapshot) -> int:
    active = {"queued", "pending", "open", "confirmed", "partially_filled"}
    return sum(
        str(order.get("status", "")).strip().lower() in active
        for order in (*account.recent_equity_orders, *account.recent_option_orders)
    )


def active_entry_order_present(account: AccountSnapshot) -> bool:
    active = {"queued", "pending", "open", "confirmed", "partially_filled"}
    return any(
        str(order.get("status", "")).strip().lower() in active
        and str(order.get("side", "")).strip().lower() == "buy"
        for order in (*account.recent_equity_orders, *account.recent_option_orders)
    )


def _validated_daily_loss(
    authority: VerifiedCapitalAuthority,
    observed_daily_loss_cents: int | None,
) -> int:
    if (
        isinstance(observed_daily_loss_cents, bool)
        or not isinstance(observed_daily_loss_cents, int)
        or observed_daily_loss_cents < 0
    ):
        raise DumbMoneyAuthorityError(
            "Broker/ledger-witnessed daily loss is required for new exposure"
        )
    if observed_daily_loss_cents >= authority.envelope.max_daily_loss_cents:
        raise DumbMoneyAuthorityError(
            "CapitalEnvelopeV1 max_daily_loss_cents is exhausted"
        )
    return observed_daily_loss_cents


def authorized_settled_cash_usd(
    authority: VerifiedCapitalAuthority,
    account: AccountSnapshot,
    spendable_settled_usd: float,
    observed_daily_loss_cents: int | None,
) -> float:
    if not math.isfinite(spendable_settled_usd) or spendable_settled_usd < 0.0:
        raise DumbMoneyAuthorityError("Settled cash must be finite and nonnegative")
    _validated_daily_loss(authority, observed_daily_loss_cents)
    open_risk = account_open_risk_cents(account)
    ceiling = min(
        authority.envelope.max_open_risk_cents,
        authority.envelope.max_correlated_risk_cents,
    )
    remaining_cents = max(0, ceiling - open_risk)
    return min(spendable_settled_usd, remaining_cents / 100.0)


def intent_incremental_risk_cents(intent: LiveExecutionIntent) -> int:
    if intent.side == "sell":
        return 0
    if intent.instrument == "option":
        contract = intent.option_contract
        multiplier = contract.get("multiplier", 100)
        try:
            maximum_loss = float(contract.get("maximum_loss_usd", 0.0))
            computed_debit = (
                float(intent.limit_price) * float(intent.quantity) * float(multiplier)
            )
        except (TypeError, ValueError) as error:
            raise DumbMoneyAuthorityError(
                "Option debit fields are not numeric"
            ) from error
        risk_usd = max(maximum_loss, computed_debit, intent.notional_usd)
    else:
        risk_usd = max(intent.notional_usd, intent.quantity * intent.limit_price)
    if not math.isfinite(risk_usd) or risk_usd <= 0.0:
        raise DumbMoneyAuthorityError("Entry intent risk must be finite and positive")
    return math.ceil(risk_usd * 100.0 - 1e-9)


def intent_authorized_instrument_id(intent: LiveExecutionIntent) -> str:
    """Return the exact broker-sink identity used by CapitalEnvelopeV1."""

    symbol = intent.symbol.strip().upper()
    if intent.instrument == "equity":
        instrument_id = f"equity:{symbol}"
        if not EQUITY_INSTRUMENT_ID_PATTERN.fullmatch(instrument_id):
            raise DumbMoneyAuthorityError(
                "Equity intent cannot form a canonical authorized instrument ID"
            )
        return instrument_id
    if intent.instrument == "option":
        contract_id = str(intent.option_contract.get("contract_id", "")).strip()
        instrument_id = f"option:{symbol}:{contract_id}"
        if not OPTION_INSTRUMENT_ID_PATTERN.fullmatch(instrument_id):
            raise DumbMoneyAuthorityError(
                "Option intent cannot form a canonical authorized instrument ID"
            )
        return instrument_id
    raise DumbMoneyAuthorityError(
        f"Unsupported Dopey execution instrument: {intent.instrument}"
    )


def authorize_intent(
    authority: VerifiedCapitalAuthority,
    account: AccountSnapshot,
    intent: LiveExecutionIntent,
    observed_daily_loss_cents: int | None,
) -> int:
    if intent.side == "sell":
        return _authorize_reducing_exit(account, intent)
    witnessed_daily_loss = _validated_daily_loss(
        authority,
        observed_daily_loss_cents,
    )
    if active_entry_order_present(account):
        raise DumbMoneyAuthorityError(
            "Existing active entry order blocks additional new exposure"
        )
    instrument_id = intent_authorized_instrument_id(intent)
    if instrument_id not in authority.envelope.authorized_instruments:
        raise DumbMoneyAuthorityError(
            "Execution intent exact broker instrument is absent from "
            "CapitalEnvelopeV1 authorized_instruments"
        )
    source_hash = _sha256_text(intent.source_hash, "intent.source_hash")
    if source_hash != authority.envelope.strategy_hashes[0]:
        raise DumbMoneyAuthorityError(
            "Execution intent strategy hash does not match the exact "
            "CapitalEnvelopeV1 strategy"
        )
    passport_hash = _sha256_text(
        intent.passport_hash,
        "intent.passport_hash",
    )
    if passport_hash != authority.envelope.passport_hashes[0]:
        raise DumbMoneyAuthorityError(
            "Execution intent passport hash does not match the exact "
            "CapitalEnvelopeV1 passport"
        )
    promotion_hash = _sha256_text(
        intent.promotion_hash,
        "intent.promotion_hash",
    )
    if promotion_hash != authority.envelope.promotion_hashes[0]:
        raise DumbMoneyAuthorityError(
            "Execution intent promotion hash does not match the exact "
            "CapitalEnvelopeV1 promotion"
        )
    incremental = intent_incremental_risk_cents(intent)
    if incremental > authority.envelope.max_order_risk_cents:
        raise DumbMoneyAuthorityError("Execution intent exceeds max_order_risk_cents")
    remaining_daily_loss_capacity = (
        authority.envelope.max_daily_loss_cents - witnessed_daily_loss
    )
    if incremental > remaining_daily_loss_capacity:
        raise DumbMoneyAuthorityError(
            "Execution intent worst-case risk exceeds remaining daily-loss capacity"
        )
    if active_order_count(account) >= authority.envelope.max_open_orders:
        raise DumbMoneyAuthorityError("CapitalEnvelopeV1 max_open_orders is exhausted")
    projected = account_open_risk_cents(account) + incremental
    if projected > authority.envelope.max_open_risk_cents:
        raise DumbMoneyAuthorityError("Execution intent exceeds max_open_risk_cents")
    if projected > authority.envelope.max_correlated_risk_cents:
        raise DumbMoneyAuthorityError(
            "Execution intent exceeds max_correlated_risk_cents"
        )
    return incremental


def _authorize_reducing_exit(
    account: AccountSnapshot,
    intent: LiveExecutionIntent,
) -> int:
    try:
        requested_quantity = float(intent.quantity)
    except (TypeError, ValueError) as error:
        raise DumbMoneyAuthorityError("Exit intent quantity is not numeric") from error
    if not math.isfinite(requested_quantity) or requested_quantity <= 0.0:
        raise DumbMoneyAuthorityError(
            "Exit intent quantity must be finite and positive"
        )
    if intent.instrument == "equity":
        positions = tuple(
            position
            for position in account.equity_positions
            if str(position.get("symbol", "")).strip().upper()
            == intent.symbol.strip().upper()
        )
        matching_active_sells = tuple(
            order
            for order in account.recent_equity_orders
            if str(order.get("symbol", "")).strip().upper()
            == intent.symbol.strip().upper()
            and str(order.get("side", "")).strip().lower() == "sell"
            and str(order.get("status", "")).strip().lower()
            in {"queued", "pending", "open", "confirmed", "partially_filled"}
        )
    elif intent.instrument == "option":
        contract_id = str(intent.option_contract.get("contract_id", "")).strip()
        if not contract_id:
            raise DumbMoneyAuthorityError(
                "Option exit intent lacks an exact contract_id"
            )
        positions = tuple(
            position
            for position in account.option_positions
            if str(position.get("contract_id", "")).strip() == contract_id
        )
        matching_active_sells = tuple(
            order
            for order in account.recent_option_orders
            if str(order.get("contract_id", "")).strip() == contract_id
            and str(order.get("side", "")).strip().lower() == "sell"
            and str(order.get("status", "")).strip().lower()
            in {"queued", "pending", "open", "confirmed", "partially_filled"}
        )
    else:
        raise DumbMoneyAuthorityError(
            f"Unsupported exit instrument: {intent.instrument}"
        )
    if len(positions) != 1:
        raise DumbMoneyAuthorityError(
            "Exit intent requires exactly one fresh matching long broker position"
        )
    if matching_active_sells:
        raise DumbMoneyAuthorityError(
            "Existing active sell order blocks another exit for the same holding"
        )
    try:
        held_quantity = float(positions[0]["quantity"])
    except (KeyError, TypeError, ValueError) as error:
        raise DumbMoneyAuthorityError(
            "Matching broker position lacks numeric quantity evidence"
        ) from error
    if not math.isfinite(held_quantity) or held_quantity <= 0.0:
        raise DumbMoneyAuthorityError(
            "Matching broker position quantity must be finite and positive"
        )
    if requested_quantity > held_quantity + 1e-9:
        raise DumbMoneyAuthorityError(
            "Exit intent would oversell the fresh witnessed long position"
        )
    return 0
