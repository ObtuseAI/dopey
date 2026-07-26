"""Per-position exit playbook: pre-computed trigger geometry for the open book.

WHAT THIS IS (V21 adaptable #7, the honest kernel): for every open forward-walk
position, pre-compute WHERE the walk's EXISTING exit discipline (premium stop
-50% / target +100% / time stop) sits in spot/IV space - the spot level that
would put the next mark at the stop, the level that would tag the target, and
the P&L surface across a small spot x IV grid. When the market moves, the
operator reads the already-computed geometry instead of improvising.

WHAT THIS IS NOT: a new exit policy, a prediction, or "zero-latency execution".
It decides nothing and changes no rule - it only maps the rules already pinned
in dopey_backtest/forward_paper_walk.py onto today's book. Model prices are
Black-Scholes mids with a documented bid haircut; real next-session bids will
differ. Risk planning only; never evidence, never a bias change.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from dopey_backtest.forward_paper_walk import (
    MAX_MARKING_SESSIONS,
    PREMIUM_STOP_PCT,
    PREMIUM_TARGET_PCT,
)
from dopey_options.greeks_engine import bs_greeks
from dopey_options.risk_free_rate import resolve_risk_free_rate
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
PLAYBOOK_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "exit_playbook.json"

BID_HAIRCUT_PCT = 0.025      # model mid -> planning bid (documented simplification)
COMMISSION_PREMIUM_UNITS = 0.0065
SPOT_GRID_PCT = (-0.06, -0.03, -0.015, 0.0, 0.015, 0.03, 0.06)
IV_SCENARIOS = (("iv_crush_x0.6", 0.6), ("iv_flat_x1.0", 1.0), ("iv_spike_x1.5", 1.5))
NEXT_SESSION_DAYS = 1


def _planning_bid(model_mid: float) -> float:
    return max(model_mid * (1.0 - BID_HAIRCUT_PCT), 0.0)


def _mark_return(bid: float, entry_fill: float) -> float:
    """Mirror forward_paper_walk's mark test exactly (net of exit commission)."""
    return (bid - COMMISSION_PREMIUM_UNITS) / entry_fill - 1.0 if entry_fill > 0 else 0.0


def _model_mid(position: dict[str, Any], spot: float, iv: float, risk_free: float, elapsed_days: int) -> float:
    anchor = str(position.get("last_mark_date") or position["entry_date"])
    try:
        dte = max((date.fromisoformat(str(position["expiry"])) - date.fromisoformat(anchor)).days - elapsed_days, 0)
    except ValueError:
        dte = 20
    return float(bs_greeks(
        max(spot, 0.01), float(position["strike"]), dte / 365.0,
        risk_free, min(max(iv, 0.01), 5.0), str(position["option_type"]),
    )["price"])


def _trigger_spot(
    position: dict[str, Any], iv: float, risk_free: float, threshold: float, entry_fill: float,
) -> float | None:
    """Bisection: spot level whose next-session planning bid puts mark_return at
    `threshold`. None when no level within +/-40% of current spot crosses it."""
    base_spot = float(position.get("current_spot") or position["entry_spot"])
    is_call = str(position["option_type"]).lower() == "call"

    def excess(spot: float) -> float:
        mid = _model_mid(position, spot, iv, risk_free, NEXT_SESSION_DAYS)
        return _mark_return(_planning_bid(mid), entry_fill) - threshold

    lo, hi = base_spot * 0.60, base_spot * 1.40
    f_lo, f_hi = excess(lo), excess(hi)
    if f_lo * f_hi > 0:
        return None
    # option value is monotone in spot for single-leg long options
    if (f_lo > f_hi) == is_call:
        lo, hi, f_lo, f_hi = hi, lo, f_hi, f_lo
    for _ in range(60):
        mid_spot = (lo + hi) / 2.0
        if excess(mid_spot) < 0:
            lo = mid_spot
        else:
            hi = mid_spot
    return round((lo + hi) / 2.0, 4)


