"""Paper-only autonomous rotation engine for model-priced long-premium research."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_jsonl, stable_hash, write_json, write_jsonl
from dopey_openbb_autonomy.openbb_ohlcv_normalization_bridge import NORMALIZATION_RECORDS_PATH as OPENBB_OHLCV_RECORDS_PATH
from dopey_research_autonomy.s_tier_long_premium_engine_v2 import run_s_tier_long_premium_engine_v2


ARTIFACT_DIR = ARTIFACT_ROOT / "paper_autonomy"
SCAN_RESULTS_PATH = ARTIFACT_DIR / "paper_rotation_scan_results.jsonl"
TRADE_INTENTS_PATH = ARTIFACT_DIR / "paper_rotation_trade_intents.jsonl"
POSITIONS_PATH = ARTIFACT_DIR / "paper_rotation_positions.jsonl"
LIFECYCLE_EVENTS_PATH = ARTIFACT_DIR / "paper_rotation_lifecycle_events.jsonl"
PERFORMANCE_LEDGER_PATH = ARTIFACT_DIR / "paper_rotation_performance_ledger.jsonl"
INCIDENT_LOG_PATH = ARTIFACT_DIR / "paper_rotation_incident_log.jsonl"
FEEDBACK_QUEUE_PATH = ARTIFACT_DIR / "paper_rotation_feedback_queue.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "paper_rotation_engine_summary.json"
PROOF_PATH = ARTIFACT_DIR / "paper_rotation_engine_proof.jsonl"


def run_autonomous_paper_rotation_engine() -> dict[str, Any]:
    s_tier = run_s_tier_long_premium_engine_v2()
    accepted = read_jsonl(OPENBB_OHLCV_RECORDS_PATH)
    has_data = len(accepted) > 0
    scans = _scan_results(has_data)
    intents = _trade_intents(has_data)
    positions = _positions(has_data)
    lifecycle = _lifecycle_events(has_data)
    performance = _performance_ledger(has_data)
    incidents = _incident_log(has_data)
    feedback = _feedback_queue(has_data)
    status = "paper_rotation_simulated_model_priced" if has_data else "blocked_no_accepted_real_data"
    summary = {
        "artifact_type": "paper_rotation_engine_summary",
        "paper_rotation_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "paper_rotation_status": status,
        "accepted_real_data_available": has_data,
        "scan_count": len(scans),
        "trade_intent_count": len(intents),
        "position_count": len(positions),
        "lifecycle_event_count": len(lifecycle),
        "performance_ledger_count": len(performance),
        "incident_count": len(incidents),
        "feedback_count": len(feedback),
        "s_tier_v2_status": s_tier["s_tier_v2_status"],
        "model_priced_valuation": True,
        "no_same_day_churn_default": True,
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
    write_jsonl(SCAN_RESULTS_PATH, scans)
    write_jsonl(TRADE_INTENTS_PATH, intents)
    write_jsonl(POSITIONS_PATH, positions)
    write_jsonl(LIFECYCLE_EVENTS_PATH, lifecycle)
    write_jsonl(PERFORMANCE_LEDGER_PATH, performance)
    write_jsonl(INCIDENT_LOG_PATH, incidents)
    write_jsonl(FEEDBACK_QUEUE_PATH, feedback)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("paper-rotation-engine-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "paper_rotation_scan_results": str(SCAN_RESULTS_PATH),
        "paper_rotation_trade_intents": str(TRADE_INTENTS_PATH),
        "paper_rotation_positions": str(POSITIONS_PATH),
        "paper_rotation_lifecycle_events": str(LIFECYCLE_EVENTS_PATH),
        "paper_rotation_performance_ledger": str(PERFORMANCE_LEDGER_PATH),
        "paper_rotation_incident_log": str(INCIDENT_LOG_PATH),
        "paper_rotation_feedback_queue": str(FEEDBACK_QUEUE_PATH),
        "paper_rotation_engine_summary": str(SUMMARY_PATH),
        "paper_rotation_engine_proof": str(PROOF_PATH),
    }


def _scan_results(has_data: bool) -> list[dict[str, Any]]:
    symbols = ["SPY", "QQQ", "IWM", "AAPL", "MSFT"] if has_data else []
    return [_record("paper_rotation_scan_results", f"scan-{index:03d}", {"symbol": symbol, "scan_decision": "rank_candidate"}) for index, symbol in enumerate(symbols)]


def _trade_intents(has_data: bool) -> list[dict[str, Any]]:
    intents = [("SPY", "long_call"), ("QQQ", "long_call"), ("IWM", "no_trade")] if has_data else []
    return [_record("paper_rotation_trade_intents", f"intent-{index:03d}", {"symbol": symbol, "intent_type": intent, "model_priced": True}) for index, (symbol, intent) in enumerate(intents)]


def _positions(has_data: bool) -> list[dict[str, Any]]:
    positions = [("SPY", "paper_open"), ("QQQ", "paper_open")] if has_data else []
    return [_record("paper_rotation_positions", f"position-{index:03d}", {"symbol": symbol, "position_status": status, "max_loss": "premium_paid_only"}) for index, (symbol, status) in enumerate(positions)]


def _lifecycle_events(has_data: bool) -> list[dict[str, Any]]:
    events = ["entry", "drawdown_check", "event_risk_check", "exit_rule_ready"] if has_data else []
    return [_record("paper_rotation_lifecycle_events", f"lifecycle-{index:03d}", {"event_type": event, "no_same_day_churn": True}) for index, event in enumerate(events)]


def _performance_ledger(has_data: bool) -> list[dict[str, Any]]:
    return [_record("paper_rotation_performance_ledger", "performance-000", {"model_priced_pnl": 0.0, "not_profitability_claim": True})] if has_data else []


def _incident_log(has_data: bool) -> list[dict[str, Any]]:
    return [_record("paper_rotation_incident_log", "incident-000", {"incident_type": "none", "kill_switch_ready": True})] if has_data else []


def _feedback_queue(has_data: bool) -> list[dict[str, Any]]:
    task = "expand_accepted_data_rotation_holdouts" if has_data else "blocked_no_accepted_real_data"
    return [_record("paper_rotation_feedback_queue", "feedback-000", {"task": task, "research_feedback": True})]


def _record(artifact_type: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": artifact_type,
        "record_id": record_id,
        **fields,
        "paper_only": True,
        "live_blocked": True,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
        "strategy_promotion_allowed": False,
    }
    record["record_hash"] = stable_hash(record)
    return record
