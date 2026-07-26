from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dopey.ascendancy import promotion
from dopey.ascendancy.identity import canonical_hash
from dopey.ascendancy.ledger import append_canonical_ascendancy_record
from dopey.ascendancy.promotion import (
    PromotionEvidence,
    PromotionPolicy,
    canonical_candidate_registration,
    derive_trial_accounting,
    v1_promotion_policy,
)
from dopey.ascendancy.router import RouteCandidate, _route_validated_candidate_for_root
from dopey.ascendancy.retirement import validate_canonical_retirement_artifact
from sealed_evaluator_client.aggregate_contract import (
    SealedAggregateResponse,
    validate_aggregate_response,
)
from sealed_evaluator_client.budget import reserve_sealed_submission
from sealed_evaluator_client.signatures import canonical_response_body_bytes
from dopey.ascendancy.forward_signatures import canonical_forward_receipt_bytes


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64


def _pinned_role_identities() -> dict[str, object]:
    roles = (
        "dynamic_anchor_authority",
        "promotion_authority",
        "sealed_evaluator",
        "forward_recorder",
        "outcome_source",
    )
    return {
        role: {
            "identity_id": f"independent-{role}",
            "identity_version": "v1",
            "key_id": f"ed25519-sha256-{HASH_A}",
            "public_key_sha256": HASH_A,
        }
        for role in roles
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _configured_budget() -> dict[str, object]:
    return {
        "schema_version": "dopey-sealed-budget-v1",
        "environment_id": "dopey-options-paper-v1",
        "aggregate_feedback_only": True,
        "raw_holdout_access": False,
        "maximum_submissions_per_frozen_candidate": 1,
        "maximum_total_submissions": 2,
        "allowed_aggregate_metric_ids": ["lower_bound_utility"],
        "evaluator_id": "independent-sealed-evaluator",
        "evaluator_version": "sealed-v1",
        "submissions_used": 0,
        "candidate_submissions": {},
        "frozen_hash_submissions": {},
        "status": "configured_external_evaluator",
    }


def _configure_sealed_trust(repository_root: Path) -> Ed25519PrivateKey:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_key_hash = hashlib.sha256(public_key).hexdigest()
    _write_json(
        repository_root / "SEALED_EVALUATOR_TRUST.json",
        {
            "schema_version": "dopey-sealed-evaluator-trust-v1",
            "environment_id": "dopey-options-paper-v1",
            "status": "configured",
            "algorithm": "ed25519",
            "evaluator_id": "independent-sealed-evaluator",
            "evaluator_version": "sealed-v1",
            "key_id": f"ed25519-sha256-{public_key_hash}",
            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
        },
    )
    return private_key


def _configure_forward_trust(
    repository_root: Path,
) -> tuple[Ed25519PrivateKey, Ed25519PrivateKey]:
    recorder_key = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))
    outcome_key = Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97)))

    def role(private_key: Ed25519PrivateKey, signer_id: str) -> dict[str, object]:
        public_key = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return {
            "signer_id": signer_id,
            "signer_version": "forward-v1",
            "key_id": f"ed25519-sha256-{hashlib.sha256(public_key).hexdigest()}",
            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
        }

    _write_json(
        repository_root / "FORWARD_EVIDENCE_TRUST.json",
        {
            "schema_version": "dopey-forward-evidence-trust-v1",
            "environment_id": "dopey-options-paper-v1",
            "status": "configured",
            "algorithm": "ed25519",
            "forward_recorder": role(recorder_key, "independent-forward-recorder"),
            "outcome_source": role(outcome_key, "independent-outcome-source"),
        },
    )
    return recorder_key, outcome_key


def _configure_promotion_authority(repository_root: Path) -> Ed25519PrivateKey:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(97, 129)))
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    _write_json(
        repository_root / "PROMOTION_AUTHORITY_TRUST.json",
        {
            "schema_version": "dopey-promotion-authority-trust-v1",
            "environment_id": "dopey-options-paper-v1",
            "status": "configured",
            "algorithm": "ed25519",
            "authority_id": "independent-promotion-authority",
            "authority_version": "authority-v1",
            "key_id": f"ed25519-sha256-{hashlib.sha256(public_key).hexdigest()}",
            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
        },
    )
    return private_key


def _signed_stage_receipt(
    private_key: Ed25519PrivateKey,
    evidence_id: str,
    proof_type: str,
    review_domain: str | None,
    candidate_id: str,
    candidate_author_id: str,
    frozen_specification_hash: str,
    experiment_id: str,
    evaluator_id: str,
    source_artifact_hash: str,
    issued_at: str,
) -> tuple[dict[str, object], str, str]:
    body = {
        "schema_version": "dopey-signed-stage-receipt-v1",
        "environment_id": "dopey-options-paper-v1",
        "authority_id": "independent-promotion-authority",
        "authority_version": "authority-v1",
        "evidence_id": evidence_id,
        "proof_type": proof_type,
        "review_domain": review_domain,
        "candidate_id": candidate_id,
        "candidate_author_id": candidate_author_id,
        "frozen_specification_hash": frozen_specification_hash,
        "experiment_id": experiment_id,
        "evaluator_id": evaluator_id,
        "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
        "passed": True,
        "source_artifact_hash": source_artifact_hash,
        "issued_at": issued_at,
        "paper_only": True,
        "live_blocked": True,
    }
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        body,
        canonical_hash(body),
        base64.b64encode(private_key.sign(encoded)).decode("ascii"),
    )


def _forward_receipt(
    private_key: Ed25519PrivateKey,
    purpose: str,
    record_id: str,
    subject_artifact_hash: str,
    issued_at: str,
    signer_id: str,
) -> tuple[dict[str, object], str, str]:
    body = {
        "schema_version": "dopey-forward-evidence-receipt-v1",
        "environment_id": "dopey-options-paper-v1",
        "purpose": purpose,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "record_id": record_id,
        "subject_artifact_hash": subject_artifact_hash,
        "issued_at": issued_at,
        "signer_id": signer_id,
        "signer_version": "forward-v1",
    }
    return (
        body,
        canonical_hash(body),
        base64.b64encode(private_key.sign(canonical_forward_receipt_bytes(body))).decode("ascii"),
    )


def _authenticate_forward_payload(
    repository_root: Path,
    payload: dict[str, object],
) -> dict[str, object]:
    recorder_key, outcome_key = _configure_forward_trust(repository_root)
    authenticated = dict(payload)
    if payload["record_type"] == "forward_decision":
        record_id = str(payload["forward_id"])
        subject_hash = str(payload["decision_artifact_hash"])
    elif payload["record_type"] == "forward_execution_observation":
        record_id = str(payload["execution_observation_id"])
        subject_hash = str(payload["fill_artifact_hash"])
    else:
        record_id = str(payload["settlement_id"])
        subject_hash = str(payload["settlement_artifact_hash"])
    recorder_body, recorder_hash, recorder_signature = _forward_receipt(
        recorder_key,
        "forward_record",
        record_id,
        subject_hash,
        str(payload["recorder_issued_at"]),
        "independent-forward-recorder",
    )
    authenticated.update(
        {
            "recorder_receipt_body": recorder_body,
            "recorder_receipt_body_hash": recorder_hash,
            "recorder_signature_base64": recorder_signature,
        }
    )
    if payload["record_type"] == "forward_settlement":
        source = payload["source_evidence_artifact"]
        assert isinstance(source, dict)
        outcome_body, outcome_hash, outcome_signature = _forward_receipt(
            outcome_key,
            "outcome_source",
            str(payload["evidence_id"]),
            str(payload["source_evidence_hash"]),
            str(payload["outcome_source_issued_at"]),
            "independent-outcome-source",
        )
        authenticated.update(
            {
                "outcome_receipt_body": outcome_body,
                "outcome_receipt_body_hash": outcome_hash,
                "outcome_signature_base64": outcome_signature,
            }
        )
    return authenticated


