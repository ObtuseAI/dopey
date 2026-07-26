"""Thin helpers for V5 watchlist diagnosis (Workstream B, V6).

All calculations are deterministic and use only fields already present in the
V5 watchlist / tournament / holdout / regime / trade records.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence


__all__ = [
    "safe_float",
    "safe_int",
    "compute_split_pass_rate",
    "compute_holdout_survival",
    "compute_stress_survival",
    "compute_concentration",
    "compute_outlier_dependence",
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
    """V5 uses win_rate as the split pass rate proxy on the watchlist record."""
    return safe_float(record.get("win_rate", 0.0))


def compute_holdout_survival(record: dict[str, object], holdout_map: dict[str, dict[str, object]]) -> bool:
    sub = str(record.get("stable_subfamily_id", ""))
    if sub in holdout_map:
        return bool(holdout_map[sub].get("holdout_survival", False))
    return bool(record.get("holdout_survival", False))


def compute_stress_survival(record: dict[str, object], regime_map: dict[str, dict[str, object]]) -> bool:
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


def failed_gate_criteria(record: dict[str, object]) -> list[str]:
    reasons = record.get("reasons", [])
    if isinstance(reasons, (list, tuple)):
        return [str(r) for r in reasons]
    return []


def repairability_score(record: dict[str, object], blockers: Sequence[str]) -> float:
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
    return round(max(0.0, base), 6)


def mutation_plan_linkage(blockers: Sequence[str]) -> list[str]:
    """Map gate blockers to V6 mutation plan types."""
    linkage: dict[str, str] = {
        "drawdown_exceeds_max": "drawdown_repair",
        "holdout_survival_failed": "holdout_survival_repair",
        "split_pass_rate_below_threshold": "split_pass_repair",
        "concentration_exceeds_max": "concentration_repair",
        "expectancy_below_threshold": "expectancy_repair",
        "stress_survival_failed": "stress_survival_repair",
        "outlier_dependence_high": "outlier_dependence_repair",
        "symbol_coverage_below_min": "symbol_broadening",
        "sector_coverage_below_min": "sector_broadening",
    }
    plans: list[str] = []
    for b in blockers:
        if b in linkage and linkage[b] not in plans:
            plans.append(linkage[b])
    return plans
