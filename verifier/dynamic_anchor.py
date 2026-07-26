"""Pinned external signatures over completed dynamic-state audit hashes."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from dopey.ascendancy.identity import JsonValue, canonical_hash, parse_utc, require_sha256, require_utc_iso

from .external_root import verify_external_trust_root


ENVIRONMENT_ID = "dopey-options-paper-v1"
DYNAMIC_ANCHOR_TRUST_FILE = "DYNAMIC_ANCHOR_TRUST.json"
DYNAMIC_ANCHOR_RECEIPT_FILE = "DYNAMIC_STATE_ANCHOR_RECEIPT.json"
ANCHOR_ID_PREFIX = "dynamic-anchor-"
TRUST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "status",
        "algorithm",
        "authority_id",
        "authority_version",
        "key_id",
        "public_key_base64",
    }
)
ANCHOR_BODY_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "dynamic_state_hash",
        "protected_manifest_sha256",
        "authority_id",
        "authority_version",
        "key_id",
        "anchor_id",
        "anchor_sequence",
        "parent_anchor_id",
        "issued_at",
    }
)
ANCHOR_RECEIPT_FIELDS = frozenset({"body", "signature_base64"})
TrustStatus = Literal["configured", "not_configured"]


@dataclass(frozen=True, slots=True)
class DynamicAnchorTrust:
    status: TrustStatus
    authority_id: str | None
    authority_version: str | None
    key_id: str | None
    public_key_bytes: bytes | None


@dataclass(frozen=True, slots=True)
class DynamicAnchorVerification:
    anchor_id: str
    anchor_sequence: int
    parent_anchor_id: str | None
    authority_id: str
    authority_version: str
    key_id: str
    dynamic_state_hash: str
    protected_manifest_sha256: str
    issued_at: str
    body_hash: str
    signature_hash: str
    receipt_sha256: str


def _reject_duplicate_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    decoded: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"dynamic anchor JSON contains a duplicate field: field={key}")
        decoded[key] = value
    return decoded


def _load_json_mapping(path: Path, artifact_name: str) -> dict[str, JsonValue]:
    decoded = json.loads(
        path.resolve(strict=True).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object,
    )
    if not isinstance(decoded, dict):
        raise ValueError(f"{artifact_name} must be a JSON mapping")
    return cast(dict[str, JsonValue], decoded)


def _require_exact_fields(
    value: dict[str, JsonValue],
    expected_fields: frozenset[str],
    artifact_name: str,
) -> None:
    observed_fields = set(value)
    if observed_fields != expected_fields:
        raise ValueError(
            f"{artifact_name} fields differ from the exact v1 schema: "
            f"missing={sorted(expected_fields.difference(observed_fields))}, "
            f"unexpected={sorted(observed_fields.difference(expected_fields))}"
        )


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"dynamic anchor requires a non-empty string: field={field_name}")
    return value


def _require_anchor_sequence(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(
            "dynamic anchor sequence must be a positive integer: "
            f"observed={value}"
        )
    return value


def _require_anchor_id(value: object, field_name: str) -> str:
    anchor_id = _require_non_empty_string(value, field_name)
    suffix = anchor_id.removeprefix(ANCHOR_ID_PREFIX)
    if (
        not anchor_id.startswith(ANCHOR_ID_PREFIX)
        or len(suffix) != 24
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(
            "dynamic anchor identity is invalid: "
            f"field={field_name}, observed={anchor_id}"
        )
    return anchor_id


def _validate_sequence_parent(
    anchor_sequence: int,
    parent_anchor_id: object,
) -> str | None:
    if anchor_sequence == 1:
        if parent_anchor_id is not None:
            raise ValueError("dynamic anchor sequence one must not declare a parent")
        return None
    if parent_anchor_id is None:
        raise ValueError("dynamic anchor sequence greater than one requires a parent")
    return _require_anchor_id(parent_anchor_id, "parent_anchor_id")


def _decode_canonical_base64(value: object, field_name: str, expected_length: int) -> bytes:
    encoded = _require_non_empty_string(value, field_name)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"dynamic anchor field is not valid base64: field={field_name}") from error
    if len(decoded) != expected_length:
        raise ValueError(
            "dynamic anchor decoded field has an invalid length: "
            f"field={field_name}, expected={expected_length}, observed={len(decoded)}"
        )
    if base64.b64encode(decoded).decode("ascii") != encoded:
        raise ValueError(f"dynamic anchor base64 is not canonical: field={field_name}")
    return decoded


def load_dynamic_anchor_trust(trust_path: Path) -> DynamicAnchorTrust:
    trust = _load_json_mapping(trust_path, "dynamic anchor trust")
    _require_exact_fields(trust, TRUST_FIELDS, "dynamic anchor trust")
    if trust["schema_version"] != "dopey-dynamic-anchor-trust-v1":
        raise ValueError("dynamic anchor trust schema version is unsupported")
    if trust["environment_id"] != ENVIRONMENT_ID:
        raise ValueError("dynamic anchor trust environment identity mismatch")
    if trust["algorithm"] != "ed25519":
        raise ValueError("dynamic anchor trust algorithm must be ed25519")
    status = trust["status"]
    if status == "not_configured":
        nullable_fields = ("authority_id", "authority_version", "key_id", "public_key_base64")
        if any(trust[field_name] is not None for field_name in nullable_fields):
            raise ValueError("unconfigured dynamic anchor trust requires null authority and key fields")
        return DynamicAnchorTrust("not_configured", None, None, None, None)
    if status != "configured":
        raise ValueError(f"dynamic anchor trust status is unsupported: status={status}")
    authority_id = _require_non_empty_string(trust["authority_id"], "authority_id")
    authority_version = _require_non_empty_string(
        trust["authority_version"],
        "authority_version",
    )
    public_key_bytes = _decode_canonical_base64(
        trust["public_key_base64"],
        "public_key_base64",
        32,
    )
    public_key_hash = hashlib.sha256(public_key_bytes).hexdigest()
    key_id = _require_non_empty_string(trust["key_id"], "key_id")
    expected_key_id = f"ed25519-sha256-{public_key_hash}"
    if key_id != expected_key_id:
        raise ValueError(
            "dynamic anchor key identity is not bound to the pinned public key: "
            f"expected={expected_key_id}, observed={key_id}"
        )
    return DynamicAnchorTrust(
        "configured",
        authority_id,
        authority_version,
        key_id,
        public_key_bytes,
    )


def _anchor_identity_body(body: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: value for key, value in body.items() if key != "anchor_id"}


def _content_bound_anchor_id(body: dict[str, JsonValue]) -> str:
    return f"{ANCHOR_ID_PREFIX}{canonical_hash(_anchor_identity_body(body))[:24]}"


def build_dynamic_anchor_body(
    dynamic_state_hash: str,
    protected_manifest_sha256: str,
    authority_id: str,
    authority_version: str,
    key_id: str,
    anchor_sequence: int,
    parent_anchor_id: str | None,
    issued_at: str,
) -> dict[str, JsonValue]:
    require_sha256(dynamic_state_hash, "dynamic_state_hash")
    require_sha256(protected_manifest_sha256, "protected_manifest_sha256")
    _require_non_empty_string(authority_id, "authority_id")
    _require_non_empty_string(authority_version, "authority_version")
    _require_non_empty_string(key_id, "key_id")
    normalized_sequence = _require_anchor_sequence(anchor_sequence)
    normalized_parent_id = _validate_sequence_parent(
        normalized_sequence,
        parent_anchor_id,
    )
    require_utc_iso(issued_at)
    body: dict[str, JsonValue] = {
        "schema_version": "dopey-dynamic-state-anchor-v2",
        "environment_id": ENVIRONMENT_ID,
        "dynamic_state_hash": dynamic_state_hash,
        "protected_manifest_sha256": protected_manifest_sha256,
        "authority_id": authority_id,
        "authority_version": authority_version,
        "key_id": key_id,
        "anchor_sequence": normalized_sequence,
        "parent_anchor_id": normalized_parent_id,
        "issued_at": issued_at,
    }
    return {**body, "anchor_id": _content_bound_anchor_id(body)}


def canonical_dynamic_anchor_body_bytes(body: dict[str, JsonValue]) -> bytes:
    _require_exact_fields(body, ANCHOR_BODY_FIELDS, "dynamic anchor body")
    if body["schema_version"] != "dopey-dynamic-state-anchor-v2":
        raise ValueError("dynamic anchor body schema version is unsupported")
    if body["environment_id"] != ENVIRONMENT_ID:
        raise ValueError("dynamic anchor body environment identity mismatch")
    dynamic_state_hash = _require_non_empty_string(
        body["dynamic_state_hash"],
        "dynamic_state_hash",
    )
    require_sha256(dynamic_state_hash, "dynamic_state_hash")
    protected_manifest_sha256 = _require_non_empty_string(
        body["protected_manifest_sha256"],
        "protected_manifest_sha256",
    )
    require_sha256(protected_manifest_sha256, "protected_manifest_sha256")
    _require_non_empty_string(body["authority_id"], "authority_id")
    _require_non_empty_string(body["authority_version"], "authority_version")
    _require_non_empty_string(body["key_id"], "key_id")
    anchor_sequence = _require_anchor_sequence(body["anchor_sequence"])
    parent_anchor_id = _validate_sequence_parent(
        anchor_sequence,
        body["parent_anchor_id"],
    )
    issued_at = _require_non_empty_string(body["issued_at"], "issued_at")
    require_utc_iso(issued_at)
    expected_anchor_id = _content_bound_anchor_id(body)
    if body["anchor_id"] != expected_anchor_id:
        raise ValueError(
            "dynamic anchor identity is not bound to its signed content: "
            f"expected={expected_anchor_id}, observed={body['anchor_id']}"
        )
    if parent_anchor_id == expected_anchor_id:
        raise ValueError("dynamic anchor cannot identify itself as its parent")
    return json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def verify_dynamic_state_anchor(
    trust_path: Path,
    receipt_path: Path,
    expected_dynamic_state_hash: str,
    expected_protected_manifest_sha256: str,
) -> DynamicAnchorVerification:
    require_sha256(expected_dynamic_state_hash, "expected_dynamic_state_hash")
    require_sha256(
        expected_protected_manifest_sha256,
        "expected_protected_manifest_sha256",
    )
    trust = load_dynamic_anchor_trust(trust_path)
    if trust.status != "configured":
        raise PermissionError("dynamic anchor trust is not configured")
    receipt = _load_json_mapping(receipt_path, "dynamic anchor receipt")
    _require_exact_fields(receipt, ANCHOR_RECEIPT_FIELDS, "dynamic anchor receipt")
    raw_body = receipt["body"]
    if not isinstance(raw_body, dict):
        raise ValueError("dynamic anchor receipt body must be a mapping")
    body = cast(dict[str, JsonValue], raw_body)
    message = canonical_dynamic_anchor_body_bytes(body)
    if body["dynamic_state_hash"] != expected_dynamic_state_hash:
        raise ValueError("dynamic anchor receipt does not bind the current dynamic-state hash")
    if body["protected_manifest_sha256"] != expected_protected_manifest_sha256:
        raise ValueError("dynamic anchor receipt does not bind the current protected-manifest hash")
    if (
        body["authority_id"] != trust.authority_id
        or body["authority_version"] != trust.authority_version
        or body["key_id"] != trust.key_id
    ):
        raise ValueError("dynamic anchor receipt authority differs from pinned trust")
    issued_at = cast(str, body["issued_at"])
    if parse_utc(issued_at) > datetime.now(timezone.utc):
        raise ValueError("dynamic anchor receipt is future-dated")
    signature = _decode_canonical_base64(receipt["signature_base64"], "signature_base64", 64)
    if trust.public_key_bytes is None or trust.key_id is None:
        raise ValueError("configured dynamic anchor trust lacks key material")
    public_key = Ed25519PublicKey.from_public_bytes(trust.public_key_bytes)
    try:
        public_key.verify(signature, message)
    except InvalidSignature as error:
        raise ValueError("dynamic anchor Ed25519 signature verification failed") from error
    receipt_bytes = receipt_path.resolve(strict=True).read_bytes()
    return DynamicAnchorVerification(
        anchor_id=cast(str, body["anchor_id"]),
        anchor_sequence=cast(int, body["anchor_sequence"]),
        parent_anchor_id=cast(str | None, body["parent_anchor_id"]),
        authority_id=cast(str, trust.authority_id),
        authority_version=cast(str, trust.authority_version),
        key_id=trust.key_id,
        dynamic_state_hash=expected_dynamic_state_hash,
        protected_manifest_sha256=expected_protected_manifest_sha256,
        issued_at=issued_at,
        body_hash=hashlib.sha256(message).hexdigest(),
        signature_hash=hashlib.sha256(signature).hexdigest(),
        receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
    )


def dynamic_anchor_audit_state(
    repository_root: Path,
    dynamic_state_hash: str,
    protected_manifest_sha256: str,
) -> dict[str, object]:
    root = repository_root.resolve(strict=True)
    trust_path = root / DYNAMIC_ANCHOR_TRUST_FILE
    receipt_path = root / DYNAMIC_ANCHOR_RECEIPT_FILE
    trust = load_dynamic_anchor_trust(trust_path)
    if trust.status == "not_configured":
        if receipt_path.exists():
            raise ValueError("dynamic anchor receipt exists while trust is not configured")
        return {
            "dynamic_anchor_status": "not_configured",
            "repository_anchor_verified": False,
            "external_anchor_verified": False,
            "external_trust_root_status": "not_supplied",
            "external_anchor_required_for_certification": True,
            "certification_eligible": False,
            "certification_block_reason": "operator_controlled_external_dynamic_state_anchor_missing",
            "dynamic_anchor_id": None,
            "dynamic_anchor_sequence": None,
            "dynamic_anchor_parent_id": None,
            "dynamic_anchor_authority_id": None,
            "dynamic_anchor_authority_version": None,
            "dynamic_anchor_issued_at": None,
            "dynamic_anchor_protected_manifest_sha256": None,
            "dynamic_anchor_receipt_sha256": None,
            "external_trust_root_id": None,
            "external_trust_root_version": None,
            "external_trust_root_sha256": None,
            "external_trust_root_minimum_anchor_sequence": None,
            "external_trust_root_pinned_identity_count": 0,
            "external_trust_root_pinned_config_sha256": {},
            "external_trust_root_pinned_role_identities": {},
        }
    if not receipt_path.exists():
        return {
            "dynamic_anchor_status": "configured_receipt_missing",
            "repository_anchor_verified": False,
            "external_anchor_verified": False,
            "external_trust_root_status": "not_supplied",
            "external_anchor_required_for_certification": True,
            "certification_eligible": False,
            "certification_block_reason": "operator_controlled_external_dynamic_state_anchor_missing",
            "dynamic_anchor_id": None,
            "dynamic_anchor_sequence": None,
            "dynamic_anchor_parent_id": None,
            "dynamic_anchor_authority_id": trust.authority_id,
            "dynamic_anchor_authority_version": trust.authority_version,
            "dynamic_anchor_issued_at": None,
            "dynamic_anchor_protected_manifest_sha256": None,
            "dynamic_anchor_receipt_sha256": None,
            "external_trust_root_id": None,
            "external_trust_root_version": None,
            "external_trust_root_sha256": None,
            "external_trust_root_minimum_anchor_sequence": None,
            "external_trust_root_pinned_identity_count": 0,
            "external_trust_root_pinned_config_sha256": {},
            "external_trust_root_pinned_role_identities": {},
        }
    verification = verify_dynamic_state_anchor(
        trust_path,
        receipt_path,
        dynamic_state_hash,
        protected_manifest_sha256,
    )
    return {
        "dynamic_anchor_status": "verified_repository_only",
        "repository_anchor_verified": True,
        "external_anchor_verified": False,
        "external_trust_root_status": "not_supplied",
        "external_anchor_required_for_certification": True,
        "certification_eligible": False,
        "certification_block_reason": "operator_controlled_external_trust_root_missing",
        "dynamic_anchor_id": verification.anchor_id,
        "dynamic_anchor_sequence": verification.anchor_sequence,
        "dynamic_anchor_parent_id": verification.parent_anchor_id,
        "dynamic_anchor_authority_id": verification.authority_id,
        "dynamic_anchor_authority_version": verification.authority_version,
        "dynamic_anchor_issued_at": verification.issued_at,
        "dynamic_anchor_protected_manifest_sha256": (
            verification.protected_manifest_sha256
        ),
        "dynamic_anchor_receipt_sha256": verification.receipt_sha256,
        "external_trust_root_id": None,
        "external_trust_root_version": None,
        "external_trust_root_sha256": None,
        "external_trust_root_minimum_anchor_sequence": None,
        "external_trust_root_pinned_identity_count": 0,
        "external_trust_root_pinned_config_sha256": {},
        "external_trust_root_pinned_role_identities": {},
    }


def dynamic_anchor_audit_state_with_external_root(
    repository_root: Path,
    dynamic_state_hash: str,
    protected_manifest_sha256: str,
    external_trust_root_path: Path,
) -> dict[str, object]:
    repository_state = dynamic_anchor_audit_state(
        repository_root,
        dynamic_state_hash,
        protected_manifest_sha256,
    )
    external_root = verify_external_trust_root(
        repository_root,
        external_trust_root_path,
        protected_manifest_sha256,
    )
    if repository_state["repository_anchor_verified"] is not True:
        raise PermissionError(
            "external certification requires a verified current repository anchor: "
            f"status={repository_state['dynamic_anchor_status']}"
        )
    anchor_id = cast(str, repository_state["dynamic_anchor_id"])
    anchor_sequence = cast(int, repository_state["dynamic_anchor_sequence"])
    parent_anchor_id = cast(str | None, repository_state["dynamic_anchor_parent_id"])
    if anchor_id != external_root.accepted_anchor_id:
        raise ValueError(
            "external trust root rejects the repository anchor identity: "
            f"expected={external_root.accepted_anchor_id}, observed={anchor_id}"
        )
    if parent_anchor_id != external_root.accepted_parent_anchor_id:
        raise ValueError(
            "external trust root rejects the repository anchor parent: "
            f"expected={external_root.accepted_parent_anchor_id}, "
            f"observed={parent_anchor_id}"
        )
    if anchor_sequence < external_root.minimum_anchor_sequence:
        raise ValueError(
            "repository anchor sequence is below the external anti-rollback minimum: "
            f"minimum={external_root.minimum_anchor_sequence}, "
            f"observed={anchor_sequence}"
        )
    return {
        **repository_state,
        "dynamic_anchor_status": "verified_external_root",
        "external_anchor_verified": True,
        "external_trust_root_status": "verified",
        "certification_eligible": True,
        "certification_block_reason": None,
        "external_trust_root_id": external_root.root_id,
        "external_trust_root_version": external_root.root_version,
        "external_trust_root_sha256": external_root.contract_sha256,
        "external_trust_root_minimum_anchor_sequence": (
            external_root.minimum_anchor_sequence
        ),
        "external_trust_root_pinned_identity_count": (
            len(external_root.pinned_role_identities)
        ),
        "external_trust_root_pinned_config_sha256": dict(
            external_root.pinned_trust_config_hashes
        ),
        "external_trust_root_pinned_role_identities": {
            identity.role: {
                "identity_id": identity.identity_id,
                "identity_version": identity.identity_version,
                "key_id": identity.key_id,
                "public_key_sha256": identity.public_key_sha256,
            }
            for identity in external_root.pinned_role_identities
        },
    }
