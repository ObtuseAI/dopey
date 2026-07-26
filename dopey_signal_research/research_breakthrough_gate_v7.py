"""V7 breakthrough gate (Workstream J).

Promotes only honest trade-active research breakthroughs for
DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7.

Criteria (all must be true to be a breakthrough):
- public_data_only
- fixture count = 0 and no forbidden test symbols
- not quarantined failed family
- stable_family_id and stable_subfamily_id present
- sample_count >= MIN_BREAKTHROUGH_SAMPLE
- symbol_count >= MIN_BREAKTHROUGH_SYMBOLS
- sector_count >= MIN_BREAKTHROUGH_SECTORS
- split_pass_rate (win_rate) >= MIN_BREAKTHROUGH_SPLIT_PASS
- holdout survival
- net_pnl > 0
- expectancy > 0
- profit_factor > MIN_BREAKTHROUGH_PF (1.10)
- drawdown acceptable (<= 2500 abs)
- no one-symbol / one-sector / one-regime fluke
- stress survival (active V7 subfamily taxonomy)
- improves versus V6 on at least one prior blocker
- trade-active subset is honest:
  - no_trade_ratio <= V7_MAX_NO_TRADE_RATIO
  - trade_active_sample >= V7_MIN_TRADE_ACTIVE_SAMPLE
  - trade_active_profit_factor > MIN_BREAKTHROUGH_PF
  - trade_active_net_pnl > 0
  - trade_active_expectancy > 0
  - trade_active_win_rate >= MIN_BREAKTHROUGH_SPLIT_PASS
  - trade_active_symbol_count >= MIN_BREAKTHROUGH_SYMBOLS
  - trade_active_sector_count >= MIN_BREAKTHROUGH_SECTORS
  - trade_active_drawdown acceptable
- no live promotion
- thresholds_lowered = False

Outputs:
- research_breakthrough_candidates_v7.jsonl
- research_watchlist_candidates_v7.jsonl
- research_breakthrough_rejections_v7.jsonl
- research_breakthrough_gate_v7_summary.json
- research_breakthrough_gate_v7_proof.jsonl
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v7_common import (
    BREAKTHROUGH_V7_PATH,
    GATE_V7_PROOF_PATH,
    GATE_V7_SUMMARY_PATH,
    MIN_BREAKTHROUGH_PF,
    MIN_BREAKTHROUGH_SAMPLE,
    MIN_BREAKTHROUGH_SECTORS,
    MIN_BREAKTHROUGH_SPLIT_PASS,
    MIN_BREAKTHROUGH_SYMBOLS,
    REJECTIONS_V7_PATH,
    RESEARCH_V7_VERSION,
    WATCHLIST_V7_PATH,
    TOURNAMENT_COMPARISON_V7_PATH,
    TOURNAMENT_HOLDOUT_V7_PATH,
    TOURNAMENT_LEADERBOARD_V7_PATH,
    TRADES_V7_PATH,
    V7_ALL_SUBFAMILIES,
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    is_forbidden_symbol,
    research_v7_proof_record,
    utc_now_iso,
)


__all__ = ["run_research_breakthrough_gate_v7"]


DRAWDOWN_ABS_MAX = 2500.0
V7_QUARANTINED_SUBFAMILIES: tuple[str, ...] = ()

MAX_SINGLE_SYMBOL_PNL_SHARE = 0.30
MAX_SINGLE_SECTOR_PNL_SHARE = 0.30
MAX_SINGLE_REGIME_PNL_SHARE = 0.30

TRADE_ACTIVE_DIRECTIONS = {"long_call", "long_put"}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
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


def _pnl_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    pnls = [_float(r.get("pnl")) for r in rows]
    if not pnls:
        return {
            "sample_count": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }
    wins = sum(p for p in pnls if p > 0.0)
    losses = -sum(p for p in pnls if p < 0.0)
    pf = (wins / losses) if losses > 0.0 else (wins if wins > 0.0 else 0.0)
    expectancy = sum(pnls) / len(pnls)

    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    win_rate = sum(1 for p in pnls if p > 0.0) / len(pnls)
    return {
        "sample_count": len(rows),
        "net_pnl": round(sum(pnls), 6),
        "profit_factor": round(pf, 6),
        "expectancy": round(expectancy, 6),
        "max_drawdown": round(-max_dd, 6),
        "win_rate": round(win_rate, 6),
    }


def _compute_trade_active_by_sub(trades: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Compute trade-active (long_call/long_put) metrics per stable_subfamily_id."""
    by_sub: dict[str, list[dict[str, object]]] = {}
    no_trade_count_by_sub: Counter[str] = Counter()
    total_count_by_sub: Counter[str] = Counter()

    for trade in trades:
        sub = str(trade.get("stable_subfamily_id", ""))
        if not sub:
            continue
        direction = str(trade.get("direction", "")).lower()
        total_count_by_sub[sub] += 1
        if direction == "no_trade":
            no_trade_count_by_sub[sub] += 1
            continue
        if direction in TRADE_ACTIVE_DIRECTIONS:
            by_sub.setdefault(sub, []).append(trade)

    out: dict[str, dict[str, object]] = {}
    for sub, active_rows in by_sub.items():
        metrics = _pnl_metrics(active_rows)
        symbols = {str(r.get("symbol", "")) for r in active_rows if str(r.get("symbol", ""))}
        sectors = {str(r.get("sector", "")) for r in active_rows if str(r.get("sector", ""))}
        total = total_count_by_sub.get(sub, 0)
        no_trade = no_trade_count_by_sub.get(sub, 0)
        ratio = round(no_trade / total, 6) if total > 0 else 1.0
        out[sub] = {
            **metrics,
            "symbol_count": len(symbols),
            "sector_count": len(sectors),
            "no_trade_count": no_trade,
            "total_count": total,
            "no_trade_ratio": ratio,
        }
    # Include subfamilies that only had no_trade rows so they are explicitly blocked.
    for sub, total in total_count_by_sub.items():
        if sub in out:
            continue
        no_trade = no_trade_count_by_sub.get(sub, 0)
        out[sub] = {
            "sample_count": 0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "symbol_count": 0,
            "sector_count": 0,
            "no_trade_count": no_trade,
            "total_count": total,
            "no_trade_ratio": 1.0 if total > 0 else 0.0,
        }
    return out