def _promotion_evidence() -> PromotionEvidence:
    return PromotionEvidence(
        "candidate-1",
        "candidate-author",
        "L3",
        "L4",
        "2026-07-17T01:00:00Z",
        HASH_A,
        "2026-07-17T08:00:00Z",
    )


def _one_pair_policy() -> PromotionPolicy:
    frozen = v1_promotion_policy()
    return PromotionPolicy(
        frozen.required_red_teams,
        frozen.required_negative_controls,
        frozen.maximum_holdout_submissions,
        1,
        1,
        1,
        0,
        0.0,
        frozen.minimum_abstention_active_policy_lower_bound_utility,
        0.25,
        0.02,
    )


def _decision_payload(
    index: int,
    opportunity_id: str,
    ticket_id: str | None,
    abstention_id: str | None,
    action_artifact: dict[str, object] | None,
) -> dict[str, object]:
    event_time = f"2026-07-17T02:0{index}:00Z"
    recorder_issued_at = f"2026-07-17T02:0{index}:10Z"
    prediction_artifact = {
        "artifact_type": "forward_prediction",
        "prediction_id": f"prediction-{index}",
        "opportunity_id": opportunity_id,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "abstention_policy",
        "success_definition": promotion.FORWARD_SUCCESS_DEFINITION,
        "prediction_time": f"2026-07-17T02:0{index - 1}:00Z",
        "predicted_success_probability": 0.8,
        "source_data_hash": HASH_A,
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "prospective_evidence_hash": HASH_B,
        "paper_only": True,
        "live_blocked": True,
    }
    prediction_artifact_hash = canonical_hash(prediction_artifact)
    market_context_hash = (
        action_artifact.get("market_context_hash")
        if action_artifact is not None
        else HASH_D
    )
    membership_attestation_hash = (
        json.loads(str(action_artifact["market_context_snapshot"]))[
            "membership_attestation_hash"
        ]
        if action_artifact is not None
        else HASH_E
    )
    decision_artifact = {
        "artifact_type": "forward_decision",
        "forward_id": f"forward-{index}",
        "prediction_id": f"prediction-{index}",
        "opportunity_id": opportunity_id,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "abstention_policy",
        "candidate_genome_hash": HASH_C,
        "prediction_artifact_hash": prediction_artifact_hash,
        "input_validation_status": "independently_validated_point_in_time_inputs",
        "membership_validation_status": (
            "independently_validated_point_in_time_membership"
        ),
        "prospective_evidence_hash": (
            action_artifact.get("prospective_evidence_hash")
            if action_artifact is not None
            else HASH_B
        ),
        "decision_time": event_time,
        "recorder_issued_at": recorder_issued_at,
        "ticket_id": ticket_id,
        "abstention_id": abstention_id,
        "market_context_hash": market_context_hash,
        "membership_attestation_hash": membership_attestation_hash,
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "paper_only": True,
        "live_blocked": True,
    }
    action_artifact_hash: str | None = None
    if action_artifact is not None:
        action_artifact_hash = canonical_hash(action_artifact)
        decision_artifact["action_type"] = (
            "paper_execution_ticket" if ticket_id is not None else "abstention_record"
        )
        decision_artifact["action_artifact"] = action_artifact
        decision_artifact["action_artifact_hash"] = action_artifact_hash
    payload: dict[str, object] = {
        "event_time": event_time,
        "recorder_issued_at": recorder_issued_at,
        "code_version": "test",
        "data_hash": HASH_A,
        "experiment_id": f"forward-decision-experiment-{index}",
        "record_type": "forward_decision",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "abstention_policy",
        "candidate_genome_hash": HASH_C,
        "environment_id": "dopey-options-paper-v1",
        "evidence_kind": "prospective_paper",
        "forward_id": f"forward-{index}",
        "prediction_id": f"prediction-{index}",
        "opportunity_id": opportunity_id,
        "session_id": "session-1",
        "ticket_id": ticket_id,
        "abstention_id": abstention_id,
        "prediction_artifact": prediction_artifact,
        "prediction_artifact_hash": prediction_artifact_hash,
        "decision_artifact": decision_artifact,
        "decision_artifact_hash": canonical_hash(decision_artifact),
        "paper_only": True,
        "live_blocked": True,
        "replay": False,
        "backtest": False,
        "realized_evidence": False,
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "market_context_hash": market_context_hash,
        "membership_attestation_hash": membership_attestation_hash,
        "prospective_evidence_hash": HASH_B,
    }
    if action_artifact_hash is not None:
        payload["action_artifact_hash"] = action_artifact_hash
    return payload


