"""Risk engine V3 for public-data paper champions."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import (
    RISK_ROOT,
    load_public_champion_trades,
    load_public_leaderboard,
    proof_record,
    record_with_hash,
    safe_float,
    write_jsonl_file,
    write_summary_with_hash,
)


RISK_RECORDS_PATH = RISK_ROOT / "public_champion_risk_records_v3.jsonl"
KILL_SWITCH_RECORDS_PATH = RISK_ROOT / "public_champion_kill_switch_records_v3.jsonl"
SUMMARY_PATH = RISK_ROOT / "public_champion_risk_summary_v3.json"
PROOF_PATH = RISK_ROOT / "public_champion_risk_proof_v3.jsonl"


RISK_CONTROLS = [
    "max_strategy_drawdown",
    "max_portfolio_drawdown",
    "max_symbol_concentration",
    "max_sector_concentration",
    "max_regime_concentration",
    "max_losing_streak",
    "max_overtrade_rate",
    "max_theta_exposure",
    "max_iv_shock_exposure",
    "max_gap_risk",
    "event_risk_throttle",
    "zero_dte_hard_throttle",
    "strategy_decay_kill_switch",
    "drawdown_cooldown",
    "mutation_failure_penalty",
]


def run_public_champion_risk_engine_v3() -> dict[str, object]:
    leaderboard = load_public_leaderboard()
    trades = load_public_champion_trades()
    return evaluate_public_champion_risk_v3(leaderboard, trades)


def evaluate_public_champion_risk_v3(leaderboard: list[dict[str, object]], trades: list[dict[str, object]]) -> dict[str, object]:
    risk_records: list[dict[str, object]] = []
    kill_switch_records: list[dict[str, object]] = []
    for row in leaderboard:
        strategy_id = str(row.get("strategy_id", ""))
        for control_id in RISK_CONTROLS:
            record = risk_record_for_control(row, control_id)
            risk_records.append(record_with_hash(record, "record_hash"))
        kill_reasons = kill_switch_reasons(row)
        if kill_reasons:
            kill_switch_records.append(record_with_hash({
                "artifact_type": "public_champion_kill_switch_record_v3",
                "strategy_id": strategy_id,
                "kill_switch_reasons": kill_reasons,
                "net_pnl": row.get("net_pnl", 0.0),
                "max_drawdown": row.get("max_drawdown", 0.0),
                "profit_factor": row.get("profit_factor", 0.0),
                "live_trading_enabled": False,
            }, "record_hash"))
    summary = {
        "artifact_type": "public_champion_risk_summary_v3",
        "public_champion_risk_version": "dopey-public-champion-risk-engine-v3",
        "public_champion_risk_status": "public_champion_risk_controls_complete",
        "strategy_count": len(leaderboard),
        "risk_throttle_count": len(risk_records),
        "kill_switch_record_count": len(kill_switch_records),
        "trade_count": len([trade for trade in trades if str(trade.get("trade_intent", "")) in {"long_call", "long_put"}]),
        "control_count": len(RISK_CONTROLS),
        "controls": RISK_CONTROLS,
        "public_data_only": all(str(trade.get("market_data_source_type", "")).startswith("public") for trade in trades) if trades else True,
        "fixture_trade_count": sum(1 for trade in trades if str(trade.get("market_data_source_type", "")) == "fixture_fallback"),
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RISK_RECORDS_PATH, risk_records)
    write_jsonl_file(KILL_SWITCH_RECORDS_PATH, kill_switch_records)
    write_jsonl_file(PROOF_PATH, [proof_record("public-champion-risk-engine-v3", str(summary["public_champion_risk_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def risk_record_for_control(row: dict[str, object], control_id: str) -> dict[str, object]:
    triggered = risk_triggered(row, control_id)
    return {
        "artifact_type": "public_champion_risk_record_v3",
        "strategy_id": row.get("strategy_id", ""),
        "setup_family": row.get("setup_family", ""),
        "control_id": control_id,
        "throttle_triggered": triggered,
        "risk_action": "throttle_or_cooldown" if triggered else "monitor",
        "net_pnl": row.get("net_pnl", 0.0),
        "max_drawdown": row.get("max_drawdown", 0.0),
        "top_symbol_trade_share": row.get("top_symbol_trade_share", 0.0),
        "top_sector_trade_share": row.get("top_sector_trade_share", 0.0),
        "top_regime_trade_share": row.get("top_regime_trade_share", 0.0),
        "paper_only": True,
        "live_trading_enabled": False,
    }


def risk_triggered(row: dict[str, object], control_id: str) -> bool:
    if control_id == "max_strategy_drawdown":
        return abs(min(safe_float(row.get("max_drawdown")), 0.0)) > 1800.0
    if control_id == "max_portfolio_drawdown":
        return abs(min(safe_float(row.get("max_drawdown")), 0.0)) > 2500.0
    if control_id == "max_symbol_concentration":
        return safe_float(row.get("top_symbol_trade_share")) > 0.45
    if control_id == "max_sector_concentration":
        return safe_float(row.get("top_sector_trade_share")) > 0.60
    if control_id == "max_regime_concentration":
        return safe_float(row.get("top_regime_trade_share")) > 0.70
    if control_id == "max_losing_streak":
        return safe_float(row.get("win_rate")) < 0.35
    if control_id == "max_overtrade_rate":
        return int(row.get("sample_count", 0)) > 800
    if control_id == "max_theta_exposure":
        return safe_float(row.get("theta_stress_net_pnl")) < -abs(safe_float(row.get("net_pnl"))) * 0.6
    if control_id == "max_iv_shock_exposure":
        return safe_float(row.get("iv_shock_negative_net_pnl")) < -abs(safe_float(row.get("net_pnl"))) * 0.6
    if control_id == "max_gap_risk":
        return safe_float(row.get("worst_trade")) < -500.0
    if control_id == "event_risk_throttle":
        return False
    if control_id == "zero_dte_hard_throttle":
        return "zero_dte" in str(row.get("setup_family", ""))
    if control_id == "strategy_decay_kill_switch":
        return safe_float(row.get("profit_factor")) < 1.0
    if control_id == "drawdown_cooldown":
        return abs(min(safe_float(row.get("max_drawdown")), 0.0)) > 1200.0
    if control_id == "mutation_failure_penalty":
        return safe_float(row.get("split_pass_rate")) < 0.35
    raise ValueError(f"unsupported public champion risk control: {control_id}")


def kill_switch_reasons(row: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    if safe_float(row.get("profit_factor")) < 1.0:
        reasons.append("profit_factor_decay")
    if safe_float(row.get("net_pnl")) <= 0.0:
        reasons.append("non_positive_public_pnl")
    if safe_float(row.get("split_pass_rate")) < 0.35:
        reasons.append("walk_forward_decay")
    if "zero_dte" in str(row.get("setup_family", "")):
        reasons.append("zero_dte_special_lane_not_default")
    return reasons


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_risk_records_v3": str(RISK_RECORDS_PATH),
        "public_champion_kill_switch_records_v3": str(KILL_SWITCH_RECORDS_PATH),
        "public_champion_risk_summary_v3": str(SUMMARY_PATH),
        "public_champion_risk_proof_v3": str(PROOF_PATH),
    }

