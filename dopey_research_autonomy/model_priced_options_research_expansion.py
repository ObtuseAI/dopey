"""Model-priced long-premium options research expansion."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl
from dopey_backtest.quote_priced_options_unlock_gate import run_quote_priced_options_unlock_gate


ARTIFACT_DIR = ARTIFACT_ROOT / "research_autonomy"
CANDIDATES_PATH = ARTIFACT_DIR / "model_priced_options_research_candidates.jsonl"
SCENARIO_GRID_PATH = ARTIFACT_DIR / "model_priced_options_scenario_grid.jsonl"
RISK_STRESS_PATH = ARTIFACT_DIR / "model_priced_options_risk_stress_results.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "model_priced_options_research_summary.json"
PROOF_PATH = ARTIFACT_DIR / "model_priced_options_research_proof.jsonl"


def run_model_priced_options_research_expansion() -> dict[str, Any]:
    unlock = run_quote_priced_options_unlock_gate()
    candidates = _research_candidates()
    scenarios = _scenario_grid()
    stresses = _risk_stress_results(scenarios)
    status = "model_priced_research_complete" if unlock["model_priced_research_allowed"] else "model_priced_research_available_but_quote_path_unlocked"
    summary = {
        "artifact_type": "model_priced_options_research_summary",
        "research_version": "dopey-open-data-breakthrough-options-evidence-completion-v1",
        "model_priced_research_status": status,
        "candidate_count": len(candidates),
        "scenario_count": len(scenarios),
        "risk_stress_count": len(stresses),
        "pricing_tier": "model_priced",
        "quote_priced": False,
        "not_real_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "strategy_promotion_allowed": False,
        "quote_priced_backtest_allowed": bool(unlock["quote_priced_backtest_allowed"]),
        "model_priced_research_allowed": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(CANDIDATES_PATH, candidates)
    write_jsonl(SCENARIO_GRID_PATH, scenarios)
    write_jsonl(RISK_STRESS_PATH, stresses)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("model-priced-options-research-proof-v1", status, summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "model_priced_options_research_candidates": str(CANDIDATES_PATH),
        "model_priced_options_scenario_grid": str(SCENARIO_GRID_PATH),
        "model_priced_options_risk_stress_results": str(RISK_STRESS_PATH),
        "model_priced_options_research_summary": str(SUMMARY_PATH),
        "model_priced_options_research_proof": str(PROOF_PATH),
    }


def _research_candidates() -> list[dict[str, Any]]:
    families = [
        ("momentum_long_call", "long_call", "trend_following", "multi_day_swing"),
        ("breakout_long_call", "long_call", "breakout", "multi_day_swing"),
        ("reversal_long_put", "long_put", "fakeout_reversal", "multi_day_swing"),
        ("regime_no_trade", "no_trade", "volatility_regime_filter", "capital_protection"),
        ("zero_dte_research_guard", "no_trade", "zero_dte_guard", "research_only"),
    ]
    return [_research_record(index, name, direction, signal, lifecycle) for index, (name, direction, signal, lifecycle) in enumerate(families)]


def _research_record(index: int, name: str, direction: str, signal: str, lifecycle: str) -> dict[str, Any]:
    record = {
        "artifact_type": "model_priced_options_research_candidates",
        "candidate_id": f"model-priced-candidate-{index:03d}",
        "candidate_name": name,
        "intent_type": direction,
        "signal_family": signal,
        "lifecycle": lifecycle,
        "moneyness_selection": "delta_bucket_35_to_60" if direction != "no_trade" else "none",
        "expiration_selection": "21_to_60_dte" if direction != "no_trade" else "none",
        "iv_proxy": "realized_volatility_scenario_grid",
        "earnings_event_exclusion": True,
        "volatility_regime_filter": True,
        "market_regime_filter": True,
        "symbol_liquidity_proxy": "underlying_volume_and_spread_stress",
        "pricing_tier": "model_priced",
        "quote_priced": False,
        "not_real_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["candidate_hash"] = stable_hash(record)
    return record


def _scenario_grid() -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    iv_shocks = [-0.25, 0.0, 0.25]
    theta_days = [1, 5, 10]
    slippage_bps = [25, 75, 150]
    index = 0
    for iv_shock in iv_shocks:
        for days in theta_days:
            for slippage in slippage_bps:
                record = {
                    "artifact_type": "model_priced_options_scenario_grid",
                    "scenario_id": f"model-priced-scenario-{index:03d}",
                    "iv_shock": iv_shock,
                    "theta_days": days,
                    "spread_slippage_bps": slippage,
                    "pricing_tier": "model_priced",
                    "quote_priced": False,
                    "not_real_options_evidence": True,
                    "not_profitability_claim": True,
                    "not_live_ready": True,
                    "strategy_promotion_allowed": False,
                    "paper_only": True,
                    "live_blocked": True,
                }
                record["scenario_hash"] = stable_hash(record)
                scenarios.append(record)
                index += 1
    return scenarios


def _risk_stress_results(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        stress_score = abs(float(scenario["iv_shock"])) + int(scenario["theta_days"]) / 20 + int(scenario["spread_slippage_bps"]) / 300
        record = {
            "artifact_type": "model_priced_options_risk_stress_results",
            "stress_id": f"stress-{scenario['scenario_id']}",
            "scenario_id": scenario["scenario_id"],
            "stress_score": round(stress_score, 6),
            "risk_verdict": "blocked_by_no_trade_gate" if stress_score >= 1.0 else "research_candidate_only",
            "pricing_tier": "model_priced",
            "quote_priced": False,
            "not_real_options_evidence": True,
            "not_profitability_claim": True,
            "not_live_ready": True,
            "strategy_promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
        record["stress_hash"] = stable_hash(record)
        results.append(record)
    return results
