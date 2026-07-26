"""Write deterministic hybrid swing/0DTE v3 replay corpus artifacts."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .hybrid_replay_models import HybridOpportunityPair
from .hybrid_swing_0dte_coverage import score_hybrid_swing_0dte_coverage
from .hybrid_swing_0dte_fixture_builder import (
    build_hybrid_opportunity_pairs_v3,
    build_hybrid_swing_candidates_v3,
    build_hybrid_underlying_families_v3,
)
from .hybrid_swing_zero_dte_replay_engine import run_hybrid_replay
from .multi_day_swing_path_builder import build_multi_day_swing_paths_v3
from .run_zero_dte_cross_underlying_v2 import run_zero_dte_cross_underlying_v2
from .swing_option_models import SwingOptionCandidate, stable_hybrid_hash
from .zero_dte_underlying_family_models import ZeroDTEUnderlyingFamily


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy"
HYBRID_UNDERLYING_FAMILIES_FIXTURE_PATH = FIXTURE_DIR / "hybrid_underlying_families_v3.json"
HYBRID_SWING_CANDIDATES_FIXTURE_PATH = FIXTURE_DIR / "hybrid_swing_candidates_v3.json"
HYBRID_OPPORTUNITY_PAIRS_FIXTURE_PATH = FIXTURE_DIR / "hybrid_opportunity_pairs_v3.json"
HYBRID_MULTI_DAY_PATHS_FIXTURE_PATH = FIXTURE_DIR / "hybrid_multi_day_paths_v3.json"
HYBRID_EXPECTED_OUTCOMES_FIXTURE_PATH = FIXTURE_DIR / "hybrid_expected_outcomes_v3.json"
HYBRID_EXPECTED_ALLOCATOR_TAGS_FIXTURE_PATH = FIXTURE_DIR / "hybrid_expected_allocator_tags_v3.json"

HYBRID_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "hybrid_swing_0dte_v3"
HYBRID_UNDERLYING_FAMILIES_PATH = HYBRID_ARTIFACT_DIR / "hybrid_underlying_families.json"
HYBRID_SWING_CANDIDATES_PATH = HYBRID_ARTIFACT_DIR / "hybrid_swing_candidates.json"
HYBRID_OPPORTUNITY_PAIRS_PATH = HYBRID_ARTIFACT_DIR / "hybrid_opportunity_pairs.json"
HYBRID_MULTI_DAY_PATHS_PATH = HYBRID_ARTIFACT_DIR / "hybrid_multi_day_paths.json"
HYBRID_REPLAY_OUTCOMES_PATH = HYBRID_ARTIFACT_DIR / "hybrid_replay_outcomes.jsonl"
HYBRID_PREFERENCE_SCORES_PATH = HYBRID_ARTIFACT_DIR / "hybrid_preference_scores.jsonl"
HYBRID_ALLOCATOR_TAGS_PATH = HYBRID_ARTIFACT_DIR / "hybrid_allocator_tags.jsonl"
HYBRID_COVERAGE_SUMMARY_PATH = HYBRID_ARTIFACT_DIR / "hybrid_coverage_summary.json"
HYBRID_THRESHOLD_SURVIVAL_PATH = HYBRID_ARTIFACT_DIR / "hybrid_threshold_survival.json"
HYBRID_REPLAY_SUMMARY_PATH = HYBRID_ARTIFACT_DIR / "hybrid_replay_summary.json"
HYBRID_CORPUS_PROOF_PATH = HYBRID_ARTIFACT_DIR / "hybrid_corpus_proof.jsonl"


def load_hybrid_underlying_families_v3(path: Path | str = HYBRID_UNDERLYING_FAMILIES_FIXTURE_PATH) -> list[ZeroDTEUnderlyingFamily]:
    target = Path(path)
    if not target.exists():
        write_hybrid_fixture_files_v3()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [ZeroDTEUnderlyingFamily.from_dict(record) for record in payload.get("families", [])]


def load_hybrid_swing_candidates_v3(path: Path | str = HYBRID_SWING_CANDIDATES_FIXTURE_PATH) -> list[SwingOptionCandidate]:
    target = Path(path)
    if not target.exists():
        write_hybrid_fixture_files_v3()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [SwingOptionCandidate.from_dict(record) for record in payload.get("candidates", [])]


def load_hybrid_opportunity_pairs_v3(path: Path | str = HYBRID_OPPORTUNITY_PAIRS_FIXTURE_PATH) -> list[HybridOpportunityPair]:
    target = Path(path)
    if not target.exists():
        write_hybrid_fixture_files_v3()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [HybridOpportunityPair.from_dict(record) for record in payload.get("pairs", [])]


def load_hybrid_multi_day_paths_v3(path: Path | str = HYBRID_MULTI_DAY_PATHS_FIXTURE_PATH) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        write_hybrid_fixture_files_v3()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return [dict(record) for record in payload.get("paths", [])]


def write_hybrid_fixture_files_v3() -> dict[str, str]:
    families = build_hybrid_underlying_families_v3()
    swing_candidates = build_hybrid_swing_candidates_v3(families)
    pairs = build_hybrid_opportunity_pairs_v3(families, swing_candidates)
    paths = build_multi_day_swing_paths_v3(pairs, swing_candidates)
    expected_outcomes = [{"pair_id": pair.pair_id, "expected_preference": pair.expected_preference, "expected_rotation_action": pair.expected_rotation_action, "paper_only": True, "live_blocked": True} for pair in pairs]
    expected_allocator_tags = [{"pair_id": pair.pair_id, "expected_allocator_tag_family": pair.expected_preference, "paper_only": True, "live_blocked": True} for pair in pairs]
    payloads = {
        HYBRID_UNDERLYING_FAMILIES_FIXTURE_PATH: {"fixture_version": "dopey-hybrid-underlying-families-v3", "family_count": len(families), "families": [family.to_dict() for family in families], "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        HYBRID_SWING_CANDIDATES_FIXTURE_PATH: {"fixture_version": "dopey-hybrid-swing-candidates-v3", "candidate_count": len(swing_candidates), "candidates": [candidate.to_dict() for candidate in swing_candidates], "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        HYBRID_OPPORTUNITY_PAIRS_FIXTURE_PATH: {"fixture_version": "dopey-hybrid-opportunity-pairs-v3", "pair_count": len(pairs), "pairs": [pair.to_dict() for pair in pairs], "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        HYBRID_MULTI_DAY_PATHS_FIXTURE_PATH: {"fixture_version": "dopey-hybrid-multi-day-paths-v3", "path_count": len(paths), "paths": paths, "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True},
        HYBRID_EXPECTED_OUTCOMES_FIXTURE_PATH: {"fixture_version": "dopey-hybrid-expected-outcomes-v3", "record_count": len(expected_outcomes), "records": expected_outcomes, "paper_only": True, "live_blocked": True},
        HYBRID_EXPECTED_ALLOCATOR_TAGS_FIXTURE_PATH: {"fixture_version": "dopey-hybrid-expected-allocator-tags-v3", "record_count": len(expected_allocator_tags), "records": expected_allocator_tags, "paper_only": True, "live_blocked": True, "real_sizing_allowed": False},
    }
    for path, payload in payloads.items():
        _write_json(path, payload)
    return {path.stem: str(path) for path in payloads}


def run_hybrid_swing_0dte_v3(summary_only: bool = False) -> dict[str, Any]:
    write_hybrid_fixture_files_v3()
    families = load_hybrid_underlying_families_v3()
    swing_candidates = load_hybrid_swing_candidates_v3()
    pairs = load_hybrid_opportunity_pairs_v3()
    paths = load_hybrid_multi_day_paths_v3()
    outcomes, preference_scores, allocator_tags, proof = run_hybrid_replay(pairs, swing_candidates, paths)
    coverage = score_hybrid_swing_0dte_coverage(families, pairs, outcomes, allocator_tags)
    v2 = run_zero_dte_cross_underlying_v2(summary_only=True)
    threshold_survival = _threshold_survival(outcomes, coverage, v2["threshold_survival"])
    summary = _summary(families, pairs, outcomes, preference_scores, allocator_tags, coverage, threshold_survival, v2["summary"])
    if not summary_only:
        HYBRID_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(HYBRID_UNDERLYING_FAMILIES_PATH, _artifact_json("hybrid_underlying_families", [family.to_dict() for family in families], "family_count"))
        _write_json(HYBRID_SWING_CANDIDATES_PATH, _artifact_json("hybrid_swing_candidates", [candidate.to_dict() for candidate in swing_candidates], "candidate_count"))
        _write_json(HYBRID_OPPORTUNITY_PAIRS_PATH, _artifact_json("hybrid_opportunity_pairs", [pair.to_dict() for pair in pairs], "pair_count"))
        _write_json(HYBRID_MULTI_DAY_PATHS_PATH, _artifact_json("hybrid_multi_day_paths", paths, "path_count"))
        _write_jsonl(HYBRID_REPLAY_OUTCOMES_PATH, outcomes)
        _write_jsonl(HYBRID_PREFERENCE_SCORES_PATH, preference_scores)
        _write_jsonl(HYBRID_ALLOCATOR_TAGS_PATH, allocator_tags)
        _write_json(HYBRID_COVERAGE_SUMMARY_PATH, coverage)
        _write_json(HYBRID_THRESHOLD_SURVIVAL_PATH, threshold_survival)
        _write_json(HYBRID_REPLAY_SUMMARY_PATH, summary)
        _write_jsonl(HYBRID_CORPUS_PROOF_PATH, proof)
    return {
        "hybrid_swing_0dte_v3_status": "ok" if summary["all_hybrid_expectations_matched"] else "fixture_expectation_mismatch",
        "summary": summary,
        "coverage": coverage,
        "threshold_survival": threshold_survival,
        "artifact_paths": hybrid_swing_0dte_artifact_paths(),
    }


def hybrid_swing_0dte_artifact_paths() -> dict[str, str]:
    return {
        "hybrid_underlying_families": str(HYBRID_UNDERLYING_FAMILIES_PATH),
        "hybrid_swing_candidates": str(HYBRID_SWING_CANDIDATES_PATH),
        "hybrid_opportunity_pairs": str(HYBRID_OPPORTUNITY_PAIRS_PATH),
        "hybrid_multi_day_paths": str(HYBRID_MULTI_DAY_PATHS_PATH),
        "hybrid_replay_outcomes": str(HYBRID_REPLAY_OUTCOMES_PATH),
        "hybrid_preference_scores": str(HYBRID_PREFERENCE_SCORES_PATH),
        "hybrid_allocator_tags": str(HYBRID_ALLOCATOR_TAGS_PATH),
        "hybrid_coverage_summary": str(HYBRID_COVERAGE_SUMMARY_PATH),
        "hybrid_threshold_survival": str(HYBRID_THRESHOLD_SURVIVAL_PATH),
        "hybrid_replay_summary": str(HYBRID_REPLAY_SUMMARY_PATH),
        "hybrid_corpus_proof": str(HYBRID_CORPUS_PROOF_PATH),
    }


def _threshold_survival(outcomes: list[dict[str, Any]], coverage: dict[str, Any], v2_survival: dict[str, Any]) -> dict[str, Any]:
    preference_counts = Counter(str(outcome["risk_adjusted_preference"]) for outcome in outcomes)
    record = {
        "artifact_type": "hybrid_threshold_survival",
        "pure_zero_dte_v2_status": v2_survival.get("stricter_gamma_theta_profile_status", ""),
        "hybrid_stricter_gamma_theta_profile_status": "paper_shadow_survives_no_research_default",
        "later_expiry_preference_status": "strengthen_later_expiry_preference_advisory_only" if preference_counts.get("prefer_swing", 0) else "not_evaluated",
        "paper_shadow_candidate_downgrade_status": "zero_dte_only_profiles_deferred_when_swing_or_delayed_rotation_preferred",
        "research_default_promotion_allowed": False,
        "live_threshold_mutation_allowed": False,
        "hybrid_overfit_pressure_score": coverage["hybrid_completeness_score"],
        "preference_distribution": dict(sorted(preference_counts.items())),
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _summary(
    families: list[ZeroDTEUnderlyingFamily],
    pairs: list[HybridOpportunityPair],
    outcomes: list[dict[str, Any]],
    preference_scores: list[dict[str, Any]],
    allocator_tags: list[dict[str, Any]],
    coverage: dict[str, Any],
    threshold_survival: dict[str, Any],
    v2_summary: dict[str, Any],
) -> dict[str, Any]:
    family_id_to_name = {family.underlying_family_id: family.family_name for family in families}
    family_counts = Counter(family_id_to_name[pair.underlying_family_id] for pair in pairs)
    regime_counts = Counter(pair.regime_family for pair in pairs)
    option_counts = Counter(pair.option_type for pair in pairs)
    preference_counts = Counter(pair.expected_preference for pair in pairs)
    tag_counts = Counter(tag for row in allocator_tags for tag in row.get("capital_allocator_tags", []))
    record = {
        "artifact_type": "hybrid_replay_summary",
        "hybrid_pair_count": len(pairs),
        "hybrid_replay_count": len(outcomes),
        "swing_candidate_count": len(pairs),
        "multi_day_path_count": len(pairs),
        "underlying_family_count": len(families),
        "underlying_family_distribution": dict(sorted(family_counts.items())),
        "regime_family_distribution": dict(sorted(regime_counts.items())),
        "option_type_distribution": dict(sorted(option_counts.items())),
        "preference_distribution": dict(sorted(preference_counts.items())),
        "allocator_tag_distribution": dict(sorted(tag_counts.items())),
        "no_day_trade_block_count": sum(1 for outcome in outcomes if outcome["no_day_trade_constraint_result"] == "same_day_close_blocked"),
        "delayed_rotation_count": sum(1 for outcome in outcomes if outcome["preferred_path"] == "delayed_rotation"),
        "special_close_count": sum(1 for outcome in outcomes if outcome["no_day_trade_constraint_result"] == "special_close_allowed_with_reason"),
        "next_day_close_count": sum(1 for outcome in outcomes if outcome["no_day_trade_constraint_result"] == "next_day_close_allowed"),
        "overnight_gap_stress_count": sum(1 for outcome in outcomes if outcome["no_day_trade_constraint_result"] == "overnight_gap_risk_recorded"),
        "all_hybrid_expectations_matched": all(outcome["expectation_matched"] for outcome in outcomes),
        "all_preference_expectations_matched": all(outcome["preference_expectation_matched"] for outcome in outcomes),
        "all_allocator_tag_expectations_matched": all(outcome["allocator_tag_expectation_matched"] for outcome in outcomes),
        "hybrid_completeness_score": coverage["hybrid_completeness_score"],
        "threshold_survival_impact": threshold_survival,
        "v2_combined_fixture_count": v2_summary.get("combined_v1_v2_fixture_count", 0),
        "research_default_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "real_sizing_allowed": False,
        "artifact_paths": hybrid_swing_0dte_artifact_paths(),
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _artifact_json(artifact_type: str, records: list[dict[str, Any]], count_key: str) -> dict[str, Any]:
    payload = {"artifact_type": artifact_type, count_key: len(records), "records": records, "paper_only": True, "live_blocked": True, "no_real_market_data": True, "no_broker": True}
    payload["reproducibility_hash"] = reproducibility_hash(payload)
    return payload


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash({k: v for k, v in payload.items() if k != "reproducibility_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    result = run_hybrid_swing_0dte_v3(args.summary_only)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["hybrid_swing_0dte_v3_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
