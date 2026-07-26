"""Operator-custodied root of trust for DOPEY certification audits."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from dopey.ascendancy.identity import JsonValue, require_sha256

from .protected_manifest import file_sha256, verify_protected_manifest


ENVIRONMENT_ID = "dopey-options-paper-v1"
EXTERNAL_TRUST_ROOT_CONTRACT_NAME = "DOPEY_DEPLOYMENT_TRUST_ROOT.json"
EXTERNAL_TRUST_ROOT_SCHEMA = "dopey-deployment-trust-root-v1"
PROTECTED_MANIFEST_FILE = "PROTECTED_MANIFEST.json"
REPOSITORY_TRUST_CONFIG_PATHS = (
    "DYNAMIC_ANCHOR_TRUST.json",
    "FORWARD_EVIDENCE_TRUST.json",
    "PROMOTION_AUTHORITY_TRUST.json",
    "SEALED_EVALUATOR_TRUST.json",
)
TRUST_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "root_id",
        "root_version",
        "protected_manifest_sha256",
        "repository_trust_pins",
        "accepted_anchor_id",
        "accepted_parent_anchor_id",
        "minimum_anchor_sequence",
    }
)
TRUST_PIN_FIELDS = frozenset({"file_sha256", "identities"})
TRUST_IDENTITY_FIELDS = frozenset(
    {
        "role",
        "identity_id",
        "identity_version",
        "key_id",
        "public_key_sha256",
    }
)
SIMPLE_TRUST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "status",
        "algorithm",
        "identity_id",
        "identity_version",
        "key_id",
        "public_key_base64",
    }
)
FORWARD_TRUST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "status",
        "algorithm",
        "forward_recorder",
        "outcome_source",
    }
)
FORWARD_ROLE_FIELDS = frozenset(
    {"signer_id", "signer_version", "key_id", "public_key_base64"}
)
ANCHOR_ID_PREFIX = "dynamic-anchor-"


@dataclass(frozen=True, slots=True)
class VerifiedTrustRoleIdentity:
    role: str
    identity_id: str
    identity_version: str
    key_id: str
    public_key_sha256: str


@dataclass(frozen=True, slots=True)
class ExternalTrustRootVerification:
    root_id: str
    root_version: str
    protected_manifest_sha256: str
    accepted_anchor_id: str
    accepted_parent_anchor_id: str | None
    minimum_anchor_sequence: int
    contract_sha256: str
    pinned_trust_config_hashes: tuple[tuple[str, str], ...]
    pinned_role_identities: tuple[VerifiedTrustRoleIdentity, ...]


def _reject_duplicate_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    decoded: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(
                "external trust-root JSON contains a duplicate field: "
                f"field={key}"
            )
        decoded[key] = value
    return decoded


def _load_json_mapping(path: Path, artifact_name: str) -> dict[str, JsonValue]:
    decoded = json.loads(
        path.resolve(strict=True).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_object,
    )
    if not isinstance(decoded, dict):
        raise ValueError(f"{artifact_name} must be a JSON mapping: path={path}")
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
        raise ValueError(
            "external trust root requires a non-empty string: "
            f"field={field_name}"
        )
    return value


def _require_sha256_value(value: object, field_name: str) -> str:
    digest = _require_non_empty_string(value, field_name)
    require_sha256(digest, field_name)
    return digest


def _require_positive_integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(
            "external trust root requires a positive integer: "
            f"field={field_name}, observed={value}"
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
            "external trust root contains an invalid dynamic-anchor identity: "
            f"field={field_name}, observed={anchor_id}"
        )
    return anchor_id


def _decode_public_key(value: object, field_name: str) -> bytes:
    encoded = _require_non_empty_string(value, field_name)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            "repository trust public key is not valid base64: "
            f"field={field_name}"
        ) from error
    if len(decoded) != 32:
        raise ValueError(
            "repository trust public key has an invalid length: "
            f"field={field_name}, expected=32, observed={len(decoded)}"
        )
    if base64.b64encode(decoded).decode("ascii") != encoded:
        raise ValueError(
            "repository trust public key is not canonical base64: "
            f"field={field_name}"
        )
    return decoded


def _key_identity(
    role: str,
    identity_id: object,
    identity_version: object,
    key_id_value: object,
    public_key_base64: object,
) -> dict[str, JsonValue]:
    normalized_identity_id = _require_non_empty_string(identity_id, f"{role}.identity_id")
    normalized_identity_version = _require_non_empty_string(
        identity_version,
        f"{role}.identity_version",
    )
    public_key_bytes = _decode_public_key(public_key_base64, f"{role}.public_key_base64")
    public_key_sha256 = hashlib.sha256(public_key_bytes).hexdigest()
    key_id = _require_non_empty_string(key_id_value, f"{role}.key_id")
    expected_key_id = f"ed25519-sha256-{public_key_sha256}"
    if key_id != expected_key_id:
        raise ValueError(
            "repository trust key identity differs from its public key: "
            f"role={role}, expected={expected_key_id}, observed={key_id}"
        )
    return {
        "role": role,
        "identity_id": normalized_identity_id,
        "identity_version": normalized_identity_version,
        "key_id": key_id,
        "public_key_sha256": public_key_sha256,
    }


def _simple_trust_identities(
    trust_path: Path,
    schema_version: str,
    identity_id_field: str,
    identity_version_field: str,
    role: str,
) -> list[JsonValue]:
    raw = _load_json_mapping(trust_path, f"repository trust config {trust_path.name}")
    renamed: dict[str, JsonValue] = {
        "schema_version": raw.get("schema_version"),
        "environment_id": raw.get("environment_id"),
        "status": raw.get("status"),
        "algorithm": raw.get("algorithm"),
        "identity_id": raw.get(identity_id_field),
        "identity_version": raw.get(identity_version_field),
        "key_id": raw.get("key_id"),
        "public_key_base64": raw.get("public_key_base64"),
    }
    expected_original_fields = frozenset(
        {
            "schema_version",
            "environment_id",
            "status",
            "algorithm",
            identity_id_field,
            identity_version_field,
            "key_id",
            "public_key_base64",
        }
    )
    _require_exact_fields(raw, expected_original_fields, trust_path.name)
    _require_exact_fields(renamed, SIMPLE_TRUST_FIELDS, trust_path.name)
    if raw["schema_version"] != schema_version:
        raise ValueError(
            "repository trust schema version is unsupported: "
            f"path={trust_path.name}"
        )
    if raw["environment_id"] != ENVIRONMENT_ID:
        raise ValueError(
            "repository trust environment identity mismatch: "
            f"path={trust_path.name}"
        )
    if raw["status"] != "configured":
        raise PermissionError(
            "external certification requires configured repository trust: "
            f"path={trust_path.name}, status={raw['status']}"
        )
    if raw["algorithm"] != "ed25519":
        raise ValueError(
            "repository trust algorithm must be ed25519: "
            f"path={trust_path.name}"
        )
    return [
        _key_identity(
            role,
            renamed["identity_id"],
            renamed["identity_version"],
            renamed["key_id"],
            renamed["public_key_base64"],
        )
    ]


def _forward_trust_identities(trust_path: Path) -> list[JsonValue]:
    trust = _load_json_mapping(trust_path, "repository forward-evidence trust")
    _require_exact_fields(trust, FORWARD_TRUST_FIELDS, trust_path.name)
    if trust["schema_version"] != "dopey-forward-evidence-trust-v1":
        raise ValueError("repository forward-evidence trust schema version is unsupported")
    if trust["environment_id"] != ENVIRONMENT_ID:
        raise ValueError("repository forward-evidence trust environment identity mismatch")
    if trust["status"] != "configured":
        raise PermissionError(
            "external certification requires configured repository trust: "
            f"path={trust_path.name}, status={trust['status']}"
        )
    if trust["algorithm"] != "ed25519":
        raise ValueError("repository forward-evidence trust algorithm must be ed25519")
    identities: list[JsonValue] = []
    for role in ("forward_recorder", "outcome_source"):
        raw_role = trust[role]
        if not isinstance(raw_role, dict):
            raise ValueError(
                "repository forward-evidence trust role must be a mapping: "
                f"role={role}"
            )
        role_mapping = cast(dict[str, JsonValue], raw_role)
        _require_exact_fields(role_mapping, FORWARD_ROLE_FIELDS, f"forward role {role}")
        identities.append(
            _key_identity(
                role,
                role_mapping["signer_id"],
                role_mapping["signer_version"],
                role_mapping["key_id"],
                role_mapping["public_key_base64"],
            )
        )
    recorder = cast(dict[str, JsonValue], identities[0])
    outcome_source = cast(dict[str, JsonValue], identities[1])
    if recorder["identity_id"] == outcome_source["identity_id"]:
        raise ValueError("forward recorder and outcome-source identities must be independent")
    if recorder["public_key_sha256"] == outcome_source["public_key_sha256"]:
        raise ValueError("forward recorder and outcome-source keys must be independent")
    return identities


def _repository_trust_identities(trust_path: Path) -> list[JsonValue]:
    if trust_path.name == "DYNAMIC_ANCHOR_TRUST.json":
        return _simple_trust_identities(
            trust_path,
            "dopey-dynamic-anchor-trust-v1",
            "authority_id",
            "authority_version",
            "dynamic_anchor_authority",
        )
    if trust_path.name == "PROMOTION_AUTHORITY_TRUST.json":
        return _simple_trust_identities(
            trust_path,
            "dopey-promotion-authority-trust-v1",
            "authority_id",
            "authority_version",
            "promotion_authority",
        )
    if trust_path.name == "SEALED_EVALUATOR_TRUST.json":
        return _simple_trust_identities(
            trust_path,
            "dopey-sealed-evaluator-trust-v1",
            "evaluator_id",
            "evaluator_version",
            "sealed_evaluator",
        )
    if trust_path.name == "FORWARD_EVIDENCE_TRUST.json":
        return _forward_trust_identities(trust_path)
    raise ValueError(f"unsupported repository trust config: path={trust_path.name}")


def _assert_repository_trust_independence(pins: dict[str, JsonValue]) -> None:
    identity_roles: dict[str, str] = {}
    public_key_roles: dict[str, str] = {}
    for relative_path in REPOSITORY_TRUST_CONFIG_PATHS:
        pin = cast(dict[str, JsonValue], pins[relative_path])
        identities = cast(list[JsonValue], pin["identities"])
        for raw_identity in identities:
            identity = cast(dict[str, JsonValue], raw_identity)
            role = cast(str, identity["role"])
            identity_id = cast(str, identity["identity_id"])
            public_key_sha256 = cast(str, identity["public_key_sha256"])
            prior_identity_role = identity_roles.get(identity_id)
            if prior_identity_role is not None:
                raise ValueError(
                    "repository trust identity is reused across independent roles: "
                    f"identity_id={identity_id}, roles={prior_identity_role},{role}"
                )
            prior_key_role = public_key_roles.get(public_key_sha256)
            if prior_key_role is not None:
                raise ValueError(
                    "repository trust public key is reused across independent roles: "
                    f"public_key_sha256={public_key_sha256}, "
                    f"roles={prior_key_role},{role}"
                )
            identity_roles[identity_id] = role
            public_key_roles[public_key_sha256] = role
    if len(identity_roles) != 5 or len(public_key_roles) != 5:
        raise ValueError(
            "repository trust must contain exactly five independent signer identities"
        )


def build_repository_trust_pins(repository_root: Path) -> dict[str, JsonValue]:
    root = repository_root.resolve(strict=True)
    pins: dict[str, JsonValue] = {}
    for relative_path in REPOSITORY_TRUST_CONFIG_PATHS:
        trust_path = (root / relative_path).resolve(strict=True)
        try:
            trust_path.relative_to(root)
        except ValueError as error:
            raise ValueError(
                "repository trust config escapes repository: "
                f"path={relative_path}"
            ) from error
        pins[relative_path] = {
            "file_sha256": file_sha256(trust_path),
            "identities": _repository_trust_identities(trust_path),
        }
    _assert_repository_trust_independence(pins)
    return pins


def build_external_trust_root_contract(
    repository_root: Path,
    root_id: str,
    root_version: str,
    accepted_anchor_id: str,
    accepted_parent_anchor_id: str | None,
    minimum_anchor_sequence: int,
) -> dict[str, JsonValue]:
    root = repository_root.resolve(strict=True)
    normalized_root_id = _require_non_empty_string(root_id, "root_id")
    normalized_root_version = _require_non_empty_string(root_version, "root_version")
    normalized_anchor_id = _require_anchor_id(accepted_anchor_id, "accepted_anchor_id")
    normalized_parent_id = (
        None
        if accepted_parent_anchor_id is None
        else _require_anchor_id(accepted_parent_anchor_id, "accepted_parent_anchor_id")
    )
    normalized_sequence = _require_positive_integer(
        minimum_anchor_sequence,
        "minimum_anchor_sequence",
    )
    protected_manifest_path = (root / PROTECTED_MANIFEST_FILE).resolve(strict=True)
    verify_protected_manifest(root, protected_manifest_path)
    protected_manifest_sha256 = file_sha256(protected_manifest_path)
    return {
        "schema_version": EXTERNAL_TRUST_ROOT_SCHEMA,
        "environment_id": ENVIRONMENT_ID,
        "root_id": normalized_root_id,
        "root_version": normalized_root_version,
        "protected_manifest_sha256": protected_manifest_sha256,
        "repository_trust_pins": build_repository_trust_pins(root),
        "accepted_anchor_id": normalized_anchor_id,
        "accepted_parent_anchor_id": normalized_parent_id,
        "minimum_anchor_sequence": normalized_sequence,
    }


def _assert_external_root_path(repository_root: Path, trust_root_path: Path) -> Path:
    root = repository_root.resolve(strict=True)
    resolved_path = trust_root_path.resolve(strict=True)
    try:
        resolved_path.relative_to(root)
    except ValueError:
        return resolved_path
    raise PermissionError(
        "deployment trust root must be operator-custodied outside the repository: "
        f"path={resolved_path}"
    )


def _validate_contract_pin(pin: object, relative_path: str) -> dict[str, JsonValue]:
    if not isinstance(pin, dict):
        raise ValueError(
            "external trust-root repository pin must be a mapping: "
            f"path={relative_path}"
        )
    mapping = cast(dict[str, JsonValue], pin)
    _require_exact_fields(mapping, TRUST_PIN_FIELDS, f"trust pin {relative_path}")
    _require_sha256_value(mapping["file_sha256"], f"{relative_path}.file_sha256")
    identities = mapping["identities"]
    if not isinstance(identities, list) or not identities:
        raise ValueError(
            "external trust-root pin requires key identities: "
            f"path={relative_path}"
        )
    observed_roles: list[str] = []
    for index, raw_identity in enumerate(identities):
        if not isinstance(raw_identity, dict):
            raise ValueError(
                "external trust-root identity must be a mapping: "
                f"path={relative_path}, index={index}"
            )
        identity = cast(dict[str, JsonValue], raw_identity)
        _require_exact_fields(
            identity,
            TRUST_IDENTITY_FIELDS,
            f"trust identity {relative_path}[{index}]",
        )
        role = _require_non_empty_string(identity["role"], "role")
        observed_roles.append(role)
        _require_non_empty_string(identity["identity_id"], f"{role}.identity_id")
        _require_non_empty_string(identity["identity_version"], f"{role}.identity_version")
        key_id = _require_non_empty_string(identity["key_id"], f"{role}.key_id")
        public_key_sha256 = _require_sha256_value(
            identity["public_key_sha256"],
            f"{role}.public_key_sha256",
        )
        if key_id != f"ed25519-sha256-{public_key_sha256}":
            raise ValueError(
                "external trust-root key identity differs from its public-key hash: "
                f"role={role}"
            )
    if len(observed_roles) != len(set(observed_roles)):
        raise ValueError(
            "external trust-root pin contains duplicate identity roles: "
            f"path={relative_path}"
        )
    return mapping


def _verified_role_identities(
    pins: dict[str, dict[str, JsonValue]],
) -> tuple[VerifiedTrustRoleIdentity, ...]:
    verified: list[VerifiedTrustRoleIdentity] = []
    for relative_path in REPOSITORY_TRUST_CONFIG_PATHS:
        raw_identities = cast(list[JsonValue], pins[relative_path]["identities"])
        for raw_identity in raw_identities:
            identity = cast(dict[str, JsonValue], raw_identity)
            verified.append(
                VerifiedTrustRoleIdentity(
                    role=cast(str, identity["role"]),
                    identity_id=cast(str, identity["identity_id"]),
                    identity_version=cast(str, identity["identity_version"]),
                    key_id=cast(str, identity["key_id"]),
                    public_key_sha256=cast(str, identity["public_key_sha256"]),
                )
            )
    return tuple(verified)


def verify_external_trust_root(
    repository_root: Path,
    external_trust_root_path: Path,
    expected_protected_manifest_sha256: str,
) -> ExternalTrustRootVerification:
    root = repository_root.resolve(strict=True)
    external_path = _assert_external_root_path(root, external_trust_root_path)
    contract = _load_json_mapping(external_path, "external deployment trust root")
    _require_exact_fields(contract, TRUST_ROOT_FIELDS, "external deployment trust root")
    if contract["schema_version"] != EXTERNAL_TRUST_ROOT_SCHEMA:
        raise ValueError("external deployment trust-root schema version is unsupported")
    if contract["environment_id"] != ENVIRONMENT_ID:
        raise ValueError("external deployment trust-root environment identity mismatch")
    root_id = _require_non_empty_string(contract["root_id"], "root_id")
    root_version = _require_non_empty_string(contract["root_version"], "root_version")
    protected_manifest_sha256 = _require_sha256_value(
        contract["protected_manifest_sha256"],
        "protected_manifest_sha256",
    )
    require_sha256(
        expected_protected_manifest_sha256,
        "expected_protected_manifest_sha256",
    )
    protected_manifest_path = (root / PROTECTED_MANIFEST_FILE).resolve(strict=True)
    verify_protected_manifest(root, protected_manifest_path)
    actual_manifest_sha256 = file_sha256(protected_manifest_path)
    if protected_manifest_sha256 != actual_manifest_sha256:
        raise ValueError(
            "external trust root does not pin the repository protected manifest: "
            f"expected={actual_manifest_sha256}, observed={protected_manifest_sha256}"
        )
    if protected_manifest_sha256 != expected_protected_manifest_sha256:
        raise ValueError(
            "external trust-root protected-manifest pin differs from the audit: "
            f"expected={expected_protected_manifest_sha256}, "
            f"observed={protected_manifest_sha256}"
        )
    accepted_anchor_id = _require_anchor_id(
        contract["accepted_anchor_id"],
        "accepted_anchor_id",
    )
    raw_parent_id = contract["accepted_parent_anchor_id"]
    accepted_parent_anchor_id = (
        None
        if raw_parent_id is None
        else _require_anchor_id(raw_parent_id, "accepted_parent_anchor_id")
    )
    minimum_anchor_sequence = _require_positive_integer(
        contract["minimum_anchor_sequence"],
        "minimum_anchor_sequence",
    )
    raw_pins = contract["repository_trust_pins"]
    if not isinstance(raw_pins, dict):
        raise ValueError("external trust-root repository pins must be a mapping")
    pins = cast(dict[str, JsonValue], raw_pins)
    expected_paths = frozenset(REPOSITORY_TRUST_CONFIG_PATHS)
    if frozenset(pins) != expected_paths:
        raise ValueError(
            "external trust root must pin exactly all repository trust configs: "
            f"missing={sorted(expected_paths.difference(pins))}, "
            f"unexpected={sorted(set(pins).difference(expected_paths))}"
        )
    validated_pins = {
        relative_path: _validate_contract_pin(pins[relative_path], relative_path)
        for relative_path in REPOSITORY_TRUST_CONFIG_PATHS
    }
    actual_pins = build_repository_trust_pins(root)
    for relative_path in REPOSITORY_TRUST_CONFIG_PATHS:
        if validated_pins[relative_path] != actual_pins[relative_path]:
            raise ValueError(
                "external trust root does not match repository trust config or key identities: "
                f"path={relative_path}"
            )
    pinned_hashes = tuple(
        (
            relative_path,
            cast(str, validated_pins[relative_path]["file_sha256"]),
        )
        for relative_path in REPOSITORY_TRUST_CONFIG_PATHS
    )
    pinned_role_identities = _verified_role_identities(validated_pins)
    return ExternalTrustRootVerification(
        root_id=root_id,
        root_version=root_version,
        protected_manifest_sha256=protected_manifest_sha256,
        accepted_anchor_id=accepted_anchor_id,
        accepted_parent_anchor_id=accepted_parent_anchor_id,
        minimum_anchor_sequence=minimum_anchor_sequence,
        contract_sha256=file_sha256(external_path),
        pinned_trust_config_hashes=pinned_hashes,
        pinned_role_identities=pinned_role_identities,
    )
