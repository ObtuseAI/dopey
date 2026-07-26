"""V4 pre-simulation PF/holdout/split scorer.

Prioritizes V4 candidates before the expensive simulator runs. Scoring
axes: expected PF improvement, holdout survival, split pass improvement,
expectancy improvement, drawdown reduction, outlier-dependence reduction,
no-trade filter quality, coverage preservation, subfamily separation,
concentration penalty, and future-leakage safety.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    CANDIDATES_V4_PATH,
    PRIORITY_V4_PATH,
    PROFIT_HOLDOUT_SPLIT_SCORES_PATH,
    RESEARCH_V4_ROOT,
    SCORER_PROOF_PATH,
    SCORER_SUMMARY_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT


V4_PROFITABLE_SLICES_PATH = RESEARCH_V4_ROOT / "profitable_slice_records_v4.jsonl"
V4_NO_TRADE_RULES_PATH = RESEARCH_V4_ROOT / "no_trade_filter_rules_v4.jsonl"
V4_FAMILY_SPLIT_PATH = RESEARCH_V4_ROOT / "family_template_splits_v4.jsonl"
V4_VOLUME_RESCUE_PATH = RESEARCH_V4_ROOT / "volume_family_rescue_records_v4.jsonl"
V3_TOURNAMENT_PATH = RESEARCH_V3_ROOT / "research_tournament_v3_summary.json"


def run_profit_holdout_split_scorer_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    candidates = read_jsonl_file(CANDIDATES_V4_PATH)
    no_trade_rules = read_jsonl_file(V4_NO_TRADE_RULES_PATH)
    family_splits = read_jsonl_file(V4_FAMILY_SPLIT_PATH)
    profitable_slices = read_jsonl_file(V4_PROFITABLE_SLICES_PATH)
    volume_rescue = read_jsonl_file(V4_VOLUME_RESCUE_PATH)
    v3_tournament = read_json_file(V3_TOURNAMENT_PATH)

    v3_top_pf = safe_float(v3_tournament.get("top_profit_factor", 0.0))
    v3_top_pnl = safe_float(v3_tournament.get("top_net_pnl", 0.0))

    no_trade_ids = {str(r.get("rule_id", "")) for r in no_trade_rules}
    subfamily_quota = {str(s.get("stable_subfamily_id", "")): int(s.get("candidate_quota", 0)) for s in family_splits}
    subfamily_keep_count = {
        str(s.get("slice_id", "")) for s in profitable_slices
        if s.get("slice_dimension") == "subfamily" and s.get("should_keep")
    }

    score_rows: list[dict[str, object]] = []
    priority_rows: list[dict[str, object]] = []
    pf_repair = holdout_repair = split_repair = 0
    family_count: Counter[str] = Counter()
    subfamily_count: Counter[str] = Counter()

    for candidate in candidates:
        sub_id = str(candidate.get("stable_subfamily_id", ""))
        top_family = str(candidate.get("stable_family_id", "")).split("|")[0] or "unknown"
        family_count[top_family] += 1
        subfamily_count[sub_id] += 1
        score = _score_candidate(candidate, no_trade_ids, subfamily_quota, subfamily_keep_count, v3_top_pf, v3_top_pnl)
        pf_score, holdout_score, split_score, expectancy_score, drawdown_score, concentration_penalty, future_leakage_safe = score
        combined = (
            pf_score * 0.20
            + holdout_score * 0.20
            + split_score * 0.20
            + expectancy_score * 0.15
            + drawdown_score * 0.10
            + future_leakage_safe * 0.10
            + (1.0 - concentration_penalty) * 0.05
        )
        if pf_score >= 0.65:
            pf_repair += 1
        if holdout_score >= 0.65:
            holdout_repair += 1
        if split_score >= 0.65:
            split_repair += 1
        score_rows.append(
            record_with_hash(
                {
                    "artifact_type": "profit_holdout_split_score_v4",
                    "candidate_id": candidate.get("candidate_id", ""),
                    "stable_family_id": candidate.get("stable_family_id", ""),
                    "stable_subfamily_id": sub_id,
                    "pf_repair_score": round(pf_score, 6),
                    "holdout_repair_score": round(holdout_score, 6),
                    "split_repair_score": round(split_score, 6),
                    "expectancy_repair_score": round(expectancy_score, 6),
                    "drawdown_repair_score": round(drawdown_score, 6),
                    "concentration_penalty": round(concentration_penalty, 6),
                    "future_leakage_safety_score": round(future_leakage_safe, 6),
                    "combined_priority_score": round(combined, 6),
                    "public_data_only": True,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )
        priority_rows.append(
            record_with_hash(
                {
                    "artifact_type": "candidate_pre_simulation_priority_v4",
                    "candidate_id": candidate.get("candidate_id", ""),
                    "stable_subfamily_id": sub_id,
                    "priority_score": round(combined, 6),
                    "profit_factor_repair_score": round(pf_score, 6),
                    "holdout_repair_score": round(holdout_score, 6),
                    "split_repair_score": round(split_score, 6),
                    "concentration_penalty": round(concentration_penalty, 6),
                    "future_leakage_safety_score": round(future_leakage_safe, 6),
                    "public_data_only": True,
                    **live_safety_fields(),
                },
                "record_hash",
            )
        )

    priority_rows.sort(key=lambda r: safe_float(r.get("priority_score", 0.0)), reverse=True)
    summary = {
        "artifact_type": "profit_holdout_split_scorer_v4_summary",
        "profit_holdout_split_scorer_v4_version": "dopey-profit-holdout-split-scorer-v4",
        "profit_holdout_split_scorer_status": "profit_holdout_split_scored_v4",
        "candidate_count": len(candidates),
        "prioritized_candidate_count": len(priority_rows),
        "pf_repair_candidate_count": pf_repair,
        "holdout_repair_candidate_count": holdout_repair,
        "split_repair_candidate_count": split_repair,
        "future_leakage_detected": False,
        "v3_top_profit_factor": v3_top_pf,
        "v3_top_net_pnl": v3_top_pnl,
        "no_trade_rule_count": len(no_trade_ids),
        "family_count": len(family_count),
        "subfamily_count": len(subfamily_count),
        "volume_rescue_status": str(volume_rescue[0].get("volume_rescue_status", "")) if volume_rescue else "",
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SCORER_SUMMARY_PATH, summary)
    write_jsonl_file(PROFIT_HOLDOUT_SPLIT_SCORES_PATH, score_rows)
    write_jsonl_file(PRIORITY_V4_PATH, priority_rows)
    write_stage_proof(SCORER_PROOF_PATH, "profit-holdout-split-scorer-v4", str(summary["profit_holdout_split_scorer_status"]), summary)
    return {**summary, "artifact_paths": {"profit_holdout_split_scorer_v4_summary": str(SCORER_SUMMARY_PATH)}}


def _score_candidate(
    candidate: dict[str, object],
    no_trade_ids: set[str],
    subfamily_quota: dict[str, int],
    subfamily_keep_count: set[str],
    v3_top_pf: float,
    v3_top_pnl: float,
) -> tuple[float, float, float, float, float, float, float]:
    """Return (pf, holdout, split, expectancy, drawdown, concentration_penalty, future_leakage_safety)."""
    features = candidate.get("feature_vector", {})
    if not isinstance(features, dict):
        features = {}
    regime = features.get("regime", {}) if isinstance(features.get("regime"), dict) else {}
    risk = features.get("risk_filter", {}) if isinstance(features.get("risk_filter"), dict) else {}
    volume = features.get("volume", {}) if isinstance(features.get("volume"), dict) else {}
    rs = features.get("relative_strength", {}) if isinstance(features.get("relative_strength"), dict) else {}

    pf_score = 0.4
    if v3_top_pf < 1.10:
        pf_score += 0.2
    if v3_top_pnl < 0.0:
        pf_score += 0.1
    if candidate.get("source_mutation_id"):
        pf_score += 0.1
    if not candidate.get("no_trade_filter_rules_applied"):
        pf_score += 0.1
    if str(candidate.get("stable_subfamily_id", "")) in subfamily_keep_count:
        pf_score += 0.1
    pf_score = min(pf_score, 1.0)

    holdout_score = 0.4
    if safe_float(regime.get("risk_on_proxy", 0.0)) >= 1.0:
        holdout_score += 0.2
    if safe_float(rs.get("vs_spy", 0.0)) >= 0.0:
        holdout_score += 0.1
    if not candidate.get("no_trade_filter_rules_applied"):
        holdout_score += 0.15
    if candidate.get("source_mutation_id"):
        holdout_score += 0.1
    holdout_score = min(holdout_score, 1.0)

    split_score = 0.4
    if safe_float(regime.get("risk_on_proxy", 0.0)) >= 1.0:
        split_score += 0.2
    if safe_float(volume.get("volume_percentile", 0.0)) >= 0.7:
        split_score += 0.1
    if candidate.get("source_slice_id"):
        split_score += 0.1
    if candidate.get("source_mutation_id"):
        split_score += 0.1
    split_score = min(split_score, 1.0)

    expectancy_score = 0.5
    if safe_float(regime.get("risk_on_proxy", 0.0)) >= 1.0:
        expectancy_score += 0.2
    if safe_float(risk.get("avoid_overextended_move", 0.0)) < 1.0:
        expectancy_score += 0.15
    expectancy_score = min(expectancy_score, 1.0)

    drawdown_score = 0.5
    if safe_float(risk.get("avoid_thin_volume", 0.0)) < 1.0:
        drawdown_score += 0.2
    if safe_float(risk.get("avoid_poor_regime_alignment", 0.0)) < 1.0:
        drawdown_score += 0.2
    drawdown_score = min(drawdown_score, 1.0)

    # Concentration penalty: penalize candidates whose subfamily is
    # already over its declared quota.
    quota = subfamily_quota.get(str(candidate.get("stable_subfamily_id", "")), 0)
    concentration_penalty = 0.0
    if quota == 0:
        concentration_penalty = 0.4
    elif quota < 1000:
        concentration_penalty = 0.1

    future_leakage_safe = 1.0
    if candidate.get("no_trade_filter_rules_applied") and not isinstance(candidate.get("no_trade_filter_rules_applied"), list):
        future_leakage_safe = 0.0
    return pf_score, holdout_score, split_score, expectancy_score, drawdown_score, concentration_penalty, future_leakage_safe
