"""Capability extraction plans and adapter boundaries for OSS candidates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .oss_models import OSS_STACK_VERSION, OssAdapterContract, OssCapabilityExtractionPlan


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "open_source"
OSS_CAPABILITY_EXTRACTION_PLAN_PATH = ARTIFACT_DIR / "oss_capability_extraction_plan.jsonl"
OSS_ADAPTER_CONTRACTS_PATH = ARTIFACT_DIR / "oss_adapter_contracts.jsonl"

CAPABILITY_CATEGORIES: tuple[str, ...] = (
    "event loop architecture",
    "portfolio/risk model",
    "fill/slippage model",
    "indicator library",
    "feature engineering",
    "options pricing/math",
    "volatility modeling",
    "ML model training workflow",
    "RL environment workflow",
    "data-quality validation",
    "benchmark/reporting",
    "explainability/audit trail",
)


def build_capability_extraction_plans() -> list[OssCapabilityExtractionPlan]:
    return [
        OssCapabilityExtractionPlan(
            artifact_type="oss_capability_extraction_plan",
            oss_stack_version=OSS_STACK_VERSION,
            capability_id=f"oss-capability-{index:02d}",
            capability_category=category,
            extraction_mode="reference_pattern_only_no_external_execution",
            allowed_output="candidate_signal_or_diagnostic_only",
            no_external_execution_required=True,
            approval_required=True,
            paper_only=True,
            live_blocked=True,
            capability_hash="",
        )
        for index, category in enumerate(CAPABILITY_CATEGORIES, start=1)
    ]


def build_adapter_contracts() -> list[OssAdapterContract]:
    candidate_ids = ["oss-quantlib", "oss-qlib", "oss-finrl", "oss-yfinance-style", "oss-fred-tools"]
    return [
        OssAdapterContract(
            artifact_type="oss_adapter_contracts",
            oss_stack_version=OSS_STACK_VERSION,
            adapter_id=f"oss-adapter-contract-{index:02d}",
            candidate_id=candidate_id,
            external_component_cannot_call_broker=True,
            external_component_cannot_fetch_network_data_unless_approved=True,
            external_component_cannot_place_orders=True,
            external_component_cannot_write_credentials=True,
            external_component_cannot_modify_promotion_gates=True,
            external_component_cannot_override_statistical_truth_or_fitness_gates=True,
            output_authority="candidate_signal_or_diagnostic_only",
            paper_only=True,
            live_blocked=True,
            adapter_hash="",
        )
        for index, candidate_id in enumerate(candidate_ids, start=1)
    ]


def write_capability_extraction_artifacts() -> dict[str, Any]:
    capability_records = [plan.to_dict() for plan in build_capability_extraction_plans()]
    adapter_records = [contract.to_dict() for contract in build_adapter_contracts()]
    _write_jsonl(OSS_CAPABILITY_EXTRACTION_PLAN_PATH, capability_records)
    _write_jsonl(OSS_ADAPTER_CONTRACTS_PATH, adapter_records)
    return {
        "capability_plan_count": len(capability_records),
        "adapter_contract_count": len(adapter_records),
        "artifact_paths": {
            "oss_capability_extraction_plan": str(OSS_CAPABILITY_EXTRACTION_PLAN_PATH),
            "oss_adapter_contracts": str(OSS_ADAPTER_CONTRACTS_PATH),
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
