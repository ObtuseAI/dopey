"""Dopey family-aware paper structure builder (offline, deterministic, paper-only).

Constructs different defined-risk paper ExecutionIntents per strategy family so the
multi-strategy tournament produces differentiated replay outcomes. Every structure is
defined-risk (no naked / undefined-risk selling). All intents are live_allowed=False and
paper=True by construction; the LiveOrderGate / PaperBroker refuse anything else.

Family -> structure mapping:
  directional_convexity      -> long call vertical (bullish regimes) / long put vertical (bearish)
  volatility_expansion       -> long strangle (buy OTM call + buy OTM put)
  volatility_compression     -> iron condor (defined-risk credit pair)
  short_duration_defined_risk-> call butterfly (defined-risk debit)
  <unknown>                  -> long call vertical (legacy default)
"""
from __future__ import annotations

from dopey_execution.execution_intent import ExecutionIntent
from dopey_options.structure_builder import build_structure_for_family
from dopey_strategy_lab.strategy_genome import StrategyGenome

from .family_outcome import BEARISH_REGIMES


def _by_strike_and_type(ranked: list[dict], option_type: str, strike: float) -> dict | None:
    for r in ranked:
        if r.get("option_type") == option_type and abs(float(r.get("strike", 0.0)) - strike) < 1e-9:
            return r
    # fall back to nearest of that type
    cands = [r for r in ranked if r.get("option_type") == option_type]
    if not cands:
        return None
    cands.sort(key=lambda r: abs(float(r.get("strike", 0.0)) - strike))
    return cands[0]


def _leg_dict(c: dict, side: str, ratio: float = 1.0) -> dict:
    mid = float(c.get("mid", 0.0))
    return {
        "side": side,
        "symbol": c["symbol"],
        "strike": float(c["strike"]),
        "expiry": c.get("expiry", ""),
        "option_type": c.get("option_type", "call"),
        "mid": mid,
        "bid": float(c.get("bid", mid)),
        "ask": float(c.get("ask", mid)),
        "volume": int(c.get("volume", 0)),
        "open_interest": int(c.get("open_interest", 0)),
        "spread_pct": float(c.get("spread_pct", 0.0)),
        "liquidity_score": float(c.get("liquidity", 0.0)),
        "liquidity_verdict": c.get("liquidity_verdict", ""),
        "quote_stability_score": float(c.get("quote_stability_score", 0.5)),
        "fillability_score": float(c.get("fillability_score", 0.5)),
        "depth_proxy_score": float(c.get("depth_proxy_score", 0.0)),
        "slippage_sensitivity_score": float(c.get("expected_slippage_pct", 0.0)),
        "delta": float(c.get("delta", 0.0)),
        "gamma": float(c.get("gamma", 0.0)),
        "theta": float(c.get("theta", 0.0)),
        "vega": float(c.get("vega", 0.0)),
        "rho": float(c.get("rho", 0.0)),
        "iv": float(c.get("iv", 0.0)),
        "ratio": ratio,
    }


