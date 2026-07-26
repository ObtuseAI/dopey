"""Central registry for unresolved autonomous DOPEY gaps."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_json, stable_hash, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "full_autonomy"
REGISTRY_PATH = ARTIFACT_DIR / "remaining_gap_registry.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "remaining_gap_eliminator_summary.json"
PROOF_PATH = ARTIFACT_DIR / "remaining_gap_eliminator_proof.jsonl"


def run_remaining_gap_eliminator() -> dict[str, Any]:
    gaps = _gap_records()
    solved = sum(1 for gap in gaps if gap["gap_status"] == "autonomously_solved")
    blocked = sum(1 for gap in gaps if gap["gap_status"] == "blocked_by_policy")
    fallback = sum(1 for gap in gaps if gap["fallback_path"])
    summary = {
        "artifact_type": "remaining_gap_eliminator_summary",
        "gap_eliminator_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "remaining_gap_count": len(gaps),
        "autonomously_solved_gap_count": solved,
        "blocked_by_policy_gap_count": blocked,
        "fallback_gap_count": fallback,
        "manual_review_dependency_count": 0,
        "operator_action_required_count": 0,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "live_trading_enabled": False,
        "strategy_promotion_allowed": False,
        "profitability_claim": False,
        "live_readiness_claim": False,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(REGISTRY_PATH, gaps)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("remaining-gap-eliminator-proof-v1", "completed", summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "remaining_gap_registry": str(REGISTRY_PATH),
        "remaining_gap_eliminator_summary": str(SUMMARY_PATH),
        "remaining_gap_eliminator_proof": str(PROOF_PATH),
    }


def _gap_records() -> list[dict[str, Any]]:
    gap_inputs = [
        ("open_ohlcv_source_gap", "blocked_by_policy", False, "OpenBB and open-data discovery attempted", "no machine-admissible OHLCV source accepted", "model_priced_research_only", "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"),
        ("open_historical_options_quote_chain_gap", "blocked_by_policy", False, "OpenBB and open-data options paths classified", "no machine-admissible open historical options quote/chain data accepted", "model_priced_not_quote_evidence", "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"),
        ("quote_priced_evidence_gap", "blocked_by_policy", False, "Quote unlock gate evaluated", "quote-priced backtest remains blocked", "model_priced_options_research_v2", "DOPEY_REAL_OPTIONS_HONEST_BACKTESTER_V1"),
        ("accepted_data_validation_gap", "blocked_by_policy", False, "OpenBB/open-data validator bridges evaluated", "valid real dataset unavailable", "paper_only_model_priced", "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"),
        ("openbb_availability_gap", _openbb_gap_status(), True, "OpenBB runtime detector executed", _openbb_result(), "adapter_ready_without_install", "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"),
        ("openbb_provider_admissibility_gap", "autonomously_solved", True, "OpenBB provider registry classified providers", "unsafe providers rejected", "no_key_no_paid_probe_only", "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"),
        ("model_priced_evidence_limitation", "autonomously_solved", True, "Model-priced V2 completed and labeled non-evidence", "model-priced artifacts complete", "model_priced_not_quote_evidence", "DOPEY_PAPER_ONLY_MODEL_PRICED_AUTONOMOUS_ROTATION_HARDENING_V1"),
        ("paper_loop_data_gap", "blocked_by_policy", False, "Paper rotation engine completed", "blocked without accepted real data", "blocked_no_accepted_real_data", "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2"),
        ("s_tier_proof_gap", "autonomously_solved", True, "S-tier V2 engineering target completed", "engineering target complete without superiority claim", "paper_only_s_tier_engineering", "DOPEY_PAPER_ONLY_MODEL_PRICED_AUTONOMOUS_ROTATION_HARDENING_V1"),
        ("export_audit_timeout_gap", "blocked_by_policy", False, "Expensive lanes capped", "timeouts recorded as inconclusive, not pass", "watchdog_safe_validation", "DOPEY_EXPORT_AUDIT_TIMEOUT_SHARDING_V1"),
    ]
    return [_gap_record(index, item) for index, item in enumerate(gap_inputs)]


def _gap_record(index: int, item: tuple[str, str, bool, str, str, str, str]) -> dict[str, Any]:
    gap_id, status, can_solve, attempted, result, fallback, target = item
    record = {
        "artifact_type": "remaining_gap_registry",
        "gap_id": gap_id,
        "gap_status": status,
        "can_be_solved_autonomously": can_solve,
        "attempted_resolution": attempted,
        "resolution_result": result,
        "fallback_path": fallback,
        "next_engineering_target": target,
        "manual_review_required": False,
        "operator_action_required": False,
        "paper_only": True,
        "live_blocked": True,
        "strategy_promotion_allowed": False,
    }
    record["gap_hash"] = stable_hash({"index": index, **record})
    return record


def _openbb_gap_status() -> str:
    runtime = read_json(ARTIFACT_ROOT / "openbb_autonomy" / "openbb_runtime_status.json")
    return "autonomously_solved" if runtime.get("openbb_import_available") else "blocked_by_policy"


def _openbb_result() -> str:
    runtime = read_json(ARTIFACT_ROOT / "openbb_autonomy" / "openbb_runtime_status.json")
    return str(runtime.get("openbb_runtime_status", "not_installed_adapter_ready"))
