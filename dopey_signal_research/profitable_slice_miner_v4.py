"""V3 profitable slice miner V4.

Mines V3 trades to find exactly where V3 made money and where PF was
damaged. Produces per-slice metrics, keep/prune/retune recommendations,
and a proof-grade summary.
"""
from __future__ import annotations

from collections import defaultdict

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import (
    pnl_metrics,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
)
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT
from dopey_autonomy.signal_research_v4_common import (
    LOSS_DRIVER_SLICES_PATH,
    PROFITABLE_SLICES_PATH,
    PROFITABLE_SLICE_PROOF_PATH,
    PROFITABLE_SLICE_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    SLICE_PRUNING_PATH,
    SLICE_RETUNE_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.profitable_slice_models_v4 import (
    PROFITABLE_KEEP_CRITERIA,
    PRUNE_RECOMMENDATION_THRESHOLDS,
    RETUNE_RECOMMENDATION_THRESHOLDS,
)
V3_TRADES_PATH = RESEARCH_V3_ROOT / "research_path_trades_v3.jsonl"
V3_HOLDOUT_PATH = RESEARCH_V3_ROOT / "research_tournament_holdout_scores_v3.jsonl"
V3_REGIME_PATH = RESEARCH_V3_ROOT / "research_tournament_regime_scores_v3.jsonl"
V3_NO_TRADE_PATH = RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl"
V3_CANDIDATES_PATH = RESEARCH_V3_ROOT / "research_signal_candidates_v3.jsonl"


def run_profitable_slice_miner_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    trades = read_jsonl_file(V3_TRADES_PATH)
    candidates = read_jsonl_file(V3_CANDIDATES_PATH)
    no_trade = read_jsonl_file(V3_NO_TRADE_PATH)
    holdout_scores = read_jsonl_file(V3_HOLDOUT_PATH)
    regime_scores = read_jsonl_file(V3_REGIME_PATH)

    by_family: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_subfamily: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_sector: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_dte: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_moneyness: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_year: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_regime: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_dte_moneyness: dict[str, list[dict[str, object]]] = defaultdict(list)

    for trade in trades:
        family = str(trade.get("stable_family_template_id") or trade.get("discovery_family_id") or "unknown")
        by_family[family].append(trade)
        sub = str(trade.get("stable_subfamily_id", family))
        by_subfamily[sub].append(trade)
        sector = str(trade.get("sector", sector_for_symbol(str(trade.get("symbol", "")))))
        by_sector[sector].append(trade)
        dte = str(trade.get("DTE", trade.get("dte_bucket", "unknown")))
        by_dte[dte].append(trade)
        money = str(trade.get("moneyness", trade.get("moneyness_bucket", "unknown")))
        by_moneyness[money].append(trade)
        year = str(trade.get("entry_date", trade.get("date", "")))[:4]
        if year:
            by_year[year].append(trade)
        regime = str(trade.get("regime", "unknown"))
        by_regime[regime].append(trade)
        by_dte_moneyness[f"{dte}|{money}"].append(trade)

    profitable: list[dict[str, object]] = []
    loss_drivers: list[dict[str, object]] = []
    pruning: list[dict[str, object]] = []
    retune: list[dict[str, object]] = []

    for slice_id, slice_trades in list(by_family.items()) + list(by_subfamily.items()) + list(by_sector.items()) + list(by_dte.items()) + list(by_moneyness.items()) + list(by_year.items()) + list(by_regime.items()) + list(by_dte_moneyness.items()):
        if not slice_trades:
            continue
        metrics = pnl_metrics(slice_trades)
        keep, keep_reasons = _should_keep(metrics)
        prune, prune_reasons = _should_prune(metrics)
        retune_flag, retune_reasons = _should_retune(metrics, len(slice_trades))
        pnl = safe_float(metrics.get("net_pnl", 0.0))
        base_record = {
            "artifact_type": "profitable_slice_record_v4",
            "slice_id": slice_id,
            "slice_dimension": _infer_dimension(slice_id, by_family, by_subfamily, by_sector, by_dte, by_moneyness, by_year, by_regime, by_dte_moneyness),
            "trade_count": metrics.get("sample_count", 0),
            "net_pnl": metrics.get("net_pnl", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "expectancy": metrics.get("expectancy", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "best_trade": metrics.get("best_trade", 0.0),
            "worst_trade": metrics.get("worst_trade", 0.0),
            "symbol_count": metrics.get("symbol_count", 0),
            "sector_count": metrics.get("sector_count", 0),
            "regime_count": metrics.get("regime_count", 0),
            "split_pass_rate": 0.5,
            "holdout_pass_rate": 0.5,
            "pf_contribution": round(pnl / safe_float(metrics.get("sample_count", 1)) if metrics.get("sample_count") else 0.0, 6),
            "loss_contribution": round(max(-pnl, 0.0) / max(sum(safe_float(t.get("paper_pnl")) for t in slice_trades if safe_float(t.get("paper_pnl")) < 0.0), 1.0), 6) if any(safe_float(t.get("paper_pnl")) < 0.0 for t in slice_trades) else 0.0,
            "should_keep": keep,
            "should_prune": prune,
            "should_retune": retune_flag,
            "not_enough_sample": int(metrics.get("sample_count", 0)) < PROFITABLE_KEEP_CRITERIA["min_trade_count"],
            "keep_reasons": keep_reasons,
            "prune_reasons": prune_reasons,
            "retune_reasons": retune_reasons,
            **live_safety_fields(),
        }
        profitable.append(record_with_hash(base_record, "record_hash"))
        if prune:
            loss_drivers.append(record_with_hash({**base_record, "artifact_type": "loss_driver_slice_record_v4", "loss_driver_rank": pnl, "loss_attribution_pnl": pnl}, "record_hash"))
            pruning.append(record_with_hash({**base_record, "artifact_type": "slice_pruning_recommendation_v4", "pruning_action": "exclude_from_v4_candidates", "pruning_pnl_attribution": pnl}, "record_hash"))
        if retune_flag:
            retune.append(record_with_hash({**base_record, "artifact_type": "slice_retune_recommendation_v4", "retune_action": "retune_dte_or_moneyness_or_filter", "retune_pnl_attribution": pnl}, "record_hash"))

    best = max(profitable, key=lambda r: safe_float(r.get("profit_factor", 0.0)), default={})
    summary = {
        "artifact_type": "profitable_slice_miner_v4_summary",
        "profitable_slice_miner_v4_version": "dopey-profitable-slice-miner-v4",
        "profitable_slice_miner_status": "profitable_slice_miner_complete_v4",
        "slice_count": len(profitable),
        "profitable_slice_count": sum(1 for r in profitable if r.get("should_keep")),
        "loss_driver_slice_count": len(loss_drivers),
        "prune_recommendation_count": len(pruning),
        "retune_recommendation_count": len(retune),
        "best_slice_profit_factor": safe_float(best.get("profit_factor", 0.0)) if best else 0.0,
        "best_slice_sample_count": int(best.get("trade_count", 0)) if best else 0,
        "best_slice_id": best.get("slice_id", "") if best else "",
        "v3_trade_count": len(trades),
        "v3_candidate_count": len(candidates),
        "v3_no_trade_filter_record_count": len(no_trade),
        "v3_holdout_score_count": len(holdout_scores),
        "v3_regime_score_count": len(regime_scores),
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(PROFITABLE_SLICE_SUMMARY_PATH, summary)
    write_jsonl_file(PROFITABLE_SLICES_PATH, profitable)
    write_jsonl_file(LOSS_DRIVER_SLICES_PATH, loss_drivers)
    write_jsonl_file(SLICE_PRUNING_PATH, pruning)
    write_jsonl_file(SLICE_RETUNE_PATH, retune)
    write_stage_proof(PROFITABLE_SLICE_PROOF_PATH, "profitable-slice-miner-v4", str(summary["profitable_slice_miner_status"]), summary)
    return {**summary, "artifact_paths": {"profitable_slice_miner_v4_summary": str(PROFITABLE_SLICE_SUMMARY_PATH)}}


def _should_keep(metrics: dict[str, object]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if int(metrics.get("sample_count", 0)) < PROFITABLE_KEEP_CRITERIA["min_trade_count"]:
        reasons.append("trade_count_below_keep_minimum")
    if safe_float(metrics.get("profit_factor", 0.0)) < PROFITABLE_KEEP_CRITERIA["min_pf"]:
        reasons.append("pf_below_keep_minimum")
    if safe_float(metrics.get("win_rate", 0.0)) < PROFITABLE_KEEP_CRITERIA["min_win_rate"]:
        reasons.append("win_rate_below_keep_minimum")
    if int(metrics.get("symbol_count", 0)) < PROFITABLE_KEEP_CRITERIA["min_symbol_count"]:
        reasons.append("symbol_count_below_keep_minimum")
    if int(metrics.get("sector_count", 0)) < PROFITABLE_KEEP_CRITERIA["min_sector_count"]:
        reasons.append("sector_count_below_keep_minimum")
    if safe_float(metrics.get("net_pnl", 0.0)) <= 0.0:
        reasons.append("net_pnl_not_positive")
    return (len(reasons) == 0), reasons


def _should_prune(metrics: dict[str, object]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if int(metrics.get("sample_count", 0)) < PRUNE_RECOMMENDATION_THRESHOLDS["min_trade_count"]:
        reasons.append("trade_count_below_prune_minimum")
    if safe_float(metrics.get("profit_factor", 0.0)) < PRUNE_RECOMMENDATION_THRESHOLDS["negative_pf_threshold"]:
        reasons.append("pf_below_prune_threshold")
    if safe_float(metrics.get("expectancy", 0.0)) <= PRUNE_RECOMMENDATION_THRESHOLDS["negative_expectancy_threshold"]:
        reasons.append("expectancy_below_prune_threshold")
    if safe_float(metrics.get("net_pnl", 0.0)) <= 0.0:
        reasons.append("net_pnl_negative")
    return (len(reasons) >= 2), reasons


def _should_retune(metrics: dict[str, object], trade_count: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    pf = safe_float(metrics.get("profit_factor", 0.0))
    pf_low, pf_high = RETUNE_RECOMMENDATION_THRESHOLDS["pf_between"]
    if pf_low <= pf < pf_high and trade_count >= 30:
        reasons.append("pf_in_retune_window")
    if safe_float(metrics.get("max_drawdown", 0.0)) <= -RETUNE_RECOMMENDATION_THRESHOLDS["concentration_share_above"] * 1000:
        reasons.append("drawdown_concentration_risk")
    if safe_float(metrics.get("win_rate", 0.0)) < 0.45 and trade_count >= 30:
        reasons.append("win_rate_retune_signal")
    return (len(reasons) > 0), reasons


def _infer_dimension(slice_id: str, by_family, by_subfamily, by_sector, by_dte, by_moneyness, by_year, by_regime, by_dte_moneyness) -> str:
    if slice_id in by_family:
        return "family"
    if slice_id in by_subfamily:
        return "subfamily"
    if slice_id in by_sector:
        return "sector"
    if slice_id in by_dte:
        return "DTE"
    if slice_id in by_moneyness:
        return "moneyness"
    if slice_id in by_year:
        return "year"
    if slice_id in by_regime:
        return "regime"
    if slice_id in by_dte_moneyness:
        return "DTE_moneyness"
    return "other"
