"""Pinned independent signatures for prospective forward-evidence receipts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .identity import JsonValue, require_sha256, require_utc_iso


TrustStatus = Literal["configured", "not_configured"]
ForwardPurpose = Literal["forward_record", "outcome_source"]
TRUST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "status",
        "algorithm",
        "forward_recorder",
        "outcome_source",
    }
)
ROLE_FIELDS = frozenset(
    {
        "signer_id",
        "signer_version",
        "key_id",
        "public_key_base64",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "purpose",
        "candidate_id",
        "frozen_specification_hash",
        "record_id",
        "subject_artifact_hash",
        "issued_at",
        "signer_id",
        "signer_version",
    }
)


@dataclass(frozen=True, slots=True)
class ForwardTrustRole:
    signer_id: str | None
    signer_version: str | None
    key_id: str | None
    public_key_bytes: bytes | None


@dataclass(frozen=True, slots=True)
class ForwardEvidenceTrust:
    status: TrustStatus
    algorithm: Literal["ed25519"]
    forward_recorder: ForwardTrustRole
    outcome_source: ForwardTrustRole


@dataclass(frozen=True, slots=True)
class ForwardSignatureVerification:
    purpose: ForwardPurpose
    signer_id: str
    signer_version: str
    signature_algorithm: Literal["ed25519"]
    key_id: str
    public_key_hash: str
    receipt_body_hash: str
    subject_artifact_hash: str
    signature_hash: str


def _reject_duplicate_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    decoded: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"forward evidence trust contains a duplicate field: field={key}")
        decoded[key] = value
    return decoded


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"forward evidence trust requires a non-empty string: field={field_name}"
        )
    return value


def _decode_canonical_base64(value: object, field_name: str, expected_length: int) -> bytes:
    encoded = _require_non_empty_string(value, field_name)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            f"forward evidence field is not valid base64: field={field_name}"
        ) from error
    if len(decoded) != expected_length:
        raise ValueError(
            "forward evidence decoded field has an invalid length: "
            f"field={field_name}, expected={expected_length}, observed={len(decoded)}"
        )
    if base64.b64encode(decoded).decode("ascii") != encoded:
        raise ValueError(f"forward evidence base64 is not canonical: field={field_name}")
    return decoded


def _empty_role(value: object, field_name: str) -> ForwardTrustRole:
    if not isinstance(value, dict) or set(value) != ROLE_FIELDS:
        raise ValueError(
            f"forward evidence trust role differs from the exact v1 schema: role={field_name}"
        )
    role = cast(dict[str, JsonValue], value)
    if any(role[key] is not None for key in ROLE_FIELDS):
        raise ValueError(
            f"unconfigured forward evidence trust requires null role fields: role={field_name}"
        )
    return ForwardTrustRole(None, None, None, None)


def _configured_role(value: object, field_name: str) -> ForwardTrustRole:
    if not isinstance(value, dict) or set(value) != ROLE_FIELDS:
        raise ValueError(
            f"forward evidence trust role differs from the exact v1 schema: role={field_name}"
        )
    role = cast(dict[str, JsonValue], value)
    signer_id = _require_non_empty_string(role["signer_id"], f"{field_name}.signer_id")
    signer_version = _require_non_empty_string(
        role["signer_version"],
        f"{field_name}.signer_version",
    )
    public_key_bytes = _decode_canonical_base64(
        role["public_key_base64"],
        f"{field_name}.public_key_base64",
        32,
    )
    public_key_hash = hashlib.sha256(public_key_bytes).hexdigest()
    key_id = _require_non_empty_string(role["key_id"], f"{field_name}.key_id")
    expected_key_id = f"ed25519-sha256-{public_key_hash}"
    if key_id != expected_key_id:
        raise ValueError(
            "forward evidence key identity is not bound to its pinned public key: "
            f"role={field_name}, expected={expected_key_id}, observed={key_id}"
        )
    return ForwardTrustRole(signer_id, signer_version, key_id, public_key_bytes)


def load_forward_evidence_trust(trust_path: Path) -> ForwardEvidenceTrust:
    resolved_path = trust_path.resolve(strict=True)
    decoded = json.loads(
        resolved_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object,
    )
    if not isinstance(decoded, dict) or set(decoded) != TRUST_FIELDS:
        observed = set(decoded) if isinstance(decoded, dict) else set()
        raise ValueError(
            "forward evidence trust fields differ from the exact v1 schema: "
            f"missing={sorted(TRUST_FIELDS.difference(observed))}, "
            f"unexpected={sorted(observed.difference(TRUST_FIELDS))}"
        )
    trust = cast(dict[str, JsonValue], decoded)
    if trust["schema_version"] != "dopey-forward-evidence-trust-v1":
        raise ValueError("forward evidence trust schema version is unsupported")
    if trust["environment_id"] != "dopey-options-paper-v1":
        raise ValueError("forward evidence trust environment identity mismatch")
    if trust["algorithm"] != "ed25519":
        raise ValueError("forward evidence trust algorithm must be ed25519")
    status = trust["status"]
    if status == "not_configured":
        return ForwardEvidenceTrust(
            "not_configured",
            "ed25519",
            _empty_role(trust["forward_recorder"], "forward_recorder"),
            _empty_role(trust["outcome_source"], "outcome_source"),
        )
    if status != "configured":
        raise ValueError(f"forward evidence trust status is unsupported: status={status}")
    recorder = _configured_role(trust["forward_recorder"], "forward_recorder")
    outcome_source = _configured_role(trust["outcome_source"], "outcome_source")
    if recorder.signer_id == outcome_source.signer_id:
        raise ValueError("forward recorder and outcome source signer identities must be independent")
    if recorder.public_key_bytes == outcome_source.public_key_bytes:
        raise ValueError("forward recorder and outcome source public keys must be independent")
    return ForwardEvidenceTrust("configured", "ed25519", recorder, outcome_source)


def _validate_receipt_body(receipt_body: dict[str, JsonValue]) -> ForwardPurpose:
    if set(receipt_body) != RECEIPT_FIELDS:
        raise ValueError("forward signed receipt differs from the exact v1 schema")
    if receipt_body["schema_version"] != "dopey-forward-evidence-receipt-v1":
        raise ValueError("forward signed receipt schema version is unsupported")
    if receipt_body["environment_id"] != "dopey-options-paper-v1":
        raise ValueError("forward signed receipt environment identity mismatch")
    purpose = receipt_body["purpose"]
    if purpose not in {"forward_record", "outcome_source"}:
        raise ValueError(f"forward signed receipt purpose is unsupported: purpose={purpose}")
    _require_non_empty_string(receipt_body["candidate_id"], "candidate_id")
    frozen_hash = _require_non_empty_string(
        receipt_body["frozen_specification_hash"],
        "frozen_specification_hash",
    )
    require_sha256(frozen_hash, "frozen_specification_hash")
    _require_non_empty_string(receipt_body["record_id"], "record_id")
    subject_hash = _require_non_empty_string(
        receipt_body["subject_artifact_hash"],
        "subject_artifact_hash",
    )
    require_sha256(subject_hash, "subject_artifact_hash")
    issued_at = _require_non_empty_string(receipt_body["issued_at"], "issued_at")
    require_utc_iso(issued_at)
    _require_non_empty_string(receipt_body["signer_id"], "signer_id")
    _require_non_empty_string(receipt_body["signer_version"], "signer_version")
    return cast(ForwardPurpose, purpose)


def canonical_forward_receipt_bytes(receipt_body: dict[str, JsonValue]) -> bytes:
    _validate_receipt_body(receipt_body)
    encoded = json.dumps(
        receipt_body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encoded.encode("utf-8")


def verify_forward_evidence_signature(
    trust_path: Path,
    receipt_body: dict[str, JsonValue],
    signature_base64: str,
) -> ForwardSignatureVerification:
    trust = load_forward_evidence_trust(trust_path)
    if trust.status != "configured":
        raise PermissionError("forward evidence trust is not configured")
    purpose = _validate_receipt_body(receipt_body)
    role = trust.forward_recorder if purpose == "forward_record" else trust.outcome_source
    if (
        receipt_body.get("signer_id") != role.signer_id
        or receipt_body.get("signer_version") != role.signer_version
    ):
        raise ValueError("forward receipt signer identity differs from its pinned trust role")
    message = canonical_forward_receipt_bytes(receipt_body)
    signature = _decode_canonical_base64(signature_base64, "signature_base64", 64)
    if role.public_key_bytes is None or role.key_id is None:
        raise ValueError("configured forward evidence trust lacks role key material")
    public_key = Ed25519PublicKey.from_public_bytes(role.public_key_bytes)
    try:
        public_key.verify(signature, message)
    except InvalidSignature as error:
        raise ValueError("forward evidence Ed25519 signature verification failed") from error
    return ForwardSignatureVerification(
        purpose=purpose,
        signer_id=cast(str, role.signer_id),
        signer_version=cast(str, role.signer_version),
        signature_algorithm="ed25519",
        key_id=role.key_id,
        public_key_hash=hashlib.sha256(role.public_key_bytes).hexdigest(),
        receipt_body_hash=hashlib.sha256(message).hexdigest(),
        subject_artifact_hash=cast(str, receipt_body["subject_artifact_hash"]),
        signature_hash=hashlib.sha256(signature).hexdigest(),
    )
