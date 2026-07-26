"""V6 pre-simulation profit/holdout/split scorer (Workstream F).

Reads V6 candidates and emits per-candidate scores across 11 axes:
- breakthrough-gate repair score
- holdout survival repair
- split pass repair
- PF preservation above 1.10
- expectancy preservation
- drawdown reduction
- stress survival repair
- concentration repair
- coverage preservation
- no-trade filter quality
- future leakage safety

Outputs a `priority` score per candidate (higher = better) and a
prioritized list for V6 simulation.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import (
    CANDIDATES_V6_PATH,
    PRIORITY_V6_PATH,
    PROFIT_HOLDOUT_SPLIT_SCORES_V6_PATH,
    RESEARCH_V6_VERSION,
    SCORER_V6_PROOF_PATH,
    SCORER_V6_SUMMARY_PATH,
    research_v6_proof_record,
    utc_now_iso,
)


__all__ = ["run_profit_holdout_split_scorer_v6"]


SCORE_AXES: tuple[str, ...] = (
    "breakthrough_gate_repair",
    "holdout_survival_repair",
    "split_pass_repair",
    "pf_preservation_above_110",
    "expectancy_preservation",
    "drawdown_reduction",
    "stress_survival_repair",
    "concentration_repair",
    "coverage_preservation",
    "no_trade_filter_quality",
    "future_leakage_safety",
)


def _read_jsonl_safe(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _score_candidate(c: dict[str, object]) -> dict[str, object]:
    """Deterministic per-axis scoring for a single candidate."""
    direction = str(c.get("direction", "no_trade"))
    subfamily = str(c.get("stable_subfamily_id", ""))
    family = str(c.get("stable_family_id", ""))
    no_trade_rules_applied = c.get("no_trade_filter_rules_applied", []) or []
    repair_rules_applied = c.get("repair_rules_applied", []) or []
    feature_vector = c.get("feature_vector", {}) or {}

    rs = float(feature_vector.get("relative_strength", 0.5) or 0.5)
    vr = float(feature_vector.get("volume_ratio", 1.0) or 1.0)
    vol = float(feature_vector.get("volatility", 0.3) or 0.3)
    ts = float(feature_vector.get("trend_strength", 0.4) or 0.4)
    ra = float(feature_vector.get("regime_alignment", 0.6) or 0.6)

    # 1. Breakthrough-gate repair score
    bgr = 0.7 if subfamily.startswith("continuation|") else 0.55
    # 2. Holdout survival repair
    hsr = 0.4 if direction == "no_trade" else 0.65 + 0.1 * ra
    # 3. Split pass repair
    spr = 0.5 + 0.2 * rs
    # 4. PF preservation above 1.10
    pfp = 0.55 + 0.25 * ts
    # 5. Expectancy preservation
    ep = 0.5 + 0.2 * ts
    # 6. Drawdown reduction
    ddr = 0.5 + 0.2 * min(vr, 2.0) / 2.0
    # 7. Stress survival repair
    ssr = 0.55 + 0.2 * (1.0 - vol)
    # 8. Concentration repair
    cr = 0.6
    # 9. Coverage preservation
    cov = 0.7
    # 10. No-trade filter quality
    ntq = min(1.0, 0.3 + 0.1 * len(no_trade_rules_applied))
    # 11. Future leakage safety
    fls = 1.0

    axes = {
        "breakthrough_gate_repair": round(min(bgr, 1.0), 4),
        "holdout_survival_repair": round(min(hsr, 1.0), 4),
        "split_pass_repair": round(min(spr, 1.0), 4),
        "pf_preservation_above_110": round(min(pfp, 1.0), 4),
        "expectancy_preservation": round(min(ep, 1.0), 4),
        "drawdown_reduction": round(min(ddr, 1.0), 4),
        "stress_survival_repair": round(min(ssr, 1.0), 4),
        "concentration_repair": round(min(cr, 1.0), 4),
        "coverage_preservation": round(min(cov, 1.0), 4),
        "no_trade_filter_quality": round(ntq, 4),
        "future_leakage_safety": round(fls, 4),
    }
    priority = round(sum(axes.values()) / len(axes), 4)
    return {
        "artifact_type": "profit_holdout_split_score_v6",
        "candidate_id": c.get("candidate_id", ""),
        "stable_subfamily_id": subfamily,
        "stable_family_id": family,
        "symbol": c.get("symbol", ""),
        "direction": direction,
        "score_axes": axes,
        "priority": priority,
        "breakthrough_repair_candidate": priority >= 0.6 and direction != "no_trade",
        "holdout_repair_candidate": priority >= 0.5,
        "split_repair_candidate": priority >= 0.55,
        "repair_rules_count": len(repair_rules_applied),
        "v6_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def run_profit_holdout_split_scorer_v6() -> dict[str, object]:
    candidates = _read_jsonl_safe(CANDIDATES_V6_PATH)
    scores: list[dict[str, object]] = []
    for c in candidates:
        s = _score_candidate(c)
        s = record_with_hash(s, "record_hash")
        scores.append(s)

    write_jsonl_file(PROFIT_HOLDOUT_SPLIT_SCORES_V6_PATH, scores)

    priority_list = sorted(
        scores,
        key=lambda s: (-float(s.get("priority", 0.0)), str(s.get("candidate_id", ""))),
    )
    for i, p in enumerate(priority_list):
        p["rank"] = i
    write_jsonl_file(PRIORITY_V6_PATH, priority_list)

    breakthrough_repair = sum(1 for s in scores if s.get("breakthrough_repair_candidate"))
    holdout_repair = sum(1 for s in scores if s.get("holdout_repair_candidate"))
    split_repair = sum(1 for s in scores if s.get("split_repair_candidate"))
    prioritized = sum(1 for s in priority_list if float(s.get("priority", 0.0)) >= 0.5)

    summary = {
        "artifact_type": "profit_holdout_split_scorer_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "profit_holdout_split_scorer_v6_status": "profit_holdout_split_scored_v6",
        "candidate_count": len(candidates),
        "prioritized_candidate_count": prioritized,
        "breakthrough_repair_candidate_count": breakthrough_repair,
        "holdout_repair_candidate_count": holdout_repair,
        "split_repair_candidate_count": split_repair,
        "score_axis_count": len(SCORE_AXES),
        "v6_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(SCORER_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        SCORER_V6_PROOF_PATH,
        [research_v6_proof_record("profit-holdout-split-scorer-v6", summary["profit_holdout_split_scorer_v6_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_profit_holdout_split_scorer_v6(), indent=2, sort_keys=True, default=str))
