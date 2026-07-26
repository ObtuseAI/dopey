"""Reproducible, read-only audit of the DOPEY Ascendancy v1 laboratory."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
from pathlib import Path
from typing import cast

from dopey.ascendancy.identity import JsonValue, canonical_hash, require_sha256, require_utc_iso
from dopey.ascendancy.ledger import GENESIS_HASH, ledger_anchor_path, verify_hash_chained_ledger
from sealed_evaluator_client.budget import PROHIBITED_REQUEST_TERMS, SUBMISSION_RECORD_FIELDS

from .dynamic_anchor import (
    dynamic_anchor_audit_state,
    dynamic_anchor_audit_state_with_external_root,
)
from .environment_freeze import verify_environment_freeze
from .protected_manifest import (
    ASCENDANCY_DYNAMIC_STATE_PATHS,
    file_sha256,
    verify_ascendancy_protected_manifest,
)


ENVIRONMENT_ID = "dopey-options-paper-v1"
REGISTRY_IDENTITIES = {
    "APPROACH_REGISTRY.jsonl": "family_id",
    "CANDIDATE_LINEAGE.jsonl": "candidate_id",
    "FAILURE_REGISTRY.jsonl": "failure_id",
    "HYPOTHESIS_REGISTRY.jsonl": "hypothesis_id",
}
SUPPORTED_BUDGET_STATUSES = frozenset(
    {"configured_external_evaluator", "not_configured_no_external_evaluator"}
)
BUDGET_COMMON_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "aggregate_feedback_only",
        "raw_holdout_access",
        "maximum_submissions_per_frozen_candidate",
        "maximum_total_submissions",
        "allowed_aggregate_metric_ids",
        "submissions_used",
        "candidate_submissions",
        "frozen_hash_submissions",
        "status",
    }
)
BUDGET_CONFIGURED_FIELDS = BUDGET_COMMON_FIELDS.union({"evaluator_id", "evaluator_version"})
SEALED_REQUEST_PREFIX = "sealed-request-"
FORWARD_RECORD_TYPES = frozenset(
    {
        "forward_decision",
        "forward_execution_observation",
        "forward_settlement",
    }
)
FORWARD_EXECUTION_OBSERVATION_STRING_FIELDS = (
    "execution_observation_id",
    "parent_decision_id",
    "ticket_id",
    "session_id",
    "event_time",
    "recorder_issued_at",
    "fill_observation_id",
    "fill_status",
    "fill_artifact_hash",
    "recorder_receipt_body_hash",
    "recorder_signature_base64",
)
FORWARD_RECEIPT_BODY_FIELDS = frozenset(
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


def _json_mapping(path: Path) -> dict[str, object]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"artifact must be a JSON mapping: path={path}")
    return cast(dict[str, object], decoded)


def _jsonl_mappings(path: Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        decoded = json.loads(line)
        if not isinstance(decoded, dict):
            raise ValueError(f"JSONL record must be a mapping: path={path}, line={line_number}")
        records.append(cast(dict[str, object], decoded))
    return tuple(records)


def _verify_approach_registry(path: Path) -> int:
    records = _jsonl_mappings(path)
    family_ids = [str(record["family_id"]) for record in records if "family_id" in record]
    if len(family_ids) != 26 or len(set(family_ids)) != 26:
        raise ValueError("approach registry must contain exactly 26 unique mechanism families")
    family_records = [record for record in records if "family_id" in record]
    if any(record.get("status") not in {"not_evaluated", "blocked"} for record in family_records):
        raise ValueError("initial approach registry contains an unsupported evidence claim")
    return len(family_ids)


def _registry_state(path: Path, identity_field: str) -> dict[str, object]:
    records = _jsonl_mappings(path)
    if not records or records[0].get("record_type") != "registry_initialization":
        raise ValueError(f"dynamic registry lacks its initialization record: path={path}")
    environment_id = records[0].get("environment_id")
    if environment_id != ENVIRONMENT_ID:
        raise ValueError(
            f"dynamic registry environment identity mismatch: path={path}, observed={environment_id}"
        )
    identities: list[str] = []
    for record in records[1:]:
        identity = record.get(identity_field)
        if not isinstance(identity, str) or not identity:
            raise ValueError(
                "dynamic registry record lacks its immutable identity: "
                f"path={path}, field={identity_field}"
            )
        identities.append(identity)
        record_environment = record.get("environment_id")
        if record_environment is not None and record_environment != ENVIRONMENT_ID:
            raise ValueError(
                "dynamic registry record environment identity mismatch: "
                f"path={path}, identity={identity}"
            )
    if len(identities) != len(set(identities)):
        raise ValueError(
            f"dynamic registry contains duplicate immutable identities: path={path}"
        )
    return {
        "file_sha256": file_sha256(path),
        "record_count": len(records),
        "registered_identity_count": len(identities),
        "identity_field": identity_field,
    }


def _positive_integer(value: object, field_name: str, allow_zero: bool) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"holdout budget field must be an integer: field={field_name}")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise ValueError(
            f"holdout budget integer is below its minimum: field={field_name}, minimum={minimum}"
        )
    return value


def _verify_holdout_budget(path: Path) -> dict[str, object]:
    budget = _json_mapping(path)
    if budget.get("schema_version") != "dopey-sealed-budget-v1":
        raise ValueError("holdout budget schema version is unsupported")
    if budget.get("environment_id") != ENVIRONMENT_ID:
        raise ValueError("holdout budget environment identity mismatch")
    if (
        budget.get("aggregate_feedback_only") is not True
        or budget.get("raw_holdout_access") is not False
        or budget.get("maximum_submissions_per_frozen_candidate") != 1
    ):
        raise ValueError("holdout budget violates aggregate-only one-shot policy")
    status = budget.get("status")
    if status not in SUPPORTED_BUDGET_STATUSES:
        raise ValueError(f"holdout budget status is unsupported: status={status}")
    expected_fields = (
        BUDGET_CONFIGURED_FIELDS
        if status == "configured_external_evaluator"
        else BUDGET_COMMON_FIELDS
    )
    if set(budget) != expected_fields:
        raise ValueError(
            "holdout budget fields differ from its exact status schema: "
            f"status={status}, missing={sorted(expected_fields.difference(budget))}, "
            f"unexpected={sorted(set(budget).difference(expected_fields))}"
        )
    maximum_total = _positive_integer(
        budget.get("maximum_total_submissions"),
        "maximum_total_submissions",
        False,
    )
    submissions_used = _positive_integer(
        budget.get("submissions_used"),
        "submissions_used",
        True,
    )
    if submissions_used > maximum_total:
        raise ValueError("holdout budget consumed submissions exceed the global maximum")
    metric_ids = budget.get("allowed_aggregate_metric_ids")
    if (
        not isinstance(metric_ids, list)
        or not metric_ids
        or any(not isinstance(metric_id, str) or not metric_id for metric_id in metric_ids)
        or len(metric_ids) != len(set(metric_ids))
        or any(
            any(term in metric_id.lower() for term in PROHIBITED_REQUEST_TERMS)
            for metric_id in metric_ids
        )
    ):
        raise ValueError("holdout budget aggregate metric IDs must be unique non-empty strings")
    candidate_submissions = budget.get("candidate_submissions")
    frozen_hash_submissions = budget.get("frozen_hash_submissions")
    if not isinstance(candidate_submissions, dict) or not isinstance(frozen_hash_submissions, dict):
        raise ValueError("holdout budget lacks candidate and specification-hash accounting")
    if (
        submissions_used != len(candidate_submissions)
        or submissions_used != len(frozen_hash_submissions)
    ):
        raise ValueError("holdout budget submission count differs from its identity maps")
    if status == "not_configured_no_external_evaluator":
        if submissions_used != 0 or candidate_submissions or frozen_hash_submissions:
            raise ValueError("unconfigured sealed evaluator requires empty zero-use accounting")
        evaluator_id: str | None = None
        evaluator_version: str | None = None
    else:
        raw_evaluator_id = budget.get("evaluator_id")
        raw_evaluator_version = budget.get("evaluator_version")
        if (
            not isinstance(raw_evaluator_id, str)
            or not raw_evaluator_id
            or not isinstance(raw_evaluator_version, str)
            or not raw_evaluator_version
        ):
            raise ValueError("configured holdout budget requires evaluator identity and version")
        evaluator_id = raw_evaluator_id
        evaluator_version = raw_evaluator_version
    request_ids: set[str] = set()
    observed_hashes: set[str] = set()
    for candidate_id, raw_record in candidate_submissions.items():
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(raw_record, dict)
            or set(raw_record) != SUBMISSION_RECORD_FIELDS
        ):
            raise ValueError("holdout budget candidate submission record is malformed")
        record = cast(dict[str, object], raw_record)
        if record.get("candidate_id") != candidate_id:
            raise ValueError("holdout budget candidate key differs from its bound record")
        frozen_hash = record.get("frozen_specification_hash")
        if not isinstance(frozen_hash, str):
            raise ValueError(
                f"holdout budget candidate lacks a frozen hash: candidate_id={candidate_id}"
            )
        require_sha256(frozen_hash, "frozen_specification_hash")
        request_id = record.get("request_id")
        requested_at = record.get("requested_at")
        if (
            record.get("submission_count") != 1
            or not isinstance(request_id, str)
            or not request_id.startswith(SEALED_REQUEST_PREFIX)
            or len(request_id) != len(SEALED_REQUEST_PREFIX) + 24
            or any(
                character not in "0123456789abcdef"
                for character in request_id[len(SEALED_REQUEST_PREFIX) :]
            )
            or not isinstance(requested_at, str)
        ):
            raise ValueError(
                f"holdout budget candidate submission is not one-shot: candidate_id={candidate_id}"
            )
        require_utc_iso(requested_at)
        if request_id in request_ids or frozen_hash in observed_hashes:
            raise ValueError("holdout budget reuses a request or frozen specification identity")
        if (
            record.get("evaluator_id") != evaluator_id
            or record.get("evaluator_version") != evaluator_version
        ):
            raise ValueError("holdout budget submission evaluator binding mismatch")
        if record.get("aggregate_metric_ids") != metric_ids:
            raise ValueError("holdout budget submission metric binding mismatch")
        request_ids.add(request_id)
        observed_hashes.add(frozen_hash)
        if frozen_hash_submissions.get(frozen_hash) != raw_record:
            raise ValueError(
                "holdout budget candidate and frozen-hash maps disagree: "
                f"candidate_id={candidate_id}, frozen_hash={frozen_hash}"
            )
    if set(frozen_hash_submissions) != observed_hashes:
        raise ValueError("holdout budget frozen-hash map contains an unpaired identity")
    for frozen_hash, raw_record in frozen_hash_submissions.items():
        if not isinstance(frozen_hash, str):
            raise ValueError("holdout budget frozen-hash key must be a SHA-256 string")
        require_sha256(frozen_hash, "frozen_specification_hash")
        if not isinstance(raw_record, dict) or set(raw_record) != SUBMISSION_RECORD_FIELDS:
            raise ValueError("holdout budget frozen-hash submission record is malformed")
        candidate_id = raw_record.get("candidate_id")
        if (
            raw_record.get("frozen_specification_hash") != frozen_hash
            or not isinstance(candidate_id, str)
            or candidate_submissions.get(candidate_id) != raw_record
        ):
            raise ValueError("holdout budget frozen-hash reverse binding mismatch")
    return {
        "file_sha256": file_sha256(path),
        "status": status,
        "submissions_used": submissions_used,
        "maximum_total_submissions": maximum_total,
        "candidate_identity_count": len(candidate_submissions),
        "frozen_hash_identity_count": len(frozen_hash_submissions),
        "allowed_aggregate_metric_ids": list(metric_ids),
        "evaluator_id": evaluator_id,
        "evaluator_version": evaluator_version,
    }


def _ledger_state(path: Path) -> dict[str, object]:
    records = verify_hash_chained_ledger(path)
    anchor_path = ledger_anchor_path(path).resolve(strict=True)
    anchor = _json_mapping(anchor_path)
    head_hash = str(records[-1]["entry_hash"]) if records else GENESIS_HASH
    return {
        "file_sha256": file_sha256(path),
        "anchor_file": anchor_path.name,
        "anchor_file_sha256": file_sha256(anchor_path),
        "anchor_hash": anchor["anchor_hash"],
        "head_hash": head_hash,
        "record_count": len(records),
    }


def _verify_forward_execution_observation(record: dict[str, object]) -> None:
    if any(
        not isinstance(record.get(field_name), str) or not record.get(field_name)
        for field_name in FORWARD_EXECUTION_OBSERVATION_STRING_FIELDS
    ):
        raise ValueError("forward execution observation lacks required string fields")
    if (
        record.get("candidate_mode") != "options_expression"
        or record.get("fill_status") not in {"filled", "missed"}
        or record.get("evidence_class") != "prospective_market_evidence"
        or record.get("opportunity_synthetic") is not False
        or record.get("profitability_evidence_eligible") is not True
    ):
        raise ValueError("forward execution observation authority or status is invalid")
    event_time = cast(str, record["event_time"])
    recorder_issued_at = cast(str, record["recorder_issued_at"])
    require_utc_iso(event_time)
    require_utc_iso(recorder_issued_at)
    fill_artifact_hash = cast(str, record["fill_artifact_hash"])
    recorder_receipt_body_hash = cast(str, record["recorder_receipt_body_hash"])
    require_sha256(fill_artifact_hash, "fill_artifact_hash")
    require_sha256(recorder_receipt_body_hash, "recorder_receipt_body_hash")
    raw_fill_artifact = record.get("fill_artifact")
    if not isinstance(raw_fill_artifact, dict):
        raise ValueError("forward execution observation fill artifact must be a mapping")
    fill_artifact = cast(dict[str, JsonValue], raw_fill_artifact)
    if canonical_hash(cast(JsonValue, fill_artifact)) != fill_artifact_hash:
        raise ValueError("forward execution observation fill artifact hash mismatch")
    if (
        fill_artifact.get("observation_id") != record["fill_observation_id"]
        or fill_artifact.get("ticket_id") != record["ticket_id"]
        or fill_artifact.get("witnessed_at") != event_time
        or fill_artifact.get("paper_fill_status") != record["fill_status"]
        or fill_artifact.get("evidence_class") != "prospective_market_evidence"
        or fill_artifact.get("profitability_evidence_eligible") is not True
        or fill_artifact.get("realized_evidence") is not False
        or fill_artifact.get("paper_only") is not True
        or fill_artifact.get("live_blocked") is not True
    ):
        raise ValueError("forward execution observation fill artifact binding is invalid")
    raw_receipt_body = record.get("recorder_receipt_body")
    if not isinstance(raw_receipt_body, dict):
        raise ValueError("forward execution observation receipt body must be a mapping")
    receipt_body = cast(dict[str, JsonValue], raw_receipt_body)
    if set(receipt_body) != FORWARD_RECEIPT_BODY_FIELDS:
        raise ValueError("forward execution observation receipt body schema is invalid")
    expected_receipt_bindings: dict[str, JsonValue] = {
        "schema_version": "dopey-forward-evidence-receipt-v1",
        "environment_id": ENVIRONMENT_ID,
        "purpose": "forward_record",
        "candidate_id": cast(str, record["candidate_id"]),
        "frozen_specification_hash": cast(
            str,
            record["frozen_specification_hash"],
        ),
        "record_id": cast(str, record["execution_observation_id"]),
        "subject_artifact_hash": fill_artifact_hash,
        "issued_at": recorder_issued_at,
    }
    if any(
        receipt_body.get(field_name) != expected_value
        for field_name, expected_value in expected_receipt_bindings.items()
    ):
        raise ValueError("forward execution observation receipt binding is invalid")
    if (
        not isinstance(receipt_body.get("signer_id"), str)
        or not receipt_body["signer_id"]
        or not isinstance(receipt_body.get("signer_version"), str)
        or not receipt_body["signer_version"]
        or canonical_hash(cast(JsonValue, receipt_body))
        != recorder_receipt_body_hash
    ):
        raise ValueError("forward execution observation receipt identity is invalid")
    signature_base64 = cast(str, record["recorder_signature_base64"])
    try:
        signature = base64.b64decode(signature_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            "forward execution observation signature is not valid base64"
        ) from error
    if (
        len(signature) != 64
        or base64.b64encode(signature).decode("ascii") != signature_base64
    ):
        raise ValueError(
            "forward execution observation signature bytes are not canonical Ed25519"
        )


def _forward_ledger_state(path: Path) -> dict[str, object]:
    records = verify_hash_chained_ledger(path)
    if not records:
        raise ValueError("forward evidence ledger requires an explicit initialization record")
    initialization = records[0]
    if (
        initialization.get("record_type") != "forward_evidence_initialization"
        or initialization.get("environment_id") != ENVIRONMENT_ID
        or initialization.get("status") != "initialized_no_forward_evidence"
        or initialization.get("substantive_trial") is not False
        or initialization.get("paper_only") is not True
        or initialization.get("live_blocked") is not True
    ):
        raise ValueError("forward evidence ledger initialization is invalid")
    decision_count = 0
    execution_observation_count = 0
    settlement_count = 0
    for record in records[1:]:
        record_type = record.get("record_type")
        if record_type not in FORWARD_RECORD_TYPES:
            raise ValueError(f"forward evidence record type is unsupported: record_type={record_type}")
        candidate_id = record.get("candidate_id")
        frozen_hash = record.get("frozen_specification_hash")
        if not isinstance(candidate_id, str) or not candidate_id or not isinstance(
            frozen_hash, str
        ):
            raise ValueError("forward evidence record lacks candidate and frozen-specification identity")
        require_sha256(frozen_hash, "frozen_specification_hash")
        if (
            record.get("environment_id") != ENVIRONMENT_ID
            or record.get("evidence_kind") != "prospective_paper"
            or record.get("paper_only") is not True
            or record.get("live_blocked") is not True
            or record.get("replay") is not False
            or record.get("backtest") is not False
            or record.get("realized_evidence") is not False
        ):
            raise ValueError("forward evidence record violates prospective paper authority")
        if record_type == "forward_decision":
            decision_count += 1
        elif record_type == "forward_execution_observation":
            _verify_forward_execution_observation(record)
            execution_observation_count += 1
        else:
            settlement_count += 1
    return {
        **_ledger_state(path),
        "initialization_status": "initialized_no_forward_evidence",
        "forward_decision_count": decision_count,
        "forward_execution_observation_record_count": execution_observation_count,
        "forward_settlement_count": settlement_count,
    }


def _audit_dynamic_state(
    repository_root: Path,
    protected_manifest_sha256: str,
    external_trust_root_path: Path | None,
) -> dict[str, object]:
    root = repository_root.resolve(strict=True)
    experiment_state = _ledger_state(root / "EXPERIMENT_REGISTRY.jsonl")
    proof_state = _ledger_state(root / "PROOF_LEDGER.jsonl")
    forward_state = _forward_ledger_state(root / "shadow_trading" / "FORWARD_EVIDENCE.jsonl")
    registry_states = {
        path: _registry_state(root / path, identity_field)
        for path, identity_field in sorted(REGISTRY_IDENTITIES.items())
    }
    approach_family_count = _verify_approach_registry(root / "APPROACH_REGISTRY.jsonl")
    budget_state = _verify_holdout_budget(root / "HOLDOUT_BUDGET.json")
    file_hashes = {
        relative_path: file_sha256((root / relative_path).resolve(strict=True))
        for relative_path in sorted(ASCENDANCY_DYNAMIC_STATE_PATHS)
    }
    state_body: dict[str, object] = {
        "schema_version": "dopey-dynamic-state-audit-v1",
        "environment_id": ENVIRONMENT_ID,
        "files": file_hashes,
        "registries": registry_states,
        "approach_family_count": approach_family_count,
        "experiment_ledger": experiment_state,
        "proof_ledger": proof_state,
        "forward_evidence_ledger": forward_state,
        "holdout_budget": budget_state,
    }
    dynamic_state_hash = canonical_hash(cast(JsonValue, state_body))
    anchor_state = (
        dynamic_anchor_audit_state(
            root,
            dynamic_state_hash,
            protected_manifest_sha256,
        )
        if external_trust_root_path is None
        else dynamic_anchor_audit_state_with_external_root(
            root,
            dynamic_state_hash,
            protected_manifest_sha256,
            external_trust_root_path,
        )
    )
    return {
        **state_body,
        "dynamic_state_hash": dynamic_state_hash,
        **anchor_state,
    }


def audit_dynamic_state(
    repository_root: Path,
    protected_manifest_sha256: str,
) -> dict[str, object]:
    return _audit_dynamic_state(repository_root, protected_manifest_sha256, None)


def audit_dynamic_state_with_external_root(
    repository_root: Path,
    protected_manifest_sha256: str,
    external_trust_root_path: Path,
) -> dict[str, object]:
    return _audit_dynamic_state(
        repository_root,
        protected_manifest_sha256,
        external_trust_root_path,
    )


def _run_ascendancy_audit(
    repository_root: Path,
    source_manifest_path: Path,
    external_trust_root_path: Path | None,
) -> dict[str, object]:
    root = repository_root.resolve(strict=True)
    environment_path = root / "environments" / "environment_v1.json"
    verify_environment_freeze(environment_path, root / "ENVIRONMENT_V1_FREEZE.json")
    protected_manifest_path = root / "PROTECTED_MANIFEST.json"
    verify_ascendancy_protected_manifest(root, protected_manifest_path)
    protected_manifest_sha256 = file_sha256(protected_manifest_path)
    dynamic_state = _audit_dynamic_state(
        root,
        protected_manifest_sha256,
        external_trust_root_path,
    )
    data_manifest = _json_mapping(root / "DATA_MANIFEST.json")
    source_hash = file_sha256(source_manifest_path.resolve(strict=True))
    frozen_source_hash = str(data_manifest.get("source_manifest_sha256", ""))
    frozen_snapshot_semantics = (
        data_manifest.get("snapshot_semantics")
        == "frozen_evaluation_corpus_not_current_operational_state"
        and data_manifest.get("current_operational_manifest_claimed") is False
    )
    source_manifest_drifted = frozen_source_hash != source_hash
    if source_manifest_drifted and not frozen_snapshot_semantics:
        raise ValueError("source data manifest hash differs from the frozen data identity")
    if data_manifest.get("profitability_evidence_eligible") is not False:
        raise ValueError("development snapshot corpus cannot be profitability evidence")
    return {
        "schema_version": "dopey-ascendancy-audit-v1",
        "environment_id": "dopey-options-paper-v1",
        "status": "pass_fail_closed_research_kernel",
        "paper_only": True,
        "live_blocked": True,
        "action_ready": False,
        "approach_family_count": dynamic_state["approach_family_count"],
        "experiment_ledger_records": cast(
            dict[str, object], dynamic_state["experiment_ledger"]
        )["record_count"],
        "proof_ledger_records": cast(dict[str, object], dynamic_state["proof_ledger"])[
            "record_count"
        ],
        "dynamic_state": dynamic_state,
        "protected_manifest_sha256": protected_manifest_sha256,
        "repository_anchor_verified": dynamic_state["repository_anchor_verified"],
        "external_anchor_verified": dynamic_state["external_anchor_verified"],
        "external_trust_root_sha256": dynamic_state["external_trust_root_sha256"],
        "certification_eligible": dynamic_state["certification_eligible"],
        "source_manifest_sha256": source_hash,
        "frozen_source_manifest_sha256": frozen_source_hash,
        "source_manifest_binding_status": (
            "frozen_snapshot_drift_observed"
            if source_manifest_drifted
            else "frozen_snapshot_matches_observed_source"
            if frozen_snapshot_semantics
            else "legacy_current_binding_matches_observed_source"
        ),
        "source_manifest_drifted": source_manifest_drifted,
        "profitability_edge_demonstrated": False,
        "forward_shadow_ready": False,
    }


def run_ascendancy_audit(
    repository_root: Path,
    source_manifest_path: Path,
) -> dict[str, object]:
    return _run_ascendancy_audit(repository_root, source_manifest_path, None)


def run_ascendancy_audit_with_external_root(
    repository_root: Path,
    source_manifest_path: Path,
    external_trust_root_path: Path,
) -> dict[str, object]:
    return _run_ascendancy_audit(
        repository_root,
        source_manifest_path,
        external_trust_root_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--external-trust-root", type=Path)
    arguments = parser.parse_args()
    result = (
        run_ascendancy_audit(arguments.repository_root, arguments.source_manifest)
        if arguments.external_trust_root is None
        else run_ascendancy_audit_with_external_root(
            arguments.repository_root,
            arguments.source_manifest,
            arguments.external_trust_root,
        )
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
