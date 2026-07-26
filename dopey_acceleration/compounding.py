"""Evidence-gated geometric compounding research from real paper returns."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dopey_backtest.forward_evidence_integrity import (
    POLICY_REPLAY_PATH,
    classify_outcomes,
)

from .common import ARTIFACT_ROOT, REPO_ROOT, read_optional_json, stamped, write_json_atomic


FORWARD_LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
PLAN_PATH = ARTIFACT_ROOT / "compounding_research_plan.json"
MIN_SAMPLE = 100


def _max_drawdown(growth: list[float]) -> float:
    peak = 1.0
    maximum = 0.0
    for value in growth:
        peak = max(peak, value)
        maximum = max(maximum, (peak - value) / peak if peak > 0 else 1.0)
    return maximum


def build_compounding_plan(repo_root: Path) -> dict[str, Any]:
    if repo_root.resolve() != REPO_ROOT.resolve():
        raise ValueError(f"repository root mismatch: expected={REPO_ROOT}, actual={repo_root}")
    ledger, ledger_status = read_optional_json(FORWARD_LEDGER_PATH)
    policy_replay, policy_replay_status = read_optional_json(POLICY_REPLAY_PATH)
    outcomes = classify_outcomes(ledger, policy_replay if policy_replay_status == "available" else {})
    closed = outcomes["validated"]
    returns = [float(row["trade_return"]) for row in closed if isinstance(row, dict) and isinstance(row.get("trade_return"), (int, float))]
    valid_returns = [max(value, -0.999999) for value in returns]
    growth: list[float] = []
    capital = 1.0
    for value in valid_returns:
        capital *= 1.0 + value
        growth.append(capital)
    geometric_mean = (capital ** (1.0 / len(valid_returns)) - 1.0) if valid_returns and capital > 0 else None
    wins = [value for value in valid_returns if value > 0]
    losses = [value for value in valid_returns if value <= 0]
    win_rate = len(wins) / len(valid_returns) if valid_returns else None
    average_win = sum(wins) / len(wins) if wins else None
    average_loss = abs(sum(losses) / len(losses)) if losses else None
    raw_kelly = None
    if win_rate is not None and average_win is not None and average_loss is not None and average_loss > 0:
        payoff = average_win / average_loss
        raw_kelly = win_rate - (1.0 - win_rate) / payoff if payoff > 0 else None
    sample_sufficient = len(valid_returns) >= MIN_SAMPLE
    positive_geometric_edge = geometric_mean is not None and geometric_mean > 0
    allocation_multiplier = max(0.0, min(float(raw_kelly or 0.0) * 0.25, 0.05)) if sample_sufficient and positive_geometric_edge else 0.0
    status = "eligible_for_fractional_compounding_research" if allocation_multiplier > 0 else "blocked_insufficient_or_nonpositive_forward_evidence"
    plan = stamped(
        {
            "artifact_type": "geometric_compounding_research_plan",
            "compounding_version": "dopey-geometric-compounding-v4",
            "ledger_status": ledger_status,
            "policy_replay_status": policy_replay_status,
            "raw_closed_record_count": sum(len(records) for records in outcomes.values()),
            "censored_outcome_count": len(outcomes["censored"]),
            "quarantined_outcome_count": len(outcomes["quarantined"]),
            "statistics_exclude_censored_and_quarantined_outcomes": True,
            "sample_count": len(valid_returns),
            "minimum_sample_required": MIN_SAMPLE,
            "sample_sufficient": sample_sufficient,
            "geometric_mean_trade_return": round(geometric_mean, 8) if geometric_mean is not None else None,
            "compounded_growth_factor_for_observed_sequence": round(capital, 8),
            "maximum_observed_drawdown": round(_max_drawdown(growth), 8),
            "win_rate": round(win_rate, 8) if win_rate is not None else None,
            "raw_kelly_fraction": round(raw_kelly, 8) if raw_kelly is not None else None,
            "allowed_fractional_compounding_multiplier": round(allocation_multiplier, 8),
            "compounding_status": status,
            "policy": "quarter_kelly_capped_at_five_percent_only_after_100_real_forward_closed_trades_and_positive_geometric_mean",
            "roi_forecast_claimed": False,
            "historical_sequence_is_not_future_return": True,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    write_json_atomic(PLAN_PATH, plan)
    return plan
