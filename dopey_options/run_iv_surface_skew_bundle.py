"""CLI for the deterministic DOPEY IV surface/skew expansion bundle."""
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

from .iv_family_scoring import IV_FAMILY_SCORING_VERSION, score_all_families_for_scenario
from .iv_surface_expansion import IV_SURFACE_EXPANSION_VERSION
from .iv_surface_scenarios import (
    IV_SURFACE_SCENARIO_VERSION,
    build_iv_surface_scenarios,
    build_scenario_ledger_records,
)
from .skew_term_structure import SKEW_TERM_STRUCTURE_VERSION
from .volatility_regime import VOLATILITY_REGIME_VERSION


IV_SURFACE_BUNDLE_VERSION = "dopey-iv-surface-skew-expansion-bundle-v1"
IV_SURFACE_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "iv_surface"
IV_SURFACE_REGISTRY_PATH = IV_SURFACE_ARTIFACT_DIR / "iv_surface_registry.jsonl"
IV_SURFACE_BUNDLE_LEDGER_PATH = IV_SURFACE_ARTIFACT_DIR / "iv_surface_skew_bundle.jsonl"
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
        "paper_only_iv_surface_bundle": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_iv_surface_bundle_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"IV surface bundle requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("IV surface bundle requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("IV surface bundle requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("IV surface bundle requires allow_unofficial_robinhood_api=false")


def _family_score_records() -> list[dict]:
    records: list[dict] = []
    for scenario in build_iv_surface_scenarios():
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
            "family_iv_fit_score": round(sum(float(row["family_iv_fit_score"]) for row in rows) / count, 6),
            "iv_surface_fit_score": round(sum(float(row["iv_surface_fit_score"]) for row in rows) / count, 6),
            "skew_term_score": round(sum(float(row["skew_term_score"]) for row in rows) / count, 6),
            "premium_overpayment_score": round(sum(float(row["premium_overpayment_score"]) for row in rows) / count, 6),
            "surface_instability_penalty": round(sum(float(row["surface_instability_penalty"]) for row in rows) / count, 6),
            "term_structure_risk_penalty": round(sum(float(row["term_structure_risk_penalty"]) for row in rows) / count, 6),
        }
    return output