def _trade_active_metrics_from_score(score: dict[str, object]) -> dict[str, object]:
    """Fallback when V7 trades are not yet available."""
    return {
        "sample_count": _int(score.get("trade_active_sample_count")),
        "symbol_count": _int(score.get("trade_active_symbol_count")),
        "sector_count": _int(score.get("trade_active_sector_count")),
        "net_pnl": _float(score.get("trade_active_net_pnl")),
        "profit_factor": _float(score.get("trade_active_profit_factor")),
        "expectancy": _float(score.get("trade_active_expectancy")),
        "max_drawdown": _float(score.get("trade_active_max_drawdown")),
        "win_rate": _float(score.get("trade_active_win_rate")),
        "no_trade_count": _int(score.get("no_trade_count")),
        "total_count": _int(score.get("total_count")),
        "no_trade_ratio": _float(score.get("no_trade_ratio"), default=1.0),
    }


def _fixture_count_for_sub(trades: list[dict[str, object]], sub: str) -> int:
    count = 0
    for trade in trades:
        if str(trade.get("stable_subfamily_id", "")) != sub:
            continue
        count += _int(trade.get("fixture_champion_count"))
        symbol = str(trade.get("symbol", ""))
        if is_forbidden_symbol(symbol):
            count += 1
        mds = str(trade.get("market_data_source_type", "")).lower()
        if "fixture" in mds or "synthetic" in mds or "test" in mds:
            count += 1
    return count


