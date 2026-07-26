"""Versioned, fail-closed contracts for DOPEY evidence-intelligence artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, TypedDict, cast

from .identity import canonical_hash


ARTIFACT_CONTRACT_REGISTRY_VERSION = "dopey-evidence-artifact-contract-registry-v1"


class ArtifactFieldRule(TypedDict, total=False):
    types: tuple[str, ...]
    const: object
    enum: tuple[object, ...]
    minimum: float


class ArtifactContract(TypedDict):
    contract_id: str
    artifact_type: str
    required_fields: dict[str, ArtifactFieldRule]
    description: str


class ArtifactContractError(ValueError):
    """Raised when a material evidence artifact violates its frozen contract."""


def _rule(types: tuple[str, ...]) -> ArtifactFieldRule:
    return {"types": types}


def _const(types: tuple[str, ...], value: object) -> ArtifactFieldRule:
    return {"types": types, "const": value}


ARTIFACT_CONTRACTS: dict[str, ArtifactContract] = {
    "strategy_dossier": {
        "contract_id": "strategy_dossier",
        "artifact_type": "strategy_evidence_dossier_summary",
        "description": "Content-addressed strategy scorecard and hard-gate verdict.",
        "required_fields": {
            "artifact_type": _const(("string",), "strategy_evidence_dossier_summary"),
            "dossier_version": _rule(("string",)),
            "run_id": _rule(("string",)),
            "dossier_status": _rule(("string",)),
            "candidate_count": {"types": ("integer",), "minimum": 0.0},
            "eligible_candidate_count": {"types": ("integer",), "minimum": 0.0},
            "trade_count": {"types": ("integer",), "minimum": 0.0},
            "truth_state": _rule(("object",)),
            "promotion_allowed": _const(("boolean",), False),
            "paper_only": _const(("boolean",), True),
            "live_blocked": _const(("boolean",), True),
        },
    },
    "capital_exposure": {
        "contract_id": "capital_exposure",
        "artifact_type": "strategy_capital_exposure_diagnostics",
        "description": "Model-premium exposure denominator diagnostics without a return claim.",
        "required_fields": {
            "artifact_type": _const(("string",), "strategy_capital_exposure_diagnostics"),
            "normalization_status": _rule(("string",)),
            "candidate_count": {"types": ("integer",), "minimum": 0.0},
            "candidate_diagnostics": _rule(("array",)),
            "annualized_return_available": _const(("boolean",), False),
            "profitability_claim_allowed": _const(("boolean",), False),
            "promotion_allowed": _const(("boolean",), False),
            "paper_only": _const(("boolean",), True),
            "live_blocked": _const(("boolean",), True),
        },
    },
    "mutation_genealogy": {
        "contract_id": "mutation_genealogy",
        "artifact_type": "mutation_genealogy_explorer",
        "description": "Current graph plus immutable historical search accounting.",
        "required_fields": {
            "artifact_type": _const(("string",), "mutation_genealogy_explorer"),
            "explorer_version": _rule(("string",)),
            "explorer_status": _const(("string",), "complete"),
            "registry_record_count": {"types": ("integer",), "minimum": 1.0},
            "node_count": {"types": ("integer",), "minimum": 1.0},
            "historical_search_budget": _rule(("object",)),
            "generation_history": _rule(("array",)),
            "champion_dynamics": _rule(("object",)),
            "promotion_allowed": _const(("boolean",), False),
            "paper_only": _const(("boolean",), True),
            "live_blocked": _const(("boolean",), True),
        },
    },
    "binomial_oracle": {
        "contract_id": "binomial_oracle",
        "artifact_type": "binomial_oracle_validation",
        "description": "Model-priced validation oracle kept separate from replay and fills.",
        "required_fields": {
            "artifact_type": _const(("string",), "binomial_oracle_validation"),
            "oracle_version": _rule(("string",)),
            "validation_status": _const(("string",), "complete"),
            "test_count": {"types": ("integer",), "minimum": 1.0},
            "passed_test_count": {"types": ("integer",), "minimum": 1.0},
            "separation_law": _rule(("object",)),
            "pricing_source_tier": _const(("string",), "model_priced_oracle"),
            "real_option_chain_absent": _const(("boolean",), True),
            "promotion_allowed": _const(("boolean",), False),
            "paper_only": _const(("boolean",), True),
            "live_blocked": _const(("boolean",), True),
        },
    },
    "context_settlement": {
        "contract_id": "context_settlement",
        "artifact_type": "external_context_outcome_update",
        "description": "Immutable-decision, append-only forward settlement operation.",
        "required_fields": {
            "artifact_type": _const(("string",), "external_context_outcome_update"),
            "settlement_version": _rule(("string",)),
            "operation_status": _const(("string",), "complete"),
            "decision_count": {"types": ("integer",), "minimum": 0.0},
            "resolved_count_after": {"types": ("integer",), "minimum": 0.0},
            "unresolved_count_after": {"types": ("integer",), "minimum": 0.0},
            "decision_ledger_immutable": _const(("boolean",), True),
            "synthetic_outcomes_used": _const(("boolean",), False),
            "paper_only": _const(("boolean",), True),
            "live_blocked": _const(("boolean",), True),
        },
    },
    "evidence_cycle": {
        "contract_id": "evidence_cycle",
        "artifact_type": "evidence_intelligence_cycle",
        "description": "Cohesive dossier, genealogy, oracle, capital, and contract audit cycle.",
        "required_fields": {
            "artifact_type": _const(("string",), "evidence_intelligence_cycle"),
            "cycle_version": _rule(("string",)),
            "cycle_status": _const(("string",), "complete"),
            "dossier_run_id": _rule(("string",)),
            "eligible_candidate_count": {"types": ("integer",), "minimum": 0.0},
            "mutation_node_count": {"types": ("integer",), "minimum": 1.0},
            "oracle_passed_test_count": {"types": ("integer",), "minimum": 1.0},
            "capital_normalization_status": _rule(("string",)),
            "contract_audit_status": _const(("string",), "complete"),
            "promotion_allowed": _const(("boolean",), False),
            "paper_only": _const(("boolean",), True),
            "live_blocked": _const(("boolean",), True),
        },
    },
}


def validate_artifact_record(
    contract_id: str,
    record: Mapping[str, object],
) -> dict[str, object]:
    """Return a deterministic validation record without weakening any issue."""

    contract = ARTIFACT_CONTRACTS.get(contract_id)
    if contract is None:
        raise KeyError(f"unknown artifact contract: contract_id={contract_id}")
    issues: list[dict[str, object]] = []
    for field_name, rule in contract["required_fields"].items():
        if field_name not in record:
            issues.append({
                "issue_id": "missing_required_field",
                "field": field_name,
                "expected_types": list(rule["types"]),
            })
            continue
        value = record[field_name]
        if not _matches_types(value, rule["types"]):
            issues.append({
                "issue_id": "field_type_mismatch",
                "field": field_name,
                "expected_types": list(rule["types"]),
                "actual_type": _json_type(value),
            })
            continue
        if "const" in rule and not _same_json_value(value, rule["const"]):
            issues.append({
                "issue_id": "field_const_mismatch",
                "field": field_name,
                "expected": rule["const"],
                "actual": value,
            })
        if "enum" in rule and not any(_same_json_value(value, allowed) for allowed in rule["enum"]):
            issues.append({
                "issue_id": "field_enum_mismatch",
                "field": field_name,
                "allowed": list(rule["enum"]),
                "actual": value,
            })
        if "minimum" in rule and isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < float(rule["minimum"]):
                issues.append({
                    "issue_id": "field_minimum_violation",
                    "field": field_name,
                    "minimum": rule["minimum"],
                    "actual": value,
                })
    if str(record.get("artifact_type", "")) != contract["artifact_type"]:
        issues.append({
            "issue_id": "artifact_type_mismatch",
            "field": "artifact_type",
            "expected": contract["artifact_type"],
            "actual": record.get("artifact_type"),
        })
    return {
        "contract_id": contract_id,
        "contract_registry_version": ARTIFACT_CONTRACT_REGISTRY_VERSION,
        "contract_status": "complete" if not issues else "failed",
        "issue_count": len(issues),
        "issues": issues,
        "artifact_hash": canonical_hash(dict(record)),
    }


def assert_artifact_record(contract_id: str, record: Mapping[str, object]) -> None:
    """Raise one actionable error if an artifact violates its declared contract."""

    validation = validate_artifact_record(contract_id, record)
    if validation["contract_status"] != "complete":
        raise ArtifactContractError(
            "DOPEY evidence artifact contract failed: "
            f"contract_id={contract_id}, issues={validation['issues']}"
        )


def write_artifact_contract_registry(output_directory: Path) -> dict[str, object]:
    """Emit machine-readable JSON Schemas and one content-addressed registry."""

    resolved_output = output_directory.resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    schema_records: list[dict[str, object]] = []
    for contract_id, contract in sorted(ARTIFACT_CONTRACTS.items()):
        schema = _json_schema(contract)
        schema_path = resolved_output / f"{contract_id}.schema.json"
        _write_json_atomic(schema_path, schema)
        schema_records.append({
            "contract_id": contract_id,
            "artifact_type": contract["artifact_type"],
            "schema_path": str(schema_path),
            "schema_hash": _file_sha256(schema_path),
        })
    registry: dict[str, object] = {
        "artifact_type": "evidence_artifact_contract_registry",
        "registry_version": ARTIFACT_CONTRACT_REGISTRY_VERSION,
        "contract_count": len(schema_records),
        "contracts": schema_records,
        "mutation_authority": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    registry["registry_hash"] = canonical_hash(registry)
    _write_json_atomic(resolved_output / "registry.json", registry)
    return registry


def audit_evidence_artifact_bundle(
    repository_root: Path,
    output_path: Path,
) -> dict[str, object]:
    """Validate the evidence bundle and its cross-artifact causal identities."""

    root = repository_root.resolve()
    source_paths = {
        "strategy_dossier": root / "artifacts" / "dopey" / "runs" / "latest_dossier.json",
        "capital_exposure": root / "artifacts" / "dopey" / "runs" / "latest_capital_exposure.json",
        "mutation_genealogy": root / "artifacts" / "dopey" / "evolution" / "mutation_genealogy.json",
        "binomial_oracle": root / "artifacts" / "dopey" / "options_oracle" / "binomial_oracle_validation.json",
        "context_settlement": root / "artifacts" / "dopey" / "equity_swing" / "latest_context_settlement.json",
    }
    records = {contract_id: _read_json_object(path) for contract_id, path in source_paths.items()}
    validations = {
        contract_id: validate_artifact_record(contract_id, record)
        for contract_id, record in records.items()
    }
    issues: list[dict[str, object]] = [
        {
            "issue_id": "artifact_contract_failed",
            "contract_id": contract_id,
            "issues": validation["issues"],
        }
        for contract_id, validation in validations.items()
        if validation["contract_status"] != "complete"
    ]
    dossier = records["strategy_dossier"]
    capital = records["capital_exposure"]
    genealogy = records["mutation_genealogy"]
    oracle = records["binomial_oracle"]
    cross_checks = (
        ("capital_candidate_count_matches_dossier", capital.get("candidate_count"), dossier.get("candidate_count")),
        (
            "genealogy_generation_count_matches_registry_records",
            len(cast(list[object], genealogy.get("generation_history", []))),
            genealogy.get("registry_record_count"),
        ),
        ("oracle_all_invariants_pass", oracle.get("passed_test_count"), oracle.get("test_count")),
    )
    for check_id, actual, expected in cross_checks:
        if actual != expected:
            issues.append({
                "issue_id": "cross_artifact_identity_mismatch",
                "check_id": check_id,
                "actual": actual,
                "expected": expected,
            })
    registry = write_artifact_contract_registry(root / "artifacts" / "dopey" / "contracts")
    result: dict[str, object] = {
        "artifact_type": "evidence_artifact_bundle_audit",
        "audit_version": "dopey-evidence-artifact-bundle-audit-v1",
        "audit_status": "complete" if not issues else "failed",
        "contract_registry_hash": registry["registry_hash"],
        "artifact_count": len(records),
        "validations": validations,
        "cross_artifact_issue_count": len(issues),
        "issues": issues,
        "source_paths": {key: str(path) for key, path in source_paths.items()},
        "source_hashes": {key: _file_sha256(path) for key, path in source_paths.items()},
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    result["audit_hash"] = canonical_hash(result)
    _write_json_atomic(output_path, result)
    if issues:
        raise ArtifactContractError(
            "DOPEY evidence artifact bundle audit failed: "
            f"output_path={output_path.resolve()}, issues={issues}"
        )
    return result


def _json_schema(contract: ArtifactContract) -> dict[str, object]:
    properties: dict[str, object] = {}
    for field_name, rule in contract["required_fields"].items():
        property_rule: dict[str, object] = {
            "type": list(rule["types"]) if len(rule["types"]) > 1 else rule["types"][0],
        }
        if "const" in rule:
            property_rule["const"] = rule["const"]
        if "enum" in rule:
            property_rule["enum"] = list(rule["enum"])
        if "minimum" in rule:
            property_rule["minimum"] = rule["minimum"]
        properties[field_name] = property_rule
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://dopey.local/contracts/{contract['contract_id']}.schema.json",
        "title": contract["contract_id"],
        "description": contract["description"],
        "type": "object",
        "required": sorted(contract["required_fields"]),
        "properties": properties,
        "additionalProperties": True,
    }


def _matches_types(value: object, expected_types: Iterable[str]) -> bool:
    actual = _json_type(value)
    return actual in set(expected_types)


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return type(value).__name__


def _same_json_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"contract audit source is missing: path={path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"contract audit source must contain one object: path={path}")
    return cast(dict[str, object], value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