def _abstention_action(
    opportunity_id: str,
    candidate_id: str,
    decision_timestamp: str,
) -> dict[str, object]:
    market_context = {
        "membership_mode": "independent_point_in_time",
        "membership_attestation_hash": HASH_E,
        "synthetic": False,
        "content_hash": HASH_D,
    }
    market_context_snapshot = json.dumps(
        market_context,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    market_context_hash = canonical_hash(market_context)
    prospective_evidence = {
        "market_context_hash": HASH_D,
        "complete_cost_model_artifact_hash": HASH_B,
        "synthetic": False,
        "content_hash": HASH_A,
    }
    prospective_evidence_snapshot = json.dumps(
        prospective_evidence,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    prospective_evidence_hash = canonical_hash(prospective_evidence)
    body: dict[str, object] = {
        "opportunity_id": opportunity_id,
        "candidate_id": candidate_id,
        "candidate_mode": "abstention_policy",
        "candidate_genome_hash": HASH_C,
        "decision_timestamp": decision_timestamp,
        "reason_codes": ["evidence_insufficient"],
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "market_context_snapshot": market_context_snapshot,
        "market_context_hash": market_context_hash,
        "prospective_evidence_snapshot": prospective_evidence_snapshot,
        "prospective_evidence_hash": prospective_evidence_hash,
        "paper_only": True,
        "live_blocked": True,
    }
    return {
        "abstention_id": f"abstain-{canonical_hash(body)[:24]}",
        **body,
    }


def _parse_promotion_abstention(value: object) -> SimpleNamespace:
    if not isinstance(value, dict):
        raise ValueError("promotion abstention fixture must be a mapping")
    expected_fields = {
        "abstention_id",
        "opportunity_id",
        "candidate_id",
        "candidate_mode",
        "candidate_genome_hash",
        "decision_timestamp",
        "reason_codes",
        "evidence_class",
        "opportunity_synthetic",
        "profitability_evidence_eligible",
        "market_context_snapshot",
        "market_context_hash",
        "prospective_evidence_snapshot",
        "prospective_evidence_hash",
        "paper_only",
        "live_blocked",
    }
    if set(value) != expected_fields:
        raise ValueError("promotion abstention fixture schema is invalid")
    body = {key: item for key, item in value.items() if key != "abstention_id"}
    if value["abstention_id"] != f"abstain-{canonical_hash(body)[:24]}":
        raise ValueError("promotion abstention fixture identity is invalid")
    if value["candidate_mode"] != "abstention_policy":
        raise ValueError("promotion abstention fixture candidate mode is invalid")
    return SimpleNamespace(**value)


@pytest.fixture(autouse=True)
def _isolate_promotion_action_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promotion,
        "abstention_record_from_mapping",
        _parse_promotion_abstention,
    )


def _valid_abstention_decision(
    index: int,
    opportunity_id: str,
) -> dict[str, object]:
    decision_timestamp = f"2026-07-17T02:0{index}:00Z"
    action_artifact = _abstention_action(
        opportunity_id,
        "candidate-1",
        decision_timestamp,
    )
    abstention_id = action_artifact["abstention_id"]
    assert isinstance(abstention_id, str)
    return _decision_payload(
        index,
        opportunity_id,
        None,
        abstention_id,
        action_artifact,
    )


def _valid_options_decision() -> tuple[dict[str, object], dict[str, object]]:
    action = _abstention_action(
        "opportunity-1",
        "candidate-1",
        "2026-07-17T02:01:00Z",
    )
    action.pop("abstention_id")
    action["ticket_id"] = "paper-ticket-1"
    action["candidate_mode"] = "options_expression"
    payload = _decision_payload(
        1,
        "opportunity-1",
        "paper-ticket-1",
        None,
        action,
    )
    prediction_artifact = dict(payload["prediction_artifact"])
    prediction_artifact["candidate_mode"] = "options_expression"
    prediction_hash = canonical_hash(prediction_artifact)
    decision_artifact = dict(payload["decision_artifact"])
    decision_artifact["candidate_mode"] = "options_expression"
    decision_artifact["prediction_artifact_hash"] = prediction_hash
    payload.update(
        {
            "candidate_mode": "options_expression",
            "prediction_artifact": prediction_artifact,
            "prediction_artifact_hash": prediction_hash,
            "decision_artifact": decision_artifact,
            "decision_artifact_hash": canonical_hash(decision_artifact),
        }
    )
    return payload, action


def _execution_observation_payload() -> dict[str, object]:
    fill_artifact = {"fixture": "mechanically-validated-fill"}
    return {
        "event_time": "2026-07-17T02:02:00Z",
        "recorder_issued_at": "2026-07-17T02:02:10Z",
        "code_version": "test",
        "data_hash": HASH_A,
        "experiment_id": "forward-fill-experiment-1",
        "record_type": "forward_execution_observation",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "options_expression",
        "environment_id": "dopey-options-paper-v1",
        "evidence_kind": "prospective_paper",
        "execution_observation_id": "execution-observation-1",
        "parent_decision_id": "forward-1",
        "ticket_id": "paper-ticket-1",
        "session_id": "session-1",
        "fill_observation_id": "paper-fill-1",
        "fill_status": "filled",
        "fill_artifact": fill_artifact,
        "fill_artifact_hash": canonical_hash(fill_artifact),
        "paper_only": True,
        "live_blocked": True,
        "replay": False,
        "backtest": False,
        "realized_evidence": False,
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
    }


def _settlement_payload(
    prediction_id: str,
    maturity_time: str,
    event_time: str,
    outcome_label: str,
    outcome_value: float,
) -> dict[str, object]:
    recorder_issued_at = f"{event_time[:-1]}.200000Z"
    outcome_source_issued_at = f"{event_time[:-1]}.100000Z"
    baseline_net_utilities = {
        "no_trade": 0.0,
        "always_express": -0.001,
        "random_abstention": -0.001,
    }
    baseline_artifact_hashes = {
        "no_trade": HASH_C,
        "always_express": HASH_D,
        "random_abstention": HASH_E,
    }
    outcome_fields: dict[str, object] = {
        "outcome_label": outcome_label,
        "outcome_unit": promotion.FORWARD_OUTCOME_UNIT,
        "success_definition": promotion.FORWARD_SUCCESS_DEFINITION,
        "candidate_net_utility": outcome_value,
        "baseline_net_utilities": baseline_net_utilities,
        "complete_cost_stack_artifact_hash": HASH_B,
        "baseline_artifact_hashes": baseline_artifact_hashes,
        "execution_observation_id": None,
        "fill_status": None,
        "missed_fill_utility_policy": None,
    }
    source_evidence_artifact = {
        "artifact_type": "forward_outcome_evidence",
        "evidence_id": "settlement-evidence-1",
        "outcome_id": "outcome-1",
        "opportunity_id": "opportunity-1",
        "prediction_id": prediction_id,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "abstention_policy",
        **outcome_fields,
        "outcome_source_issued_at": outcome_source_issued_at,
        "observed_at": maturity_time,
        "data_hash": HASH_A,
        "outcome_derivation_id": "signed-close-to-close-return-v1",
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "paper_only": True,
        "live_blocked": True,
    }
    source_evidence_hash = canonical_hash(source_evidence_artifact)
    settlement_artifact = {
        "artifact_type": "forward_settlement",
        "settlement_id": "settlement-1",
        "parent_decision_id": "forward-1",
        "prediction_id": prediction_id,
        "opportunity_id": "opportunity-1",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "abstention_policy",
        "maturity_time": maturity_time,
        "settlement_time": event_time,
        "recorder_issued_at": recorder_issued_at,
        "outcome_source_issued_at": outcome_source_issued_at,
        "outcome_id": "outcome-1",
        **outcome_fields,
        "grade": "settled_forward_outcome",
        "evidence_id": "settlement-evidence-1",
        "source_evidence_hash": source_evidence_hash,
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
        "paper_only": True,
        "live_blocked": True,
    }
    return {
        "event_time": event_time,
        "recorder_issued_at": recorder_issued_at,
        "outcome_source_issued_at": outcome_source_issued_at,
        "code_version": "test",
        "data_hash": HASH_A,
        "experiment_id": "forward-settlement-experiment-1",
        "record_type": "forward_settlement",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "candidate_mode": "abstention_policy",
        "environment_id": "dopey-options-paper-v1",
        "evidence_kind": "prospective_paper",
        "settlement_id": "settlement-1",
        "parent_decision_id": "forward-1",
        "prediction_id": prediction_id,
        "opportunity_id": "opportunity-1",
        "session_id": "session-1",
        "maturity_time": maturity_time,
        "outcome_id": "outcome-1",
        **outcome_fields,
        "grade": "settled_forward_outcome",
        "evidence_id": "settlement-evidence-1",
        "settlement_artifact": settlement_artifact,
        "settlement_artifact_hash": canonical_hash(settlement_artifact),
        "source_evidence_artifact": source_evidence_artifact,
        "source_evidence_hash": source_evidence_hash,
        "paper_only": True,
        "live_blocked": True,
        "replay": False,
        "backtest": False,
        "realized_evidence": False,
        "evidence_class": "prospective_market_evidence",
        "opportunity_synthetic": False,
        "profitability_evidence_eligible": True,
    }


def test_trial_accounting_rejects_duplicate_substantive_experiment_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "EXPERIMENT_REGISTRY.jsonl"
    common = {
        "event_time": "2026-07-17T02:01:00Z",
        "code_version": "test",
        "data_hash": HASH_A,
        "experiment_id": "experiment-duplicate",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "result_artifact_hash": HASH_B,
        "substantive_trial": True,
        "status": "completed",
    }
    append_canonical_ascendancy_record(tmp_path, "experiment", "record-1", common)
    append_canonical_ascendancy_record(tmp_path, "experiment", "record-2", common)

    with pytest.raises(ValueError, match="duplicate substantive experiment_id"):
        derive_trial_accounting(path, "candidate-1", HASH_A, "2026-07-17T08:00:00Z")


def test_trial_accounting_binds_frozen_hash_and_completed_result_artifact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "EXPERIMENT_REGISTRY.jsonl"
    wrong_hash_trial = {
        "event_time": "2026-07-17T02:01:00Z",
        "code_version": "test",
        "data_hash": HASH_A,
        "experiment_id": "experiment-other-version",
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_B,
        "result_artifact_hash": HASH_C,
        "substantive_trial": True,
        "status": "completed",
    }
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "record-other-version",
        wrong_hash_trial,
    )
    accounting = derive_trial_accounting(
        path,
        "candidate-1",
        HASH_A,
        "2026-07-17T08:00:00Z",
    )
    assert accounting.registered == 0

    missing_result = {
        **wrong_hash_trial,
        "experiment_id": "experiment-missing-result",
        "frozen_specification_hash": HASH_A,
    }
    missing_result.pop("result_artifact_hash")
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "record-missing-result",
        missing_result,
    )
    with pytest.raises(ValueError, match="result_artifact_hash"):
        derive_trial_accounting(
            path,
            "candidate-1",
            HASH_A,
            "2026-07-17T08:00:00Z",
        )