def _gate_decision(
    score: dict[str, object],
    holdout_by_sub: dict[str, dict[str, object]],
    comparison_by_sub: dict[str, dict[str, object]],
    trade_active_by_sub: dict[str, dict[str, object]],
    fixture_count: int,
) -> tuple[bool, list[str], dict[str, object]]:
    """Return (is_breakthrough, rejection_reasons, trade_active_metrics)."""
    reasons: list[str] = []
    sub = str(score.get("stable_subfamily_id", ""))
    family = str(score.get("stable_family_id", ""))

    if not sub or not family:
        reasons.append("missing_stable_family_or_subfamily")
    if family in V7_QUARANTINED_SUBFAMILIES or sub in V7_QUARANTINED_SUBFAMILIES:
        reasons.append("quarantined_failed_family")
    if fixture_count > 0:
        reasons.append("fixture_or_test_symbol_present")

    if _int(score.get("sample_count")) < MIN_BREAKTHROUGH_SAMPLE:
        reasons.append("sample_count_below_minimum")
    if _int(score.get("symbol_count")) < MIN_BREAKTHROUGH_SYMBOLS:
        reasons.append("symbol_count_below_minimum")
    if _int(score.get("sector_count")) < MIN_BREAKTHROUGH_SECTORS:
        reasons.append("sector_count_below_minimum")

    pf = _float(score.get("profit_factor"))
    if pf <= MIN_BREAKTHROUGH_PF:
        reasons.append("profit_factor_below_threshold")
    if _float(score.get("net_pnl")) <= 0:
        reasons.append("net_pnl_not_positive")
    if _float(score.get("expectancy")) <= 0:
        reasons.append("expectancy_not_positive")
    if abs(_float(score.get("max_drawdown"))) > DRAWDOWN_ABS_MAX:
        reasons.append("drawdown_exceeds_max")

    win_rate = _float(score.get("win_rate"))
    if win_rate < MIN_BREAKTHROUGH_SPLIT_PASS:
        reasons.append("split_pass_rate_below_threshold")

    top_symbol_share = _float(score.get("top_symbol_trade_share"))
    if top_symbol_share > MAX_SINGLE_SYMBOL_PNL_SHARE:
        reasons.append("one_symbol_fluke")
    top_sector_share = _float(score.get("top_sector_trade_share"))
    if top_sector_share > MAX_SINGLE_SECTOR_PNL_SHARE:
        reasons.append("one_sector_fluke")
    top_regime_share = _float(score.get("top_regime_trade_share"))
    if top_regime_share > MAX_SINGLE_REGIME_PNL_SHARE:
        reasons.append("one_regime_fluke")

    if sub not in V7_ALL_SUBFAMILIES:
        reasons.append("stress_subfamily_not_active")

    ho = holdout_by_sub.get(sub, {})
    if not ho.get("holdout_survival"):
        reasons.append("holdout_survival_failed")

    cmp_ = comparison_by_sub.get(sub, {})
    improved_vs_v6 = bool(cmp_.get("improved_vs_v6", cmp_.get("improved_vs_v5", False)))
    if not improved_vs_v6:
        reasons.append("no_improvement_vs_v6")

    # Trade-active / no-trade honesty checks (never bypassed)
    ta = trade_active_by_sub.get(sub, _trade_active_metrics_from_score(score))
    no_trade_ratio = _float(ta.get("no_trade_ratio"), default=1.0)
    if no_trade_ratio > V7_MAX_NO_TRADE_RATIO:
        reasons.append("no_trade_dominance_above_max")

    ta_sample = _int(ta.get("sample_count"))
    if ta_sample < V7_MIN_TRADE_ACTIVE_SAMPLE:
        reasons.append("trade_active_sample_below_minimum")

    if ta_sample > 0:
        if _float(ta.get("profit_factor")) <= MIN_BREAKTHROUGH_PF:
            reasons.append("trade_active_profit_factor_below_threshold")
        if _float(ta.get("net_pnl")) <= 0:
            reasons.append("trade_active_net_pnl_not_positive")
        if _float(ta.get("expectancy")) <= 0:
            reasons.append("trade_active_expectancy_not_positive")
        if abs(_float(ta.get("max_drawdown"))) > DRAWDOWN_ABS_MAX:
            reasons.append("trade_active_drawdown_exceeds_max")
        ta_win_rate = _float(ta.get("win_rate"))
        if ta_win_rate < MIN_BREAKTHROUGH_SPLIT_PASS:
            reasons.append("trade_active_split_pass_rate_below_threshold")
        if _int(ta.get("symbol_count")) < MIN_BREAKTHROUGH_SYMBOLS:
            reasons.append("trade_active_symbol_count_below_minimum")
        if _int(ta.get("sector_count")) < MIN_BREAKTHROUGH_SECTORS:
            reasons.append("trade_active_sector_count_below_minimum")
    else:
        reasons.append("trade_active_missing")

    return (len(reasons) == 0, reasons, ta)


