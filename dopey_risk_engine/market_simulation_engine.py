"""Market simulation engine: distributional stress from REAL resampled history.

WHAT THIS IS: a stationary block bootstrap over the governed real spine's
joint daily returns (date-blocks resampled together, so cross-symbol
correlation is preserved exactly), generating thousands of counterfactual
short-horizon market paths. The open paper book is re-priced along every path,
yielding a full P&L DISTRIBUTION - expected shortfall, tail probabilities,
worst-path anatomy - instead of seven hand-picked scenarios.

WHAT THIS IS NOT: evidence, edge, or a signal source. Synthetic paths graded
as wins is the exact disease this system was rebuilt to kill (V1-V7). Every
artifact here carries evidence_class=simulation_only and promotion_allowed
false; the truth layer and readiness gate never read it. Simulation informs
RISK - it can only ever argue for smaller, never for readier.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date
from pathlib import Path
from typing import Any

from dopey_data.history_validator import validate_default_history_dataset
from dopey_options.greeks_engine import bs_greeks
from dopey_options.risk_free_rate import resolve_risk_free_rate
from dopey_research_pipeline.artifact_io import write_json_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "artifacts" / "dopey" / "forward_walk" / "forward_walk_ledger.json"
SIMULATION_PATH = REPO_ROOT / "artifacts" / "dopey" / "distributional_stress" / "distributional_stress.json"

SIMULATION_SEED = 20260710
PATH_COUNT = 500
HORIZON_DAYS = 5
MEAN_BLOCK_LENGTH = 10
RETURN_WINDOW_YEARS = 3
HIGH_VOL_IV_BUMP = 1.25  # deterministic rule: stressed paths reprice at bumped IV
BOOK_LOSS_ALARM_PCT = 0.30


def joint_return_matrix(bars: list[dict[str, Any]], window_years: int = RETURN_WINDOW_YEARS) -> tuple[list[str], dict[str, list[float]]]:
    """(sorted dates, symbol -> aligned daily log returns) over the trailing window."""
    closes: dict[str, dict[str, float]] = {}
    for bar in bars:
        closes.setdefault(str(bar["symbol"]), {})[str(bar["date"])] = float(bar["adjusted_close"])
    all_dates = sorted(set.intersection(*(set(series) for series in closes.values()))) if closes else []
    cutoff = f"{int(all_dates[-1][:4]) - window_years}{all_dates[-1][4:]}" if all_dates else ""
    dates = [day for day in all_dates if day >= cutoff]
    returns: dict[str, list[float]] = {}
    for symbol, series in closes.items():
        values = [series[day] for day in dates]
        returns[symbol] = [
            math.log(later / earlier) if earlier > 0 and later > 0 else 0.0
            for earlier, later in zip(values, values[1:])
        ]
    return dates[1:], returns


def bootstrap_paths(
    return_dates: list[str], returns: dict[str, list[float]],
    path_count: int = PATH_COUNT, horizon: int = HORIZON_DAYS, seed: int = SIMULATION_SEED,
) -> list[dict[str, float]]:
    """Stationary block bootstrap (joint across symbols): each path is a dict of
    symbol -> cumulative horizon return. Deterministic under the fixed seed."""
    rng = random.Random(seed)
    n = len(return_dates)
    paths: list[dict[str, float]] = []
    if n < horizon + 5 or not returns:
        return paths
    for _ in range(path_count):
        cumulative = {symbol: 0.0 for symbol in returns}
        steps = 0
        while steps < horizon:
            start = rng.randrange(n)
            block = 1 + min(int(-math.log(max(rng.random(), 1e-12)) * MEAN_BLOCK_LENGTH), horizon)
            for offset in range(block):
                if steps >= horizon:
                    break
                position = (start + offset) % n
                for symbol in cumulative:
                    cumulative[symbol] += returns[symbol][position]
                steps += 1
        paths.append({symbol: math.expm1(value) for symbol, value in cumulative.items()})
    return paths


def reprice_book(positions: list[dict[str, Any]], paths: list[dict[str, float]], risk_free: float) -> list[float]:
    """Book P&L (premium units) along each path: spot moved by the path's real
    resampled return, tenor rolled forward HORIZON_DAYS, IV bumped on stressed
    paths (a documented deterministic simplification, not a vol model)."""
    pnls: list[float] = []
    stress_bar = sorted(abs(sum(path.values())) for path in paths)[int(0.9 * len(paths))] if paths else 0.0
    for path in paths:
        book = 0.0
        stressed = abs(sum(path.values())) >= stress_bar and stress_bar > 0
        for position in positions:
            symbol = str(position["symbol"])
            move = path.get(symbol, 0.0)
            spot = float(position.get("current_spot") or position["entry_spot"]) * (1.0 + move)
            iv = float(position.get("current_iv") or position["entry_iv"]) * (HIGH_VOL_IV_BUMP if stressed else 1.0)
            expiry = str(position["expiry"])
            anchor = str(position.get("last_mark_date") or position["entry_date"])
            try:
                dte = max((date.fromisoformat(expiry) - date.fromisoformat(anchor)).days - HORIZON_DAYS, 0)
            except ValueError:
                dte = 20
            value = bs_greeks(max(spot, 0.01), float(position["strike"]), dte / 365.0, risk_free, min(iv, 5.0), str(position["option_type"]))["price"]
            book += value - float(position["entry_fill"])
        pnls.append(round(book, 6))
    return sorted(pnls)


# Named scenario classes (V21 adaptable #3 extension): deterministic parametric
# probes of the SAME book, each a documented stylized shock. sigma is each
# symbol's own trailing daily return stdev from the real matrix - no RNG, no
# generative model, no "muscle memory": these are risk probes, never evidence.
SCENARIO_CLASSES: tuple[dict[str, Any], ...] = (
    {"name": "gap_down_3sigma", "spot_sigma": -3.0, "iv_mult": 1.50, "days": 1,
     "haircut": 0.0, "note": "broad 3-sigma overnight gap, panic vol bid"},
    {"name": "liquidity_hole_iv_blowout", "spot_sigma": -1.0, "iv_mult": 2.00, "days": 1,
     "haircut": 0.15, "note": "spreads blow out: marks liquidate 15% under model value"},
    {"name": "vol_spike_no_move", "spot_sigma": 0.0, "iv_mult": 1.75, "days": 1,
     "haircut": 0.0, "note": "event vol repricing, spot pinned (long premium gains)"},
    {"name": "vol_crush_no_move", "spot_sigma": 0.0, "iv_mult": 0.60, "days": 1,
     "haircut": 0.0, "note": "the long-premium killer: IV crush, no directional help"},
    {"name": "weekend_gap_monday", "spot_sigma": -1.5, "iv_mult": 1.30, "days": 3,
     "haircut": 0.0, "note": "three calendar days of decay plus a Monday gap down"},
)


def _symbol_sigmas(returns: dict[str, list[float]]) -> dict[str, float]:
    sigmas: dict[str, float] = {}
    for symbol, series in returns.items():
        n = len(series)
        if n < 20:
            sigmas[symbol] = 0.0
            continue
        mean = sum(series) / n
        sigmas[symbol] = (sum((value - mean) ** 2 for value in series) / n) ** 0.5
    return sigmas


def run_named_scenarios(
    positions: list[dict[str, Any]],
    returns: dict[str, list[float]],
    risk_free: float,
) -> list[dict[str, Any]]:
    """Reprice the open book under each named scenario; per-scenario book P&L
    plus the three worst position contributors (risk anatomy, not advice)."""
    sigmas = _symbol_sigmas(returns)
    results: list[dict[str, Any]] = []
    for scenario in SCENARIO_CLASSES:
        book = 0.0
        contributions: list[tuple[float, str]] = []
        for position in positions:
            symbol = str(position["symbol"])
            sigma = sigmas.get(symbol, 0.0)
            move = math.expm1(float(scenario["spot_sigma"]) * sigma)
            spot = float(position.get("current_spot") or position["entry_spot"]) * (1.0 + move)
            iv = float(position.get("current_iv") or position["entry_iv"]) * float(scenario["iv_mult"])
            anchor = str(position.get("last_mark_date") or position["entry_date"])
            try:
                dte = max((date.fromisoformat(str(position["expiry"])) - date.fromisoformat(anchor)).days - int(scenario["days"]), 0)
            except ValueError:
                dte = 20
            value = bs_greeks(
                max(spot, 0.01), float(position["strike"]), dte / 365.0,
                risk_free, min(max(iv, 0.01), 5.0), str(position["option_type"]),
            )["price"] * (1.0 - float(scenario["haircut"]))
            pnl = value - float(position["entry_fill"])
            book += pnl
            contributions.append((pnl, f"{position.get('position_id', symbol)}:{symbol}"))
        contributions.sort()
        results.append({
            "scenario": scenario["name"],
            "note": scenario["note"],
            "spot_shock_sigmas": scenario["spot_sigma"],
            "iv_multiplier": scenario["iv_mult"],
            "elapsed_days": scenario["days"],
            "liquidation_haircut": scenario["haircut"],
            "book_pnl_premium_units": round(book, 6),
            "worst_positions": [
                {"position": label, "pnl": round(pnl, 6)} for pnl, label in contributions[:3]
            ],
        })
    return results


def run_market_simulation_engine() -> dict[str, Any]:
    dataset = validate_default_history_dataset()
    if dataset["dataset_status"] != "valid_real_dataset":
        summary = _base("blocked_missing_valid_real_history")
        write_json_atomic(SIMULATION_PATH, summary)
        return summary
    if not LEDGER_PATH.exists():
        summary = _base("blocked_missing_forward_ledger")
        write_json_atomic(SIMULATION_PATH, summary)
        return summary
    positions = json.loads(LEDGER_PATH.read_text(encoding="utf-8")).get("open_positions", [])
    if not positions:
        summary = _base("no_open_positions_distribution_trivial")
        write_json_atomic(SIMULATION_PATH, summary)
        return summary
    return_dates, returns = joint_return_matrix([bar for bar in dataset["bars_loaded"] if bar["symbol"] != "VIX"])
    paths = bootstrap_paths(return_dates, returns)
    if not paths:
        summary = _base("blocked_insufficient_return_history")
        write_json_atomic(SIMULATION_PATH, summary)
        return summary
    risk_free, risk_free_source = resolve_risk_free_rate()
    pnls = reprice_book(positions, paths, risk_free)
    premium = sum(float(position["entry_fill"]) for position in positions)
    tail = pnls[: max(len(pnls) // 20, 1)]
    summary = _base("distributional_stress_complete")
    summary.update({
        "path_count": len(pnls),
        "horizon_days": HORIZON_DAYS,
        "bootstrap": f"stationary_block_mean_len_{MEAN_BLOCK_LENGTH}_joint_across_symbols",
        "return_window_years": RETURN_WINDOW_YEARS,
        "seed": SIMULATION_SEED,
        "open_positions": len(positions),
        "book_entry_premium_units": round(premium, 6),
        "pnl_p05": pnls[int(0.05 * len(pnls))],
        "pnl_median": pnls[len(pnls) // 2],
        "pnl_p95": pnls[int(0.95 * len(pnls))],
        "expected_shortfall_5pct": round(sum(tail) / len(tail), 6),
        "prob_book_loss_exceeds_30pct_premium": round(sum(1 for value in pnls if value < -BOOK_LOSS_ALARM_PCT * premium) / len(pnls), 4),
        "risk_free_rate": risk_free,
        "risk_free_source": risk_free_source,
        "iv_treatment": f"held_at_current_iv_x{HIGH_VOL_IV_BUMP}_on_stressed_decile_paths_documented_simplification",
        "named_scenarios": run_named_scenarios(positions, returns, risk_free),
    })
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    write_json_atomic(SIMULATION_PATH, summary)
    return summary


def _base(status: str) -> dict[str, Any]:
    return {
        "artifact_type": "distributional_stress_summary",
        "simulation_status": status,
        "evidence_class": "simulation_only_resampled_from_real_history",
        "synthetic_resampled_from_real": True,
        "not_edge_evidence": True,
        "strategy_promotion_allowed": False,
        "informs": "risk_sizing_only_can_argue_for_smaller_never_for_readier",
        "paper_only": True,
        "live_blocked": True,
    }