def test_stage_proof_requires_pinned_signed_receipt_and_bound_result_artifact(
    tmp_path: Path,
) -> None:
    private_key = _configure_promotion_authority(tmp_path)
    source_artifact = {
        "artifact_type": "authenticated_stage_evaluation",
        "schema_version": "dopey-authenticated-stage-evaluation-v1",
        "proof_type": "development",
        "evidence_id": "development-e1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "frozen_specification_hash": HASH_A,
        "experiment_id": "development-experiment-1",
        "evaluator_id": "ascendancy-development-evaluator-v1",
        "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
        "evaluated_at": "2026-07-17T03:00:00Z",
        "passed": True,
        "paper_only": True,
        "live_blocked": True,
    }
    source_hash = canonical_hash(source_artifact)
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "development-experiment-record-1",
        {
            "event_time": "2026-07-17T02:00:00Z",
            "code_version": "test",
            "data_hash": HASH_B,
            "experiment_id": "development-experiment-1",
            "candidate_id": "candidate-1",
            "frozen_specification_hash": HASH_A,
            "result_artifact_hash": source_hash,
            "substantive_trial": True,
            "status": "completed",
        },
    )
    receipt, receipt_hash, signature = _signed_stage_receipt(
        private_key,
        "development-e1",
        "development",
        None,
        "candidate-1",
        "candidate-author",
        HASH_A,
        "development-experiment-1",
        "ascendancy-development-evaluator-v1",
        source_hash,
        "2026-07-17T03:00:00Z",
    )
    proof = {
        "event_time": "2026-07-17T03:00:00Z",
        "code_version": "test",
        "data_hash": HASH_B,
        "experiment_id": "development-experiment-1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "frozen_specification_hash": HASH_A,
        "environment_id": "dopey-options-paper-v1",
        "proof_type": "development",
        "evidence_id": "development-e1",
        "evaluator_id": "ascendancy-development-evaluator-v1",
        "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
        "authentication_method": promotion.STAGE_AUTHENTICATION_METHOD,
        "passed": True,
        "source_artifact": source_artifact,
        "source_artifact_hash": source_hash,
        "receipt_body": receipt,
        "receipt_body_hash": receipt_hash,
        "receipt_signature_base64": signature,
        "paper_only": True,
        "live_blocked": True,
    }
    append_canonical_ascendancy_record(tmp_path, "proof", "development-proof-1", proof)
    records, _ = promotion._candidate_proofs(
        tmp_path / "PROOF_LEDGER.jsonl",
        replace(_promotion_evidence(), current_level="L0", requested_level="L1"),
    )
    authenticated, reasons = promotion._authenticated_stage_proofs(
        records,
        tmp_path / "EXPERIMENT_REGISTRY.jsonl",
        replace(_promotion_evidence(), current_level="L0", requested_level="L1"),
        True,
        tmp_path,
        frozenset({"development"}),
    )
    assert len(authenticated) == 1 and reasons == ()

    forged = ({**records[0], "passed": False},)
    authenticated, reasons = promotion._authenticated_stage_proofs(
        forged,
        tmp_path / "EXPERIMENT_REGISTRY.jsonl",
        replace(_promotion_evidence(), current_level="L0", requested_level="L1"),
        True,
        tmp_path,
        frozenset({"development"}),
    )
    assert authenticated == ()
    assert reasons == ("stage_proof_authentication_invalid:development-e1",)


def test_sealed_response_requires_evaluator_binding_and_nonempty_result() -> None:
    response = SealedAggregateResponse(
        "sealed-request-1234567890abcdef12345678",
        "candidate-1",
        HASH_A,
        1,
        (("lower_bound_utility", 0.1),),
        (),
        "sealed-v1",
        True,
        "2026-07-17T03:00:00Z",
    )
    arguments = (
        frozenset({"lower_bound_utility"}),
        response.request_id,
        response.candidate_id,
        response.frozen_specification_hash,
        "sealed-v1",
    )
    validate_aggregate_response(response, *arguments)

    with pytest.raises(ValueError, match="evaluator version"):
        validate_aggregate_response(replace(response, evaluator_version="forged-v2"), *arguments)
    with pytest.raises(ValueError, match="requires aggregate metrics"):
        validate_aggregate_response(
            replace(response, aggregate_metrics=(), failure_codes=()),
            *arguments,
        )


def test_sealed_budget_binds_full_reverse_maps_and_configured_evaluator(
    tmp_path: Path,
) -> None:
    mismatched_path = tmp_path / "mismatched-budget.json"
    _write_json(mismatched_path, _configured_budget())
    with pytest.raises(PermissionError, match="evaluator version"):
        reserve_sealed_submission(
            mismatched_path,
            "candidate-1",
            HASH_A,
            ("lower_bound_utility",),
            "forged-v2",
            "2026-07-17T02:00:00Z",
        )

    budget_path = tmp_path / "budget.json"
    _write_json(budget_path, _configured_budget())
    request = reserve_sealed_submission(
        budget_path,
        "candidate-1",
        HASH_A,
        ("lower_bound_utility",),
        "sealed-v1",
        "2026-07-17T02:00:00Z",
    )
    decoded = json.loads(budget_path.read_text(encoding="utf-8"))
    candidate_record = decoded["candidate_submissions"]["candidate-1"]
    assert candidate_record == decoded["frozen_hash_submissions"][HASH_A]
    assert candidate_record["candidate_id"] == "candidate-1"
    assert candidate_record["evaluator_id"] == request.evaluator_id
    assert candidate_record["evaluator_version"] == request.evaluator_version
    assert candidate_record["aggregate_metric_ids"] == ["lower_bound_utility"]


def test_l4_budget_requires_configured_consumed_evaluator_bound_response(
    tmp_path: Path,
) -> None:
    private_key = _configure_sealed_trust(tmp_path)
    budget_path = tmp_path / "budget.json"
    _write_json(budget_path, _configured_budget())
    request = reserve_sealed_submission(
        budget_path,
        "candidate-1",
        HASH_A,
        ("lower_bound_utility",),
        "sealed-v1",
        "2026-07-17T02:00:00Z",
    )
    metrics = {"lower_bound_utility": 0.1}
    response_body = {
        "request_id": request.request_id,
        "candidate_id": "candidate-1",
        "frozen_specification_hash": HASH_A,
        "submission_number": 1,
        "evaluator_id": "independent-sealed-evaluator",
        "evaluator_version": "sealed-v1",
        "evaluator_issued_at": "2026-07-17T03:00:00Z",
        "passed": True,
        "aggregate_feedback_only": True,
        "raw_holdout_access": False,
        "aggregate_metrics": metrics,
        "failure_codes": [],
    }
    response_body_hash = canonical_hash(response_body)
    signature_base64 = base64.b64encode(
        private_key.sign(canonical_response_body_bytes(response_body))
    ).decode("ascii")
    proof = {
        "proof_type": "sealed_evaluation",
        "passed": True,
        "request_id": request.request_id,
        "event_time": "2026-07-17T03:00:00Z",
        "evaluator_id": "independent-sealed-evaluator",
        "evaluator_version": "sealed-v1",
        "submission_number": 1,
        "aggregate_feedback_only": True,
        "raw_holdout_access": False,
        "aggregate_metrics": metrics,
        "failure_codes": [],
        "response_body": response_body,
        "response_body_hash": response_body_hash,
        "source_artifact_hash": response_body_hash,
        "signature_base64": signature_base64,
    }
    reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        (proof,),
        v1_promotion_policy(),
        tmp_path,
    )
    assert reasons == []

    incomplete = {**proof, "aggregate_metrics": {}}
    incomplete_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        (incomplete,),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_response_metric_set_mismatch" in incomplete_reasons

    tampered_response = {
        **proof,
        "response_body": {**response_body, "aggregate_metrics": {"lower_bound_utility": 0.2}},
    }
    tampered_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        (tampered_response,),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_response_body_binding_invalid" in tampered_reasons

    unsigned_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        ({**proof, "signature_base64": ""},),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_external_signature_verification_missing" in unsigned_reasons

    forged_verdict_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        ({**proof, "passed": False},),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_response_body_binding_invalid" in forged_verdict_reasons

    forged_time_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        ({**proof, "event_time": "2026-07-17T03:30:00Z"},),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_response_body_binding_invalid" in forged_time_reasons

    failure_response_body = {
        **response_body,
        "passed": False,
        "aggregate_metrics": {},
        "failure_codes": ["candidate_failed_metric_floor"],
    }
    failure_response_hash = canonical_hash(failure_response_body)
    failure_signature_base64 = base64.b64encode(
        private_key.sign(canonical_response_body_bytes(failure_response_body))
    ).decode("ascii")
    explicit_failure = {
        **proof,
        "passed": False,
        "aggregate_metrics": {},
        "failure_codes": ["candidate_failed_metric_floor"],
        "response_body": failure_response_body,
        "response_body_hash": failure_response_hash,
        "source_artifact_hash": failure_response_hash,
        "signature_base64": failure_signature_base64,
    }
    explicit_failure_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        (explicit_failure,),
        v1_promotion_policy(),
        tmp_path,
    )
    assert explicit_failure_reasons == ["sealed_evaluation_reported_failure"]

    decoded = json.loads(budget_path.read_text(encoding="utf-8"))
    decoded["status"] = "not_configured_no_external_evaluator"
    _write_json(budget_path, decoded)
    unconfigured_reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        (proof,),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_evaluator_not_configured" in unconfigured_reasons


