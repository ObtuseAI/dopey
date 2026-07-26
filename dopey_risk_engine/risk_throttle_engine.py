"""Risk throttles for paper capital survival."""
from __future__ import annotations

from collections import Counter, defaultdict

from dopey_wealth_engine.common import stable_hash


def build_risk_throttle_records(trades: list[dict], scores: list[dict]) -> list[dict]:
    records: list[dict] = []
    symbol_counts = Counter(str(trade["underlying_symbol"]) for trade in trades)
    total_trades = max(len(trades), 1)
    for symbol, count in symbol_counts.items():
        if count / total_trades > 0.18:
            records.append(_record("symbol_concentration", symbol, "reduce_new_entries", count / total_trades))
    for score in scores:
        if abs(float(score["max_drawdown"])) > 2_500:
            records.append(_record("max_strategy_drawdown", str(score["strategy_family"]), "throttle_strategy", abs(float(score["max_drawdown"]))))
        if int(score["loss_streak"]) >= 3:
            records.append(_record("max_losing_streak", str(score["strategy_family"]), "kill_or_shadow", float(score["loss_streak"])))
        if int(score["turnover"]) > 12:
            records.append(_record("max_overtrade_frequency", str(score["strategy_family"]), "reduce_allocation", float(score["turnover"])))
    theta_by_family: dict[str, float] = defaultdict(float)
    for trade in trades:
        theta_by_family[str(trade["strategy_family"])] += float(trade["theta_bleed_stress"])
    for family, theta in theta_by_family.items():
        if theta > 25.0:
            records.append(_record("max_theta_bleed", family, "prefer_later_expiry_or_reduce_size", theta))
    for record in records:
        record["record_hash"] = stable_hash(record)
    return records


def _record(throttle_type: str, target: str, action: str, observed_value: float) -> dict:
    return {
        "artifact_type": "risk_throttle_record",
        "throttle_type": throttle_type,
        "target": target,
        "action": action,
        "observed_value": round(observed_value, 6),
        "throttle_blocks_all_research": False,
        "paper_capital_protected": True,
        "paper_only": True,
        "live_blocked": True,
    }

