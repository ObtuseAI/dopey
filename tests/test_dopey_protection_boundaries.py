from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import dopey.ascendancy.ledger as ascendancy_ledger
import verifier.audit as verifier_audit
from dopey.ascendancy.identity import JsonValue, canonical_hash
from dopey.ascendancy.ledger import LedgerKind, append_canonical_ascendancy_record
from sealed_evaluator_client.budget import reserve_sealed_submission
from verifier.audit import (
    audit_dynamic_state,
    audit_dynamic_state_with_external_root,
)
from verifier.dynamic_anchor import (
    build_dynamic_anchor_body,
    canonical_dynamic_anchor_body_bytes,
    load_dynamic_anchor_trust,
)
from verifier.external_root import (
    EXTERNAL_TRUST_ROOT_CONTRACT_NAME,
    build_external_trust_root_contract,
)
from verifier.path_policy import assert_candidate_write_path_allowed
from verifier.protected_manifest import (
    ASCENDANCY_DYNAMIC_STATE_PATHS,
    ASCENDANCY_PROTECTED_PATHS,
    ASCENDANCY_PROTECTED_SOURCE_ROOTS,
    build_protected_manifest,
    discover_protected_python_sources,
    file_sha256,
    verify_ascendancy_protected_source_coverage,
    verify_protected_manifest,
    verify_protected_source_coverage,
)


HASH = "a" * 64
ENVIRONMENT_ID = "dopey-options-paper-v1"


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: tuple[dict[str, object], ...]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _ledger_payload(experiment_id: str, status: str) -> dict[str, object]:
    return {
        "event_time": "2026-07-17T14:00:00Z",
        "code_version": "test",
        "data_hash": HASH,
        "experiment_id": experiment_id,
        "status": status,
        "substantive_trial": False,
    }


def _unconfigured_dynamic_anchor_trust() -> dict[str, object]:
    return {
        "schema_version": "dopey-dynamic-anchor-trust-v1",
        "environment_id": ENVIRONMENT_ID,
        "status": "not_configured",
        "algorithm": "ed25519",
        "authority_id": None,
        "authority_version": None,
        "key_id": None,
        "public_key_base64": None,
    }


def _configured_dynamic_anchor_trust(
    private_key: Ed25519PrivateKey,
) -> dict[str, object]:
    public_key_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_key_hash = hashlib.sha256(public_key_bytes).hexdigest()
    return {
        "schema_version": "dopey-dynamic-anchor-trust-v1",
        "environment_id": ENVIRONMENT_ID,
        "status": "configured",
        "algorithm": "ed25519",
        "authority_id": "independent-dynamic-anchor-authority",
        "authority_version": "anchor-v1",
        "key_id": f"ed25519-sha256-{public_key_hash}",
        "public_key_base64": base64.b64encode(public_key_bytes).decode("ascii"),
    }


def _configured_key_fields(private_key: Ed25519PrivateKey) -> dict[str, object]:
    public_key_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_key_hash = hashlib.sha256(public_key_bytes).hexdigest()
    return {
        "key_id": f"ed25519-sha256-{public_key_hash}",
        "public_key_base64": base64.b64encode(public_key_bytes).decode("ascii"),
    }


def _write_configured_repository_trust(
    root: Path,
    dynamic_anchor_private_key: Ed25519PrivateKey,
) -> dict[str, object]:
    dynamic_trust = _configured_dynamic_anchor_trust(dynamic_anchor_private_key)
    _write_json(root / "DYNAMIC_ANCHOR_TRUST.json", dynamic_trust)
    promotion_fields = _configured_key_fields(Ed25519PrivateKey.generate())
    _write_json(
        root / "PROMOTION_AUTHORITY_TRUST.json",
        {
            "schema_version": "dopey-promotion-authority-trust-v1",
            "environment_id": ENVIRONMENT_ID,
            "status": "configured",
            "algorithm": "ed25519",
            "authority_id": "independent-promotion-authority",
            "authority_version": "promotion-v1",
            **promotion_fields,
        },
    )
    evaluator_fields = _configured_key_fields(Ed25519PrivateKey.generate())
    _write_json(
        root / "SEALED_EVALUATOR_TRUST.json",
        {
            "schema_version": "dopey-sealed-evaluator-trust-v1",
            "environment_id": ENVIRONMENT_ID,
            "status": "configured",
            "algorithm": "ed25519",
            "evaluator_id": "independent-sealed-evaluator",
            "evaluator_version": "evaluator-v1",
            **evaluator_fields,
        },
    )
    recorder_fields = _configured_key_fields(Ed25519PrivateKey.generate())
    outcome_fields = _configured_key_fields(Ed25519PrivateKey.generate())
    _write_json(
        root / "FORWARD_EVIDENCE_TRUST.json",
        {
            "schema_version": "dopey-forward-evidence-trust-v1",
            "environment_id": ENVIRONMENT_ID,
            "status": "configured",
            "algorithm": "ed25519",
            "forward_recorder": {
                "signer_id": "independent-forward-recorder",
                "signer_version": "recorder-v1",
                **recorder_fields,
            },
            "outcome_source": {
                "signer_id": "independent-outcome-source",
                "signer_version": "outcome-v1",
                **outcome_fields,
            },
        },
    )
    return dynamic_trust