def run_research_breakthrough_gate_v7() -> dict[str, object]:
    scores = _read_jsonl_safe(TOURNAMENT_LEADERBOARD_V7_PATH)
    holdout = _read_jsonl_safe(TOURNAMENT_HOLDOUT_V7_PATH)
    comparison = _read_jsonl_safe(TOURNAMENT_COMPARISON_V7_PATH)
    trades = _read_jsonl_safe(TRADES_V7_PATH)

    holdout_by_sub = {str(h.get("stable_subfamily_id", "")): h for h in holdout}
    comparison_by_sub = {str(c.get("stable_subfamily_id", "")): c for c in comparison}

    trade_active_by_sub = _compute_trade_active_by_sub(trades)

    breakthroughs: list[dict[str, object]] = []
    watchlist: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    rejection_reasons: Counter[str] = Counter()

    for score in scores:
        sub = str(score.get("stable_subfamily_id", ""))
        family = str(score.get("stable_family_id", ""))
        fixture_count = _fixture_count_for_sub(trades, sub) if trades else _int(score.get("fixture_count"))

        is_breakthrough, reasons, ta = _gate_decision(
            score,
            holdout_by_sub,
            comparison_by_sub,
            trade_active_by_sub,
            fixture_count,
        )

        cmp_ = comparison_by_sub.get(sub, {})
        improved_vs_v6 = bool(cmp_.get("improved_vs_v6", cmp_.get("improved_vs_v5", False)))
        ho = holdout_by_sub.get(sub, {})

        base: dict[str, object] = {
            "artifact_type": "research_breakthrough_gate_result_v7",
            "stable_family_id": family,
            "stable_subfamily_id": sub,
            "cohort_id": str(score.get("cohort_id", "")),
            "sample_count": _int(score.get("sample_count")),
            "symbol_count": _int(score.get("symbol_count")),
            "sector_count": _int(score.get("sector_count")),
            "profit_factor": _float(score.get("profit_factor")),
            "net_pnl": _float(score.get("net_pnl")),
            "expectancy": _float(score.get("expectancy")),
            "max_drawdown": _float(score.get("max_drawdown")),
            "win_rate": _float(score.get("win_rate")),
            "top_symbol_trade_share": _float(score.get("top_symbol_trade_share")),
            "top_sector_trade_share": _float(score.get("top_sector_trade_share")),
            "top_regime_trade_share": _float(score.get("top_regime_trade_share")),
            "no_trade_ratio": _float(ta.get("no_trade_ratio")),
            "trade_active_sample_count": _int(ta.get("sample_count")),
            "trade_active_symbol_count": _int(ta.get("symbol_count")),
            "trade_active_sector_count": _int(ta.get("sector_count")),
            "trade_active_profit_factor": _float(ta.get("profit_factor")),
            "trade_active_net_pnl": _float(ta.get("net_pnl")),
            "trade_active_expectancy": _float(ta.get("expectancy")),
            "trade_active_max_drawdown": _float(ta.get("max_drawdown")),
            "trade_active_win_rate": _float(ta.get("win_rate")),
            "fixture_count": fixture_count,
            "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
            "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
            "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
            "thresholds_lowered": False,
            "public_data_only": True,
            "live_trading_enabled": False,
            "reasons": list(reasons),
            "improved_vs_v6": improved_vs_v6,
            "holdout_survival": bool(ho.get("holdout_survival", False)),
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }

        if is_breakthrough:
            base["status"] = "research_breakthrough"
            base["paper_champion_candidate_locked"] = True
            breakthroughs.append(record_with_hash(base, "record_hash"))
        else:
            watchlist_reasons = {
                "sample_count_below_minimum",
                "symbol_count_below_minimum",
                "sector_count_below_minimum",
                "split_pass_rate_below_threshold",
                "holdout_survival_failed",
                "drawdown_exceeds_max",
                "one_symbol_fluke",
                "one_sector_fluke",
                "one_regime_fluke",
                "stress_subfamily_not_active",
                "no_trade_dominance_above_max",
                "trade_active_sample_below_minimum",
                "trade_active_symbol_count_below_minimum",
                "trade_active_sector_count_below_minimum",
                "trade_active_split_pass_rate_below_threshold",
                "trade_active_drawdown_exceeds_max",
            }
            if improved_vs_v6 and any(r in watchlist_reasons for r in reasons):
                base["status"] = "research_watchlist"
                watchlist.append(record_with_hash(base, "record_hash"))
            else:
                base["status"] = "research_candidate"
                rejections.append(record_with_hash(base, "record_hash"))
            for r in reasons:
                rejection_reasons[r] += 1

    write_jsonl_file(BREAKTHROUGH_V7_PATH, breakthroughs)
    write_jsonl_file(WATCHLIST_V7_PATH, watchlist)
    write_jsonl_file(REJECTIONS_V7_PATH, rejections)

    pf_above_threshold_count = sum(
        1 for s in scores if _float(s.get("profit_factor")) > MIN_BREAKTHROUGH_PF
    )
    blocked_no_trade_only_count = sum(
        1
        for rec in [*watchlist, *rejections]
        if any(
            r in {"no_trade_dominance_above_max", "trade_active_missing", "trade_active_sample_below_minimum"}
            for r in rec.get("reasons", [])
        )
    )

    summary = {
        "artifact_type": "research_breakthrough_gate_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "research_breakthrough_gate_v7_status": "research_breakthrough_gate_complete_v7",
        "candidate_count": len(scores),
        "breakthrough_candidate_count": len(breakthroughs),
        "watchlist_count": len(watchlist),
        "improved_watchlist_count": len(watchlist),
        "rejection_count": len(rejections),
        "pf_above_threshold_count": pf_above_threshold_count,
        "trade_active_breakthrough_count": len(breakthroughs),
        "blocked_no_trade_only_count": blocked_no_trade_only_count,
        "paper_champion_candidate_locked_count": len(breakthroughs),
        "top_rejection_reasons": dict(rejection_reasons.most_common()),
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_min_breakthrough_sample": MIN_BREAKTHROUGH_SAMPLE,
        "v7_min_breakthrough_symbols": MIN_BREAKTHROUGH_SYMBOLS,
        "v7_min_breakthrough_sectors": MIN_BREAKTHROUGH_SECTORS,
        "v7_min_breakthrough_split_pass": MIN_BREAKTHROUGH_SPLIT_PASS,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(GATE_V7_SUMMARY_PATH, summary)
    write_jsonl_file(
        GATE_V7_PROOF_PATH,
        [research_v7_proof_record("research-breakthrough-gate-v7", summary["research_breakthrough_gate_v7_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_breakthrough_gate_v7(), indent=2, sort_keys=True, default=str))
