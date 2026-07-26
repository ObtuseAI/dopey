"""Dopey pipeline paper fill simulator: deterministic simulated paper fill via PaperBroker.

Wraps dopey_execution.PaperBroker to produce a richer deterministic paper fill record without
implying real market execution quality. No live broker is ever involved. Returns a structured
fill record.

Restored behavior: fills are priced with the dynamic regime/contract-aware slippage model
(dopey_execution.slippage_model), replacing the old fixed 0.2% heuristic. `fill_context`
carries {regime_tag, strategy_family, structure_type, leg_count, microstructure_context}
so bad-fill regimes and fragile structures degrade the simulated fill deterministically.
"""
from __future__ import annotations

from dopey_execution.paper_broker import PaperBroker
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.slippage_model import build_slippage_input_from_leg, estimate_slippage


DETERMINISTIC_TIMESTAMP = "2024-01-02T14:30:00Z"


def simulate_paper_fill(broker: PaperBroker, intent: ExecutionIntent,
                        chain_mids: dict[str, float], timestamp: str = DETERMINISTIC_TIMESTAMP,
                        fill_context: dict | None = None) -> dict:
    """Simulate a paper fill deterministically via the dynamic slippage model
    (buy legs slip up toward ask, sell legs slip down toward bid). Returns a structured record.

    `chain_mids` maps leg symbol -> fixture mid price (the expected/reference mid).
    `fill_context` optionally carries regime/family/structure context for the slippage model.
    """
    if intent.live_allowed:
        from dopey_execution.errors import LiveTradingDisabledError
        raise LiveTradingDisabledError("simulate_paper_fill refuses live_allowed intents")
    placement = broker.place_order(intent)
    if not placement.get("ok"):
        return {"ok": False, "errors": placement.get("errors", []), "paper": True}

    context = dict(fill_context or {})
    context.setdefault("structure_type", intent.structure)
    context.setdefault("leg_count", len(intent.legs))

    filled_legs = []
    total_fill = 0.0
    expected_total = 0.0
    slippage_pcts: list[float] = []
    fill_qualities: list[float] = []
    liquidity_scores: list[float] = []
    worst_verdict = "excellent"
    verdict_rank = {"excellent": 0, "good": 1, "acceptable": 2, "fragile": 3, "poor": 4, "reject": 5}
    for leg in intent.legs:
        sym = leg.get("symbol", "")
        mid = chain_mids.get(sym, leg.get("mid", 0.0))
        side = leg.get("side", "buy")
        liquidity = float(leg.get("liquidity_score", leg.get("liquidity", context.get("liquidity_score", 0.5))))
        quote_stability = float(leg.get("quote_stability_score", context.get("quote_stability_score", 0.5)))
        model_leg = dict(leg)
        model_leg.setdefault("mid", mid)
        model_leg["side"] = side
        result = estimate_slippage(build_slippage_input_from_leg(
            model_leg, liquidity, quote_stability, context))
        slip = round(mid * result.expected_slippage_pct, 6)
        if side == "buy":
            fill_price = round(mid + slip, 6)
        else:
            fill_price = round(max(0.01, mid - slip), 6)
        slippage_pcts.append(result.expected_slippage_pct)
        fill_qualities.append(result.fill_quality_score)
        liquidity_scores.append(liquidity)
        if verdict_rank.get(result.slippage_verdict, 5) > verdict_rank.get(worst_verdict, 0):
            worst_verdict = result.slippage_verdict
        filled_legs.append({
            "side": side, "symbol": sym, "strike": leg.get("strike"),
            "expiry": leg.get("expiry"), "option_type": leg.get("option_type"),
            "requested_mid": mid, "simulated_fill_price": fill_price,
            "simulated_slippage": round(fill_price - mid, 6) if side == "buy" else round(mid - fill_price, 6),
            "expected_slippage_pct": result.expected_slippage_pct,
            "fill_quality_score": result.fill_quality_score,
            "slippage_verdict": result.slippage_verdict,
        })
        if side == "buy":
            total_fill += fill_price
            expected_total += mid
        else:
            total_fill -= fill_price
            expected_total -= mid

    net_fill = round(total_fill * intent.quantity, 6)
    net_expected = round(expected_total * intent.quantity, 6)
    simulated_slippage = round(net_fill - net_expected, 6)
    leg_count = max(1, len(filled_legs))
    return {
        "ok": True,
        "order_id": placement.get("order_id", "paper-?"),
        "strategy_id": intent.strategy_id,
        "symbol": intent.symbol,
        "legs": filled_legs,
        "requested_net_price": net_expected,
        "simulated_fill_price": net_fill,
        "simulated_slippage": simulated_slippage,
        "expected_slippage_pct": round(sum(slippage_pcts) / leg_count, 6),
        "fill_quality_score": round(sum(fill_qualities) / leg_count, 6),
        "liquidity_score": round(sum(liquidity_scores) / leg_count, 6),
        "slippage_verdict": worst_verdict,
        "timestamp": timestamp,
        "paper_only": True,
        "paper": True,
        "live": False,
    }