def test_l4_rejects_unconfigured_zero_use_budget(tmp_path: Path) -> None:
    budget_path = tmp_path / "budget.json"
    budget = _configured_budget()
    budget["status"] = "not_configured_no_external_evaluator"
    _write_json(budget_path, budget)

    reasons = promotion._sealed_budget_reasons(
        budget_path,
        _promotion_evidence(),
        (),
        v1_promotion_policy(),
        tmp_path,
    )
    assert "sealed_evaluator_not_configured" in reasons
    assert "sealed_evaluation_submission_missing" in reasons


def test_forward_validation_counts_only_complete_chronological_pairs(tmp_path: Path) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _valid_abstention_decision(1, "opportunity-1"),
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "settlement-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _settlement_payload(
                "prediction-1",
                "2026-07-17T03:00:00Z",
                "2026-07-17T04:00:00Z",
                "win",
                0.01,
            ),
        ),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert reasons == []


def test_forward_validation_blocks_count_complete_but_low_quality_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _valid_abstention_decision(1, "opportunity-1"),
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "settlement-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _settlement_payload(
                "prediction-1",
                "2026-07-17T03:00:00Z",
                "2026-07-17T04:00:00Z",
                "loss",
                -0.01,
            ),
        ),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "insufficient_forward_decisions" not in reasons
    assert "insufficient_forward_settlements" not in reasons
    assert "abstention_inferior_to_no_trade" in reasons
    assert "forward_cluster_calibration_above_threshold" in reasons


def test_forward_validation_separates_event_and_recorder_clocks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    payload = _valid_abstention_decision(1, "opportunity-1")
    decision_artifact = dict(payload["decision_artifact"])
    recorder_issued_at = "2026-07-17T02:00:59Z"
    decision_artifact["recorder_issued_at"] = recorder_issued_at
    decision_hash = canonical_hash(decision_artifact)
    payload["decision_artifact"] = decision_artifact
    payload["decision_artifact_hash"] = decision_hash
    payload["recorder_issued_at"] = recorder_issued_at
    recorder_key, _ = _configure_forward_trust(tmp_path)
    receipt, receipt_hash, signature = _forward_receipt(
        recorder_key,
        "forward_record",
        "forward-1",
        decision_hash,
        recorder_issued_at,
        "independent-forward-recorder",
    )
    payload.update(
        {
            "recorder_receipt_body": receipt,
            "recorder_receipt_body_hash": receipt_hash,
            "recorder_signature_base64": signature,
        }
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        payload,
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_recorder_receipt_invalid" in reasons
    assert "insufficient_forward_decisions" in reasons


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("evidence_class", "synthetic_mechanics_only"),
        ("opportunity_synthetic", True),
        ("profitability_evidence_eligible", False),
    ),
)
def test_forward_validation_rejects_non_qualifying_or_synthetic_action_evidence(
    tmp_path: Path,
    field_name: str,
    invalid_value: object,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    decision = _valid_abstention_decision(1, "opportunity-1")
    decision[field_name] = invalid_value
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        decision,
    )
    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_evidence_not_profitability_eligible" in reasons
    assert "insufficient_forward_decisions" in reasons


def test_forward_validation_rejects_opaque_ticket_identifier(tmp_path: Path) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _decision_payload(
            1,
            "opportunity-1",
            "paper-ticket-1",
            None,
            None,
        ),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_decision_action_artifact_invalid" in reasons
    assert "insufficient_forward_decisions" in reasons


@pytest.mark.parametrize(
    ("action_opportunity_id", "action_candidate_id", "action_decision_timestamp"),
    (
        ("opportunity-rebound", "candidate-1", "2026-07-17T02:01:00Z"),
        ("opportunity-1", "candidate-rebound", "2026-07-17T02:01:00Z"),
        ("opportunity-1", "candidate-1", "2026-07-17T02:00:30Z"),
    ),
)
def test_forward_validation_rejects_rehashed_action_binding_changes(
    tmp_path: Path,
    action_opportunity_id: str,
    action_candidate_id: str,
    action_decision_timestamp: str,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    action_artifact = _abstention_action(
        action_opportunity_id,
        action_candidate_id,
        action_decision_timestamp,
    )
    abstention_id = action_artifact["abstention_id"]
    assert isinstance(abstention_id, str)
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _decision_payload(
            1,
            "opportunity-1",
            None,
            abstention_id,
            action_artifact,
        ),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_decision_action_binding_invalid" in reasons
    assert "insufficient_forward_decisions" in reasons


def test_forward_validation_rejects_action_content_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    decision = _valid_abstention_decision(1, "opportunity-1")
    decision_artifact = dict(decision["decision_artifact"])
    action_artifact = dict(decision_artifact["action_artifact"])
    action_artifact["reason_codes"] = ["changed_after_hashing"]
    decision_artifact["action_artifact"] = action_artifact
    decision["decision_artifact"] = decision_artifact
    decision["decision_artifact_hash"] = canonical_hash(decision_artifact)
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        decision,
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_decision_action_artifact_invalid" in reasons
    assert "insufficient_forward_decisions" in reasons


def test_forward_validation_rejects_non_attested_prospective_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    decision = _authenticate_forward_payload(
        tmp_path,
        _valid_abstention_decision(1, "opportunity-1"),
    )
    decision_artifact = dict(decision["decision_artifact"])
    decision_artifact["prospective_evidence_hash"] = HASH_C
    decision["decision_artifact"] = decision_artifact
    decision["decision_artifact_hash"] = canonical_hash(decision_artifact)
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        decision,
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_recorder_receipt_invalid" in reasons
    assert "forward_input_attestation_invalid" in reasons
    assert "insufficient_forward_decisions" in reasons


def test_forward_validation_rejects_ambiguous_decision_identity(tmp_path: Path) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _decision_payload(
            1,
            "opportunity-1",
            "paper-ticket-1",
            "abstention-1",
            None,
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-2",
        _valid_abstention_decision(2, "opportunity-1"),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_decision_action_identity_invalid" in reasons
    assert "forward_opportunity_id_duplicated" not in reasons
    assert "insufficient_forward_settlements" in reasons


def test_forward_validation_rejects_duplicate_frozen_opportunity(tmp_path: Path) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _valid_abstention_decision(1, "opportunity-1"),
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-2",
        _authenticate_forward_payload(
            tmp_path,
            _valid_abstention_decision(2, "opportunity-1"),
        ),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_opportunity_id_duplicated" in reasons


def test_forward_validation_rejects_rehashed_record_with_tampered_embedded_artifact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    decision = _valid_abstention_decision(1, "opportunity-1")
    prediction_artifact = dict(decision["prediction_artifact"])
    prediction_artifact["opportunity_id"] = "opportunity-rebound"
    decision["prediction_artifact"] = prediction_artifact
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        decision,
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert "forward_decision_artifact_content_invalid" in reasons


@pytest.mark.parametrize(
    ("prediction_id", "maturity_time", "event_time", "expected_reason"),
    (
        (
            "prediction-mismatch",
            "2026-07-17T03:00:00Z",
            "2026-07-17T04:00:00Z",
            "forward_settlement_parent_identity_mismatch",
        ),
        (
            "prediction-1",
            "2026-07-17T05:00:00Z",
            "2026-07-17T04:00:00Z",
            "forward_settlement_not_after_maturity",
        ),
        (
            "prediction-1",
            "2026-07-17T02:01:00Z",
            "2026-07-17T04:00:00Z",
            "forward_maturity_precedes_decision",
        ),
    ),
)
def test_forward_validation_rejects_unbound_or_premature_settlement(
    tmp_path: Path,
    prediction_id: str,
    maturity_time: str,
    event_time: str,
    expected_reason: str,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _valid_abstention_decision(1, "opportunity-1"),
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "settlement-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _settlement_payload(
                prediction_id,
                maturity_time,
                event_time,
                "win",
                0.01,
            ),
        ),
    )

    reasons = promotion._forward_reasons(
        path, _promotion_evidence(), _one_pair_policy(), "abstention_policy", HASH_C
    )
    assert expected_reason in reasons
    assert "insufficient_forward_settlements" in reasons


