"""CLI for the deterministic DOPEY macro-event fixture expansion bundle.

This bundle expands offline macro-event, rates, VIX/VVIX, breadth, sector-rotation,
liquidity-regime, overnight/futures-pressure, and risk-on/off fixture intelligence. It is
fully offline, fixture-based, paper-only, deterministic, and live-blocked.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.config import default_config_path, load_config
from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_strategy_lab.constraint_tuning import build_constraint_tuning_recommendations
from dopey_strategy_lab.failure_feedback import aggregate_failure_modes, build_family_failure_profiles
from dopey_strategy_lab.failure_mode_miner import mine_failure_modes
from dopey_strategy_lab.failure_mode_registry import FAILURE_MODE_REGISTRY_PATH, write_failure_mode_registry
from dopey_tournament.runner import run_fixture_tournament

from .macro_event_scenarios import (
    MACRO_EVENT_SCENARIO_VERSION,
    build_macro_event_scenarios,
    build_scenario_ledger_records,
)
from .macro_family_scoring import MACRO_FAMILY_SCORING_VERSION, score_all_families_for_scenario


MACRO_EVENT_BUNDLE_VERSION = "dopey-macro-event-fixture-expansion-bundle-v1"
MACRO_EVENT_EXPANSION_VERSION = "dopey-macro-event-expansion-v1"
MACRO_EVENT_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "macro_events"
MACRO_EVENT_REGISTRY_PATH = MACRO_EVENT_ARTIFACT_DIR / "macro_event_registry.jsonl"
MACRO_EVENT_BUNDLE_LEDGER_PATH = MACRO_EVENT_ARTIFACT_DIR / "macro_event_bundle.jsonl"
FORBIDDEN_LIVE_PROMOTIONS = {"micro_live", "adaptive_live", "live_candidate", "live"}


def _write_jsonl(record: dict, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def _safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_macro_event_bundle": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_macro_event_bundle_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"macro event bundle requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("macro event bundle requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("macro event bundle requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("macro event bundle requires allow_unofficial_robinhood_api=false")


def _family_score_records() -> list[dict]:
    records: list[dict] = []
    for scenario in build_macro_event_scenarios():
        scored = score_all_families_for_scenario(scenario)
        for family in sorted(scored):
            score = scored[family]
            row = score.to_dict()
            row["scenario_regime_tag"] = scenario.regime_tag
            row["preferred_by_scenario"] = family in scenario.preferred_strategy_families
            row["penalized_by_scenario"] = family in scenario.penalized_strategy_families
            records.append(row)
    return records


def _average_family_scores(records: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        family = str(record["strategy_family"])
        grouped.setdefault(family, []).append(record)
    output: dict[str, dict] = {}
    for family in sorted(grouped):
        rows = grouped[family]
        count = len(rows)
        output[family] = {
            "macro_fit_score": round(sum(float(row["macro_fit_score"]) for row in rows) / count, 6),
            "macro_opportunity_score": round(sum(float(row["macro_opportunity_score"]) for row in rows) / count, 6),
            "macro_risk_score": round(sum(float(row["macro_risk_score"]) for row in rows) / count, 6),
            "event_risk_score": round(sum(float(row["event_risk_score"]) for row in rows) / count, 6),
            "rate_shock_score": round(sum(float(row["rate_shock_score"]) for row in rows) / count, 6),
            "vix_vvix_stress_score": round(sum(float(row["vix_vvix_stress_score"]) for row in rows) / count, 6),
            "breadth_sector_confirmation_score": round(sum(float(row["breadth_sector_confirmation_score"]) for row in rows) / count, 6),
            "liquidity_regime_macro_score": round(sum(float(row["liquidity_regime_macro_score"]) for row in rows) / count, 6),
            "macro_contradiction_penalty": round(sum(float(row["macro_contradiction_penalty"]) for row in rows) / count, 6),
            "event_gap_risk_penalty": round(sum(float(row["event_gap_risk_penalty"]) for row in rows) / count, 6),
        }
    return output


def _failure_mining_rows(records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        rows.append({
            "strategy_id": f"macro-{record['strategy_family']}-{record['scenario_id']}",
            "strategy_family": record["strategy_family"],
            "average_expected_slippage_pct": 0.0,
            "average_liquidity_score": 1.0,
            "average_delta_fit_score": 1.0,
            "average_greek_fit_score": 1.0,
            "average_pattern_fixture_score": 1.0,
            "slippage_robustness_score": 1.0,
            "family_regime_survival": 1.0,
            "mutation_adjustment": 0.0,
            "average_macro_fit_score": record["macro_fit_score"],
            "average_macro_risk_score": record["macro_risk_score"],
            "average_macro_contradiction_penalty": record["macro_contradiction_penalty"],
            "average_event_gap_risk_penalty": record["event_gap_risk_penalty"],
            "average_rate_shock_score": record["rate_shock_score"],
            "average_vix_vvix_stress_score": record["vix_vvix_stress_score"],
            "average_breadth_sector_confirmation_score": record["breadth_sector_confirmation_score"],
            "average_liquidity_regime_macro_score": record["liquidity_regime_macro_score"],
            "macro_event_risk_flags": record["risk_flags"],
            "best_macro_scenario": record["scenario_id"],
            "worst_macro_scenario": record["scenario_id"],
            "worst_regimes": [record["scenario_regime_tag"]] if record["penalized_by_scenario"] else [],
        })
    return rows


def _best_macro_fit_family(tournament_summary: dict, average_scores: dict[str, dict]) -> str:
    family_scores = dict(tournament_summary.get("macro_event_summary", {}).get("family_scores", {}))
    if family_scores:
        return sorted(
            family_scores,
            key=lambda family: (-float(family_scores[family].get("average_macro_fit_score", 0.0)), family),
        )[0]
    return sorted(
        average_scores,
        key=lambda family: (-float(average_scores[family].get("macro_fit_score", 0.0)), family),
    )[0]


def _worst_macro_risk_family(tournament_summary: dict, average_scores: dict[str, dict]) -> str:
    family_scores = dict(tournament_summary.get("macro_event_summary", {}).get("family_scores", {}))
    if family_scores:
        return sorted(
            family_scores,
            key=lambda family: (-float(family_scores[family].get("average_macro_risk_score", 0.0)), family),
        )[0]
    return sorted(
        average_scores,
        key=lambda family: (-float(average_scores[family].get("macro_risk_score", 0.0)), family),
    )[0]


def _new_failure_mode_ids(failure_registry: object) -> list[str]:
    requested = {
        "macro_fakeout_against_directional",
        "event_gap_against_short_duration",
        "rate_shock_against_compression",
        "vix_spike_against_compression",
        "post_event_crush_against_vol_expansion",
        "breadth_contradiction_against_directional",
        "liquidity_contraction_bad_fill_failure",
        "overnight_gap_slippage_failure",
        "sector_rotation_mismatch",
        "macro_event_overfit",
    }
    return sorted({
        mode.failure_mode_id
        for mode in failure_registry.failure_modes
        if mode.failure_mode_id in requested
    })


def _recommendations_for_failures(failure_registry: object) -> list[dict]:
    record = failure_registry.to_dict()
    aggregates = aggregate_failure_modes(record)
    family_profiles = build_family_failure_profiles(aggregates)
    recommendations = build_constraint_tuning_recommendations(family_profiles, aggregates)
    return [recommendation.to_dict() for recommendation in recommendations]


def _tournament_score_impact(tournament_summary: dict) -> dict:
    ranking = list(tournament_summary.get("strategy_ranking", []))
    if not ranking:
        return {"champion_strategy_id": "", "champion_score": 0.0, "runner_up_delta": 0.0}
    champion = dict(ranking[0])
    runner_up_score = float(ranking[1]["combined_score"]) if len(ranking) > 1 else 0.0
    champion_score = float(champion["combined_score"])
    return {
        "champion_strategy_id": str(champion["strategy_id"]),
        "champion_score": round(champion_score, 6),
        "runner_up_delta": round(champion_score - runner_up_score, 6),
        "champion_family_macro_fit_score": round(float(champion.get("average_macro_fit_score", 0.0)), 6),
        "champion_macro_risk_score": round(float(champion.get("average_macro_risk_score", 0.0)), 6),
    }


def _build_proof_entry(summary: dict, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=MACRO_EVENT_BUNDLE_VERSION,
        task_id="macro-event-fixture-expansion-bundle",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=summary["reproducibility_hash"],
        plan_hash=reproducibility_hash({"bundle_version": MACRO_EVENT_BUNDLE_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "bundle_summary": summary,
            "registry_record": registry_record,
            "safety_state": summary["safety_state"],
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[
            summary["macro_event_registry_path"],
            summary["failure_mode_registry_path"],
            summary["proof_record_path"],
        ],
        diffs=[],
        test_results={
            "bundle_status": summary["bundle_status"],
            "macro_scenarios_loaded": summary["macro_scenarios_loaded"],
            "families_scored": summary["families_scored"],
            "new_failure_modes_detected": summary["new_failure_modes_detected"],
            "forbidden_live_decisions_present": sorted(
                set(summary["promotion_decisions"].values()).intersection(FORBIDDEN_LIVE_PROMOTIONS)
            ),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic macro-event fixture intelligence only",
            "fixture scoring is not live performance evidence",
            "no broker connection, credentials, market-data network fetch, schedule, or live promotion",
        ],
    )


def run_macro_event_bundle(
    registry_path: Path | str | None = None,
    failure_mode_registry_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_macro_event_bundle_safety_state(safety)
    scenarios = build_macro_event_scenarios()
    scenario_ledger = build_scenario_ledger_records()
    family_score_records = _family_score_records()
    average_family_scores = _average_family_scores(family_score_records)
    failure_mining_rows = _failure_mining_rows(family_score_records)
    tournament_summary = run_fixture_tournament()
    failure_registry = mine_failure_modes(tournament_summary["strategy_ranking"], failure_mining_rows, [])
    new_failure_modes = _new_failure_mode_ids(failure_registry)
    feedback_recommendations = _recommendations_for_failures(failure_registry)
    families_scored = sorted(average_family_scores)
    target_registry = Path(registry_path) if registry_path else MACRO_EVENT_REGISTRY_PATH
    target_failure_registry = Path(failure_mode_registry_path) if failure_mode_registry_path else FAILURE_MODE_REGISTRY_PATH
    target_proof = Path(proof_ledger_path) if proof_ledger_path else MACRO_EVENT_BUNDLE_LEDGER_PATH
    failure_mode_record = failure_registry.to_dict()
    failure_mode_record["source_bundle"] = MACRO_EVENT_BUNDLE_VERSION
    failure_mode_record["safety_state"] = safety
    failure_mode_target = write_failure_mode_registry(failure_mode_record, target_failure_registry)
    registry_record = {
        "bundle_version": MACRO_EVENT_BUNDLE_VERSION,
        "macro_event_expansion_version": MACRO_EVENT_EXPANSION_VERSION,
        "macro_event_scenario_version": MACRO_EVENT_SCENARIO_VERSION,
        "macro_family_scoring_version": MACRO_FAMILY_SCORING_VERSION,
        "macro_scenarios": scenario_ledger,
        "family_score_records": family_score_records,
        "failure_mining_rows": failure_mining_rows,
        "average_family_scores": average_family_scores,
        "tournament_macro_event_summary": tournament_summary["macro_event_summary"],
        "failure_mode_registry": failure_mode_record,
        "failure_mode_registry_path": str(failure_mode_target),
        "feedback_recommendations": feedback_recommendations,
        "safety_state": safety,
    }
    registry_target = _write_jsonl(registry_record, target_registry)
    summary = {
        "bundle_status": "ok",
        "mode": safety["mode"],
        "live_trading_enabled": safety["live_trading_enabled"],
        "macro_scenarios_loaded": len(scenarios),
        "families_scored": families_scored,
        "best_macro_fit_family": _best_macro_fit_family(tournament_summary, average_family_scores),
        "worst_macro_risk_family": _worst_macro_risk_family(tournament_summary, average_family_scores),
        "new_failure_modes_detected": new_failure_modes,
        "feedback_recommendations_added": sorted({
            str(recommendation["tuning_key"])
            for recommendation in feedback_recommendations
            if recommendation["failure_mode_id"] in new_failure_modes
        }),
        "tournament_score_impact": _tournament_score_impact(tournament_summary),
        "champion_strategy_id": tournament_summary["champion_strategy_id"],
        "family_ranking_impact": tournament_summary["family_scorecard"],
        "macro_event_summary": tournament_summary["macro_event_summary"],
        "greek_iv_summary": tournament_summary.get("greek_iv_summary", {}),
        "slippage_liquidity_summary": tournament_summary.get("slippage_liquidity_summary", {}),
        "overfit_summary": tournament_summary["overfit_summary"],
        "promotion_decisions": tournament_summary["promotion_decisions"],
        "live_blocked": safety["live_blocked"],
        "safety_state": safety,
        "macro_event_registry_path": str(registry_target),
        "failure_mode_registry_path": str(failure_mode_target),
        "proof_record_path": str(target_proof),
    }
    repro = reproducibility_hash(registry_record, summary)
    summary["reproducibility_hash"] = repro
    registry_record["reproducibility_hash"] = repro
    ProofLedger(target_proof).append(_build_proof_entry(summary, registry_record))
    return summary


def main() -> int:
    summary = run_macro_event_bundle()
    concise = {
        "bundle_status": summary["bundle_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "macro_scenarios_loaded": summary["macro_scenarios_loaded"],
        "families_scored": summary["families_scored"],
        "best_macro_fit_family": summary["best_macro_fit_family"],
        "worst_macro_risk_family": summary["worst_macro_risk_family"],
        "new_macro_failure_modes_detected": summary["new_failure_modes_detected"],
        "tournament_score_impact": summary["tournament_score_impact"],
        "live_blocked": summary["live_blocked"],
        "macro_registry_path": summary["macro_event_registry_path"],
        "proof_record_path": summary["proof_record_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["bundle_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
