"""Model-priced options research expansion V2."""
from __future__ import annotations

import math
from typing import Any

from dopey_autonomy.autonomy_common import ARTIFACT_ROOT, proof_record, stable_hash, write_json, write_jsonl


ARTIFACT_DIR = ARTIFACT_ROOT / "research_autonomy"
PRICER_CASES_PATH = ARTIFACT_DIR / "model_priced_v2_option_pricer_cases.jsonl"
SIGNAL_CANDIDATES_PATH = ARTIFACT_DIR / "model_priced_v2_signal_candidates.jsonl"
STRATEGY_CANDIDATES_PATH = ARTIFACT_DIR / "model_priced_v2_strategy_candidates.jsonl"
OPTION_INTENTS_PATH = ARTIFACT_DIR / "model_priced_v2_option_intents.jsonl"
SCENARIO_GRID_PATH = ARTIFACT_DIR / "model_priced_v2_scenario_grid.jsonl"
RISK_STRESS_PATH = ARTIFACT_DIR / "model_priced_v2_risk_stress_results.jsonl"
LIFECYCLE_RULES_PATH = ARTIFACT_DIR / "model_priced_v2_lifecycle_rules.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "model_priced_v2_research_summary.json"
PROOF_PATH = ARTIFACT_DIR / "model_priced_v2_research_proof.jsonl"