def test_flat_forward_outcome_uses_zero_success_target(tmp_path: Path) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _valid_abstention_decision(1, "opportunity-1"),
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "settlement-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _settlement_payload(
                "prediction-1",
                "2026-07-17T03:00:00Z",
                "2026-07-17T04:00:00Z",
                "flat",
                0.0,
            ),
        ),
    )
    reasons = promotion._forward_reasons(
        path,
        _promotion_evidence(),
        _one_pair_policy(),
        "abstention_policy",
        HASH_C,
    )
    assert "forward_cluster_calibration_above_threshold" in reasons
    assert "abstention_inferior_to_no_trade" not in reasons


def test_session_cluster_bound_does_not_count_same_session_multiplicity() -> None:
    one_session = promotion._session_cluster_bounds(
        {"session-1": [0.01] * 100}
    )
    twenty_sessions = promotion._session_cluster_bounds(
        {f"session-{index}": [0.01] for index in range(20)}
    )
    assert one_session.cluster_count == 1
    assert twenty_sessions.cluster_count == 20
    assert one_session.lower_bound == pytest.approx(0.01)
    assert twenty_sessions.lower_bound == pytest.approx(0.01)


def test_candidate_registration_rejects_shell_or_malformed_genome() -> None:
    shell = {
        "artifact_type": "frozen_candidate_specification",
        "schema_version": "dopey-frozen-candidate-v1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "candidate_mode": "abstention_policy",
        "frozen_at": "2026-07-17T01:00:00Z",
        "paper_only": True,
        "live_blocked": True,
    }
    with pytest.raises(ValueError, match="exact canonical v1 schema"):
        canonical_candidate_registration(
            "candidate-1",
            "candidate-author",
            "2026-07-17T01:00:00Z",
            shell,
        )
    malformed = {
        **shell,
        "candidate_genome_hash": HASH_C,
        "candidate_genome": {},
    }
    with pytest.raises(ValueError, match="candidate genome mapping"):
        canonical_candidate_registration(
            "candidate-1",
            "candidate-author",
            "2026-07-17T01:00:00Z",
            malformed,
        )


def test_candidate_author_cannot_be_forward_recorder_or_governor() -> None:
    dynamic_state = {
        "external_trust_root_pinned_role_identities": _pinned_role_identities()
    }
    assert promotion._candidate_author_conflict_reasons(
        "independent-forward_recorder",
        dynamic_state,
    ) == (
        "candidate_author_conflicts_with_protected_role:external:forward_recorder",
    )
    assert promotion._candidate_author_conflict_reasons(
        promotion.PROMOTION_GOVERNOR_ID,
        dynamic_state,
    ) == (
        "candidate_author_conflicts_with_protected_role:promotion_governor",
    )


def test_options_forward_requires_one_signed_fill_observation_per_ticket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "shadow_trading" / "FORWARD_EVIDENCE.jsonl"
    decision, action = _valid_options_decision()
    monkeypatch.setattr(
        promotion,
        "paper_execution_ticket_from_mapping",
        lambda _: SimpleNamespace(**action),
    )
    monkeypatch.setattr(
        promotion,
        "paper_fill_observation_from_mapping",
        lambda _artifact, _ticket: SimpleNamespace(
            observation_id="paper-fill-1",
            ticket_id="paper-ticket-1",
            witnessed_at="2026-07-17T02:02:00Z",
            paper_fill_status="filled",
            evidence_class="prospective_market_evidence",
            profitability_evidence_eligible=True,
            realized_evidence=False,
            paper_only=True,
            live_blocked=True,
        ),
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "decision-record-1",
        _authenticate_forward_payload(tmp_path, decision),
    )
    missing_reasons = promotion._forward_reasons(
        path,
        _promotion_evidence(),
        _one_pair_policy(),
        "options_expression",
        HASH_C,
    )
    assert "forward_execution_observation_coverage_incomplete" in missing_reasons
    append_canonical_ascendancy_record(
        tmp_path,
        "forward",
        "fill-record-1",
        _authenticate_forward_payload(
            tmp_path,
            _execution_observation_payload(),
        ),
    )
    observed_reasons = promotion._forward_reasons(
        path,
        _promotion_evidence(),
        _one_pair_policy(),
        "options_expression",
        HASH_C,
    )
    assert "forward_execution_observation_coverage_incomplete" not in observed_reasons