def build_position_playbook(position: dict[str, Any], risk_free: float) -> dict[str, Any]:
    entry_fill = float(position["entry_fill"])
    base_spot = float(position.get("current_spot") or position["entry_spot"])
    base_iv = float(position.get("current_iv") or position["entry_iv"])
    sessions_used = int(position.get("marking_sessions", 0))
    scenarios: list[dict[str, Any]] = []
    for label, iv_mult in IV_SCENARIOS:
        iv = base_iv * iv_mult
        grid = []
        for pct in SPOT_GRID_PCT:
            spot = base_spot * (1.0 + pct)
            bid = _planning_bid(_model_mid(position, spot, iv, risk_free, NEXT_SESSION_DAYS))
            ret = _mark_return(bid, entry_fill)
            if ret <= PREMIUM_STOP_PCT:
                action = "discipline_closes_premium_stop"
            elif ret >= PREMIUM_TARGET_PCT:
                action = "discipline_closes_premium_target"
            elif sessions_used + 1 >= MAX_MARKING_SESSIONS:
                action = "discipline_closes_time_stop"
            else:
                action = "hold_per_discipline"
            grid.append({
                "spot_move_pct": pct,
                "planning_bid": round(bid, 6),
                "mark_return": round(ret, 6),
                "pnl_premium_units": round(bid - COMMISSION_PREMIUM_UNITS - entry_fill, 6),
                "action": action,
            })
        scenarios.append({
            "iv_scenario": label,
            "stop_trigger_spot": _trigger_spot(position, iv, risk_free, PREMIUM_STOP_PCT, entry_fill),
            "target_trigger_spot": _trigger_spot(position, iv, risk_free, PREMIUM_TARGET_PCT, entry_fill),
            "grid": grid,
        })
    return {
        "position_id": position.get("position_id"),
        "symbol": position.get("symbol"),
        "option_type": position.get("option_type"),
        "strike": position.get("strike"),
        "expiry": position.get("expiry"),
        "entry_fill": entry_fill,
        "current_spot": base_spot,
        "current_iv": base_iv,
        "marking_sessions_used": sessions_used,
        "sessions_until_time_stop": max(MAX_MARKING_SESSIONS - sessions_used, 0),
        "scenarios": scenarios,
    }


def run_exit_playbook() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        summary = _base("blocked_missing_forward_ledger")
        write_json_atomic(PLAYBOOK_PATH, summary)
        return summary
    positions = json.loads(LEDGER_PATH.read_text(encoding="utf-8")).get("open_positions", [])
    if not positions:
        summary = _base("no_open_positions_playbook_trivial")
        write_json_atomic(PLAYBOOK_PATH, summary)
        return summary
    risk_free, risk_free_source = resolve_risk_free_rate()
    playbooks = [build_position_playbook(position, risk_free) for position in positions]
    summary = _base("exit_playbook_complete")
    summary.update({
        "open_positions": len(playbooks),
        "risk_free_rate": risk_free,
        "risk_free_source": risk_free_source,
        "discipline": {
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "premium_target_pct": PREMIUM_TARGET_PCT,
            "max_marking_sessions": MAX_MARKING_SESSIONS,
            "source": "dopey_backtest/forward_paper_walk.py (pinned; this artifact changes nothing)",
        },
        "planning_bid_model": f"bs_mid_x_(1-{BID_HAIRCUT_PCT})_minus_commission_documented_simplification",
        "positions": playbooks,
    })
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(PLAYBOOK_PATH, summary)
    return summary


def _base(status: str) -> dict[str, Any]:
    return {
        "artifact_type": "exit_playbook_summary",
        "playbook_status": status,
        "evidence_class": "risk_planning_only_maps_existing_discipline",
        "not_edge_evidence": True,
        "strategy_promotion_allowed": False,
        "changes_no_rule": True,
        "informs": "operator_risk_reading_only_discipline_already_pinned",
        "paper_only": True,
        "live_blocked": True,
    }


if __name__ == "__main__":
    result = run_exit_playbook()
    print(json.dumps({k: v for k, v in result.items() if k != "positions"}, indent=2)[:800])
