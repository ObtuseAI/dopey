from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from dopey.ascendancy.forward_signatures import (
    canonical_forward_receipt_bytes,
    load_forward_evidence_trust,
    verify_forward_evidence_signature,
)
from dopey.ascendancy.identity import JsonValue


HASH_A = "a" * 64
HASH_B = "b" * 64


def _role(
    private_key: Ed25519PrivateKey,
    signer_id: str,
    signer_version: str,
) -> dict[str, object]:
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_key_hash = hashlib.sha256(public_key).hexdigest()
    return {
        "signer_id": signer_id,
        "signer_version": signer_version,
        "key_id": f"ed25519-sha256-{public_key_hash}",
        "public_key_base64": base64.b64encode(public_key).decode("ascii"),
    }


def _configured_trust(
    recorder_key: Ed25519PrivateKey,
    outcome_key: Ed25519PrivateKey,
) -> dict[str, object]:
    return {
        "schema_version": "dopey-forward-evidence-trust-v1",
        "environment_id": "dopey-options-paper-v1",
        "status": "configured",
        "algorithm": "ed25519",
        "forward_recorder": _role(recorder_key, "independent-forward-recorder", "recorder-v1"),
        "outcome_source": _role(outcome_key, "independent-outcome-source", "source-v1"),
    }


