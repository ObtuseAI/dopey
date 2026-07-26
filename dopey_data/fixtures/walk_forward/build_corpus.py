"""Deterministic generator for the expanded DOPEY regime fixture corpus.

Produces 12 walk-forward windows (window_001..window_012) + 12 matching analysis-context
fixtures under this directory. Pure deterministic engineering fixtures — NO real data,
NO network. Run:  python -m dopey_data.fixtures.walk_forward.build_corpus
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent

# (regime_tag, window_type, next_price_move_pct, iv_effect, liquidity_quality,
#  spread_penalty, slippage_penalty, macro_contradiction, technical_fakeout,
#  pattern_confidence, invalidation_quality, direction, vol_bias, exit_reason, notes)
REGIMES = [
    ("trend_vol_expansion", "train", +1.6, +0.30, 0.82, 0.05, 0.08, 0.10, 0.20, 0.72, 0.65, "bull", "expansion", "target_profit_reached", "train: risk-on uptrend + vol expansion favors long convexity"),
    ("chop_vol_compression", "train", +0.1, -0.20, 0.80, 0.06, 0.07, 0.15, 0.30, 0.55, 0.60, "neutral", "compression", "expiry_time_decay", "train: chop + IV compression favors defined-risk compression"),
    ("gap_reversal", "train", -0.3, +0.10, 0.70, 0.10, 0.12, 0.20, 0.55, 0.45, 0.50, "neutral", "expansion", "invalidation_triggered", "train: gap fades and reverses; punishes short-duration directional"),
    ("liquidity_decay", "train", -0.4, -0.05, 0.45, 0.20, 0.22, 0.25, 0.35, 0.40, 0.45, "bear", "neutral", "invalidation_triggered", "train: liquidity decays through session; long vol suffers"),
    ("event_vol_expansion", "validation", +2.2, +0.45, 0.65, 0.12, 0.15, 0.30, 0.40, 0.60, 0.50, "bull", "expansion", "target_profit_reached", "validation: event shock expands IV; long strangle wins"),
    ("post_event_iv_crush", "validation", +0.2, -0.35, 0.72, 0.08, 0.10, 0.15, 0.25, 0.55, 0.60, "neutral", "compression", "expiry_time_decay", "validation: IV crush after event; compression structures win"),
    ("bearish_breakdown", "validation", -2.0, +0.20, 0.78, 0.06, 0.08, 0.12, 0.20, 0.68, 0.62, "bear", "expansion", "target_profit_reached", "validation: bearish breakdown; long put vertical wins"),
    ("bullish_breakout", "validation", +2.4, +0.18, 0.83, 0.05, 0.07, 0.08, 0.18, 0.75, 0.66, "bull", "expansion", "target_profit_reached", "validation: clean bullish breakout; call vertical + short-DTE win"),
    ("range_bound_pin", "validation", +0.0, -0.15, 0.81, 0.06, 0.07, 0.12, 0.28, 0.58, 0.62, "neutral", "compression", "expiry_time_decay", "validation: pin to mid; iron condor wins"),
    ("high_spread_bad_fill", "holdout", +0.5, +0.05, 0.30, 0.55, 0.50, 0.20, 0.45, 0.35, 0.30, "neutral", "neutral", "invalidation_triggered", "holdout: wide spreads + bad fills punish all, short-DTE worst"),
    ("low_liquidity_decay", "holdout", -0.2, -0.08, 0.25, 0.45, 0.48, 0.30, 0.50, 0.30, 0.28, "bear", "neutral", "invalidation_triggered", "holdout: thin book decays; short-DTE defined-risk punished"),
    ("macro_shock_risk_off", "holdout", -2.6, +0.50, 0.55, 0.18, 0.20, 0.40, 0.35, 0.50, 0.40, "bear", "expansion", "invalidation_triggered", "holdout: macro shock risk-off; long vol expansion wins, compression loses"),
]

FAMILIES = ["directional_convexity", "volatility_expansion", "volatility_compression", "short_duration_defined_risk"]

# family hints per regime (must match dopey_walk_forward.family_outcome.REGIME_FAMILY_HINTS)
HINTS = {
    "trend_vol_expansion":      [0.80, 0.80, 0.20, 0.65],
    "chop_vol_compression":     [0.25, 0.20, 0.85, 0.40],
    "gap_reversal":             [0.30, 0.55, 0.45, 0.20],
    "liquidity_decay":          [0.40, 0.25, 0.40, 0.30],
    "event_vol_expansion":      [0.45, 0.90, 0.15, 0.30],
    "post_event_iv_crush":      [0.40, 0.15, 0.85, 0.40],
    "bearish_breakdown":        [0.80, 0.60, 0.20, 0.55],
    "bullish_breakout":         [0.85, 0.60, 0.20, 0.70],
    "range_bound_pin":          [0.20, 0.25, 0.85, 0.40],
    "high_spread_bad_fill":     [0.25, 0.25, 0.40, 0.15],
    "low_liquidity_decay":      [0.30, 0.25, 0.40, 0.15],
    "macro_shock_risk_off":     [0.40, 0.85, 0.15, 0.30],
}

S0 = 450.0
STRIKES = [440.0, 450.0, 460.0]
EXPIRY = "2024-01-19"


def _contract(strike, otype, iv, spread_pct, vol, oi):
    # deterministic mid table around S0=450 (fixture, not market data)
    base = {
        ("call", 440.0): 13.40, ("call", 450.0): 8.25, ("call", 460.0): 4.50,
        ("put", 440.0): 3.25, ("put", 450.0): 7.05, ("put", 460.0): 12.10,
    }[(otype, strike)]
    # scale by iv relative to 0.18 baseline (vega-ish): higher iv -> higher premium for OTM
    iv_scale = 1.0 + (iv - 0.18) * 1.5
    mid = round(max(0.05, base * iv_scale), 2)
    half = round(max(0.02, mid * spread_pct / 2.0), 2)
    bid = round(max(0.01, mid - half), 2)
    ask = round(mid + half, 2)
    delta = {
        ("call", 440.0): 0.72, ("call", 450.0): 0.52, ("call", 460.0): 0.34,
        ("put", 440.0): -0.28, ("put", 450.0): -0.48, ("put", 460.0): -0.68,
    }[(otype, strike)]
    return {
        "symbol": f"SPYFIX240119{otype[0].upper()}{int(strike*1000):08d}",
        "underlying_symbol": "SPY_FIXTURE",
        "option_type": otype,
        "strike": strike,
        "expiry": EXPIRY,
        "bid": bid, "ask": ask, "last": mid,
        "volume": vol, "open_interest": oi,
        "iv": round(iv, 4),
        "delta": delta, "gamma": 0.022, "theta": -0.12, "vega": 0.23, "rho": 0.06,
        "defined_risk": True,
    }


def _chain(iv, spread_pct, vol, oi):
    contracts = []
    for otype in ("call", "put"):
        for k in STRIKES:
            v = vol if otype == "call" else int(vol * 0.8)
            o = oi if otype == "call" else int(oi * 0.75)
            contracts.append(_contract(k, otype, iv, spread_pct, v, o))
    return {"underlying": {"symbol": "SPY_FIXTURE", "asset_class": "equity", "price": S0, "currency": "USD"},
            "as_of": "2024-01-02T14:30:00Z", "contracts": contracts}


def _analysis(regime, iv_effect, liq, spread, slip, macro_con, fakeout, pat_conf, direction, vol_bias):
    risk_on = {"bull": 0.82, "bear": 0.25, "neutral": 0.5}[direction]
    event_risk = 0.75 if "event" in regime or "shock" in regime else 0.18
    return {
        "macro": {"regime_tag": regime, "risk_on_score": risk_on,
                  "volatility_regime_score": round(min(1.0, 0.5 + iv_effect), 4),
                  "event_risk_score": event_risk, "sector_rotation_score": round(risk_on * 0.9, 4),
                  "breadth_score": round(risk_on * 0.95, 4), "liquidity_regime_score": round(liq, 4),
                  "notes": f"{regime}: deterministic macro placeholder (no real data)"},
        "microstructure": {"spread_quality_score": round(1.0 - spread, 4), "liquidity_score": round(liq, 4),
                           "slippage_sensitivity_score": round(slip, 4), "volume_oi_anomaly_score": round(1.0 - liq, 4),
                           "quote_stability_score": round(1.0 - slip, 4), "contract_fillability_score": round(liq * 0.9, 4),
                           "notes": f"{regime}: deterministic microstructure placeholder"},
        "technical": {"trend_score": round(risk_on, 4), "momentum_score": round(risk_on * 0.95, 4),
                      "realized_volatility_score": round(min(1.0, 0.4 + iv_effect), 4),
                      "breakout_score": round(0.7 if "breakout" in regime or "trend" in regime else 0.3, 4),
                      "fakeout_risk_score": round(fakeout, 4), "support_resistance_score": 0.6,
                      "volume_confirmation_score": round(liq * 0.9, 4), "gap_behavior_score": round(1.0 - fakeout, 4),
                      "notes": f"{regime}: deterministic technical placeholder"},
        "fundamental": {"earnings_risk_score": round(event_risk, 4), "filing_event_score": 0.1,
                        "valuation_context_score": round(risk_on, 4), "growth_quality_score": round(risk_on * 0.9, 4),
                        "analyst_revision_score": round(risk_on * 0.85, 4), "sector_peer_score": 0.6,
                        "fundamental_support_score": round(risk_on * 0.9, 4),
                        "notes": f"{regime}: deterministic fundamental placeholder"},
        "patterns": [
            {"pattern_id": f"p-{regime}-dir", "pattern_type": f"{direction}_directional",
             "confidence": round(pat_conf, 4), "directional_bias": direction,
             "volatility_bias": vol_bias, "regime_dependency": regime,
             "failure_mode": "fakeout" if fakeout > 0.4 else "", "notes": "deterministic placeholder"},
        ],
    }


def build():
    for i, spec in enumerate(REGIMES, start=1):
        (regime, wtype, move_pct, iv_eff, liq, spread, slip, macro_con, fakeout,
         pat_conf, inval, direction, vol_bias, exit_reason, notes) = spec
        seq = i
        ts = f"2024-01-{i:02d}T14:30:00Z"
        next_price = round(S0 * (1.0 + move_pct / 100.0), 2)
        iv = round(0.18 + iv_eff * 0.2, 4)  # entry IV
        next_iv = round(max(0.05, iv + iv_eff * 0.15), 4)
        # liquidity-driven OI/volume
        oi = int(5000 + liq * 40000)
        vol = int(800 + liq * 9000)
        spread_pct = round(0.02 + spread, 4)
        chain = _chain(iv, spread_pct, vol, oi)
        hints = {fam: HINTS[regime][j] for j, fam in enumerate(FAMILIES)}
        regime_context = {
            "liquidity_quality": round(liq, 4),
            "spread_penalty": round(spread, 4),
            "slippage_penalty": round(slip, 4),
            "iv_effect": round(iv_eff, 4),
            "macro_contradiction": round(macro_con, 4),
            "technical_fakeout": round(fakeout, 4),
            "pattern_confidence": round(pat_conf, 4),
            "invalidation_quality": round(inval, 4),
            "direction": direction,
            "vol_bias": vol_bias,
        }
        window = {
            "window_id": f"window_{i:03d}_{wtype}",
            "window_type": wtype,
            "timestamp": ts,
            "sequence_id": seq,
            "regime_tag": regime,
            "underlying_snapshot": {"symbol": "SPY_FIXTURE", "asset_class": "equity",
                                    "price": S0, "currency": "USD", "prev_close": round(S0 - 0.5, 2),
                                    "realized_vol_20d": round(iv, 4), "regime_score": round(liq, 4)},
            "option_chain": chain,
            "expected_outcome": {
                "next_underlying_price": next_price,
                "next_iv": next_iv,
                "days_to_exit": 3 if wtype == "holdout" else 5,
                "exit_reason": exit_reason,
                "favorable_move": round(abs(move_pct), 4),
                "adverse_move_pct": round(-abs(move_pct) * 0.4, 4) if direction == "bull" else round(abs(move_pct), 4),
                "notes": notes,
            },
            "family_outcome_hints": hints,
            "regime_context": regime_context,
            "notes": notes,
        }
        wf = OUT / f"window_{i:03d}_{wtype}.json"
        wf.write_text(json.dumps(window, indent=2), encoding="utf-8")
        af = OUT / f"window_{i:03d}_{wtype}_analysis.json"
        af.write_text(json.dumps(_analysis(regime, iv_eff, liq, spread, slip, macro_con, fakeout,
                                           pat_conf, direction, vol_bias), indent=2), encoding="utf-8")
    print(f"wrote {len(REGIMES)} windows + analysis fixtures to {OUT}")


if __name__ == "__main__":
    build()
