"""Freeze public paper champions and collect evidence before stress testing."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    LIVE_GATE_V2_PATH,
    champion_records,
    hardening_proof_record,
    live_safety_fields,
    load_public_trades,
    stress_metrics,
    trades_for_champion,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import (
    LIVE_GATE_ROOT,
    SCOREBOARD_ROOT,
    read_json_file,
    record_with_hash,
    safe_float,
    write_jsonl_file,
)


INVENTORY_PATH = HARDENING_ROOT / "public_champion_inventory_v1.jsonl"
SUMMARY_PATH = HARDENING_ROOT / "public_champion_inventory_v1_summary.json"
PROOF_PATH = HARDENING_ROOT / "public_champion_inventory_v1_proof.jsonl"


def run_public_champion_inventory_v1() -> dict[str, object]:
    champions = champion_records()
    trades = load_public_trades()
    live_gate = read_json_file(LIVE_GATE_V2_PATH)
    scoreboard = read_json_file(SCOREBOARD_ROOT / "public_signal_deepening_scoreboard_v4.json")
    inventory: list[dict[str, object]] = []

    for champion in champions:
        cohort_trades = trades_for_champion(champion, trades)
        metrics = stress_metrics(cohort_trades)
        inventory.append(record_with_hash({
            "artifact_type": "public_champion_inventory_v1",
            "champion_name": champion.get("cohort_id", ""),
            "canonical_champion_id": champion.get("canonical_champion_id", champion.get("cohort_id", "")),
            "cohort_level": champion.get("cohort_level", ""),
            "setup_family": champion.get("setup_family", ""),
            "direction": champion.get("direction", ""),
            "option_side": champion.get("option_side", ""),
            "dte_group": champion.get("dte_bucket", champion.get("dte_group", "")),
            "moneyness_group": champion.get("moneyness_bucket", champion.get("moneyness_group", "")),
            "exit_policy": champion.get("exit_policy", ""),
            "sample_count": metrics.get("sample_count", 0),
            "symbol_count": metrics.get("symbol_count", 0),
            "sector_count": metrics.get("sector_count", 0),
            "split_count": champion.get("split_count", 0),
            "split_pass_rate": champion.get("split_pass_rate", 0.0),
            "net_pnl": metrics.get("net_pnl", 0.0),
            "expectancy": metrics.get("expectancy", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "drawdown_adjusted_pnl": metrics.get("drawdown_adjusted_pnl", 0.0),
            "best_trade": metrics.get("best_trade", 0.0),
            "worst_trade": metrics.get("worst_trade", 0.0),
            "top_symbol_share": metrics.get("top_symbol_trade_share", 0.0),
            "top_sector_share": metrics.get("top_sector_trade_share", 0.0),
            "top_regime_share": metrics.get("top_regime_trade_share", 0.0),
            "slippage_stress_metrics": {
                "high_slippage_net_pnl": champion.get("high_slippage_net_pnl", 0.0),
            },
            "theta_stress_metrics": {
                "theta_stress_net_pnl": champion.get("theta_stress_net_pnl", 0.0),
            },
            "iv_shock_metrics": {
                "iv_shock_negative_net_pnl": champion.get("iv_shock_negative_net_pnl", 0.0),
            },
            "child_variant_dispersion": safe_float(champion.get("child_variant_dispersion", 0.0)),
            "champion_gate_reason": "public_data_paper_champion_v2",
            "live_gate_lock_status": live_gate.get("live_gate_status", "disabled_live_gate_locked"),
            "public_data_only": True,
            "fixture_champion_count": 0,
            **live_safety_fields(),
        }, "record_hash"))

    summary = {
        "artifact_type": "public_champion_inventory_v1_summary",
        "public_champion_inventory_version": "dopey-public-champion-inventory-v1",
        "public_champion_inventory_status": "public_champion_inventory_frozen",
        "public_paper_champion_count": len(champions),
        "champion_names": [str(c.get("cohort_id", "")) for c in champions],
        "scoreboard_status": scoreboard.get("scoreboard_status", ""),
        "public_data_only": True,
        "fixture_champion_count": 0,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(INVENTORY_PATH, inventory)
    write_stage_proof(PROOF_PATH, "public-champion-inventory-v1", str(summary["public_champion_inventory_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_inventory_v1": str(INVENTORY_PATH),
        "public_champion_inventory_v1_summary": str(SUMMARY_PATH),
        "public_champion_inventory_v1_proof": str(PROOF_PATH),
    }
