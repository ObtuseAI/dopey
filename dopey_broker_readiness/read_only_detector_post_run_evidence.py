"""Post-run evidence contract for the read-only detector."""
from __future__ import annotations

from typing import Any

from .broker_readiness_models import stable_hash
from .read_only_detector_models import READ_ONLY_DETECTOR_NEXT_GATE


def build_read_only_detector_post_run_evidence(
    run_request: dict[str, Any],
    run_result: dict[str, Any],
    provider_health: dict[str, Any],
    capability_records: list[dict[str, Any]],
    blocked_records: list[dict[str, Any]],
    approval_proof: dict[str, Any],
    pre_run_proof: dict[str, Any],
) -> dict[str, Any]:
    safety_summary = {
        "no_credential_access": run_result["credential_access_attempted"] is False,
        "no_live_order_access": run_result["live_order_attempted"] is False,
        "no_order_placement": run_result["order_placement_attempted"] is False,
        "no_order_cancellation": run_result["order_cancellation_attempted"] is False,
        "no_scheduler": run_result["scheduler_attempted"] is False,
        "no_real_sizing": run_result["real_sizing_attempted"] is False,
        "no_account_balance_or_buying_power": provider_health.get("account_balance_dependency") is False and provider_health.get("buying_power_dependency") is False,
        "no_broker_mutation": provider_health.get("broker_mutation_attempted") is False,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
    }
    seed = {
        "artifact_type": "read_only_detector_post_run_evidence",
        "run_id": run_result["run_id"],
        "request_id": run_request["request_id"],
        "approval_proof_consumed": bool(approval_proof),
        "approval_proof_hash": approval_proof.get("proof_hash", ""),
        "pre_run_safety_proof_consumed": bool(pre_run_proof),
        "pre_run_safety_proof_hash": pre_run_proof.get("proof_hash", ""),
        "provider_type_used": provider_health.get("provider_type", "none"),
        "capability_records_written": len(capability_records),
        "blocked_write_execute_records_written": len(blocked_records),
        "no_credential_access": safety_summary["no_credential_access"],
        "no_live_order_access": safety_summary["no_live_order_access"],
        "no_order_placement": safety_summary["no_order_placement"],
        "no_order_cancellation": safety_summary["no_order_cancellation"],
        "no_scheduler": safety_summary["no_scheduler"],
        "no_real_sizing": safety_summary["no_real_sizing"],
        "no_account_balance": provider_health.get("account_balance_dependency") is False,
        "no_buying_power": provider_health.get("buying_power_dependency") is False,
        "no_broker_mutation": safety_summary["no_broker_mutation"],
        "post_run_detector_result": run_result,
        "post_run_safety_summary": safety_summary,
        "next_required_gate": READ_ONLY_DETECTOR_NEXT_GATE,
        "paper_only": True,
        "live_blocked": True,
        "evidence_hash": "",
    }
    return {**seed, "evidence_hash": stable_hash(seed)}