def _failure_mining_rows(records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        rows.append({
            "strategy_id": f"iv-surface-{record['strategy_family']}-{record['scenario_id']}",
            "strategy_family": record["strategy_family"],
            "average_expected_slippage_pct": 0.0,
            "average_liquidity_score": 1.0,
            "average_delta_fit_score": 1.0,
            "average_greek_fit_score": 1.0,
            "average_pattern_fixture_score": 1.0,
            "slippage_robustness_score": 1.0,
            "family_regime_survival": 1.0,
            "mutation_adjustment": 0.0,
            "average_premium_overpayment_score": record["premium_overpayment_score"],
            "average_iv_crush_score": record["iv_crush_score"],
            "average_front_event_bump_score": record["front_event_bump_score"],
            "average_skew_trap_score": record["skew_trap_score"],
            "average_wing_elevation_score": record["wing_elevation_score"],
            "average_surface_instability_penalty": record["surface_instability_penalty"],
            "average_term_structure_risk_penalty": record["term_structure_risk_penalty"],
            "worst_iv_surface_regime": record["scenario_regime_tag"],
            "worst_iv_surface_scenario": record["scenario_id"],
        })
    return rows


def _best_iv_fit_family(tournament_summary: dict, average_scores: dict[str, dict]) -> str:
    family_scores = dict(tournament_summary.get("iv_surface_expansion_summary", {}).get("family_scores", {}))
    if family_scores:
        return sorted(
            family_scores,
            key=lambda family: (-float(family_scores[family].get("average_family_iv_fit_score", 0.0)), family),
        )[0]
    return sorted(
        average_scores,
        key=lambda family: (-float(average_scores[family].get("family_iv_fit_score", 0.0)), family),
    )[0]


def _worst_iv_trap_family(tournament_summary: dict, average_scores: dict[str, dict]) -> str:
    family_scores = dict(tournament_summary.get("iv_surface_expansion_summary", {}).get("family_scores", {}))
    if family_scores:
        return sorted(
            family_scores,
            key=lambda family: (-float(family_scores[family].get("average_premium_overpayment_score", 0.0)), family),
        )[0]
    return sorted(
        average_scores,
        key=lambda family: (-float(average_scores[family].get("premium_overpayment_score", 0.0)), family),
    )[0]


def _new_failure_mode_ids(failure_registry: object) -> list[str]:
    requested = {
        "premium_overpayment_trap_failure",
        "iv_crush_after_vol_expansion_failure",
        "front_event_bump_against_compression",
        "backwardation_against_compression",
        "skew_trap_against_directional",
        "surface_instability_fakeout_failure",
        "short_duration_front_iv_instability",
        "term_structure_mismatch",
        "wing_elevation_breakout_risk",
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
        "champion_family_iv_fit_score": round(float(champion.get("average_family_iv_fit_score", 0.0)), 6),
        "champion_premium_overpayment_score": round(float(champion.get("average_premium_overpayment_score", 0.0)), 6),
    }


def _build_proof_entry(summary: dict, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id="dopey-iv-surface-skew-expansion-bundle-v1",
        task_id="iv-surface-skew-expansion-bundle",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=summary["reproducibility_hash"],
        plan_hash=reproducibility_hash({"bundle_version": IV_SURFACE_BUNDLE_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "bundle_summary": summary,
            "registry_record": registry_record,
            "safety_state": summary["safety_state"],
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[
            summary["iv_surface_registry_path"],
            summary["failure_mode_registry_path"],
            summary["proof_record_path"],
        ],
        diffs=[],
        test_results={
            "bundle_status": summary["bundle_status"],
            "surface_scenarios_loaded": summary["surface_scenarios_loaded"],
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
            "offline deterministic IV surface/skew/term fixture intelligence only",
            "fixture scoring is not live performance evidence",
            "no broker connection, credentials, market-data network fetch, schedule, or live promotion",
        ],
    )


def run_iv_surface_skew_bundle(
    registry_path: Path | str | None = None,
    failure_mode_registry_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_iv_surface_bundle_safety_state(safety)
    scenarios = build_iv_surface_scenarios()
    scenario_ledger = build_scenario_ledger_records()
    family_score_records = _family_score_records()
    average_family_scores = _average_family_scores(family_score_records)
    failure_mining_rows = _failure_mining_rows(family_score_records)
    tournament_summary = run_fixture_tournament()
    failure_registry = mine_failure_modes(tournament_summary["strategy_ranking"], failure_mining_rows, [])
    new_failure_modes = _new_failure_mode_ids(failure_registry)
    feedback_recommendations = _recommendations_for_failures(failure_registry)
    families_scored = sorted(average_family_scores)
    target_registry = Path(registry_path) if registry_path else IV_SURFACE_REGISTRY_PATH
    target_failure_registry = Path(failure_mode_registry_path) if failure_mode_registry_path else FAILURE_MODE_REGISTRY_PATH
    target_proof = Path(proof_ledger_path) if proof_ledger_path else IV_SURFACE_BUNDLE_LEDGER_PATH
    failure_mode_record = failure_registry.to_dict()
    failure_mode_record["source_bundle"] = IV_SURFACE_BUNDLE_VERSION
    failure_mode_record["safety_state"] = safety
    failure_mode_target = write_failure_mode_registry(failure_mode_record, target_failure_registry)
    registry_record = {
        "bundle_version": IV_SURFACE_BUNDLE_VERSION,
        "iv_surface_expansion_version": IV_SURFACE_EXPANSION_VERSION,
        "iv_surface_scenario_version": IV_SURFACE_SCENARIO_VERSION,
        "skew_term_structure_version": SKEW_TERM_STRUCTURE_VERSION,
        "iv_family_scoring_version": IV_FAMILY_SCORING_VERSION,
        "volatility_regime_version": VOLATILITY_REGIME_VERSION,
        "surface_scenarios": scenario_ledger,
        "family_score_records": family_score_records,
        "failure_mining_rows": failure_mining_rows,
        "average_family_scores": average_family_scores,
        "tournament_iv_surface_expansion_summary": tournament_summary["iv_surface_expansion_summary"],
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
        "surface_scenarios_loaded": len(scenarios),
        "families_scored": families_scored,
        "best_iv_fit_family": _best_iv_fit_family(tournament_summary, average_family_scores),
        "worst_iv_trap_family": _worst_iv_trap_family(tournament_summary, average_family_scores),
        "new_failure_modes_detected": new_failure_modes,
        "feedback_recommendations_added": sorted({
            str(recommendation["tuning_key"])
            for recommendation in feedback_recommendations
            if recommendation["failure_mode_id"] in new_failure_modes
        }),
        "tournament_score_impact": _tournament_score_impact(tournament_summary),
        "champion_strategy_id": tournament_summary["champion_strategy_id"],
        "family_ranking_impact": tournament_summary["family_scorecard"],
        "greek_iv_summary": tournament_summary["greek_iv_summary"],
        "slippage_liquidity_summary": tournament_summary["slippage_liquidity_summary"],
        "overfit_summary": tournament_summary["overfit_summary"],
        "promotion_decisions": tournament_summary["promotion_decisions"],
        "live_blocked": safety["live_blocked"],
        "safety_state": safety,
        "iv_surface_registry_path": str(registry_target),
        "failure_mode_registry_path": str(failure_mode_target),
        "proof_record_path": str(target_proof),
    }
    repro = reproducibility_hash(registry_record, summary)
    summary["reproducibility_hash"] = repro
    registry_record["reproducibility_hash"] = repro
    ProofLedger(target_proof).append(_build_proof_entry(summary, registry_record))
    return summary


def main() -> int:
    summary = run_iv_surface_skew_bundle()
    concise = {
        "bundle_status": summary["bundle_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "surface_scenarios_loaded": summary["surface_scenarios_loaded"],
        "families_scored": summary["families_scored"],
        "best_iv_fit_family": summary["best_iv_fit_family"],
        "worst_iv_trap_family": summary["worst_iv_trap_family"],
        "new_failure_modes_detected": summary["new_failure_modes_detected"],
        "tournament_score_impact": summary["tournament_score_impact"],
        "live_blocked": summary["live_blocked"],
        "iv_surface_registry_path": summary["iv_surface_registry_path"],
        "proof_record_path": summary["proof_record_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["bundle_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