def _receipt(purpose: str) -> dict[str, JsonValue]:
    signer_id = (
        "independent-forward-recorder"
        if purpose == "forward_record"
        else "independent-outcome-source"
    )
    signer_version = "recorder-v1" if purpose == "forward_record" else "source-v1"
    return {
        "schema_version": "dopey-forward-evidence-receipt-v1",
        "environment_id": "dopey-options-paper-v1",
        "purpose": purpose,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "record_id": "forward-1" if purpose == "forward_record" else "evidence-1",
        "subject_artifact_hash": HASH_B,
        "issued_at": "2026-07-17T03:00:00Z",
        "signer_id": signer_id,
        "signer_version": signer_version,
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sign(private_key: Ed25519PrivateKey, body: dict[str, JsonValue]) -> str:
    signature = private_key.sign(canonical_forward_receipt_bytes(body))
    return base64.b64encode(signature).decode("ascii")


def test_independent_pinned_roles_verify_only_their_exact_receipts(tmp_path: Path) -> None:
    recorder_key = Ed25519PrivateKey.generate()
    outcome_key = Ed25519PrivateKey.generate()
    trust_path = tmp_path / "trust.json"
    _write_json(trust_path, _configured_trust(recorder_key, outcome_key))

    recorder_receipt = _receipt("forward_record")
    recorder_result = verify_forward_evidence_signature(
        trust_path,
        recorder_receipt,
        _sign(recorder_key, recorder_receipt),
    )
    assert recorder_result.purpose == "forward_record"
    assert recorder_result.signer_id == "independent-forward-recorder"
    assert recorder_result.subject_artifact_hash == HASH_B

    outcome_receipt = _receipt("outcome_source")
    outcome_result = verify_forward_evidence_signature(
        trust_path,
        outcome_receipt,
        _sign(outcome_key, outcome_receipt),
    )
    assert outcome_result.purpose == "outcome_source"
    assert outcome_result.signer_id == "independent-outcome-source"
    assert recorder_result.key_id != outcome_result.key_id


def test_receipt_tampering_and_cross_role_signatures_fail_closed(tmp_path: Path) -> None:
    recorder_key = Ed25519PrivateKey.generate()
    outcome_key = Ed25519PrivateKey.generate()
    trust_path = tmp_path / "trust.json"
    _write_json(trust_path, _configured_trust(recorder_key, outcome_key))

    recorder_receipt = _receipt("forward_record")
    recorder_signature = _sign(recorder_key, recorder_receipt)
    tampered_subject = {**recorder_receipt, "subject_artifact_hash": HASH_A}
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_forward_evidence_signature(
            trust_path,
            tampered_subject,
            recorder_signature,
        )

    outcome_receipt = _receipt("outcome_source")
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_forward_evidence_signature(
            trust_path,
            outcome_receipt,
            _sign(recorder_key, outcome_receipt),
        )

    wrong_identity = {**outcome_receipt, "signer_id": "independent-forward-recorder"}
    with pytest.raises(ValueError, match="pinned trust role"):
        verify_forward_evidence_signature(
            trust_path,
            wrong_identity,
            _sign(outcome_key, wrong_identity),
        )


def test_unconfigured_default_is_valid_but_cannot_verify() -> None:
    root = Path(__file__).resolve().parents[1]
    trust_path = root / "FORWARD_EVIDENCE_TRUST.json"
    trust = load_forward_evidence_trust(trust_path)
    assert trust.status == "not_configured"
    assert trust.forward_recorder.public_key_bytes is None
    assert trust.outcome_source.public_key_bytes is None

    receipt = _receipt("forward_record")
    placeholder_signature = base64.b64encode(b"x" * 64).decode("ascii")
    with pytest.raises(PermissionError, match="not configured"):
        verify_forward_evidence_signature(
            trust_path,
            receipt,
            placeholder_signature,
        )


def test_trust_schema_and_role_independence_are_exact(tmp_path: Path) -> None:
    recorder_key = Ed25519PrivateKey.generate()
    outcome_key = Ed25519PrivateKey.generate()
    trust = _configured_trust(recorder_key, outcome_key)
    trust_path = tmp_path / "trust.json"

    _write_json(trust_path, {**trust, "unexpected": True})
    with pytest.raises(ValueError, match="exact v1 schema"):
        load_forward_evidence_trust(trust_path)

    wrong_key_identity = _configured_trust(recorder_key, outcome_key)
    recorder_role = dict(wrong_key_identity["forward_recorder"])
    recorder_role["key_id"] = f"ed25519-sha256-{'0' * 64}"
    wrong_key_identity["forward_recorder"] = recorder_role
    _write_json(trust_path, wrong_key_identity)
    with pytest.raises(ValueError, match="not bound to its pinned public key"):
        load_forward_evidence_trust(trust_path)

    same_identity = _configured_trust(recorder_key, outcome_key)
    outcome_role = dict(same_identity["outcome_source"])
    outcome_role["signer_id"] = "independent-forward-recorder"
    same_identity["outcome_source"] = outcome_role
    _write_json(trust_path, same_identity)
    with pytest.raises(ValueError, match="signer identities must be independent"):
        load_forward_evidence_trust(trust_path)

    shared_key = _configured_trust(recorder_key, recorder_key)
    _write_json(trust_path, shared_key)
    with pytest.raises(ValueError, match="public keys must be independent"):
        load_forward_evidence_trust(trust_path)

    configured_with_null_role = _configured_trust(recorder_key, outcome_key)
    configured_with_null_role["forward_recorder"] = {
        "signer_id": None,
        "signer_version": None,
        "key_id": None,
        "public_key_base64": None,
    }
    _write_json(trust_path, configured_with_null_role)
    with pytest.raises(ValueError, match="non-empty string"):
        load_forward_evidence_trust(trust_path)


def test_receipt_schema_hashes_and_timestamp_are_exact() -> None:
    receipt = _receipt("forward_record")
    canonical_forward_receipt_bytes(receipt)

    with pytest.raises(ValueError, match="exact v1 schema"):
        canonical_forward_receipt_bytes({**receipt, "verified": True})
    missing_record = dict(receipt)
    missing_record.pop("record_id")
    with pytest.raises(ValueError, match="exact v1 schema"):
        canonical_forward_receipt_bytes(missing_record)
    with pytest.raises(ValueError, match="canonical UTC ISO-8601"):
        canonical_forward_receipt_bytes(
            {**receipt, "issued_at": "2026-07-16T22:00:00-05:00"}
        )
    with pytest.raises(ValueError, match="SHA-256"):
        canonical_forward_receipt_bytes(
            {**receipt, "subject_artifact_hash": "not-a-hash"}
        )
    with pytest.raises(ValueError, match="purpose is unsupported"):
        canonical_forward_receipt_bytes({**receipt, "purpose": "self_asserted"})