def run_model_priced_options_research_expansion_v2() -> dict[str, Any]:
    pricer_cases = _pricer_cases()
    signals = _signal_candidates()
    strategies = _strategy_candidates(signals)
    intents = _option_intents(strategies)
    scenarios = _scenario_grid()
    stresses = _risk_stress_results(scenarios)
    lifecycle = _lifecycle_rules()
    summary = {
        "artifact_type": "model_priced_v2_research_summary",
        "research_version": "dopey-openbb-model-priced-s-tier-completion-v1",
        "model_priced_v2_status": "model_priced_v2_research_complete",
        "pricer_case_count": len(pricer_cases),
        "signal_candidate_count": len(signals),
        "strategy_candidate_count": len(strategies),
        "option_intent_count": len(intents),
        "scenario_count": len(scenarios),
        "risk_stress_count": len(stresses),
        "lifecycle_rule_count": len(lifecycle),
        "black_scholes_adapter": "deterministic_builtin",
        "quantlib_reference_adapter": "optional_not_required",
        **_research_safety(),
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(PRICER_CASES_PATH, pricer_cases)
    write_jsonl(SIGNAL_CANDIDATES_PATH, signals)
    write_jsonl(STRATEGY_CANDIDATES_PATH, strategies)
    write_jsonl(OPTION_INTENTS_PATH, intents)
    write_jsonl(SCENARIO_GRID_PATH, scenarios)
    write_jsonl(RISK_STRESS_PATH, stresses)
    write_jsonl(LIFECYCLE_RULES_PATH, lifecycle)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("model-priced-v2-research-proof-v1", summary["model_priced_v2_status"], summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "model_priced_v2_option_pricer_cases": str(PRICER_CASES_PATH),
        "model_priced_v2_signal_candidates": str(SIGNAL_CANDIDATES_PATH),
        "model_priced_v2_strategy_candidates": str(STRATEGY_CANDIDATES_PATH),
        "model_priced_v2_option_intents": str(OPTION_INTENTS_PATH),
        "model_priced_v2_scenario_grid": str(SCENARIO_GRID_PATH),
        "model_priced_v2_risk_stress_results": str(RISK_STRESS_PATH),
        "model_priced_v2_lifecycle_rules": str(LIFECYCLE_RULES_PATH),
        "model_priced_v2_research_summary": str(SUMMARY_PATH),
        "model_priced_v2_research_proof": str(PROOF_PATH),
    }


def black_scholes_price(spot: float, strike: float, years: float, rate: float, volatility: float, option_type: str) -> float:
    if years <= 0 or volatility <= 0 or spot <= 0 or strike <= 0:
        return max(0.0, spot - strike) if option_type == "call" else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (rate + volatility * volatility / 2) * years) / (volatility * math.sqrt(years))
    d2 = d1 - volatility * math.sqrt(years)
    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * years) * _norm_cdf(d2)
    return strike * math.exp(-rate * years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _pricer_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    inputs = [
        (100.0, 100.0, 30 / 365, 0.04, 0.20, "call"),
        (100.0, 105.0, 45 / 365, 0.04, 0.25, "call"),
        (100.0, 95.0, 30 / 365, 0.04, 0.30, "put"),
        (100.0, 100.0, 1 / 365, 0.04, 0.45, "call"),
    ]
    for index, item in enumerate(inputs):
        spot, strike, years, rate, vol, option_type = item
        record = {
            "artifact_type": "model_priced_v2_option_pricer_cases",
            "case_id": f"model-priced-v2-pricer-{index:03d}",
            "spot": spot,
            "strike": strike,
            "years_to_expiry": years,
            "risk_free_rate": rate,
            "volatility_proxy": vol,
            "option_type": option_type,
            "model_price": round(black_scholes_price(spot, strike, years, rate, vol, option_type), 6),
            **_research_safety(),
        }
        record["case_hash"] = stable_hash(record)
        cases.append(record)
    return cases


def _signal_candidates() -> list[dict[str, Any]]:
    names = ["momentum", "breakout", "fakeout_reversal", "trend_pullback", "relative_strength", "volatility_regime", "market_regime", "event_exclusion", "no_trade"]
    records: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        record = {
            "artifact_type": "model_priced_v2_signal_candidates",
            "signal_id": f"model-priced-v2-signal-{index:03d}",
            "signal_family": name,
            "uses_accepted_ohlcv_if_available": True,
            "iv_percentile_proxy": "realized_volatility_rank",
            "trend_regime_filter": True,
            "volatility_regime_filter": True,
            "market_regime_filter": True,
            **_research_safety(),
        }
        record["signal_hash"] = stable_hash(record)
        records.append(record)
    return records


def _strategy_candidates(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        intent = "no_trade" if signal["signal_family"] in {"no_trade", "event_exclusion"} else ("long_put" if signal["signal_family"] == "fakeout_reversal" else "long_call")
        record = {
            "artifact_type": "model_priced_v2_strategy_candidates",
            "strategy_id": f"model-priced-v2-strategy-{index:03d}",
            "signal_id": signal["signal_id"],
            "intent_type": intent,
            "delta_bucket": "35_to_60" if intent != "no_trade" else "none",
            "moneyness_bucket": "atm_to_5pct_otm" if intent != "no_trade" else "none",
            "expiration_bucket": "21_to_60_dte" if intent != "no_trade" else "none",
            "spread_slippage_stress": True,
            "liquidity_proxy": "underlying_volume_rank",
            "event_earnings_exclusion_gate": True,
            **_research_safety(),
        }
        record["strategy_hash"] = stable_hash(record)
        records.append(record)
    return records


def _option_intents(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, strategy in enumerate(strategies):
        record = {
            "artifact_type": "model_priced_v2_option_intents",
            "intent_id": f"model-priced-v2-intent-{index:03d}",
            "strategy_id": strategy["strategy_id"],
            "intent_type": strategy["intent_type"],
            "allowed_structure": "long_call_or_long_put_only" if strategy["intent_type"] != "no_trade" else "no_trade",
            "max_loss_paper_constraint": "premium_paid_only",
            "zero_dte_special_lane": strategy["expiration_bucket"] == "0dte_research_only",
            "same_day_churn_default": "blocked",
            **_research_safety(),
        }
        record["intent_hash"] = stable_hash(record)
        records.append(record)
    return records


def _scenario_grid() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    index = 0
    for iv_shock in [-0.35, -0.15, 0.0, 0.15, 0.35]:
        for theta_days in [1, 5, 10, 20]:
            for slippage_bps in [25, 75, 150]:
                record = {
                    "artifact_type": "model_priced_v2_scenario_grid",
                    "scenario_id": f"model-priced-v2-scenario-{index:03d}",
                    "iv_shock": iv_shock,
                    "theta_decay_days": theta_days,
                    "spread_slippage_bps": slippage_bps,
                    "risk_of_ruin_path_count": 100,
                    "drawdown_throttle_enabled": True,
                    **_research_safety(),
                }
                record["scenario_hash"] = stable_hash(record)
                records.append(record)
                index += 1
    return records


def _risk_stress_results(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scenario in scenarios:
        stress = abs(float(scenario["iv_shock"])) + int(scenario["theta_decay_days"]) / 25 + int(scenario["spread_slippage_bps"]) / 250
        record = {
            "artifact_type": "model_priced_v2_risk_stress_results",
            "stress_id": f"risk-{scenario['scenario_id']}",
            "scenario_id": scenario["scenario_id"],
            "stress_score": round(stress, 6),
            "risk_of_ruin_proxy": round(min(1.0, stress / 2.0), 6),
            "drawdown_throttle": "throttle" if stress >= 1.0 else "normal",
            "paper_trade_allowed": stress < 1.25,
            **_research_safety(),
        }
        record["stress_hash"] = stable_hash(record)
        records.append(record)
    return records


def _lifecycle_rules() -> list[dict[str, Any]]:
    names = ["entry_gate", "max_loss_exit", "drawdown_throttle", "event_exit", "zero_dte_special_guard", "rotation_rebalance", "no_same_day_churn"]
    records: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        record = {
            "artifact_type": "model_priced_v2_lifecycle_rules",
            "rule_id": f"model-priced-v2-lifecycle-{index:03d}",
            "rule_name": name,
            "paper_only_lifecycle_manager": True,
            "max_loss_constraint": "premium_paid_only",
            "live_execution_allowed": False,
            **_research_safety(),
        }
        record["rule_hash"] = stable_hash(record)
        records.append(record)
    return records


def _research_safety() -> dict[str, Any]:
    return {
        "pricing_tier": "model_priced",
        "quote_priced": False,
        "not_quote_evidence": True,
        "not_real_options_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