def _strikes(ranked: list[dict]) -> tuple[float, float, float]:
    """Return (low, mid, high) strike triple from the ranked chain."""
    strikes = sorted({round(float(r.get("strike", 0.0)), 6) for r in ranked})
    if len(strikes) >= 3:
        return strikes[0], strikes[len(strikes) // 2], strikes[-1]
    if len(strikes) == 2:
        lo, hi = strikes
        return lo, round((lo + hi) / 2.0, 6), hi
    s = strikes[0] if strikes else 450.0
    return s - 10.0, s, s + 10.0


def _directional(genome: StrategyGenome, symbol: str, ranked: list[dict],
                 regime_tag: str, promotion_decision: dict, proof: dict) -> tuple[ExecutionIntent, str]:
    lo, mid, hi = _strikes(ranked)
    bearish = regime_tag in BEARISH_REGIMES
    if bearish:
        # long put vertical: buy mid-strike put, sell low-strike put
        buy = _by_strike_and_type(ranked, "put", mid) or _by_strike_and_type(ranked, "put", lo)
        sell = _by_strike_and_type(ranked, "put", lo) or buy
        structure = "vertical"
    else:
        # long call vertical: buy mid-strike call, sell high-strike call
        buy = _by_strike_and_type(ranked, "call", mid) or _by_strike_and_type(ranked, "call", lo)
        sell = _by_strike_and_type(ranked, "call", hi) or buy
        structure = "vertical"
    if buy is None or sell is None or buy is sell:
        # ultimate fallback: first two calls
        calls = [r for r in ranked if r.get("option_type") == "call"]
        calls.sort(key=lambda r: float(r.get("strike", 0.0)))
        buy, sell = calls[0], calls[1]
    width = abs(float(buy["strike"]) - float(sell["strike"]))
    net_debit = round(max(0.0, float(buy.get("mid", 0.0)) - float(sell.get("mid", 0.0))), 6)
    max_loss = round(net_debit, 6)
    target_profit = round(max(0.0, width - net_debit), 6)
    legs = [_leg_dict(buy, "buy"), _leg_dict(sell, "sell")]
    intent = ExecutionIntent(
        intent_id=f"paper-intent-{genome.genome_id}",
        symbol=symbol, structure=structure, legs=legs, quantity=1,
        defined_risk=True, live_allowed=False, paper=True, broker_preference="paper",
        strategy_id=genome.genome_id, max_loss=max_loss or 0.01, target_profit=target_profit,
        invalidation_rule=genome.parameters.get("invalidation_rule", ""),
        proof_score=proof.get("proof_strength", 0.0),
        aggression_tier=promotion_decision.get("decision", "rejected"),
    )
    return intent, structure


def _volatility_expansion(genome: StrategyGenome, symbol: str, ranked: list[dict],
                          promotion_decision: dict, proof: dict) -> tuple[ExecutionIntent, str]:
    lo, mid, hi = _strikes(ranked)
    call = _by_strike_and_type(ranked, "call", hi) or _by_strike_and_type(ranked, "call", mid)
    put = _by_strike_and_type(ranked, "put", lo) or _by_strike_and_type(ranked, "put", mid)
    if call is None or put is None:
        calls = [r for r in ranked if r.get("option_type") == "call"]
        puts = [r for r in ranked if r.get("option_type") == "put"]
        call, put = calls[0], puts[0]
    net_debit = round(float(call.get("mid", 0.0)) + float(put.get("mid", 0.0)), 6)
    legs = [_leg_dict(call, "buy"), _leg_dict(put, "buy")]
    intent = ExecutionIntent(
        intent_id=f"paper-intent-{genome.genome_id}", symbol=symbol, structure="strangle",
        legs=legs, quantity=1, defined_risk=True, live_allowed=False, paper=True,
        broker_preference="paper", strategy_id=genome.genome_id,
        max_loss=net_debit or 0.01, target_profit=round(net_debit * 2.0, 6),
        invalidation_rule=genome.parameters.get("invalidation_rule", ""),
        proof_score=proof.get("proof_strength", 0.0),
        aggression_tier=promotion_decision.get("decision", "rejected"),
    )
    return intent, "strangle"


def _volatility_compression(genome: StrategyGenome, symbol: str, ranked: list[dict],
                            promotion_decision: dict, proof: dict) -> tuple[ExecutionIntent, str]:
    lo, mid, hi = _strikes(ranked)
    # iron condor: sell mid call, buy hi call, sell mid put, buy lo put (defined-risk credit)
    short_call = _by_strike_and_type(ranked, "call", mid)
    long_call = _by_strike_and_type(ranked, "call", hi)
    short_put = _by_strike_and_type(ranked, "put", mid)
    long_put = _by_strike_and_type(ranked, "put", lo)
    if not all([short_call, long_call, short_put, long_put]):
        # fallback to a single vertical (still defined-risk)
        return _directional(genome, symbol, ranked, "chop_vol_compression", promotion_decision, proof)
    call_credit = float(short_call.get("mid", 0.0)) - float(long_call.get("mid", 0.0))
    put_credit = float(short_put.get("mid", 0.0)) - float(long_put.get("mid", 0.0))
    credit = round(max(0.0, call_credit + put_credit), 6)
    width = abs(float(long_call["strike"]) - float(short_call["strike"]))
    max_loss = round(max(0.01, width - credit), 6)
    legs = [
        _leg_dict(short_call, "sell"),
        _leg_dict(long_call, "buy"),
        _leg_dict(short_put, "sell"),
        _leg_dict(long_put, "buy"),
    ]
    intent = ExecutionIntent(
        intent_id=f"paper-intent-{genome.genome_id}", symbol=symbol, structure="iron_condor",
        legs=legs, quantity=1, defined_risk=True, live_allowed=False, paper=True,
        broker_preference="paper", strategy_id=genome.genome_id,
        max_loss=max_loss, target_profit=round(credit, 6),
        invalidation_rule=genome.parameters.get("invalidation_rule", ""),
        proof_score=proof.get("proof_strength", 0.0),
        aggression_tier=promotion_decision.get("decision", "rejected"),
    )
    return intent, "iron_condor"


def _short_duration(genome: StrategyGenome, symbol: str, ranked: list[dict],
                    promotion_decision: dict, proof: dict) -> tuple[ExecutionIntent, str]:
    lo, mid, hi = _strikes(ranked)
    c_lo = _by_strike_and_type(ranked, "call", lo)
    c_mid = _by_strike_and_type(ranked, "call", mid)
    c_hi = _by_strike_and_type(ranked, "call", hi)
    if not all([c_lo, c_mid, c_hi]):
        return _directional(genome, symbol, ranked, "bullish_breakout", promotion_decision, proof)
    # call butterfly: buy lo call, sell 2x mid call, buy hi call (defined-risk debit)
    net_debit = round(
        float(c_lo.get("mid", 0.0)) - 2.0 * float(c_mid.get("mid", 0.0)) + float(c_hi.get("mid", 0.0)),
        6)
    net_debit = max(0.01, net_debit)
    width = abs(float(c_mid["strike"]) - float(c_lo["strike"]))
    legs = [
        _leg_dict(c_lo, "buy"),
        _leg_dict(c_mid, "sell", ratio=2.0),
        _leg_dict(c_hi, "buy"),
    ]
    intent = ExecutionIntent(
        intent_id=f"paper-intent-{genome.genome_id}", symbol=symbol, structure="butterfly",
        legs=legs, quantity=1, defined_risk=True, live_allowed=False, paper=True,
        broker_preference="paper", strategy_id=genome.genome_id,
        max_loss=net_debit, target_profit=round(width, 6),
        invalidation_rule=genome.parameters.get("invalidation_rule", ""),
        proof_score=proof.get("proof_strength", 0.0),
        aggression_tier=promotion_decision.get("decision", "rejected"),
    )
    return intent, "butterfly"


def _with_entry_net(intent: ExecutionIntent, entry_net: float) -> ExecutionIntent:
    """Deprecated no-op; entry net is recovered via entry_net_from_intent by the replay engine."""
    return intent


def build_family_intent(genome: StrategyGenome, symbol: str, ranked: list[dict],
                        regime_tag: str, promotion_decision: dict,
                        proof: dict) -> tuple[ExecutionIntent, str]:
    """Build a family-specific paper ExecutionIntent. Returns (intent, structure_name).

    Always live_allowed=False, paper=True, defined_risk=True. Unknown families fall back to a
    long-call vertical (legacy behavior)."""
    build_result = build_structure_for_family(
        genome.family,
        symbol,
        ranked,
        regime_tag,
        dict(genome.parameters),
    )
    if not build_result.ok or build_result.structure is None:
        raise ValueError(f"failed to build defined-risk paper structure: {build_result.rejection_reason}")
    risk = build_result.risk_summary
    structure = build_result.structure
    intent = ExecutionIntent(
        intent_id=f"paper-intent-{genome.genome_id}",
        symbol=symbol,
        structure=structure.execution_structure,
        legs=[leg.to_dict() for leg in structure.legs],
        quantity=1,
        defined_risk=True,
        live_allowed=False,
        paper=True,
        broker_preference="paper",
        strategy_id=genome.genome_id,
        max_loss=risk.max_loss or 0.01,
        target_profit=risk.max_reward,
        invalidation_rule=genome.parameters.get("invalidation_rule", ""),
        proof_score=proof.get("proof_strength", 0.0),
        aggression_tier=promotion_decision.get("decision", "rejected"),
    )
    intent.structure_build_result = build_result.to_dict()
    return intent, structure.execution_structure


def entry_net_from_intent(intent: ExecutionIntent) -> float:
    """Recover the signed entry net used by the outcome model.

    Convention: for debit structures returns the net debit paid (>=0); for credit structures
    (iron_condor) returns the net credit received (>=0). The outcome model uses this consistently.
    """
    structure = intent.structure
    debit = 0.0
    for leg in intent.legs:
        mid = float(leg.get("mid", 0.0))
        ratio = float(leg.get("ratio", 1.0))
        if leg.get("side") == "buy":
            debit += mid * ratio
        else:
            debit -= mid * ratio
    if structure == "iron_condor":
        # credit received = -debit (sell premiums exceed buy premiums)
        return round(max(0.0, -debit), 6)
    return round(max(0.0, debit), 6)