def test_router_requires_signed_canonical_promotion_and_routing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = _configure_promotion_authority(tmp_path)
    monkeypatch.setattr(
        promotion,
        "candidate_genome_from_mapping",
        lambda _: SimpleNamespace(
            candidate_id="candidate-1",
            candidate_mode="abstention_policy",
            genome_hash=HASH_C,
        ),
    )
    frozen_specification = {
        "artifact_type": "frozen_candidate_specification",
        "schema_version": "dopey-frozen-candidate-v1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "candidate_mode": "abstention_policy",
        "frozen_at": "2026-07-17T01:00:00Z",
        "candidate_genome_hash": HASH_C,
        "candidate_genome": {"fixture": "validated-by-isolated-contract-suite"},
        "paper_only": True,
        "live_blocked": True,
    }
    registration = canonical_candidate_registration(
        "candidate-1",
        "candidate-author",
        "2026-07-17T01:00:00Z",
        frozen_specification,
    )
    frozen_hash = str(registration["frozen_specification_hash"])
    (tmp_path / "CANDIDATE_LINEAGE.jsonl").write_text(
        json.dumps(
            {
                "environment_id": "dopey-options-paper-v1",
                "record_type": "registry_initialization",
                "registered_candidates": 0,
                "status": "empty",
            }
        )
        + "\n"
        + json.dumps(registration)
        + "\n",
        encoding="utf-8",
    )
    transition_source = {
        "artifact_type": "promotion_decision",
        "schema_version": "dopey-promotion-decision-v1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "candidate_mode": "abstention_policy",
        "frozen_specification_hash": frozen_hash,
        "from_level": "L0",
        "to_level": "L1",
        "allowed": True,
        "reason_codes": [],
        "evaluated_at": "2026-07-17T03:00:00Z",
        "trial_registry_hash": canonical_hash([]),
        "experiment_registry_record_count": 0,
        "proof_registry_hash_before": canonical_hash([]),
        "proof_registry_record_count_before": 0,
        "dynamic_state_hash": HASH_D,
        "audit_snapshot_hash": HASH_E,
        "paper_only": True,
        "live_blocked": True,
    }
    transition_hash = canonical_hash(transition_source)
    transition_receipt, transition_receipt_hash, transition_signature = (
        _signed_stage_receipt(
            private_key,
            "promotion-e1",
            "promotion_transition",
            None,
            "candidate-1",
            "candidate-author",
            frozen_hash,
            "promotion-transition-1",
            promotion.PROMOTION_GOVERNOR_ID,
            transition_hash,
            "2026-07-17T03:00:00Z",
        )
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "proof",
        "promotion-transition-record-1",
        {
            "event_time": "2026-07-17T03:00:00Z",
            "code_version": "test",
            "data_hash": transition_hash,
            "experiment_id": "promotion-transition-1",
            "record_type": "promotion_transition",
            "proof_type": "promotion_transition",
            "evidence_id": "promotion-e1",
            "candidate_id": "candidate-1",
            "candidate_author_id": "candidate-author",
            "frozen_specification_hash": frozen_hash,
            "environment_id": "dopey-options-paper-v1",
            "evaluator_id": promotion.PROMOTION_GOVERNOR_ID,
            "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
            "authentication_method": promotion.STAGE_AUTHENTICATION_METHOD,
            "from_level": "L0",
            "to_level": "L1",
            "passed": True,
            "source_artifact": transition_source,
            "source_artifact_hash": transition_hash,
            "receipt_body": transition_receipt,
            "receipt_body_hash": transition_receipt_hash,
            "receipt_signature_base64": transition_signature,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    routing_source = {
        "artifact_type": "authenticated_stage_evaluation",
        "schema_version": "dopey-authenticated-stage-evaluation-v1",
        "proof_type": "routing_eligibility",
        "evidence_id": "routing-e1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "frozen_specification_hash": frozen_hash,
        "experiment_id": "routing-experiment-1",
        "evaluator_id": "ascendancy-routing-evaluator-v1",
        "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
        "evaluated_at": "2026-07-17T04:00:00Z",
        "passed": True,
        "promotion_evidence_id": "promotion-e1",
        "retirement_evidence_id": "retirement-e1",
        "candidate_mode": "abstention_policy",
        "evidence_level": "L1",
        "validated_contexts": ["liquid_non_event"],
        "lower_bound_utility": 0.1,
        "quote_gate_passed": True,
        "risk_gate_passed": True,
        "quarantined": False,
        "paper_only": True,
        "live_blocked": True,
    }
    routing_hash = canonical_hash(routing_source)
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "routing-experiment-record-1",
        {
            "event_time": "2026-07-17T03:30:00Z",
            "code_version": "test",
            "data_hash": HASH_E,
            "experiment_id": "routing-experiment-1",
            "candidate_id": "candidate-1",
            "frozen_specification_hash": frozen_hash,
            "result_artifact_hash": routing_hash,
            "substantive_trial": True,
            "status": "completed",
        },
    )
    routing_receipt, routing_receipt_hash, routing_signature = _signed_stage_receipt(
        private_key,
        "routing-e1",
        "routing_eligibility",
        None,
        "candidate-1",
        "candidate-author",
        frozen_hash,
        "routing-experiment-1",
        "ascendancy-routing-evaluator-v1",
        routing_hash,
        "2026-07-17T04:00:00Z",
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "proof",
        "routing-proof-record-1",
        {
            "event_time": "2026-07-17T04:00:00Z",
            "code_version": "test",
            "data_hash": HASH_E,
            "experiment_id": "routing-experiment-1",
            "proof_type": "routing_eligibility",
            "evidence_id": "routing-e1",
            "candidate_id": "candidate-1",
            "candidate_author_id": "candidate-author",
            "frozen_specification_hash": frozen_hash,
            "environment_id": "dopey-options-paper-v1",
            "evaluator_id": "ascendancy-routing-evaluator-v1",
            "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
            "authentication_method": promotion.STAGE_AUTHENTICATION_METHOD,
            "passed": True,
            "source_artifact": routing_source,
            "source_artifact_hash": routing_hash,
            "receipt_body": routing_receipt,
            "receipt_body_hash": routing_receipt_hash,
            "receipt_signature_base64": routing_signature,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    trusted_audit: dict[str, object] = {
        "external_anchor_verified": True,
        "certification_eligible": True,
        "protected_manifest_sha256": HASH_A,
        "source_manifest_sha256": HASH_B,
    }
    trusted_dynamic_state: dict[str, object] = {
        "repository_anchor_verified": True,
        "external_anchor_verified": True,
        "certification_eligible": True,
        "dynamic_state_hash": HASH_C,
        "dynamic_anchor_id": "anchor-1",
        "dynamic_anchor_sequence": 1,
        "dynamic_anchor_parent_id": None,
        "dynamic_anchor_receipt_sha256": HASH_D,
        "external_trust_root_id": "external-root-1",
        "external_trust_root_version": "external-root-v1",
        "external_trust_root_sha256": HASH_E,
        "external_trust_root_pinned_role_identities": _pinned_role_identities(),
        "files": {},
    }
    monkeypatch.setattr(
        "dopey.ascendancy.router._run_full_canonical_audit",
        lambda _: (trusted_audit, trusted_dynamic_state),
    )
    monkeypatch.setattr(
        "dopey.ascendancy.promotion._run_full_canonical_audit",
        lambda _: (trusted_audit, trusted_dynamic_state),
    )
    candidate = RouteCandidate(
        "candidate-1",
        frozen_hash,
        "promotion-e1",
        "routing-e1",
        "retirement-e1",
        "L1",
        frozenset({"liquid_non_event"}),
        0.1,
        True,
        True,
        False,
    )
    cumulative_gate_blocked = _route_validated_candidate_for_root(
        tmp_path,
        "liquid_non_event",
        (candidate,),
        "L1",
        "2026-07-17T04:30:00Z",
    )
    assert cumulative_gate_blocked.action == "abstain"
    assert cumulative_gate_blocked.reason_codes == (
        "router_candidate_evidence_invalid:candidate-1",
    )

    monkeypatch.setattr(
        "dopey.ascendancy.router._cumulative_promotion_gate_state",
        lambda *_: ((), None, (), HASH_A),
    )
    missing_retirement = _route_validated_candidate_for_root(
        tmp_path,
        "liquid_non_event",
        (candidate,),
        "L1",
        "2026-07-17T04:30:00Z",
    )
    assert missing_retirement.action == "abstain"
    assert missing_retirement.reason_codes == (
        "router_candidate_evidence_invalid:candidate-1",
    )

    retirement_source = {
        "artifact_type": "candidate_retirement_state",
        "schema_version": "dopey-candidate-retirement-state-v1",
        "environment_id": "dopey-options-paper-v1",
        "proof_type": "retirement_state",
        "evidence_id": "retirement-e1",
        "candidate_id": "candidate-1",
        "candidate_author_id": "candidate-author",
        "frozen_specification_hash": frozen_hash,
        "experiment_id": "retirement-experiment-1",
        "evaluator_id": "ascendancy-retirement-evaluator-v1",
        "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
        "evaluated_at": "2026-07-17T03:45:00Z",
        "valid_until": "2026-07-17T04:45:00Z",
        "monitoring_state": {
            "calibration_error": 0.01,
            "execution_degradation": 0.01,
            "drawdown_fraction": 0.01,
            "specification_deviations": 0,
            "unsettled_fraction": 0.01,
            "protected_manifest_valid": True,
            "expected_edge_exceeds_costs": True,
            "liquidity_policy_valid": True,
        },
        "retirement_policy": {
            "maximum_calibration_error": 0.10,
            "maximum_execution_degradation": 0.25,
            "maximum_drawdown_fraction": 0.10,
            "maximum_specification_deviations": 0,
            "maximum_unsettled_fraction": 0.05,
        },
        "retirement_state": "CONTINUE_PAPER",
        "reason_codes": [],
        "passed": True,
        "paper_only": True,
        "live_blocked": True,
    }
    retirement_hash = canonical_hash(retirement_source)
    append_canonical_ascendancy_record(
        tmp_path,
        "experiment",
        "retirement-experiment-record-1",
        {
            "event_time": "2026-07-17T03:40:00Z",
            "code_version": "test",
            "data_hash": HASH_E,
            "experiment_id": "retirement-experiment-1",
            "candidate_id": "candidate-1",
            "frozen_specification_hash": frozen_hash,
            "result_artifact_hash": retirement_hash,
            "substantive_trial": True,
            "status": "completed",
        },
    )
    retirement_receipt, retirement_receipt_hash, retirement_signature = (
        _signed_stage_receipt(
            private_key,
            "retirement-e1",
            "retirement_state",
            None,
            "candidate-1",
            "candidate-author",
            frozen_hash,
            "retirement-experiment-1",
            "ascendancy-retirement-evaluator-v1",
            retirement_hash,
            "2026-07-17T03:45:00Z",
        )
    )
    append_canonical_ascendancy_record(
        tmp_path,
        "proof",
        "retirement-proof-record-1",
        {
            "event_time": "2026-07-17T03:45:00Z",
            "code_version": "test",
            "data_hash": HASH_E,
            "experiment_id": "retirement-experiment-1",
            "proof_type": "retirement_state",
            "evidence_id": "retirement-e1",
            "candidate_id": "candidate-1",
            "candidate_author_id": "candidate-author",
            "frozen_specification_hash": frozen_hash,
            "environment_id": "dopey-options-paper-v1",
            "evaluator_id": "ascendancy-retirement-evaluator-v1",
            "evaluator_version": promotion.STAGE_EVALUATOR_VERSION,
            "authentication_method": promotion.STAGE_AUTHENTICATION_METHOD,
            "passed": True,
            "source_artifact": retirement_source,
            "source_artifact_hash": retirement_hash,
            "receipt_body": retirement_receipt,
            "receipt_body_hash": retirement_receipt_hash,
            "receipt_signature_base64": retirement_signature,
            "paper_only": True,
            "live_blocked": True,
        },
    )
    caller_downgrade_blocked = _route_validated_candidate_for_root(
        tmp_path,
        "liquid_non_event",
        (candidate,),
        "L1",
        "2026-07-17T04:30:00Z",
    )
    assert caller_downgrade_blocked.action == "abstain"
    assert caller_downgrade_blocked.reason_codes == (
        "no_validated_positive_lower_bound_candidate",
    )
    monkeypatch.setattr(
        "dopey.ascendancy.router.V1_PROSPECTIVE_ROUTING_MINIMUM_EVIDENCE_LEVEL",
        "L1",
    )
    selected = _route_validated_candidate_for_root(
        tmp_path,
        "liquid_non_event",
        (candidate,),
        "L0",
        "2026-07-17T04:30:00Z",
    )
    assert selected.selected_candidate_id == "candidate-1"

    forged_retirement = json.loads(json.dumps(retirement_source))
    forged_monitoring_state = forged_retirement["monitoring_state"]
    assert isinstance(forged_monitoring_state, dict)
    forged_monitoring_state["drawdown_fraction"] = 0.50
    with pytest.raises(ValueError, match="measurement-derived"):
        validate_canonical_retirement_artifact(
            forged_retirement,
            "candidate-1",
            "candidate-author",
            frozen_hash,
            "retirement-e1",
            "2026-07-17T03:45:00Z",
        )

    stale = _route_validated_candidate_for_root(
        tmp_path,
        "liquid_non_event",
        (candidate,),
        "L1",
        "2026-07-17T05:01:00Z",
    )
    assert stale.action == "abstain"
    assert stale.reason_codes == (
        "router_candidate_evidence_invalid:candidate-1",
    )

    forged = _route_validated_candidate_for_root(
        tmp_path,
        "liquid_non_event",
        (replace(candidate, promotion_evidence_id="forged-promotion"),),
        "L1",
        "2026-07-17T04:30:00Z",
    )
    assert forged.action == "abstain"
    assert forged.reason_codes == ("router_candidate_evidence_invalid:candidate-1",)


def test_evaluation_timestamp_and_canonical_dynamic_anchor_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="future-dated"):
        promotion.evaluate_promotion(
            replace(_promotion_evidence(), evaluated_at="2099-01-01T00:00:00Z"),
            v1_promotion_policy(),
        )

    trusted_audit: dict[str, object] = {
        "external_anchor_verified": True,
        "certification_eligible": True,
        "protected_manifest_sha256": HASH_A,
        "source_manifest_sha256": HASH_B,
    }
    trusted_dynamic_state: dict[str, object] = {
        "repository_anchor_verified": True,
        "external_anchor_verified": True,
        "certification_eligible": True,
        "dynamic_state_hash": HASH_C,
        "dynamic_anchor_id": "anchor-1",
        "dynamic_anchor_sequence": 1,
        "dynamic_anchor_parent_id": None,
        "dynamic_anchor_receipt_sha256": HASH_D,
        "external_trust_root_id": "external-root-1",
        "external_trust_root_version": "external-root-v1",
        "external_trust_root_sha256": HASH_E,
        "external_trust_root_pinned_role_identities": _pinned_role_identities(),
        "files": {},
    }
    monkeypatch.setattr(
        promotion,
        "_run_full_canonical_audit",
        lambda _: (trusted_audit, trusted_dynamic_state),
    )
    with pytest.raises(ValueError, match="canonical lineage registration"):
        promotion.evaluate_promotion(
            _promotion_evidence(),
            v1_promotion_policy(),
        )


def test_external_root_audit_snapshot_reuses_and_binds_exact_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external_root_path = tmp_path / "operator" / "external-root.json"
    external_root_path.parent.mkdir()
    external_root_path.write_text("{}", encoding="utf-8")
    trusted_audit: dict[str, object] = {
        "external_anchor_verified": True,
        "certification_eligible": True,
        "protected_manifest_sha256": HASH_A,
        "source_manifest_sha256": HASH_B,
    }
    trusted_dynamic_state: dict[str, object] = {
        "repository_anchor_verified": True,
        "external_anchor_verified": True,
        "certification_eligible": True,
        "dynamic_state_hash": HASH_C,
        "dynamic_anchor_id": "anchor-1",
        "dynamic_anchor_sequence": 1,
        "dynamic_anchor_parent_id": None,
        "dynamic_anchor_receipt_sha256": HASH_D,
        "external_trust_root_id": "external-root-1",
        "external_trust_root_version": "external-root-v1",
        "external_trust_root_sha256": HASH_E,
        "external_trust_root_pinned_role_identities": _pinned_role_identities(),
        "files": {},
    }
    observed_paths: list[Path] = []

    def run_with_external_root(
        repository_root: Path,
        observed_external_root_path: Path,
    ) -> tuple[dict[str, object], dict[str, object]]:
        assert repository_root == tmp_path
        observed_paths.append(observed_external_root_path)
        return trusted_audit, trusted_dynamic_state

    monkeypatch.setattr(
        promotion,
        "_run_full_canonical_audit_with_external_root",
        run_with_external_root,
    )
    snapshot_hash = promotion._canonical_audit_snapshot_hash(
        trusted_audit,
        trusted_dynamic_state,
    )
    promotion._assert_canonical_audit_snapshot_unchanged_with_external_root(
        tmp_path,
        external_root_path,
        snapshot_hash,
    )
    assert observed_paths == [external_root_path.resolve(strict=True)]
    changed_state = {
        **trusted_dynamic_state,
        "external_trust_root_sha256": HASH_A,
    }
    assert (
        promotion._canonical_audit_snapshot_hash(trusted_audit, changed_state)
        != snapshot_hash
    )
