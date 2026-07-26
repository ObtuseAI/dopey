"""CLI for the deterministic DOPEY sector/peer/fundamental fixture expansion bundle.

This bundle broadens offline sector / peer / fundamental / valuation / earnings-quality /
crowding fixture intelligence. It is fully offline, fixture-based, paper-only,
deterministic, and live-blocked.
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

from .fundamental_coverage import build_fundamental_coverage
from .fundamental_family_scoring import (
    FUNDAMENTAL_FAMILY_SCORING_VERSION,
    score_all_families_for_scenario,
)
from .fundamental_fixture_models import scenario_hash
from .sector_peer_scenarios import (
    REQUIRED_SCENARIO_IDS,
    SECTOR_PEER_SCENARIO_VERSION,
    build_scenario_ledger_records,
    build_sector_peer_fundamental_scenarios,
)


SECTOR_PEER_FUNDAMENTAL_BUNDLE_VERSION = "dopey-sector-peer-fundamental-fixture-expansion-v1"
SECTOR_PEER_FUNDAMENTAL_EXPANSION_VERSION = "dopey-sector-peer-fundamental-expansion-v1"
FUNDAMENTAL_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "fundamental_fixtures"
FUNDAMENTAL_REGISTRY_PATH = FUNDAMENTAL_ARTIFACT_DIR / "fundamental_registry.jsonl"
FUNDAMENTAL_BUNDLE_LEDGER_PATH = FUNDAMENTAL_ARTIFACT_DIR / "fundamental_bundle.jsonl"
FUNDAMENTAL_COVERAGE_PATH = FUNDAMENTAL_ARTIFACT_DIR / "fundamental_coverage.jsonl"
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
        "paper_only_fundamental_bundle": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_sector_peer_fundamental_bundle_safety_state(safety_state: dict) -> None:
    if safety_state.get("mode") != "RESEARCH":
        raise ValueError(f"fundamental bundle requires RESEARCH mode, got {safety_state.get('mode')}")
    if safety_state.get("live_trading_enabled") is not False:
        raise ValueError("fundamental bundle requires live_trading_enabled=false")
    if safety_state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("fundamental bundle requires funded_broker_connections_enabled=false")
    if safety_state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("fundamental bundle requires allow_unofficial_robinhood_api=false")


def _family_score_records() -> list[dict]:
    records: list[dict] = []
    for scenario in build_sector_peer_fundamental_scenarios():
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
            "fundamental_fit_score": round(sum(float(row["fundamental_fit_score"]) for row in rows) / count, 6),
            "sector_fit_score": round(sum(float(row["sector_fit_score"]) for row in rows) / count, 6),
            "peer_confirmation_score": round(sum(float(row["peer_confirmation_score"]) for row in rows) / count, 6),
            "fundamental_confirmation_score": round(sum(float(row["fundamental_confirmation_score"]) for row in rows) / count, 6),
            "valuation_risk_score": round(sum(float(row["valuation_risk_score"]) for row in rows) / count, 6),
            "earnings_quality_score": round(sum(float(row["earnings_quality_score"]) for row in rows) / count, 6),
            "crowding_risk_score": round(sum(float(row["crowding_risk_score"]) for row in rows) / count, 6),
            "fundamental_contradiction_penalty": round(sum(float(row["fundamental_contradiction_penalty"]) for row in rows) / count, 6),
            "fragility_penalty": round(sum(float(row["fragility_penalty"]) for row in rows) / count, 6),
        }
    return output


def _failure_mining_rows(records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for record in records:
        rows.append({
            "strategy_id": f"fundamental-{record['strategy_family']}-{record['scenario_id']}",
            "strategy_family": record["strategy_family"],
            "average_expected_slippage_pct": 0.0,
            "average_liquidity_score": 1.0,
            "average_delta_fit_score": 1.0,
            "average_greek_fit_score": 1.0,
            "average_pattern_fixture_score": 1.0,
            "slippage_robustness_score": 1.0,
            "family_regime_survival": 1.0,
            "mutation_adjustment": 0.0,
            "average_fundamental_fit_score": record["fundamental_fit_score"],
            "average_sector_fit_score": record["sector_fit_score"],
            "average_peer_confirmation_score": record["peer_confirmation_score"],
            "average_fundamental_confirmation_score": record["fundamental_confirmation_score"],
            "average_valuation_risk_score": record["valuation_risk_score"],
            "average_earnings_quality_score": record["earnings_quality_score"],
            "average_crowding_risk_score": record["crowding_risk_score"],
            "average_fundamental_contradiction_penalty": record["fundamental_contradiction_penalty"],
            "average_fragility_penalty": record["fragility_penalty"],
            "fundamental_risk_flags": record["risk_flags"],
            "best_fundamental_scenario": record["scenario_id"],
            "worst_fundamental_scenario": record["scenario_id"],
            "worst_regimes": [record["scenario_regime_tag"]] if record["penalized_by_scenario"] else [],
        })
    return rows


def _new_failure_mode_ids(failure_registry: object) -> list[str]:
    requested = {
        "peer_contradiction_against_directional",
        "valuation_trap_against_directional",
        "low_dispersion_against_vol_expansion",
        "post_event_clarity_against_vol_expansion",
        "high_dispersion_against_compression",
        "revision_shock_against_compression",
        "crowded_fakeout_against_short_duration",
        "small_cap_liquidity_decay_against_short_duration",
        "sector_rotation_late_day_bad_fill",
        "fundamental_event_overfit",
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


def _best_fundamental_fit_family(average_scores: dict[str, dict]) -> str:
    if not average_scores:
        return ""
    return sorted(
        average_scores,
        key=lambda family: (-float(average_scores[family].get("fundamental_fit_score", 0.0)), family),
    )[0]


def _worst_fundamental_trap_family(average_scores: dict[str, dict]) -> str:
    if not average_scores:
        return ""
    return sorted(
        average_scores,
        key=lambda family: (
            -float(average_scores[family].get("fundamental_contradiction_penalty", 0.0)),
            -float(average_scores[family].get("valuation_risk_score", 0.0)),
            family,
        ),
    )[0]


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
        "champion_family_fundamental_fit_score": round(float(champion.get("average_fundamental_fit_score", 0.0)), 6),
        "champion_fundamental_contradiction_penalty": round(float(champion.get("average_fundamental_contradiction_penalty", 0.0)), 6),
    }


def _build_proof_entry(summary: dict, registry_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=SECTOR_PEER_FUNDAMENTAL_BUNDLE_VERSION,
        task_id="sector-peer-fundamental-fixture-expansion-bundle",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=summary["reproducibility_hash"],
        plan_hash=reproducibility_hash({"bundle_version": SECTOR_PEER_FUNDAMENTAL_BUNDLE_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "bundle_summary": summary,
            "registry_record": registry_record,
            "safety_state": summary["safety_state"],
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=[
            summary["fundamental_registry_path"],
            summary["fundamental_coverage_path"],
            summary["failure_mode_registry_path"],
            summary["proof_record_path"],
        ],
        diffs=[],
        test_results={
            "bundle_status": summary["bundle_status"],
            "scenarios_loaded": summary["scenarios_loaded"],
            "families_scored": summary["families_scored"],
            "new_fundamental_failure_modes_detected": summary["new_fundamental_failure_modes_detected"],
            "forbidden_live_decisions_present": sorted(
                set(summary["promotion_decisions"].values()).intersection(FORBIDDEN_LIVE_PROMOTIONS)
            ),
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "offline deterministic sector/peer/fundamental fixture intelligence only",
            "fixture scoring is not live performance evidence",
            "no broker connection, credentials, market-data network fetch, schedule, or live promotion",
        ],
    )


def run_sector_peer_fundamental_bundle(
    registry_path: Path | str | None = None,
    coverage_path: Path | str | None = None,
    failure_mode_registry_path: Path | str | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict:
    safety = _safety_state()
    verify_sector_peer_fundamental_bundle_safety_state(safety)
    scenarios = build_sector_peer_fundamental_scenarios()
    scenario_ids = {s.scenario_id for s in scenarios}
    missing_ids = sorted(REQUIRED_SCENARIO_IDS - scenario_ids)
    if missing_ids:
        raise ValueError(f"missing required scenarios: {missing_ids}")
    scenario_ledger = build_scenario_ledger_records()
    family_score_records = _family_score_records()
    average_family_scores = _average_family_scores(family_score_records)
    failure_mining_rows = _failure_mining_rows(family_score_records)
    coverage = build_fundamental_coverage(scenarios)
    tournament_summary = run_fixture_tournament()
    failure_registry = mine_failure_modes(tournament_summary["strategy_ranking"], failure_mining_rows, [])
    new_failure_modes = _new_failure_mode_ids(failure_registry)
    feedback_recommendations = _recommendations_for_failures(failure_registry)
    families_scored = sorted(average_family_scores)
    target_registry = Path(registry_path) if registry_path else FUNDAMENTAL_REGISTRY_PATH
    target_coverage = Path(coverage_path) if coverage_path else FUNDAMENTAL_COVERAGE_PATH
    target_failure_registry = Path(failure_mode_registry_path) if failure_mode_registry_path else FAILURE_MODE_REGISTRY_PATH
    target_proof = Path(proof_ledger_path) if proof_ledger_path else FUNDAMENTAL_BUNDLE_LEDGER_PATH
    failure_mode_record = failure_registry.to_dict()
    failure_mode_record["source_bundle"] = SECTOR_PEER_FUNDAMENTAL_BUNDLE_VERSION
    failure_mode_record["safety_state"] = safety
    failure_mode_target = write_failure_mode_registry(failure_mode_record, target_failure_registry)
    scenario_hashes = {scenario.scenario_id: scenario_hash(scenario) for scenario in scenarios}
    registry_record = {
        "bundle_version": SECTOR_PEER_FUNDAMENTAL_BUNDLE_VERSION,
        "sector_peer_fundamental_expansion_version": SECTOR_PEER_FUNDAMENTAL_EXPANSION_VERSION,
        "sector_peer_scenario_version": SECTOR_PEER_SCENARIO_VERSION,
        "fundamental_family_scoring_version": FUNDAMENTAL_FAMILY_SCORING_VERSION,
        "scenarios": scenario_ledger,
        "scenario_hashes": scenario_hashes,
        "family_score_records": family_score_records,
        "failure_mining_rows": failure_mining_rows,
        "average_family_scores": average_family_scores,
        "coverage": coverage.to_dict(),
        "tournament_fundamental_summary": tournament_summary.get("fundamental_summary", {}),
        "failure_mode_registry": failure_mode_record,
        "failure_mode_registry_path": str(failure_mode_target),
        "feedback_recommendations": feedback_recommendations,
        "safety_state": safety,
    }
    registry_target = _write_jsonl(registry_record, target_registry)
    coverage_target = _write_jsonl(coverage.to_dict(), target_coverage)
    summary = {
        "bundle_status": "ok",
        "mode": safety["mode"],
        "live_trading_enabled": safety["live_trading_enabled"],
        "scenarios_loaded": len(scenarios),
        "families_scored": families_scored,
        "best_fundamental_fit_family": _best_fundamental_fit_family(average_family_scores),
        "worst_fundamental_trap_family": _worst_fundamental_trap_family(average_family_scores),
        "new_fundamental_failure_modes_detected": new_failure_modes,
        "feedback_recommendations_added": sorted({
            str(recommendation["tuning_key"])
            for recommendation in feedback_recommendations
            if recommendation["failure_mode_id"] in new_failure_modes
        }),
        "tournament_score_impact": _tournament_score_impact(tournament_summary),
        "champion_strategy_id": tournament_summary["champion_strategy_id"],
        "family_ranking_impact": tournament_summary["family_scorecard"],
        "fundamental_summary": tournament_summary.get("fundamental_summary", {}),
        "macro_event_summary": tournament_summary.get("macro_event_summary", {}),
        "greek_iv_summary": tournament_summary.get("greek_iv_summary", {}),
        "slippage_liquidity_summary": tournament_summary.get("slippage_liquidity_summary", {}),
        "overfit_summary": tournament_summary["overfit_summary"],
        "promotion_decisions": tournament_summary["promotion_decisions"],
        "live_blocked": safety["live_blocked"],
        "safety_state": safety,
        "fundamental_registry_path": str(registry_target),
        "fundamental_coverage_path": str(coverage_target),
        "failure_mode_registry_path": str(failure_mode_target),
        "proof_record_path": str(target_proof),
    }
    repro = reproducibility_hash(registry_record, summary)
    summary["reproducibility_hash"] = repro
    registry_record["reproducibility_hash"] = repro
    ProofLedger(target_proof).append(_build_proof_entry(summary, registry_record))
    return summary


def main() -> int:
    summary = run_sector_peer_fundamental_bundle()
    concise = {
        "fundamental_bundle_status": summary["bundle_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "scenarios_loaded": summary["scenarios_loaded"],
        "families_scored": summary["families_scored"],
        "best_fundamental_fit_family": summary["best_fundamental_fit_family"],
        "worst_fundamental_trap_family": summary["worst_fundamental_trap_family"],
        "new_fundamental_failure_modes_detected": summary["new_fundamental_failure_modes_detected"],
        "tournament_score_impact": summary["tournament_score_impact"],
        "live_blocked": summary["live_blocked"],
        "fundamental_registry_path": summary["fundamental_registry_path"],
        "proof_record_path": summary["proof_record_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["bundle_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
