"""Pinned Ed25519 verification for aggregate-only sealed evaluator responses."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .aggregate_contract import (
    ALLOWED_FAILURE_CODES,
    PROHIBITED_RAW_KEYS,
    require_canonical_utc,
)


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
TrustStatus = Literal["configured", "not_configured"]
TRUST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "status",
        "algorithm",
        "evaluator_id",
        "evaluator_version",
        "key_id",
        "public_key_base64",
    }
)
SIGNED_RESPONSE_BODY_FIELDS = frozenset(
    {
        "request_id",
        "candidate_id",
        "frozen_specification_hash",
        "submission_number",
        "evaluator_id",
        "evaluator_version",
        "evaluator_issued_at",
        "passed",
        "aggregate_feedback_only",
        "raw_holdout_access",
        "aggregate_metrics",
        "failure_codes",
    }
)
SEALED_REQUEST_PREFIX = "sealed-request-"


@dataclass(frozen=True, slots=True)
class SealedEvaluatorTrust:
    status: TrustStatus
    algorithm: Literal["ed25519"]
    evaluator_id: str | None
    evaluator_version: str | None
    key_id: str | None
    public_key_bytes: bytes | None


@dataclass(frozen=True, slots=True)
class SealedSignatureVerification:
    evaluator_id: str
    evaluator_version: str
    signature_algorithm: Literal["ed25519"]
    key_id: str
    public_key_hash: str
    response_body_hash: str
    signature_hash: str


def _reject_duplicate_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    decoded: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"sealed evaluator trust contains a duplicate field: field={key}")
        decoded[key] = value
    return decoded


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"sealed evaluator trust requires a non-empty string: field={field_name}")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"sealed response requires a SHA-256 identity: field={field_name}")
    return value


def _decode_canonical_base64(value: object, field_name: str, expected_length: int) -> bytes:
    encoded = _require_non_empty_string(value, field_name)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            f"sealed evaluator field is not valid base64: field={field_name}"
        ) from error
    if len(decoded) != expected_length:
        raise ValueError(
            "sealed evaluator decoded field has an invalid length: "
            f"field={field_name}, expected={expected_length}, observed={len(decoded)}"
        )
    if base64.b64encode(decoded).decode("ascii") != encoded:
        raise ValueError(f"sealed evaluator base64 is not canonical: field={field_name}")
    return decoded


def load_sealed_evaluator_trust(trust_path: Path) -> SealedEvaluatorTrust:
    resolved_path = trust_path.resolve(strict=True)
    decoded = json.loads(
        resolved_path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object,
    )
    if not isinstance(decoded, dict) or set(decoded) != TRUST_FIELDS:
        observed = set(decoded) if isinstance(decoded, dict) else set()
        raise ValueError(
            "sealed evaluator trust fields differ from the exact v1 schema: "
            f"missing={sorted(TRUST_FIELDS.difference(observed))}, "
            f"unexpected={sorted(observed.difference(TRUST_FIELDS))}"
        )
    trust = cast(dict[str, JsonValue], decoded)
    if trust["schema_version"] != "dopey-sealed-evaluator-trust-v1":
        raise ValueError("sealed evaluator trust schema version is unsupported")
    if trust["environment_id"] != "dopey-options-paper-v1":
        raise ValueError("sealed evaluator trust environment identity mismatch")
    if trust["algorithm"] != "ed25519":
        raise ValueError("sealed evaluator trust algorithm must be ed25519")
    status = trust["status"]
    if status == "not_configured":
        nullable_fields = ("evaluator_id", "evaluator_version", "key_id", "public_key_base64")
        if any(trust[field_name] is not None for field_name in nullable_fields):
            raise ValueError("unconfigured sealed evaluator trust requires null evaluator and key fields")
        return SealedEvaluatorTrust("not_configured", "ed25519", None, None, None, None)
    if status != "configured":
        raise ValueError(f"sealed evaluator trust status is unsupported: status={status}")
    evaluator_id = _require_non_empty_string(trust["evaluator_id"], "evaluator_id")
    evaluator_version = _require_non_empty_string(
        trust["evaluator_version"],
        "evaluator_version",
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
            "sealed evaluator key identity is not bound to the pinned public key: "
            f"expected={expected_key_id}, observed={key_id}"
        )
    return SealedEvaluatorTrust(
        "configured",
        "ed25519",
        evaluator_id,
        evaluator_version,
        key_id,
        public_key_bytes,
    )


def _validate_response_body(response_body: dict[str, JsonValue]) -> None:
    if set(response_body) != SIGNED_RESPONSE_BODY_FIELDS:
        raise ValueError("sealed signed response body differs from the exact aggregate v1 schema")
    request_id = response_body["request_id"]
    if (
        not isinstance(request_id, str)
        or not request_id.startswith(SEALED_REQUEST_PREFIX)
        or len(request_id) != len(SEALED_REQUEST_PREFIX) + 24
        or any(
            character not in "0123456789abcdef"
            for character in request_id[len(SEALED_REQUEST_PREFIX) :]
        )
    ):
        raise ValueError("sealed signed response request identity is invalid")
    _require_non_empty_string(response_body["candidate_id"], "candidate_id")
    _require_sha256(response_body["frozen_specification_hash"], "frozen_specification_hash")
    _require_non_empty_string(response_body["evaluator_id"], "evaluator_id")
    _require_non_empty_string(response_body["evaluator_version"], "evaluator_version")
    require_canonical_utc(response_body["evaluator_issued_at"], "evaluator_issued_at")
    passed = response_body["passed"]
    if not isinstance(passed, bool):
        raise ValueError("sealed signed response passed verdict must be boolean")
    if (
        response_body["submission_number"] != 1
        or response_body["aggregate_feedback_only"] is not True
        or response_body["raw_holdout_access"] is not False
    ):
        raise ValueError("sealed signed response violates aggregate-only one-shot authority")
    metrics = response_body["aggregate_metrics"]
    failure_codes = response_body["failure_codes"]
    if not isinstance(metrics, dict) or any(
        not isinstance(metric_id, str)
        or not metric_id
        or any(raw_key in metric_id.lower() for raw_key in PROHIBITED_RAW_KEYS)
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for metric_id, value in metrics.items()
    ):
        raise ValueError("sealed signed response aggregate metrics are invalid")
    if (
        not isinstance(failure_codes, list)
        or any(not isinstance(code, str) or code not in ALLOWED_FAILURE_CODES for code in failure_codes)
        or len(failure_codes) != len(set(failure_codes))
    ):
        raise ValueError("sealed signed response failure codes are invalid")
    if passed:
        if not metrics or failure_codes:
            raise ValueError(
                "passed sealed signed response requires metrics and no failure codes"
            )
    elif metrics or not failure_codes:
        raise ValueError(
            "failed sealed signed response requires failure codes and no metrics"
        )


def canonical_response_body_bytes(response_body: dict[str, JsonValue]) -> bytes:
    _validate_response_body(response_body)
    encoded = json.dumps(
        response_body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return encoded.encode("utf-8")


def verify_sealed_response_signature(
    trust_path: Path,
    response_body: dict[str, JsonValue],
    signature_base64: str,
) -> SealedSignatureVerification:
    trust = load_sealed_evaluator_trust(trust_path)
    if trust.status != "configured":
        raise PermissionError("sealed evaluator trust is not configured")
    if (
        response_body.get("evaluator_id") != trust.evaluator_id
        or response_body.get("evaluator_version") != trust.evaluator_version
    ):
        raise ValueError("sealed response evaluator identity differs from the pinned trust root")
    message = canonical_response_body_bytes(response_body)
    signature = _decode_canonical_base64(signature_base64, "signature_base64", 64)
    if trust.public_key_bytes is None or trust.key_id is None:
        raise ValueError("configured sealed evaluator trust lacks key material")
    public_key = Ed25519PublicKey.from_public_bytes(trust.public_key_bytes)
    try:
        public_key.verify(signature, message)
    except InvalidSignature as error:
        raise ValueError("sealed response Ed25519 signature verification failed") from error
    return SealedSignatureVerification(
        evaluator_id=cast(str, trust.evaluator_id),
        evaluator_version=cast(str, trust.evaluator_version),
        signature_algorithm="ed25519",
        key_id=trust.key_id,
        public_key_hash=hashlib.sha256(trust.public_key_bytes).hexdigest(),
        response_body_hash=hashlib.sha256(message).hexdigest(),
        signature_hash=hashlib.sha256(signature).hexdigest(),
    )
