"""Thin helpers for V6 watchlist and blocker diagnosis (Workstream C, V7).

All calculations are deterministic and use only fields already present in the
immutable V6 watchlist / gate rejections / tournament / holdout / regime / path
trade records.  V7 adds trade-active ratio checks so no-trade-dominant
candidates are explicitly diagnosed.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

from dopey_autonomy.signal_research_v7_common import (
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
)


__all__ = [
    "safe_float",
    "safe_int",
    "compute_split_pass_rate",
    "compute_holdout_survival",
    "compute_stress_survival",
    "compute_concentration",
    "compute_outlier_dependence",
    "compute_trade_active_ratio",
    "is_no_trade_dominant",
    "failed_gate_criteria",
    "repairability_score",
    "mutation_plan_linkage",
]


def safe_float(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if __import__("math").isfinite(parsed):
        return parsed
    return 0.0


def safe_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def compute_split_pass_rate(record: dict[str, object]) -> float:
    """V6 uses win_rate as the split-pass-rate proxy on the record."""
    return safe_float(record.get("win_rate", 0.0))


def compute_holdout_survival(
    record: dict[str, object],
    holdout_map: dict[str, dict[str, object]],
) -> bool:
    sub = str(record.get("stable_subfamily_id", ""))
    if sub in holdout_map:
        return bool(holdout_map[sub].get("holdout_survival", False))
    return bool(record.get("holdout_survival", False))


def compute_stress_survival(
    record: dict[str, object],
    regime_map: dict[str, dict[str, object]],
) -> bool:
    """Stress survival proxy: at least one regime bucket for the family has PF >= 1.05."""
    family = str(record.get("stable_family_id", ""))
    if not family:
        return False
    for regime_key, regime in regime_map.items():
        if regime_key.startswith(family + "|") or regime_key == family:
            pf = safe_float(regime.get("pf", 0.0))
            if pf >= 1.05:
                return True
    return False


def compute_concentration(
    subfamily_id: str,
    trades: Sequence[dict[str, object]],
) -> dict[str, float]:
    """Return top-symbol and top-sector trade-share concentration for a subfamily."""
    subset = [t for t in trades if str(t.get("stable_subfamily_id", "")) == subfamily_id]
    total = len(subset)
    if total == 0:
        return {"top_symbol_trade_share": 0.0, "top_sector_trade_share": 0.0}
    symbol_counts = Counter(str(t.get("symbol", "")) for t in subset if str(t.get("symbol", "")))
    sector_counts = Counter(str(t.get("sector", "")) for t in subset if str(t.get("sector", "")))
    top_symbol_share = symbol_counts.most_common(1)[0][1] / total if symbol_counts else 0.0
    top_sector_share = sector_counts.most_common(1)[0][1] / total if sector_counts else 0.0
    return {
        "top_symbol_trade_share": round(top_symbol_share, 6),
        "top_sector_trade_share": round(top_sector_share, 6),
    }


def compute_outlier_dependence(
    record: dict[str, object],
    trades: Sequence[dict[str, object]],
) -> dict[str, float]:
    """Measure outlier dependence via the largest single-trade PnL magnitude vs drawdown."""
    subfamily_id = str(record.get("stable_subfamily_id", ""))
    subset = [t for t in trades if str(t.get("stable_subfamily_id", "")) == subfamily_id]
    pnls = [safe_float(t.get("pnl", 0.0)) for t in subset]
    max_drawdown = abs(safe_float(record.get("max_drawdown", 0.0)))
    if not pnls or max_drawdown <= 0.0:
        return {"max_trade_pnl_magnitude": 0.0, "max_trade_to_drawdown_ratio": 0.0}
    max_mag = max(abs(p) for p in pnls)
    return {
        "max_trade_pnl_magnitude": round(max_mag, 6),
        "max_trade_to_drawdown_ratio": round(max_mag / max_drawdown, 6),
    }


def compute_trade_active_ratio(
    subfamily_id: str,
    trades: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Return long-call/long-put vs no-trade counts and ratios for a subfamily."""
    subset = [t for t in trades if str(t.get("stable_subfamily_id", "")) == subfamily_id]
    total = len(subset)
    trade_active = sum(
        1
        for t in subset
        if str(t.get("direction", "")).lower() in {"long_call", "long_put"}
    )
    no_trade = sum(
        1
        for t in subset
        if str(t.get("direction", "")).lower() == "no_trade"
    )
    if total == 0:
        return {
            "trade_active_count": 0,
            "no_trade_count": 0,
            "trade_active_ratio": 0.0,
            "no_trade_ratio": 1.0,
        }
    return {
        "trade_active_count": trade_active,
        "no_trade_count": no_trade,
        "trade_active_ratio": round(trade_active / total, 6),
        "no_trade_ratio": round(no_trade / total, 6),
    }


def is_no_trade_dominant(trade_active_ratio: dict[str, object]) -> bool:
    """True when the candidate is no-trade-dominant per V7 caps."""
    no_trade_ratio = safe_float(trade_active_ratio.get("no_trade_ratio", 1.0))
    trade_active_count = safe_int(trade_active_ratio.get("trade_active_count", 0))
    return (
        no_trade_ratio > V7_MAX_NO_TRADE_RATIO
        or trade_active_count < V7_MIN_TRADE_ACTIVE_SAMPLE
    )


def failed_gate_criteria(record: dict[str, object]) -> list[str]:
    reasons = record.get("reasons", [])
    if isinstance(reasons, (list, tuple)):
        return [str(r) for r in reasons]
    return []


def repairability_score(
    record: dict[str, object],
    blockers: Sequence[str],
    no_trade_dominant: bool,
) -> float:
    """Deterministic repairability: more blockers and larger drawdown reduce score."""
    base = 1.0
    base -= 0.08 * len(blockers)
    max_dd = abs(safe_float(record.get("max_drawdown", 0.0)))
    if max_dd > 2500.0:
        base -= 0.10
    if not compute_holdout_survival(record, {}):
        base -= 0.10
    split_pass = compute_split_pass_rate(record)
    if split_pass < 0.55:
        base -= 0.05
    if no_trade_dominant:
        base -= 0.05
    return round(max(0.0, base), 6)


def mutation_plan_linkage(blockers: Sequence[str]) -> list[str]:
    """Map gate blockers and no-trade dominance to V7 canonical mutation types."""
    linkage: dict[str, list[str]] = {
        "drawdown_exceeds_max": ["drawdown_repair"],
        "holdout_survival_failed": ["holdout_survival_repair"],
        "split_pass_rate_below_threshold": ["split_pass_repair"],
        "concentration_exceeds_max": ["concentration_repair"],
        "expectancy_below_threshold": ["expectancy_repair"],
        "expectancy_not_positive": ["expectancy_repair"],
        "stress_survival_failed": ["stress_survival_repair"],
        "outlier_dependence_high": ["outlier_dependence_repair"],
        "symbol_coverage_below_min": ["symbol_broadening"],
        "sector_coverage_below_min": ["sector_broadening"],
        "no_improvement_vs_v5": ["improvement_vs_v5_repair"],
        "profit_factor_below_threshold": ["pf_repair_above_110"],
        "net_pnl_not_positive": ["net_pnl_repair"],
        "no_trade_dominant": ["trade_active_activation", "no_trade_ratio_reduction"],
    }
    plans: list[str] = []
    for b in blockers:
        for plan in linkage.get(b, []):
            if plan not in plans:
                plans.append(plan)
    return plans
