"""Public signal deepening live-gate status V2.

Hard-locks live trading even when public paper champions exist. Corrects the
Robinhood policy: official agent/MCP market-data access is allowed for research
and paper scoring if official terms permit; unofficial access, scraping,
reverse-engineering, and live trading remain blocked.
"""
from __future__ import annotations

from dopey_autonomy.public_champion_common import (
    CHAMPION_ROOT,
    LIVE_GATE_ROOT,
    proof_record,
    read_json_file,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_wealth_engine.common import REPO_ROOT


STATUS_PATH = LIVE_GATE_ROOT / "public_signal_deepening_live_gate_status_v2.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_signal_deepening_live_gate_blockers_v2.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_signal_deepening_live_gate_proof_v2.jsonl"


def run_public_signal_deepening_live_gate_status_v2() -> dict[str, object]:
    champion_summary = read_json_file(CHAMPION_ROOT / "public_paper_champion_gate_v2_summary.json")
    status = build_live_gate_status_v2(champion_summary)
    blockers = build_live_gate_blockers_v2(status)
    summary = write_summary_with_hash(STATUS_PATH, status)
    write_jsonl_file(BLOCKERS_PATH, blockers)
    write_jsonl_file(PROOF_PATH, [proof_record("public-signal-deepening-live-gate-status-v2", str(summary["live_gate_status"]), summary)])
    return {**summary, "blocker_count": len(blockers), "artifact_paths": artifact_paths()}


def build_live_gate_status_v2(champion_summary: dict[str, object]) -> dict[str, object]:
    env_path = REPO_ROOT / ".env"
    return {
        "artifact_type": "public_signal_deepening_live_gate_status_v2",
        "public_signal_deepening_live_gate_version": "dopey-public-signal-deepening-live-gate-status-v2",
        "live_gate_status": "disabled_live_gate_locked",
        "public_paper_champion_count": int(champion_summary.get("public_paper_champion_count", 0)),
        "live_trading_enabled": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": env_path.exists(),
        "env_created": False,
        "broker_connection_used": False,
        "credentials_created": False,
        "real_orders_placed": False,
        "real_broker_adapter_required": False,
        "capital_risk_review_required": True,
        "separate_future_bundle_required": True,
        "human_live_approval_required": True,
        "paper_champion_hardening_required": True,
        "robinhood_policy": {
            "official_robinhood_agent_mcp_market_data_allowed": True,
            "official_robinhood_permitted_market_data_research_allowed": True,
            "unofficial_robinhood_api_blocked": True,
            "robinhood_scraping_blocked": True,
            "robinhood_reverse_engineered_auth_blocked": True,
            "robinhood_hidden_credentials_blocked": True,
            "robinhood_live_trading_blocked": True,
            "robinhood_real_orders_blocked": True,
        },
    }


def build_live_gate_blockers_v2(status: dict[str, object]) -> list[dict[str, object]]:
    blockers = [
        ("live_trading_disabled", "live trading remains disabled even though public paper champions exist"),
        ("no_broker_connection", "no broker connection is established or required in this bundle"),
        ("no_real_orders", "no real orders are placed or enabled"),
        ("no_credentials", "no broker credentials are created or stored"),
        ("no_env", "no .env file is created; secret values are never written"),
        ("capital_risk_review_required", "real capital review remains outside this bundle"),
        ("separate_future_bundle_required", "live gate requires a separate future bundle"),
        ("human_live_approval_required", "human approval is required before any live gate work"),
        ("paper_champion_hardening_required", "paper champions require deeper public stress before live consideration"),
        ("official_robinhood_market_data_lane_research_only", "official Robinhood agent/MCP market-data access is allowed for research/paper scoring if official terms permit; no live trading"),
        ("unofficial_robinhood_access_blocked", "unofficial Robinhood APIs, scraping, and reverse-engineered auth remain blocked"),
    ]
    records: list[dict[str, object]] = []
    for blocker_id, message in blockers:
        records.append(record_with_hash({
            "artifact_type": "public_signal_deepening_live_gate_blocker_v2",
            "blocker_id": blocker_id,
            "message": message,
            "public_paper_champion_count": status.get("public_paper_champion_count", 0),
            "live_trading_enabled": False,
            "broker_connection_enabled": False,
            "real_order_enabled": False,
        }, "record_hash"))
    return records


def artifact_paths() -> dict[str, str]:
    return {
        "public_signal_deepening_live_gate_status_v2": str(STATUS_PATH),
        "public_signal_deepening_live_gate_blockers_v2": str(BLOCKERS_PATH),
        "public_signal_deepening_live_gate_proof_v2": str(PROOF_PATH),
    }
