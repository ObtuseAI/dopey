"""V7 mutation queue (Workstream K).

Generates next mutations from V7 breakthroughs / watchlist / near-breakthroughs.
Rules:
- if an honest trade-active breakthrough exists, mutate it
- else if an improved watchlist candidate exists, mutate it
- else if a near-breakthrough exists (PF > floor but still rejected), mutate it
- if no mutations are possible, record the exact reason honestly

V7 never lowers MIN_BREAKTHROUGH_PF, never enables live trading, and blocks
no-trade-only breakthroughs.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    BREAKTHROUGH_V7_PATH,
    GATE_V7_SUMMARY_PATH,
    MIN_BREAKTHROUGH_PF,
    MUTATION_QUEUE_V7_PATH,
    MUTATION_QUEUE_V7_PROOF_PATH,
    MUTATION_QUEUE_V7_SUMMARY_PATH,
    REJECTIONS_V7_PATH,
    RESEARCH_V7_VERSION,
    V7_MAX_NO_TRADE_RATIO,
    WATCHLIST_V7_PATH,
    is_forbidden_symbol,
    research_v7_proof_record,
    utc_now_iso,
)


__all__ = ["run_research_mutation_queue_v7"]


# V7 canonical mutation types for the next queue.  The list intentionally
# includes trade-active activation and no-trade-ratio reduction so that any
# no-trade-dominant watchlist / near-breakthrough seed is converted into an
# honest long-call / long-put candidate rather than promoted on no-trade PnL.
MUTATION_TYPES_V7: tuple[str, ...] = (
    "trade_active_activation",
    "no_trade_ratio_reduction",
    "long_call_activation",
    "long_put_activation",
    "holdout_survival_repair",
    "split_pass_repair",
    "concentration_repair",
    "drawdown_repair",
    "expectancy_repair",
    "stress_survival_repair",
    "outlier_dependence_repair",
    "symbol_broadening",
    "sector_broadening",
    "symbol_pruning",
    "sector_pruning",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "hold_window_retune",
    "stop_target_retune",
    "feature_threshold_retune",
    "regime_filter_retune",
    "recent_market_reinforcement",
    "sample_expansion",
    "family_subfamily_split",
    "watchlist_candidate_isolation",
    "pf_preserving_holdout_repair",
    "public_data_reinforcement",
    "fixture_zero_guard",
)


MUTATION_TYPE_TO_INTENDED_FIX: dict[str, str] = {
    "trade_active_activation": "Convert no-trade-dominant candidate into executable long-call/long-put triggers without future leakage",
    "no_trade_ratio_reduction": "Reduce no-trade ratio below the V7 maximum while preserving signal quality",
    "long_call_activation": "Add honest long-call entry triggers using only pre-entry information",
    "long_put_activation": "Add honest long-put entry triggers using only pre-entry information",
    "holdout_survival_repair": "Tighten pre-entry filters to improve holdout survival without future leakage",
    "split_pass_repair": "Stabilize cohort across time-based splits; reduce single-window dependence",
    "concentration_repair": "Reduce top-symbol and top-sector concentration",
    "drawdown_repair": "Tighten stops and reduce per-trade risk",
    "expectancy_repair": "Filter low-expectancy contexts using pre-entry edge estimates",
    "stress_survival_repair": "Add stress-period filters from historical regime proxies",
    "outlier_dependence_repair": "Cap dependence on extreme trades via robust statistics",
    "symbol_broadening": "Broaden eligible symbol universe while preserving coverage",
    "sector_broadening": "Broaden eligible sector coverage while preserving coverage",
    "symbol_pruning": "Prune worst-attribution symbols while preserving gate coverage",
    "sector_pruning": "Prune worst-attribution sectors while preserving gate coverage",
    "dte_retune": "Re-evaluate DTE windows using only pre-entry term structure",
    "moneyness_retune": "Re-evaluate moneyness strikes using pre-entry spot and historical skew",
    "exit_policy_retune": "Re-evaluate stop/target asymmetry with pre-entry statistics",
    "hold_window_retune": "Evaluate hold windows 1/2/3/5/7 days using prior holding-period stats",
    "stop_target_retune": "Re-tune stop/target combinations using historical ranges",
    "feature_threshold_retune": "Re-tune pre-entry feature thresholds using prior historical bins",
    "regime_filter_retune": "Re-tune regime filters using historical regime labels only",
    "recent_market_reinforcement": "Reinforce on recent market window; verify no leakage",
    "sample_expansion": "Expand sample by replicating profitable pre-entry slices",
    "family_subfamily_split": "Split family into demote/rescue branches by historical behavior",
    "watchlist_candidate_isolation": "Isolate watchlist candidates from shared feature leakage",
    "pf_preserving_holdout_repair": "Repair holdout survival while keeping PF above 1.10",
    "public_data_reinforcement": "Reinforce signal on additional public data sources without leakage",
    "fixture_zero_guard": "Maintain zero SIM/TEST/FIXTURE/SYNTH champion exposure",
}


MUTATION_TYPE_TO_EVAL_AXIS: dict[str, str] = {
    "trade_active_activation": "trade_active_ratio",
    "no_trade_ratio_reduction": "no_trade_ratio",
    "long_call_activation": "long_call_sample_count",
    "long_put_activation": "long_put_sample_count",
    "holdout_survival_repair": "holdout_survival",
    "split_pass_repair": "split_pass_rate",
    "concentration_repair": "symbol_sector_concentration",
    "drawdown_repair": "max_drawdown",
    "expectancy_repair": "expectancy",
    "stress_survival_repair": "stress_survival",
    "outlier_dependence_repair": "outlier_dependence",
    "symbol_broadening": "symbol_coverage",
    "sector_broadening": "sector_coverage",
    "symbol_pruning": "symbol_concentration",
    "sector_pruning": "sector_concentration",
    "dte_retune": "dte_holding_window",
    "moneyness_retune": "moneyness",
    "exit_policy_retune": "stop_target_asymmetry",
    "hold_window_retune": "hold_window",
    "stop_target_retune": "stop_target_combination",
    "feature_threshold_retune": "feature_threshold_quality",
    "regime_filter_retune": "regime_filter_quality",
    "recent_market_reinforcement": "recent_window_performance",
    "sample_expansion": "sample_count",
    "family_subfamily_split": "family_separation",
    "watchlist_candidate_isolation": "cross_contamination_risk",
    "pf_preserving_holdout_repair": "pf_holdout_tradeoff",
    "public_data_reinforcement": "public_data_coverage",
    "fixture_zero_guard": "fixture_champion_count",
}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


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


def _read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed
    return {"records": parsed}


def _mutation_id(idx: int, source_type: str) -> str:
    return f"mut-q-v7-{source_type[:4]}-{idx:04d}"


def _is_honest_trade_active_breakthrough(src: dict[str, object]) -> bool:
    """Gate already enforces this; keep a local guard to block no-trade-only seeds."""
    status = str(src.get("status", ""))
    if status != "research_breakthrough":
        return False
    no_trade_ratio = _float(src.get("no_trade_ratio"), default=1.0)
    ta_sample = int(_float(src.get("trade_active_sample_count"), default=0.0))
    ta_pf = _float(src.get("trade_active_profit_factor"), default=0.0)
    sub = str(src.get("stable_subfamily_id", ""))
    if not sub:
        return False
    if no_trade_ratio > V7_MAX_NO_TRADE_RATIO:
        return False
    if ta_sample < 1:
        return False
    if ta_pf <= MIN_BREAKTHROUGH_PF:
        return False
    if any(is_forbidden_symbol(s) for s in sub.split("|") if s):
        return False
    return True


def _is_watchlist_seed(src: dict[str, object]) -> bool:
    status = str(src.get("status", ""))
    if status != "research_watchlist":
        return False
    sub = str(src.get("stable_subfamily_id", ""))
    if not sub:
        return False
    if any(is_forbidden_symbol(s) for s in sub.split("|") if s):
        return False
    return True


def _is_near_breakthrough(src: dict[str, object]) -> bool:
    """PF above floor but still rejected (or watchlist-blocker)."""
    status = str(src.get("status", ""))
    if status not in {"research_candidate", "research_watchlist"}:
        return False
    pf = _float(src.get("profit_factor"), default=0.0)
    if pf <= MIN_BREAKTHROUGH_PF:
        return False
    sub = str(src.get("stable_subfamily_id", ""))
    if not sub:
        return False
    if any(is_forbidden_symbol(s) for s in sub.split("|") if s):
        return False
    return True


def _build_mutation_records(
    sources: list[dict[str, object]],
    source_type: str,
    start_idx: int,
) -> tuple[list[dict[str, object]], int]:
    """Build one V7 mutation record per (source, mutation_type) pair."""
    records: list[dict[str, object]] = []
    idx = start_idx
    for src in sources:
        sub = str(src.get("stable_subfamily_id", ""))
        family = str(src.get("stable_family_id", ""))
        cohort = str(src.get("cohort_id", ""))
        seed = sub
        source_record_hash = str(src.get("record_hash", ""))
        for mtype in MUTATION_TYPES_V7:
            rec = {
                "artifact_type": "research_mutation_queue_v7",
                "mutation_id": _mutation_id(idx, source_type),
                "mutation_type": mtype,
                "source_type": source_type,
                "stable_family_id": family,
                "stable_subfamily_id": sub,
                "parent_family_id": family,
                "parent_subfamily_id": sub,
                "parent_cohort_id": cohort,
                "watchlist_seed_id": seed,
                "breakthrough_seed_id": seed if source_type == "breakthrough" else "",
                "near_breakthrough_seed_id": seed if source_type == "near_breakthrough" else "",
                "source_status": str(src.get("status", "")),
                "source_record_hash": source_record_hash,
                "intended_fix": MUTATION_TYPE_TO_INTENDED_FIX.get(
                    mtype, f"V7 mutation seed for {mtype} on {sub}"
                ),
                "expected_evaluation_axis": MUTATION_TYPE_TO_EVAL_AXIS.get(mtype, mtype),
                "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
                "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
                "thresholds_lowered": False,
                "public_data_only": True,
                "fixture_count": 0,
                "live_trading_enabled": False,
                "blocks_no_trade_only_breakthrough": True,
                "no_trade_only_breakthrough_blocked": True,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
            records.append(record_with_hash(rec, "record_hash"))
            idx += 1
    return records, idx


def run_research_mutation_queue_v7() -> dict[str, object]:
    breakthroughs = [r for r in _read_jsonl_safe(BREAKTHROUGH_V7_PATH) if _is_honest_trade_active_breakthrough(r)]
    watchlist = [r for r in _read_jsonl_safe(WATCHLIST_V7_PATH) if _is_watchlist_seed(r)]
    rejections = _read_jsonl_safe(REJECTIONS_V7_PATH)
    near_breakthroughs = [r for r in rejections if _is_near_breakthrough(r)]

    source_breakthrough_count = len(breakthroughs)
    source_watchlist_count = len(watchlist)
    source_near_breakthrough_count = len(near_breakthroughs)

    records: list[dict[str, object]] = []
    idx = 0
    reason = ""

    if breakthroughs:
        recs, idx = _build_mutation_records(breakthroughs, "breakthrough", idx)
        records.extend(recs)
    elif watchlist:
        recs, idx = _build_mutation_records(watchlist, "watchlist", idx)
        records.extend(recs)
    elif near_breakthroughs:
        recs, idx = _build_mutation_records(near_breakthroughs, "near_breakthrough", idx)
        records.extend(recs)
    else:
        reason = "no_breakthrough_no_watchlist_no_near_breakthrough"

    write_jsonl_file(MUTATION_QUEUE_V7_PATH, records)

    type_counts: dict[str, int] = {}
    for r in records:
        type_counts[r["mutation_type"]] = type_counts.get(r["mutation_type"], 0) + 1

    gate_summary = _read_json_file(GATE_V7_SUMMARY_PATH)

    status = "research_mutation_queue_written_v7"
    summary = {
        "artifact_type": "research_mutation_queue_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "research_mutation_queue_v7_status": status,
        "source_breakthrough_count": source_breakthrough_count,
        "source_watchlist_count": source_watchlist_count,
        "source_near_breakthrough_count": source_near_breakthrough_count,
        "source_rejection_count": len(rejections),
        "gate_breakthrough_count": _int(gate_summary.get("breakthrough_candidate_count"), 0),
        "gate_watchlist_count": _int(gate_summary.get("watchlist_count"), 0),
        "gate_pf_above_threshold_count": _int(gate_summary.get("pf_above_threshold_count"), 0),
        "mutation_queue_count": len(records),
        "mutation_type_counts": type_counts,
        "no_mutations_reason": reason,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "thresholds_lowered": False,
        "public_data_only": True,
        "fixture_count": 0,
        "live_trading_enabled": False,
        "blocks_no_trade_only_breakthrough": True,
        "no_trade_only_breakthroughs_blocked": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(MUTATION_QUEUE_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        MUTATION_QUEUE_V7_PROOF_PATH,
        [research_v7_proof_record("research-mutation-queue-v7", status, summary)],
    )
    return summary


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_mutation_queue_v7(), indent=2, sort_keys=True, default=str))
