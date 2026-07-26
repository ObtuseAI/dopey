from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sealed_evaluator_client.signatures import (
    JsonValue,
    canonical_response_body_bytes,
    load_sealed_evaluator_trust,
    verify_sealed_response_signature,
)


HASH = "a" * 64
REQUEST_ID = f"sealed-request-{'1' * 24}"


def _response_body() -> dict[str, JsonValue]:
    return {
        "request_id": REQUEST_ID,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH,
        "submission_number": 1,
        "evaluator_id": "independent-sealed-evaluator",
        "evaluator_version": "sealed-v1",
        "evaluator_issued_at": "2026-07-17T03:00:00Z",
        "passed": True,
        "aggregate_feedback_only": True,
        "raw_holdout_access": False,
        "aggregate_metrics": {"lower_bound_utility": 0.125},
        "failure_codes": [],
    }


def _configured_trust(private_key: Ed25519PrivateKey) -> dict[str, object]:
    public_key_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_key_hash = hashlib.sha256(public_key_bytes).hexdigest()
    return {
        "schema_version": "dopey-sealed-evaluator-trust-v1",
        "environment_id": "dopey-options-paper-v1",
        "status": "configured",
        "algorithm": "ed25519",
        "evaluator_id": "independent-sealed-evaluator",
        "evaluator_version": "sealed-v1",
        "key_id": f"ed25519-sha256-{public_key_hash}",
        "public_key_base64": base64.b64encode(public_key_bytes).decode("ascii"),
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_ed25519_verification_uses_pinned_key_and_canonical_response_bytes(
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trust_path = tmp_path / "trust.json"
    _write_json(trust_path, _configured_trust(private_key))
    response_body = _response_body()
    message = canonical_response_body_bytes(response_body)
    signature = private_key.sign(message)
    result = verify_sealed_response_signature(
        trust_path,
        response_body,
        base64.b64encode(signature).decode("ascii"),
    )

    assert result.evaluator_id == "independent-sealed-evaluator"
    assert result.evaluator_version == "sealed-v1"
    assert result.signature_algorithm == "ed25519"
    assert result.response_body_hash == hashlib.sha256(message).hexdigest()
    assert result.signature_hash == hashlib.sha256(signature).hexdigest()
    assert not hasattr(result, "verified")


def test_ed25519_verification_rejects_tampering_and_wrong_pinned_key(tmp_path: Path) -> None:
    signer = Ed25519PrivateKey.generate()
    response_body = _response_body()
    signature_base64 = base64.b64encode(
        signer.sign(canonical_response_body_bytes(response_body))
    ).decode("ascii")
    trust_path = tmp_path / "trust.json"
    _write_json(trust_path, _configured_trust(signer))

    tampered = {
        **response_body,
        "aggregate_metrics": {"lower_bound_utility": 0.126},
    }
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_sealed_response_signature(trust_path, tampered, signature_base64)

    tampered_verdict = {
        **response_body,
        "passed": False,
        "aggregate_metrics": {},
        "failure_codes": ["candidate_failed_metric_floor"],
    }
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_sealed_response_signature(trust_path, tampered_verdict, signature_base64)

    tampered_issued_at = {
        **response_body,
        "evaluator_issued_at": "2026-07-17T03:00:01Z",
    }
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_sealed_response_signature(trust_path, tampered_issued_at, signature_base64)

    _write_json(trust_path, _configured_trust(Ed25519PrivateKey.generate()))
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_sealed_response_signature(trust_path, response_body, signature_base64)


def test_unconfigured_trust_is_valid_state_but_cannot_verify(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    trust_path = root / "SEALED_EVALUATOR_TRUST.json"
    trust = load_sealed_evaluator_trust(trust_path)
    assert trust.status == "not_configured"
    assert trust.public_key_bytes is None

    signature = base64.b64encode(b"x" * 64).decode("ascii")
    with pytest.raises(PermissionError, match="not configured"):
        verify_sealed_response_signature(trust_path, _response_body(), signature)


def test_exact_trust_and_signed_body_schemas_reject_self_asserted_verification(
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    trust = _configured_trust(private_key)
    trust_path = tmp_path / "trust.json"
    _write_json(trust_path, {**trust, "unexpected": True})
    with pytest.raises(ValueError, match="exact v1 schema"):
        load_sealed_evaluator_trust(trust_path)

    _write_json(trust_path, trust)
    response_body = {**_response_body(), "verified": True}
    with pytest.raises(ValueError, match="exact aggregate v1 schema"):
        canonical_response_body_bytes(response_body)

    missing_verdict = _response_body()
    missing_verdict.pop("passed")
    with pytest.raises(ValueError, match="exact aggregate v1 schema"):
        canonical_response_body_bytes(missing_verdict)

    missing_issued_at = _response_body()
    missing_issued_at.pop("evaluator_issued_at")
    with pytest.raises(ValueError, match="exact aggregate v1 schema"):
        canonical_response_body_bytes(missing_issued_at)


def test_signed_response_requires_canonical_issued_time_and_consistent_verdict() -> None:
    with pytest.raises(ValueError, match="canonical UTC ISO-8601"):
        canonical_response_body_bytes(
            {**_response_body(), "evaluator_issued_at": "2026-07-16T22:00:00-05:00"}
        )
    with pytest.raises(ValueError, match="passed verdict must be boolean"):
        canonical_response_body_bytes({**_response_body(), "passed": 1})
    with pytest.raises(ValueError, match="requires metrics and no failure codes"):
        canonical_response_body_bytes(
            {
                **_response_body(),
                "failure_codes": ["candidate_failed_metric_floor"],
            }
        )

    failed_response = {
        **_response_body(),
        "passed": False,
        "aggregate_metrics": {},
        "failure_codes": ["candidate_failed_metric_floor"],
    }
    canonical_response_body_bytes(failed_response)
    with pytest.raises(ValueError, match="requires failure codes and no metrics"):
        canonical_response_body_bytes(
            {**failed_response, "aggregate_metrics": {"lower_bound_utility": 0.125}}
        )
