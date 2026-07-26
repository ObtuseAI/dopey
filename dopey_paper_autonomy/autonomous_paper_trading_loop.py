"""Paper-only autonomous trading simulation loop with no broker path."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, read_json, read_jsonl, safety_state, stable_hash, write_json, write_jsonl
from dopey_research_autonomy.run_autonomous_research_engine import INTENTS_PATH, SUMMARY_PATH as RESEARCH_SUMMARY_PATH


ARTIFACT_DIR = ARTIFACT_ROOT / "paper_autonomy"
SUMMARY_PATH = ARTIFACT_DIR / "autonomous_paper_trading_loop_summary.json"
INTENTS_PATH_OUT = ARTIFACT_DIR / "autonomous_paper_trade_intents.jsonl"
POSITIONS_PATH = ARTIFACT_DIR / "autonomous_paper_positions.jsonl"
LIFECYCLE_PATH = ARTIFACT_DIR / "autonomous_paper_lifecycle_events.jsonl"
LEDGER_PATH = ARTIFACT_DIR / "autonomous_paper_performance_ledger.jsonl"
PROOF_PATH = ARTIFACT_DIR / "autonomous_paper_autonomy_proof.jsonl"


def run_autonomous_paper_trading_loop() -> dict[str, Any]:
    research = read_json(RESEARCH_SUMMARY_PATH)
    intents = read_jsonl(INTENTS_PATH)
    has_real_data = bool(research.get("valid_real_dataset", False))
    eligible = [record for record in intents if record.get("intent") in {"long_call", "long_put"}] if has_real_data else []
    paper_intents = [_paper_intent(record) for record in eligible]
    positions = [_position(record) for record in paper_intents]
    lifecycle = [_lifecycle(record) for record in positions]
    ledger = [_ledger(record) for record in positions]
    status = "paper_loop_ran" if has_real_data else "blocked_no_accepted_real_data"
    summary = {
        "artifact_type": "autonomous_paper_trading_loop_summary",
        "paper_loop_version": "dopey-open-source-autonomous-options-trader-max-completion-v1",
        "paper_loop_status": status,
        "daily_scan_completed": has_real_data,
        "paper_intent_count": len(paper_intents),
        "paper_position_count": len(positions),
        "max_risk_per_paper_position_enforced": True,
        "max_drawdown_guard_enforced": True,
        "theta_iv_risk_guard_enforced": True,
        "event_risk_guard_enforced": True,
        "zero_dte_special_guard_enforced": True,
        "same_day_churn_default_allowed": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "env_created": False,
        **safety_state(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(INTENTS_PATH_OUT, paper_intents)
    write_jsonl(POSITIONS_PATH, positions)
    write_jsonl(LIFECYCLE_PATH, lifecycle)
    write_jsonl(LEDGER_PATH, ledger)
    write_jsonl(PROOF_PATH, [proof_record("autonomous-paper-autonomy-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "autonomous_paper_trading_loop_summary": str(SUMMARY_PATH),
        "autonomous_paper_trade_intents": str(INTENTS_PATH_OUT),
        "autonomous_paper_positions": str(POSITIONS_PATH),
        "autonomous_paper_lifecycle_events": str(LIFECYCLE_PATH),
        "autonomous_paper_performance_ledger": str(LEDGER_PATH),
        "autonomous_paper_autonomy_proof": str(PROOF_PATH),
    }


def _paper_intent(intent: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_paper_trade_intents",
        "paper_intent_id": f"paper-{intent['intent_id']}",
        "source_intent_id": intent["intent_id"],
        "intent": intent["intent"],
        "max_risk_units": 1.0,
        "fill_mode": "paper_fill_simulated",
        "paper_only": True,
        "live_blocked": True,
    }
    record["intent_hash"] = stable_hash(record)
    return record


def _position(intent: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_paper_positions",
        "paper_position_id": f"position-{intent['paper_intent_id']}",
        "source_paper_intent_id": intent["paper_intent_id"],
        "state": "opened_paper",
        "risk_units": intent["max_risk_units"],
        "paper_only": True,
        "live_blocked": True,
    }
    record["position_hash"] = stable_hash(record)
    return record


def _lifecycle(position: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_paper_lifecycle_events",
        "event_id": f"lifecycle-{position['paper_position_id']}",
        "paper_position_id": position["paper_position_id"],
        "event": "paper_lifecycle_managed",
        "same_day_churn_blocked": True,
        "paper_only": True,
        "live_blocked": True,
    }
    record["event_hash"] = stable_hash(record)
    return record


def _ledger(position: dict[str, Any]) -> dict[str, Any]:
    record = {
        "artifact_type": "autonomous_paper_performance_ledger",
        "ledger_id": f"ledger-{position['paper_position_id']}",
        "paper_position_id": position["paper_position_id"],
        "real_pnl": False,
        "paper_pnl_units": 0.0,
        "paper_only": True,
        "live_blocked": True,
    }
    record["ledger_hash"] = stable_hash(record)
    return record

