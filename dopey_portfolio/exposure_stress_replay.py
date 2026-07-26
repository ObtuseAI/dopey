"""Portfolio exposure stress replay records."""
from __future__ import annotations

from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash


STRESS_DIMENSION_BY_TAG: dict[str, str] = {
    "zero_dte_concentration": "0dte_concentration_stress",
    "family_concentration": "same_underlying_family_stress",
    "regime_concentration": "same_regime_stress",
    "call_heavy": "call_heavy_exposure_stress",
    "put_heavy": "put_heavy_exposure_stress",
    "high_gamma": "high_gamma_stress",
    "high_theta": "high_theta_stress",
    "iv_crush": "iv_crush_stress",
    "event_macro": "event_macro_stress",
    "live_path_injection": "live_path_injection_stress",
    "broker_boundary_injection": "broker_path_injection_stress",
    "real_sizing_injection": "real_sizing_injection_stress",
}


def build_exposure_stress_results(
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    decision_by_case = {_case_id_from_decision(record): record for record in decisions}
    snapshot_by_case = {_case_id_from_snapshot(record): record for record in snapshots}
    records: list[dict[str, Any]] = []
    for case in cases:
        stress_dimensions = _stress_dimensions(case)
        if not stress_dimensions and case["case_family"] not in {"delayed_rotation_case", "same_day_close_blocked_case", "paper_shadow_containment_case"}:
            continue
        case_id = str(case["case_id"])
        decision = decision_by_case[case_id]
        snapshot = snapshot_by_case[case_id]
        record = {
            "artifact_type": "exposure_stress_result",
            "stress_scenario_id": f"portfolio-stress-{case_id}",
            "case_id": case_id,
            "stress_dimensions": stress_dimensions or [_fallback_stress_dimension(case)],
            "exposure_before": case["exposure_before"],
            "attempted_action": case["attempted_action"],
            "exposure_after": {
                "total_paper_premium_risk_units": snapshot["total_paper_premium_risk_units"],
                "zero_dte_paper_units": snapshot["zero_dte_paper_units"],
                "swing_paper_units": snapshot["swing_paper_units"],
                "high_gamma_units": snapshot["high_gamma_units"],
                "high_theta_units": snapshot["high_theta_units"],
                "iv_crush_exposed_units": snapshot["iv_crush_exposed_units"],
                "event_macro_exposed_units": snapshot["event_macro_exposed_units"],
            },
            "allowed": bool(decision["entry_allowed"] or decision["exit_allowed"]),
            "blocked": not bool(decision["entry_allowed"] or decision["exit_allowed"]),
            "reason_codes": list(decision["reason_codes"]),
            "policy_result": snapshot["constraint_status"],
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
        }
        record["reproducibility_hash"] = reproducibility_hash(record)
        records.append(record)
    return records


def _stress_dimensions(case: dict[str, Any]) -> list[str]:
    return sorted({STRESS_DIMENSION_BY_TAG[tag] for tag in case["risk_tags"] if tag in STRESS_DIMENSION_BY_TAG})


def _fallback_stress_dimension(case: dict[str, Any]) -> str:
    if case["case_family"] == "delayed_rotation_case":
        return "delayed_rotation_backlog_stress"
    if case["case_family"] == "same_day_close_blocked_case":
        return "no_day_trade_close_block_stress"
    if case["case_family"] == "paper_shadow_containment_case":
        return "paper_shadow_leakage_stress"
    return "portfolio_policy_stress"


def _case_id_from_decision(record: dict[str, Any]) -> str:
    return str(record["rotation_decision_id"]).replace("portfolio-rotation-", "", 1)


def _case_id_from_snapshot(record: dict[str, Any]) -> str:
    return str(record["snapshot_id"]).replace("portfolio-exposure-", "", 1)

