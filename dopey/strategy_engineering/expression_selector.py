"""Release-Angle Selector: the same throw from any platform (Mahomes' arm talent).

DOPEY expresses every directional thesis exactly one way: an ATM ~30DTE single
leg. Mahomes' signature is that when the standard platform is obstructed he
changes the release - sidearm, off-platform, different arm angle - and still
makes the throw. The options analogue: the SAME underlying thesis can be
expressed across a grid of (DTE x moneyness), and each cell pays a different
mix of theta, spread tax, and leverage. A thesis that dies at one release angle
might (or might not) clear the cost line at another.

This sweeps the expression grid with the real deterministic pricing kernel and
the documented cost stack and answers, per cell: what favorable underlying move
breaks even, and what is the net option return at a given edge? Then the honest
headline: does ANY release angle let this edge survive?

Assumption note: costs are the documented flat percent-of-premium stack. For
deep-ITM options, real half-spreads as a fraction of premium are typically
SMALLER than for ATM, so the model is conservative toward ITM cells - a cell
that survives here likely survives reality; a cell that fails here might
still fail by less.

Measure-only: it ranks expressions, it never sizes, orders, or promotes.
"""
from __future__ import annotations

from typing import Any

from .option_expression_cost import breakeven_move, net_return_for_move

SELECTOR_VERSION = "dopey-expression-selector-v1"

# The release-angle grid: DTE x moneyness (strike as a fraction of spot for a
# CALL; the put grid mirrors by symmetry of the model's flat-vol pricing).
DTE_GRID = (14, 30, 60, 90)
# moneyness < 1.0 is ITM for a call (strike below spot); > 1.0 is OTM.
MONEYNESS_GRID = (0.90, 0.95, 1.00, 1.05)
HORIZON_DAYS = 5


def evaluate_expression_grid(
    underlying_excess: float,
    iv: float = 0.30,
    option_type: str = "call",
) -> dict[str, Any]:
    """Sweep the grid; per cell report breakeven and net return at the excess."""
    magnitude = abs(float(underlying_excess))
    cells: list[dict[str, Any]] = []
    for dte in DTE_GRID:
        for moneyness in MONEYNESS_GRID:
            strike = 100.0 * moneyness
            try:
                net = net_return_for_move(
                    magnitude, spot=100.0, iv=iv, dte_days=dte,
                    horizon_days=HORIZON_DAYS, option_type=option_type,
                    strike=strike,
                )
                breakeven = breakeven_move(
                    spot=100.0, iv=iv, dte_days=dte, horizon_days=HORIZON_DAYS,
                    option_type=option_type, strike=strike,
                )
            except Exception as error:  # noqa: BLE001 - a degenerate cell must not kill the sweep
                cells.append({
                    "dte_days": dte, "moneyness": moneyness,
                    "cell_status": f"unpriceable:{type(error).__name__}",
                })
                continue
            cells.append({
                "dte_days": dte,
                "moneyness": moneyness,
                "leg": (
                    "itm" if (moneyness < 1.0) == (option_type == "call") and moneyness != 1.0
                    else "atm" if moneyness == 1.0 else "otm"
                ),
                "breakeven_underlying_move": breakeven,
                "net_return_at_excess": round(net, 6),
                "survives": bool(net > 0.0),
                "cell_status": "priced",
            })
    priced = [c for c in cells if c.get("cell_status") == "priced"]
    surviving = [c for c in priced if c["survives"]]
    best = max(priced, key=lambda c: c["net_return_at_excess"]) if priced else None
    return {
        "artifact_type": "expression_grid_evaluation",
        "selector_version": SELECTOR_VERSION,
        "underlying_excess_magnitude": round(magnitude, 6),
        "implied_vol": iv,
        "option_type": option_type,
        "horizon_days": HORIZON_DAYS,
        "cells": cells,
        "any_expression_survives": bool(surviving),
        "surviving_cells": [
            {"dte_days": c["dte_days"], "moneyness": c["moneyness"], "net": c["net_return_at_excess"]}
            for c in sorted(surviving, key=lambda c: -c["net_return_at_excess"])
        ],
        "best_release_angle": (
            {"dte_days": best["dte_days"], "moneyness": best["moneyness"],
             "net_return_at_excess": best["net_return_at_excess"],
             "breakeven_underlying_move": best["breakeven_underlying_move"]}
            if best else None
        ),
        "headline": (
            f"{len(surviving)}/{len(priced)} release angles survive this edge"
            if priced else "grid unpriceable"
        ),
        "cost_model_note": (
            "flat percent-of-premium costs are conservative toward ITM cells "
            "(real ITM spreads are typically a smaller premium fraction)"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
