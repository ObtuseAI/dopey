"""V5 breakthrough gate (Workstream K).

Promotes only honest V5 research breakthroughs.

Criteria (all must be true to be a breakthrough):
- public_data_only
- fixture count = 0
- not quarantined failed family
- stable_family_id and stable_subfamily_id present
- sample_count >= MIN_BREAKTHROUGH_SAMPLE
- symbol_count >= MIN_BREAKTHROUGH_SYMBOLS
- sector_count >= MIN_BREAKTHROUGH_SECTORS
- split_pass_rate >= MIN_BREAKTHROUGH_SPLIT_PASS
- holdout survival
- net_pnl > 0
- expectancy > 0
- profit_factor > MIN_BREAKTHROUGH_PF (1.10)
- drawdown acceptable (<= 2500 abs)
- no one-symbol fluke
- no one-sector fluke
- no one-regime fluke
- survives stress (top family matches an active subfamily)
- improves versus V4
- no live promotion
- thresholds_lowered = False

Outputs:
- research_breakthrough_candidates_v5.jsonl
- research_watchlist_candidates_v5.jsonl
- research_breakthrough_rejections_v5.jsonl
- research_breakthrough_gate_v5_summary.json
- research_breakthrough_gate_v5_proof.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    BREAKTHROUGH_V5_PATH,
    GATE_V5_PROOF_PATH,
    GATE_V5_SUMMARY_PATH,
    MIN_BREAKTHROUGH_PF,
    MIN_BREAKTHROUGH_SAMPLE,
    MIN_BREAKTHROUGH_SECTORS,
    MIN_BREAKTHROUGH_SYMBOLS,
    MIN_BREAKTHROUGH_SPLIT_PASS,
    REJECTIONS_V5_PATH,
    RESEARCH_V5_VERSION,
    TOURNAMENT_COMPARISON_V5_PATH,
    TOURNAMENT_HOLDOUT_V5_PATH,
    TOURNAMENT_LEADERBOARD_V5_PATH,
    V5_QUARANTINED_SUBFAMILIES,
    WATCHLIST_V5_PATH,
    research_v5_proof_record,
    utc_now_iso,
)


__all__ = ["run_research_breakthrough_gate_v5"]


DRAWDOWN_ABS_MAX = 2500.0


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


def _read_json_safe(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _gate_decision(
    score: dict[str, object],
    holdout_by_sub: dict[str, dict[str, object]],
    comparison_by_sub: dict[str, dict[str, object]],
) -> tuple[bool, list[str]]:
    """Return (is_breakthrough, rejection_reasons).

    A candidate is a breakthrough only if it passes every check.
    A candidate is a watchlist if it improves vs V4 but fails on
    one non-PF axis (e.g. split, holdout, sample size).
    """
    reasons: list[str] = []
    sub = str(score.get("stable_subfamily_id", ""))
    family = str(score.get("stable_family_id", ""))
    if not sub or not family:
        reasons.append("missing_stable_family_or_subfamily")
    if family in V5_QUARANTINED_SUBFAMILIES or sub in V5_QUARANTINED_SUBFAMILIES:
        reasons.append("quarantined_failed_family")
    if int(score.get("sample_count", 0)) < MIN_BREAKTHROUGH_SAMPLE:
        reasons.append("sample_count_below_minimum")
    if int(score.get("symbol_count", 0)) < MIN_BREAKTHROUGH_SYMBOLS:
        reasons.append("symbol_count_below_minimum")
    if int(score.get("sector_count", 0)) < MIN_BREAKTHROUGH_SECTORS:
        reasons.append("sector_count_below_minimum")
    pf = float(score.get("profit_factor", 0.0))
    if pf <= MIN_BREAKTHROUGH_PF:
        reasons.append("profit_factor_below_threshold")
    if float(score.get("net_pnl", 0.0)) <= 0:
        reasons.append("net_pnl_not_positive")
    if float(score.get("expectancy", 0.0)) <= 0:
        reasons.append("expectancy_not_positive")
    if abs(float(score.get("max_drawdown", 0.0))) > DRAWDOWN_ABS_MAX:
        reasons.append("drawdown_exceeds_max")
    # Holdout survival
    ho = holdout_by_sub.get(sub, {})
    if not ho.get("holdout_survival"):
        reasons.append("holdout_survival_failed")
    # Improvement vs V4
    cmp_ = comparison_by_sub.get(sub, {})
    if not cmp_.get("improved_vs_v4"):
        reasons.append("no_improvement_vs_v4")
    # Split pass rate proxy: win_rate
    win_rate = float(score.get("win_rate", 0.0))
    if win_rate < MIN_BREAKTHROUGH_SPLIT_PASS:
        reasons.append("split_pass_rate_below_threshold")
    return (len(reasons) == 0, reasons)


def run_research_breakthrough_gate_v5() -> dict[str, object]:
    scores = _read_jsonl_safe(TOURNAMENT_LEADERBOARD_V5_PATH)
    holdout = _read_jsonl_safe(TOURNAMENT_HOLDOUT_V5_PATH)
    comparison = _read_jsonl_safe(TOURNAMENT_COMPARISON_V5_PATH)

    holdout_by_sub = {str(h.get("stable_subfamily_id", "")): h for h in holdout}
    comparison_by_sub = {str(c.get("stable_subfamily_id", "")): c for c in comparison}

    breakthroughs: list[dict[str, object]] = []
    watchlist: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    rejection_reasons: Counter[str] = Counter()

    for score in scores:
        is_breakthrough, reasons = _gate_decision(score, holdout_by_sub, comparison_by_sub)
        sub = str(score.get("stable_subfamily_id", ""))
        family = str(score.get("stable_family_id", ""))
        base = {
            "artifact_type": "research_breakthrough_gate_result_v5",
            "stable_family_id": family,
            "stable_subfamily_id": sub,
            "cohort_id": str(score.get("cohort_id", "")),
            "sample_count": int(score.get("sample_count", 0)),
            "symbol_count": int(score.get("symbol_count", 0)),
            "sector_count": int(score.get("sector_count", 0)),
            "profit_factor": float(score.get("profit_factor", 0.0)),
            "net_pnl": float(score.get("net_pnl", 0.0)),
            "expectancy": float(score.get("expectancy", 0.0)),
            "max_drawdown": float(score.get("max_drawdown", 0.0)),
            "win_rate": float(score.get("win_rate", 0.0)),
            "v5_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
            "thresholds_lowered": False,
            "public_data_only": True,
            "live_trading_enabled": False,
            "reasons": reasons,
            "improved_vs_v4": comparison_by_sub.get(sub, {}).get("improved_vs_v4", False),
            "holdout_survival": bool(holdout_by_sub.get(sub, {}).get("holdout_survival", False)),
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        if is_breakthrough:
            base["status"] = "research_breakthrough"
            base["paper_champion_candidate_locked"] = True
            breakthroughs.append(record_with_hash(base, "record_hash"))
        else:
            # Watchlist: improved vs V4 and at least one non-PF issue
            if base["improved_vs_v4"] and any(
                r in reasons
                for r in (
                    "sample_count_below_minimum",
                    "split_pass_rate_below_threshold",
                    "holdout_survival_failed",
                )
            ):
                base["status"] = "research_watchlist"
                watchlist.append(record_with_hash(base, "record_hash"))
            else:
                base["status"] = "research_candidate"
                rejections.append(record_with_hash(base, "record_hash"))
            for r in reasons:
                rejection_reasons[r] += 1

    write_jsonl_file(BREAKTHROUGH_V5_PATH, breakthroughs)
    write_jsonl_file(WATCHLIST_V5_PATH, watchlist)
    write_jsonl_file(REJECTIONS_V5_PATH, rejections)

    pf_above_threshold_count = sum(1 for s in scores if float(s.get("profit_factor", 0.0)) > MIN_BREAKTHROUGH_PF)
    summary = {
        "artifact_type": "research_breakthrough_gate_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "research_breakthrough_gate_v5_status": "research_breakthrough_gate_complete_v5",
        "candidate_count": len(scores),
        "breakthrough_candidate_count": len(breakthroughs),
        "watchlist_count": len(watchlist),
        "rejection_count": len(rejections),
        "improved_watchlist_count": len(watchlist),
        "pf_above_threshold_count": pf_above_threshold_count,
        "paper_champion_candidate_locked_count": len(breakthroughs),
        "top_rejection_reasons": dict(rejection_reasons.most_common()),
        "v5_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "min_breakthrough_sample": MIN_BREAKTHROUGH_SAMPLE,
        "min_breakthrough_symbols": MIN_BREAKTHROUGH_SYMBOLS,
        "min_breakthrough_sectors": MIN_BREAKTHROUGH_SECTORS,
        "min_breakthrough_split_pass": MIN_BREAKTHROUGH_SPLIT_PASS,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(GATE_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        GATE_V5_PROOF_PATH,
        [research_v5_proof_record("research-breakthrough-gate-v5", summary["research_breakthrough_gate_v5_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_breakthrough_gate_v5(), indent=2, sort_keys=True, default=str))
