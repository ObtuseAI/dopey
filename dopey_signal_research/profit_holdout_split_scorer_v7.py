"""V7 pre-simulation profit/holdout/split scorer (Workstream G).

Reads V7 candidates and emits per-candidate scores across 12 axes:
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
- trade-active edge boost

Outputs a `priority` score per candidate (higher = better) and a
prioritized list for V7 simulation.  No-trade-only candidates are
explicitly blocked from breakthrough repair promotion; trade-active
long-call / long-put candidates receive a priority boost so the
simulator can produce honest trade-active evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    CANDIDATES_V7_PATH,
    MIN_BREAKTHROUGH_PF,
    PRIORITY_V7_PATH,
    PROFIT_HOLDOUT_SPLIT_SCORES_V7_PATH,
    RESEARCH_V7_VERSION,
    SCORER_V7_PROOF_PATH,
    SCORER_V7_SUMMARY_PATH,
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    is_forbidden_symbol,
    research_v7_proof_record,
    utc_now_iso,
)
from dopey_autonomy.signal_research_v6_common import CANDIDATES_V6_PATH


__all__ = ["run_profit_holdout_split_scorer_v7"]


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
    "trade_active_edge",
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


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _is_trade_active(direction: str) -> bool:
    return direction in {"long_call", "long_put"}


def _score_candidate(c: dict[str, object]) -> dict[str, object]:
    """Deterministic per-axis scoring for a single V7 candidate."""
    direction = str(c.get("direction", "no_trade"))
    subfamily = str(c.get("stable_subfamily_id", ""))
    family = str(c.get("stable_family_id", ""))
    symbol = str(c.get("symbol", ""))
    no_trade_rules_applied = c.get("no_trade_filter_rules_applied", []) or []
    repair_rules_applied = c.get("repair_rules_applied", []) or []
    feature_vector = c.get("feature_vector", {}) or {}
    hold_window = _safe_float(c.get("hold_window", 1), default=1.0)

    rs = _safe_float(feature_vector.get("relative_strength"), default=0.5)
    vr = _safe_float(feature_vector.get("volume_ratio"), default=1.0)
    vol = _safe_float(feature_vector.get("volatility"), default=0.3)
    ts = _safe_float(feature_vector.get("trend_strength"), default=0.4)
    ra = _safe_float(feature_vector.get("regime_alignment"), default=0.6)

    trade_active = _is_trade_active(direction)
    forbidden = is_forbidden_symbol(symbol)

    # 1. Breakthrough-gate repair score
    bgr = 0.7 if subfamily.startswith("continuation|") else 0.55
    # 2. Holdout survival repair
    hsr = 0.35 if direction == "no_trade" else 0.65 + 0.1 * ra
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
    # 10. No-trade filter quality (higher when rules are present but direction is trade-active)
    ntq = 0.5 if trade_active else min(1.0, 0.3 + 0.1 * len(no_trade_rules_applied))
    # 11. Future leakage safety
    fls = 0.0 if forbidden else 1.0
    # 12. Trade-active edge boost (core V7 objective)
    tae = 0.75 if trade_active else 0.25

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
        "trade_active_edge": round(tae, 4),
    }

    raw_priority = sum(axes.values()) / len(axes)
    # V7: trade-active candidates get a small tie-break boost so the simulator
    # receives more honest long-call / long-put samples.
    priority = raw_priority + (0.05 if trade_active else 0.0)
    priority = round(min(priority, 1.0), 4)

    # V7 safety: block no-trade-only breakthrough promotion.
    breakthrough_repair_candidate = priority >= 0.6 and trade_active and not forbidden
    holdout_repair_candidate = priority >= 0.5 and not forbidden
    split_repair_candidate = priority >= 0.55 and not forbidden
    trade_active_repair_candidate = priority >= 0.55 and trade_active and not forbidden

    return {
        "artifact_type": "profit_holdout_split_score_v7",
        "candidate_id": c.get("candidate_id", ""),
        "stable_subfamily_id": subfamily,
        "stable_family_id": family,
        "symbol": symbol,
        "sector": c.get("sector", ""),
        "direction": direction,
        "hold_window": hold_window,
        "score_axes": axes,
        "priority": priority,
        "raw_priority": round(raw_priority, 4),
        "breakthrough_repair_candidate": breakthrough_repair_candidate,
        "holdout_repair_candidate": holdout_repair_candidate,
        "split_repair_candidate": split_repair_candidate,
        "trade_active_repair_candidate": trade_active_repair_candidate,
        "no_trade_only_breakthrough_blocked": not breakthrough_repair_candidate and direction == "no_trade",
        "trade_active_edge_boost_applied": trade_active,
        "repair_rules_count": len(repair_rules_applied),
        "no_trade_rules_count": len(no_trade_rules_applied),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def _load_candidates() -> list[dict[str, object]]:
    """Prefer V7 candidates; fall back to V6 candidates for standalone testing."""
    candidates = _read_jsonl_safe(CANDIDATES_V7_PATH)
    if candidates:
        return candidates
    return _read_jsonl_safe(CANDIDATES_V6_PATH)


def run_profit_holdout_split_scorer_v7() -> dict[str, object]:
    candidates = _load_candidates()
    scores: list[dict[str, object]] = []
    for c in candidates:
        s = _score_candidate(c)
        s = record_with_hash(s, "record_hash")
        scores.append(s)

    write_jsonl_file(PROFIT_HOLDOUT_SPLIT_SCORES_V7_PATH, scores)

    priority_list = sorted(
        scores,
        key=lambda s: (-float(s.get("priority", 0.0)), str(s.get("candidate_id", ""))),
    )
    for i, p in enumerate(priority_list):
        p["rank"] = i
    write_jsonl_file(PRIORITY_V7_PATH, priority_list)

    trade_active_count = sum(1 for s in scores if _is_trade_active(str(s.get("direction", ""))))
    no_trade_count = sum(1 for s in scores if str(s.get("direction", "")) == "no_trade")
    breakthrough_repair = sum(1 for s in scores if s.get("breakthrough_repair_candidate"))
    holdout_repair = sum(1 for s in scores if s.get("holdout_repair_candidate"))
    split_repair = sum(1 for s in scores if s.get("split_repair_candidate"))
    trade_active_repair = sum(1 for s in scores if s.get("trade_active_repair_candidate"))
    no_trade_blocked = sum(1 for s in scores if s.get("no_trade_only_breakthrough_blocked"))
    prioritized = sum(1 for s in priority_list if float(s.get("priority", 0.0)) >= 0.5)

    no_trade_ratio = round(no_trade_count / len(scores), 6) if scores else 0.0

    summary = {
        "artifact_type": "profit_holdout_split_scorer_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "profit_holdout_split_scorer_v7_status": "profit_holdout_split_scored_v7",
        "candidate_count": len(candidates),
        "prioritized_candidate_count": prioritized,
        "breakthrough_repair_candidate_count": breakthrough_repair,
        "holdout_repair_candidate_count": holdout_repair,
        "split_repair_candidate_count": split_repair,
        "trade_active_repair_candidate_count": trade_active_repair,
        "trade_active_candidate_count": trade_active_count,
        "no_trade_candidate_count": no_trade_count,
        "no_trade_only_breakthrough_blocked_count": no_trade_blocked,
        "no_trade_ratio": no_trade_ratio,
        "no_trade_ratio_below_cap": no_trade_ratio <= V7_MAX_NO_TRADE_RATIO,
        "score_axis_count": len(SCORE_AXES),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(SCORER_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        SCORER_V7_PROOF_PATH,
        [research_v7_proof_record("profit-holdout-split-scorer-v7", summary["profit_holdout_split_scorer_v7_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_profit_holdout_split_scorer_v7(), indent=2, sort_keys=True, default=str))