def _write_minimal_protected_manifest(root: Path) -> str:
    protected_control = root / "protected-control.txt"
    protected_control.write_text("protected\n", encoding="utf-8")
    manifest = build_protected_manifest(root, ("protected-control.txt",))
    _write_json(root / "PROTECTED_MANIFEST.json", manifest)
    return file_sha256(root / "PROTECTED_MANIFEST.json")


def _write_dynamic_anchor_receipt(
    path: Path,
    body: dict[str, object],
    private_key: Ed25519PrivateKey,
) -> None:
    message = canonical_dynamic_anchor_body_bytes(cast(dict[str, object], body))
    _write_json(
        path,
        {
            "body": body,
            "signature_base64": base64.b64encode(private_key.sign(message)).decode("ascii"),
        },
    )


def _initialize_dynamic_state(root: Path) -> None:
    _write_json(root / "DYNAMIC_ANCHOR_TRUST.json", _unconfigured_dynamic_anchor_trust())
    approach_records = (
        {
            "environment_id": ENVIRONMENT_ID,
            "record_type": "registry_initialization",
            "registered_families": 26,
            "status": "mechanisms_registered_no_approaches_evaluated",
        },
        *(
            {
                "family_id": f"F{index:02d}",
                "status": "not_evaluated",
            }
            for index in range(1, 27)
        ),
    )
    _write_jsonl(root / "APPROACH_REGISTRY.jsonl", approach_records)
    registry_specs = (
        ("CANDIDATE_LINEAGE.jsonl", "registered_candidates"),
        ("FAILURE_REGISTRY.jsonl", "registered_failures"),
        ("HYPOTHESIS_REGISTRY.jsonl", "registered_hypotheses"),
    )
    for file_name, count_field in registry_specs:
        _write_jsonl(
            root / file_name,
            (
                {
                    "environment_id": ENVIRONMENT_ID,
                    "record_type": "registry_initialization",
                    count_field: 0,
                    "status": "empty",
                },
            ),
        )
    append_canonical_ascendancy_record(
        root,
        "experiment",
        "experiment-genesis",
        _ledger_payload("experiment-initialization", "completed"),
    )
    append_canonical_ascendancy_record(
        root,
        "proof",
        "proof-genesis",
        _ledger_payload("proof-initialization", "completed"),
    )
    append_canonical_ascendancy_record(
        root,
        "forward",
        "forward-genesis",
        {
            **_ledger_payload("forward-evidence-initialization", "completed"),
            "record_type": "forward_evidence_initialization",
            "environment_id": ENVIRONMENT_ID,
            "status": "initialized_no_forward_evidence",
            "substantive_trial": False,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    _write_json(
        root / "HOLDOUT_BUDGET.json",
        {
            "schema_version": "dopey-sealed-budget-v1",
            "environment_id": ENVIRONMENT_ID,
            "aggregate_feedback_only": True,
            "raw_holdout_access": False,
            "maximum_submissions_per_frozen_candidate": 1,
            "maximum_total_submissions": 100,
            "allowed_aggregate_metric_ids": ["lower_bound_utility"],
            "submissions_used": 0,
            "candidate_submissions": {},
            "frozen_hash_submissions": {},
            "status": "not_configured_no_external_evaluator",
        },
    )


def test_static_manifest_covers_all_protected_sources_and_excludes_runtime_state() -> None:
    root = Path(__file__).resolve().parents[1]
    assert len(ASCENDANCY_PROTECTED_PATHS) >= 58
    assert len(ASCENDANCY_DYNAMIC_STATE_PATHS) == 11
    assert ASCENDANCY_PROTECTED_PATHS.isdisjoint(ASCENDANCY_DYNAMIC_STATE_PATHS)
    verify_ascendancy_protected_source_coverage(root)
    discovered = discover_protected_python_sources(root, ASCENDANCY_PROTECTED_SOURCE_ROOTS)
    assert discovered.issubset(ASCENDANCY_PROTECTED_PATHS)
    assert {
        "dopey/truth/causal_evaluation.py",
        "dopey/settlement/grading.py",
        "dopey/settlement/predictions.py",
        "sealed_evaluator_client/signatures.py",
        "verifier/dynamic_anchor.py",
        "verifier/external_root.py",
    }.issubset(discovered)
    assert {
        "DYNAMIC_ANCHOR_TRUST.json",
        "FORWARD_EVIDENCE_TRUST.json",
        "PROMOTION_AUTHORITY_TRUST.json",
        "data_contracts/universe_v1.json",
        "pyproject.toml",
        "SEALED_EVALUATOR_TRUST.json",
    }.issubset(
        ASCENDANCY_PROTECTED_PATHS
    )
    assert load_dynamic_anchor_trust(root / "DYNAMIC_ANCHOR_TRUST.json").status == (
        "not_configured"
    )


def test_source_coverage_rejects_an_unlisted_python_module(tmp_path: Path) -> None:
    source_root = tmp_path / "dopey" / "truth"
    source_root.mkdir(parents=True)
    (source_root / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source_root / "unlisted.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unprotected=.*unlisted.py"):
        verify_protected_source_coverage(
            tmp_path,
            frozenset({"dopey/truth/core.py"}),
            ("dopey/truth",),
        )


def test_dynamic_state_is_locally_consistent_but_not_certification_eligible(
    tmp_path: Path,
) -> None:
    _initialize_dynamic_state(tmp_path)
    first = audit_dynamic_state(tmp_path, HASH)
    assert first["external_anchor_verified"] is False
    assert first["external_anchor_required_for_certification"] is True
    assert first["certification_eligible"] is False
    assert first["external_trust_root_pinned_role_identities"] == {}
    assert first["certification_block_reason"] == (
        "operator_controlled_external_dynamic_state_anchor_missing"
    )
    assert set(first["files"]) == ASCENDANCY_DYNAMIC_STATE_PATHS
    experiment_state = first["experiment_ledger"]
    assert isinstance(experiment_state, dict)
    assert experiment_state["record_count"] == 1
    forward_state = first["forward_evidence_ledger"]
    assert isinstance(forward_state, dict)
    assert forward_state["forward_execution_observation_record_count"] == 0

    static_file = tmp_path / "constitution.md"
    static_file.write_text("paper-only\n", encoding="utf-8")
    static_manifest = build_protected_manifest(tmp_path, ("constitution.md",))
    static_manifest_path = tmp_path / "STATIC_MANIFEST.json"
    _write_json(static_manifest_path, static_manifest)
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "experiment-two",
        _ledger_payload("experiment-two", "failed"),
    )
    second = audit_dynamic_state(tmp_path, HASH)
    assert second["dynamic_state_hash"] != first["dynamic_state_hash"]
    second_experiment_state = second["experiment_ledger"]
    assert isinstance(second_experiment_state, dict)
    assert second_experiment_state["record_count"] == 2
    verify_protected_manifest(tmp_path, static_manifest_path)


def test_repository_anchor_alone_remains_ineligible_without_external_root(
    tmp_path: Path,
) -> None:
    _initialize_dynamic_state(tmp_path)
    unanchored = audit_dynamic_state(tmp_path, HASH)
    assert unanchored["dynamic_anchor_status"] == "not_configured"

    private_key = Ed25519PrivateKey.generate()
    trust = _configured_dynamic_anchor_trust(private_key)
    _write_json(tmp_path / "DYNAMIC_ANCHOR_TRUST.json", trust)
    configured_without_receipt = audit_dynamic_state(tmp_path, HASH)
    assert configured_without_receipt["dynamic_anchor_status"] == (
        "configured_receipt_missing"
    )
    assert configured_without_receipt["external_anchor_verified"] is False
    assert configured_without_receipt["certification_eligible"] is False
    body = build_dynamic_anchor_body(
        str(unanchored["dynamic_state_hash"]),
        HASH,
        str(trust["authority_id"]),
        str(trust["authority_version"]),
        str(trust["key_id"]),
        1,
        None,
        "2026-07-16T00:00:00Z",
    )
    _write_dynamic_anchor_receipt(
        tmp_path / "DYNAMIC_STATE_ANCHOR_RECEIPT.json",
        cast(dict[str, object], body),
        private_key,
    )

    anchored = audit_dynamic_state(tmp_path, HASH)
    assert anchored["dynamic_state_hash"] == unanchored["dynamic_state_hash"]
    assert anchored["dynamic_anchor_status"] == "verified_repository_only"
    assert anchored["repository_anchor_verified"] is True
    assert anchored["external_anchor_verified"] is False
    assert anchored["certification_eligible"] is False
    assert anchored["certification_block_reason"] == (
        "operator_controlled_external_trust_root_missing"
    )
    assert anchored["dynamic_anchor_id"] == body["anchor_id"]
    assert anchored["dynamic_anchor_sequence"] == 1
    assert anchored["dynamic_anchor_parent_id"] is None
    assert anchored["dynamic_anchor_protected_manifest_sha256"] == HASH
    with pytest.raises(ValueError, match="current protected-manifest hash"):
        audit_dynamic_state(tmp_path, "b" * 64)


def test_external_root_is_required_outside_repository_and_pins_all_trust(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    _initialize_dynamic_state(repository_root)
    anchor_private_key = Ed25519PrivateKey.generate()
    trust = _write_configured_repository_trust(repository_root, anchor_private_key)
    manifest_sha256 = _write_minimal_protected_manifest(repository_root)
    unanchored = audit_dynamic_state(repository_root, manifest_sha256)
    body = build_dynamic_anchor_body(
        str(unanchored["dynamic_state_hash"]),
        manifest_sha256,
        str(trust["authority_id"]),
        str(trust["authority_version"]),
        str(trust["key_id"]),
        1,
        None,
        "2026-07-16T00:00:00Z",
    )
    _write_dynamic_anchor_receipt(
        repository_root / "DYNAMIC_STATE_ANCHOR_RECEIPT.json",
        cast(dict[str, object], body),
        anchor_private_key,
    )
    repository_only = audit_dynamic_state(repository_root, manifest_sha256)
    assert repository_only["repository_anchor_verified"] is True
    assert repository_only["external_anchor_verified"] is False
    assert repository_only["certification_eligible"] is False

    contract = build_external_trust_root_contract(
        repository_root,
        "operator-controlled-deployment-root",
        "root-v1",
        str(body["anchor_id"]),
        None,
        1,
    )
    external_path = tmp_path / EXTERNAL_TRUST_ROOT_CONTRACT_NAME
    _write_json(external_path, cast(dict[str, object], contract))
    certified = audit_dynamic_state_with_external_root(
        repository_root,
        manifest_sha256,
        external_path,
    )
    assert certified["dynamic_anchor_status"] == "verified_external_root"
    assert certified["repository_anchor_verified"] is True
    assert certified["external_anchor_verified"] is True
    assert certified["external_trust_root_status"] == "verified"
    assert certified["external_trust_root_pinned_identity_count"] == 5
    assert set(certified["external_trust_root_pinned_config_sha256"]) == {
        "DYNAMIC_ANCHOR_TRUST.json",
        "FORWARD_EVIDENCE_TRUST.json",
        "PROMOTION_AUTHORITY_TRUST.json",
        "SEALED_EVALUATOR_TRUST.json",
    }
    role_identities = certified["external_trust_root_pinned_role_identities"]
    assert isinstance(role_identities, dict)
    assert set(role_identities) == {
        "dynamic_anchor_authority",
        "forward_recorder",
        "outcome_source",
        "promotion_authority",
        "sealed_evaluator",
    }
    dynamic_identity = role_identities["dynamic_anchor_authority"]
    assert isinstance(dynamic_identity, dict)
    assert dynamic_identity["identity_id"] == trust["authority_id"]
    assert dynamic_identity["identity_version"] == trust["authority_version"]
    identity_ids = {
        str(identity["identity_id"])
        for identity in role_identities.values()
        if isinstance(identity, dict)
    }
    public_key_hashes = {
        str(identity["public_key_sha256"])
        for identity in role_identities.values()
        if isinstance(identity, dict)
    }
    assert len(identity_ids) == 5
    assert len(public_key_hashes) == 5
    assert all(
        identity["key_id"] == f"ed25519-sha256-{identity['public_key_sha256']}"
        for identity in role_identities.values()
        if isinstance(identity, dict)
    )
    assert certified["certification_eligible"] is True
    assert certified["certification_block_reason"] is None

    in_repository_path = repository_root / EXTERNAL_TRUST_ROOT_CONTRACT_NAME
    _write_json(in_repository_path, cast(dict[str, object], contract))
    with pytest.raises(PermissionError, match="outside the repository"):
        audit_dynamic_state_with_external_root(
            repository_root,
            manifest_sha256,
            in_repository_path,
        )
    promotion_path = repository_root / "PROMOTION_AUTHORITY_TRUST.json"
    promotion_trust = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert isinstance(promotion_trust, dict)
    _write_json(
        promotion_path,
        {**promotion_trust, "authority_version": "promotion-v2"},
    )
    with pytest.raises(ValueError, match="does not match repository trust config"):
        audit_dynamic_state_with_external_root(
            repository_root,
            manifest_sha256,
            external_path,
        )
    _write_json(promotion_path, cast(dict[str, object], promotion_trust))
    (repository_root / "protected-control.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="protected manifest mismatch"):
        audit_dynamic_state_with_external_root(
            repository_root,
            manifest_sha256,
            external_path,
        )


def test_external_root_rejects_receipt_rollback_sequence_and_parent_drift(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    _initialize_dynamic_state(repository_root)
    anchor_private_key = Ed25519PrivateKey.generate()
    trust = _write_configured_repository_trust(repository_root, anchor_private_key)
    manifest_sha256 = _write_minimal_protected_manifest(repository_root)
    initial = audit_dynamic_state(repository_root, manifest_sha256)
    first_body = build_dynamic_anchor_body(
        str(initial["dynamic_state_hash"]),
        manifest_sha256,
        str(trust["authority_id"]),
        str(trust["authority_version"]),
        str(trust["key_id"]),
        1,
        None,
        "2026-07-16T00:00:00Z",
    )
    receipt_path = repository_root / "DYNAMIC_STATE_ANCHOR_RECEIPT.json"
    _write_dynamic_anchor_receipt(
        receipt_path,
        cast(dict[str, object], first_body),
        anchor_private_key,
    )
    first_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert isinstance(first_receipt, dict)
    second_body = build_dynamic_anchor_body(
        str(initial["dynamic_state_hash"]),
        manifest_sha256,
        str(trust["authority_id"]),
        str(trust["authority_version"]),
        str(trust["key_id"]),
        2,
        str(first_body["anchor_id"]),
        "2026-07-16T01:00:00Z",
    )
    _write_dynamic_anchor_receipt(
        receipt_path,
        cast(dict[str, object], second_body),
        anchor_private_key,
    )
    current_contract = build_external_trust_root_contract(
        repository_root,
        "operator-controlled-deployment-root",
        "root-v2",
        str(second_body["anchor_id"]),
        str(first_body["anchor_id"]),
        2,
    )
    external_path = tmp_path / EXTERNAL_TRUST_ROOT_CONTRACT_NAME
    _write_json(external_path, cast(dict[str, object], current_contract))
    current = audit_dynamic_state_with_external_root(
        repository_root,
        manifest_sha256,
        external_path,
    )
    assert current["dynamic_anchor_sequence"] == 2
    assert current["dynamic_anchor_parent_id"] == first_body["anchor_id"]
    assert current["certification_eligible"] is True

    _write_json(receipt_path, cast(dict[str, object], first_receipt))
    with pytest.raises(ValueError, match="rejects the repository anchor identity"):
        audit_dynamic_state_with_external_root(
            repository_root,
            manifest_sha256,
            external_path,
        )

    rollback_contract = build_external_trust_root_contract(
        repository_root,
        "operator-controlled-deployment-root",
        "root-rollback-test",
        str(first_body["anchor_id"]),
        None,
        2,
    )
    _write_json(external_path, cast(dict[str, object], rollback_contract))
    with pytest.raises(ValueError, match="below the external anti-rollback minimum"):
        audit_dynamic_state_with_external_root(
            repository_root,
            manifest_sha256,
            external_path,
        )

    _write_dynamic_anchor_receipt(
        receipt_path,
        cast(dict[str, object], second_body),
        anchor_private_key,
    )
    wrong_parent_contract = build_external_trust_root_contract(
        repository_root,
        "operator-controlled-deployment-root",
        "root-parent-test",
        str(second_body["anchor_id"]),
        f"dynamic-anchor-{'f' * 24}",
        2,
    )
    _write_json(external_path, cast(dict[str, object], wrong_parent_contract))
    with pytest.raises(ValueError, match="rejects the repository anchor parent"):
        audit_dynamic_state_with_external_root(
            repository_root,
            manifest_sha256,
            external_path,
        )


def test_external_root_rejects_cross_role_identity_and_key_reuse(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    _initialize_dynamic_state(repository_root)
    anchor_private_key = Ed25519PrivateKey.generate()
    dynamic_trust = _write_configured_repository_trust(
        repository_root,
        anchor_private_key,
    )
    _write_minimal_protected_manifest(repository_root)
    promotion_path = repository_root / "PROMOTION_AUTHORITY_TRUST.json"
    promotion_trust = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert isinstance(promotion_trust, dict)

    _write_json(
        promotion_path,
        {
            **promotion_trust,
            "authority_id": dynamic_trust["authority_id"],
        },
    )
    with pytest.raises(ValueError, match="identity is reused across independent roles"):
        build_external_trust_root_contract(
            repository_root,
            "operator-controlled-deployment-root",
            "root-identity-reuse-test",
            f"dynamic-anchor-{'a' * 24}",
            None,
            1,
        )

    _write_json(
        promotion_path,
        {
            **promotion_trust,
            "key_id": dynamic_trust["key_id"],
            "public_key_base64": dynamic_trust["public_key_base64"],
        },
    )
    with pytest.raises(ValueError, match="public key is reused across independent roles"):
        build_external_trust_root_contract(
            repository_root,
            "operator-controlled-deployment-root",
            "root-key-reuse-test",
            f"dynamic-anchor-{'b' * 24}",
            None,
            1,
        )


def test_dynamic_anchor_rejects_stale_tampered_and_noncanonical_receipts(
    tmp_path: Path,
) -> None:
    _initialize_dynamic_state(tmp_path)
    initial = audit_dynamic_state(tmp_path, HASH)
    private_key = Ed25519PrivateKey.generate()
    trust = _configured_dynamic_anchor_trust(private_key)
    _write_json(tmp_path / "DYNAMIC_ANCHOR_TRUST.json", trust)
    body = build_dynamic_anchor_body(
        str(initial["dynamic_state_hash"]),
        HASH,
        str(trust["authority_id"]),
        str(trust["authority_version"]),
        str(trust["key_id"]),
        1,
        None,
        "2026-07-16T00:00:00Z",
    )
    receipt_path = tmp_path / "DYNAMIC_STATE_ANCHOR_RECEIPT.json"
    _write_dynamic_anchor_receipt(
        receipt_path,
        cast(dict[str, object], body),
        private_key,
    )
    valid_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert isinstance(valid_receipt, dict)

    _write_json(receipt_path, {**valid_receipt, "unexpected": True})
    with pytest.raises(ValueError, match="exact v1 schema"):
        audit_dynamic_state(tmp_path, HASH)

    _write_json(
        receipt_path,
        {
            **valid_receipt,
            "signature_base64": base64.b64encode(b"x" * 64).decode("ascii"),
        },
    )
    with pytest.raises(ValueError, match="signature verification failed"):
        audit_dynamic_state(tmp_path, HASH)

    _write_json(receipt_path, valid_receipt)
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "experiment-after-anchor",
        _ledger_payload("experiment-after-anchor", "failed"),
    )
    with pytest.raises(ValueError, match="does not bind the current dynamic-state hash"):
        audit_dynamic_state(tmp_path, HASH)

    with pytest.raises(ValueError, match="canonical UTC ISO-8601"):
        build_dynamic_anchor_body(
            HASH,
            HASH,
            str(trust["authority_id"]),
            str(trust["authority_version"]),
            str(trust["key_id"]),
            1,
            None,
            "2026-07-15T19:00:00-05:00",
        )
    with pytest.raises(ValueError, match="greater than one requires a parent"):
        build_dynamic_anchor_body(
            HASH,
            HASH,
            str(trust["authority_id"]),
            str(trust["authority_version"]),
            str(trust["key_id"]),
            2,
            None,
            "2026-07-16T00:00:00Z",
        )
    with pytest.raises(ValueError, match="sequence one must not declare a parent"):
        build_dynamic_anchor_body(
            HASH,
            HASH,
            str(trust["authority_id"]),
            str(trust["authority_version"]),
            str(trust["key_id"]),
            1,
            f"dynamic-anchor-{'e' * 24}",
            "2026-07-16T00:00:00Z",
        )


def test_dynamic_anchor_trust_exact_schema_and_unconfigured_receipt_conflict(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "DYNAMIC_ANCHOR_TRUST.json"
    _write_json(trust_path, {**_unconfigured_dynamic_anchor_trust(), "unexpected": True})
    with pytest.raises(ValueError, match="exact v1 schema"):
        load_dynamic_anchor_trust(trust_path)

    _initialize_dynamic_state(tmp_path)
    _write_json(tmp_path / "DYNAMIC_STATE_ANCHOR_RECEIPT.json", {"body": {}, "signature_base64": ""})
    with pytest.raises(ValueError, match="trust is not configured"):
        audit_dynamic_state(tmp_path, HASH)


def test_dynamic_audit_rejects_holdout_budget_identity_map_drift(tmp_path: Path) -> None:
    _initialize_dynamic_state(tmp_path)
    budget_path = tmp_path / "HOLDOUT_BUDGET.json"
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert isinstance(budget, dict)
    budget["submissions_used"] = 1
    _write_json(budget_path, budget)
    with pytest.raises(ValueError, match="submission count differs"):
        audit_dynamic_state(tmp_path, HASH)


def test_dynamic_audit_binds_configured_budget_records_exactly(tmp_path: Path) -> None:
    _initialize_dynamic_state(tmp_path)
    budget_path = tmp_path / "HOLDOUT_BUDGET.json"
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    assert isinstance(budget, dict)
    budget["status"] = "configured_external_evaluator"
    budget["evaluator_id"] = "independent-sealed-evaluator"
    budget["evaluator_version"] = "sealed-v1"
    _write_json(budget_path, budget)
    request = reserve_sealed_submission(
        budget_path,
        "candidate-1",
        HASH,
        ("lower_bound_utility",),
        "sealed-v1",
        "2026-07-17T14:01:00Z",
    )
    valid = json.loads(budget_path.read_text(encoding="utf-8"))
    assert isinstance(valid, dict)
    state = audit_dynamic_state(tmp_path, HASH)
    budget_state = state["holdout_budget"]
    assert isinstance(budget_state, dict)
    assert budget_state["evaluator_id"] == request.evaluator_id

    malformed = copy.deepcopy(valid)
    malformed["candidate_submissions"]["candidate-1"]["unexpected"] = True
    malformed["frozen_hash_submissions"][HASH]["unexpected"] = True
    _write_json(budget_path, malformed)
    with pytest.raises(ValueError, match="submission record is malformed"):
        audit_dynamic_state(tmp_path, HASH)

    wrong_evaluator = copy.deepcopy(valid)
    wrong_evaluator["candidate_submissions"]["candidate-1"]["evaluator_version"] = "forged-v2"
    wrong_evaluator["frozen_hash_submissions"][HASH]["evaluator_version"] = "forged-v2"
    _write_json(budget_path, wrong_evaluator)
    with pytest.raises(ValueError, match="evaluator binding mismatch"):
        audit_dynamic_state(tmp_path, HASH)

    wrong_request = copy.deepcopy(valid)
    wrong_request["candidate_submissions"]["candidate-1"]["request_id"] = "wrong-prefix"
    wrong_request["frozen_hash_submissions"][HASH]["request_id"] = "wrong-prefix"
    _write_json(budget_path, wrong_request)
    with pytest.raises(ValueError, match="not one-shot"):
        audit_dynamic_state(tmp_path, HASH)


def test_dynamic_audit_rejects_nonprospective_forward_records(tmp_path: Path) -> None:
    _initialize_dynamic_state(tmp_path)
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "replay-record",
        {
            **_ledger_payload("replay-record", "completed"),
            "record_type": "historical_replay",
            "environment_id": ENVIRONMENT_ID,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    with pytest.raises(ValueError, match="record type is unsupported"):
        audit_dynamic_state(tmp_path, HASH)


def test_dynamic_audit_retains_structurally_signed_execution_observations(
    tmp_path: Path,
) -> None:
    _initialize_dynamic_state(tmp_path)
    execution_observation_id = "execution-observation-1"
    ticket_id = "paper-ticket-1"
    event_time = "2026-07-17T14:00:00Z"
    recorder_issued_at = "2026-07-17T14:00:01Z"
    fill_observation_id = "paper-fill-1"
    fill_artifact: dict[str, JsonValue] = {
        "observation_id": fill_observation_id,
        "ticket_id": ticket_id,
        "witnessed_at": event_time,
        "paper_fill_status": "filled",
        "evidence_class": "prospective_market_evidence",
        "profitability_evidence_eligible": True,
        "realized_evidence": False,
        "paper_only": True,
        "live_blocked": True,
    }
    fill_artifact_hash = canonical_hash(fill_artifact)
    recorder_receipt_body: dict[str, JsonValue] = {
        "schema_version": "dopey-forward-evidence-receipt-v1",
        "environment_id": ENVIRONMENT_ID,
        "purpose": "forward_record",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH,
        "record_id": execution_observation_id,
        "subject_artifact_hash": fill_artifact_hash,
        "issued_at": recorder_issued_at,
        "signer_id": "independent-forward-recorder",
        "signer_version": "recorder-v1",
    }
    valid_payload: dict[str, object] = {
        **_ledger_payload("execution-observation-experiment", "completed"),
        "record_type": "forward_execution_observation",
        "environment_id": ENVIRONMENT_ID,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH,
        "candidate_mode": "options_expression",
        "execution_observation_id": execution_observation_id,
        "parent_decision_id": "forward-decision-1",
        "ticket_id": ticket_id,
        "session_id": "session-1",
        "event_time": event_time,
        "recorder_issued_at": recorder_issued_at,
        "fill_observation_id": fill_observation_id,
        "fill_status": "filled",
        "fill_artifact_hash": fill_artifact_hash,
        "fill_artifact": fill_artifact,
        "evidence_kind": "prospective_paper",
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "replay": False,
        "backtest": False,
        "realized_evidence": False,
        "paper_only": True,
        "live_blocked": True,
        "recorder_receipt_body": recorder_receipt_body,
        "recorder_receipt_body_hash": canonical_hash(recorder_receipt_body),
        "recorder_signature_base64": base64.b64encode(b"s" * 64).decode("ascii"),
    }
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "execution-observation-entry-1",
        valid_payload,
    )
    state = audit_dynamic_state(tmp_path, HASH)
    forward_state = state["forward_evidence_ledger"]
    assert isinstance(forward_state, dict)
    assert forward_state["record_count"] == 2
    assert forward_state["forward_decision_count"] == 0
    assert forward_state["forward_execution_observation_record_count"] == 1
    assert forward_state["forward_settlement_count"] == 0

    invalid_receipt_body = {
        **recorder_receipt_body,
        "record_id": "execution-observation-2",
    }
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "execution-observation-entry-2",
        {
            **valid_payload,
            "execution_observation_id": "execution-observation-2",
            "fill_status": "partial",
            "recorder_receipt_body": invalid_receipt_body,
            "recorder_receipt_body_hash": canonical_hash(
                cast(dict[str, JsonValue], invalid_receipt_body)
            ),
        },
    )
    with pytest.raises(ValueError, match="authority or status is invalid"):
        audit_dynamic_state(tmp_path, HASH)


def test_candidate_write_policy_denies_every_dynamic_state_artifact(tmp_path: Path) -> None:
    (tmp_path / "candidates").mkdir()
    assert_candidate_write_path_allowed(tmp_path, tmp_path / "candidates" / "candidate.json")
    for relative_path in ASCENDANCY_DYNAMIC_STATE_PATHS:
        with pytest.raises(PermissionError, match="protected root"):
            assert_candidate_write_path_allowed(tmp_path, tmp_path / relative_path)
    for relative_path in (
        "DYNAMIC_ANCHOR_TRUST.json",
        "DYNAMIC_STATE_ANCHOR_RECEIPT.json",
        "FORWARD_EVIDENCE_TRUST.json",
        "PROMOTION_AUTHORITY_TRUST.json",
        "PROTECTED_MANIFEST.json",
        "SEALED_EVALUATOR_TRUST.json",
    ):
        with pytest.raises(PermissionError, match="protected root"):
            assert_candidate_write_path_allowed(tmp_path, tmp_path / relative_path)
    with pytest.raises(PermissionError, match="impersonates an external trust-root"):
        assert_candidate_write_path_allowed(
            tmp_path,
            tmp_path / "candidates" / EXTERNAL_TRUST_ROOT_CONTRACT_NAME,
        )


def test_audit_cli_uses_only_an_explicit_external_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = tmp_path / "repository"
    source_manifest_path = tmp_path / "source-manifest.json"
    external_root_path = tmp_path / EXTERNAL_TRUST_ROOT_CONTRACT_NAME
    local_calls: list[tuple[Path, Path]] = []
    external_calls: list[tuple[Path, Path, Path]] = []

    def local_audit(root: Path, source_manifest: Path) -> dict[str, object]:
        local_calls.append((root, source_manifest))
        return {"mode": "local_fail_closed"}

    def external_audit(
        root: Path,
        source_manifest: Path,
        external_root: Path,
    ) -> dict[str, object]:
        external_calls.append((root, source_manifest, external_root))
        return {"mode": "explicit_external_root"}

    monkeypatch.setattr(verifier_audit, "run_ascendancy_audit", local_audit)
    monkeypatch.setattr(
        verifier_audit,
        "run_ascendancy_audit_with_external_root",
        external_audit,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verifier.audit",
            "--repository-root",
            str(repository_root),
            "--source-manifest",
            str(source_manifest_path),
        ],
    )
    verifier_audit.main()
    local_result = json.loads(capsys.readouterr().out)
    assert local_result == {"mode": "local_fail_closed"}
    assert local_calls == [(repository_root, source_manifest_path)]
    assert external_calls == []

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verifier.audit",
            "--repository-root",
            str(repository_root),
            "--source-manifest",
            str(source_manifest_path),
            "--external-trust-root",
            str(external_root_path),
        ],
    )
    verifier_audit.main()
    external_result = json.loads(capsys.readouterr().out)
    assert external_result == {"mode": "explicit_external_root"}
    assert external_calls == [
        (repository_root, source_manifest_path, external_root_path)
    ]


def test_canonical_append_rejects_arbitrary_ledger_kinds(tmp_path: Path) -> None:
    assert not hasattr(ascendancy_ledger, "append_hash_chained_record")
    with pytest.raises(ValueError, match="unsupported canonical Ascendancy ledger kind"):
        append_canonical_ascendancy_record(
            tmp_path,
            cast(LedgerKind, "../outside"),
            "escape-attempt",
            _ledger_payload("escape-attempt", "completed"),
        )
