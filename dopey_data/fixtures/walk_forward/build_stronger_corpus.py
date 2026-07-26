"""Deterministic generator for the additional DOPEY walk-forward windows
(Workstream B of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`).

Produces windows 013..024 (12 additional windows) + 12 matching analysis-context
fixtures. NO real data, NO network. Run:
    python -m dopey_data.fixtures.walk_forward.build_stronger_corpus
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_walk_forward.split_builder import ADDITIONAL_WINDOW_TEMPLATES

OUT = Path(__file__).resolve().parent

S0 = 450.0
STRIKES = [440.0, 450.0, 460.0]
EXPIRY = "2024-01-19"

# Map our template sequence onto the next sequence_id block (13..24).
# sequence_id is computed as: existing 12 windows use 1..12; we extend with 13..24.
DEFAULT_TIMESTAMP = "2024-02-01T14:30:00Z"


def _contract(strike, otype, iv, spread_pct, vol, oi):
    base = {
        ("call", 440.0): 13.40, ("call", 450.0): 8.25, ("call", 460.0): 4.50,
        ("put", 440.0): 3.25, ("put", 450.0): 7.05, ("put", 460.0): 12.10,
    }[(otype, strike)]
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
    event_risk = 0.75 if "event" in regime or "shock" in regime or "macro" in regime else 0.18
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
                      "breakout_score": round(0.7 if "breakout" in regime or "trend" in regime or "expansion" in regime else 0.3, 4),
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


def _seq_id(window_id: str) -> int:
    """Extract the integer prefix from a window id like 'window_013_train' -> 13."""
    parts = window_id.split("_")
    for p in parts:
        if p.isdigit():
            return int(p)
    return 0


def _existing_count() -> int:
    """Count existing window JSON files in the corpus (window_NNN_*.json)."""
    return sum(1 for _ in OUT.glob("window_*_train.json")) + \
           sum(1 for _ in OUT.glob("window_*_validation.json")) + \
           sum(1 for _ in OUT.glob("window_*_holdout.json"))


def build() -> int:
    written = 0
    base_seq = _existing_count()  # next sequence id
    for i, template in enumerate(ADDITIONAL_WINDOW_TEMPLATES):
        seq = base_seq + i
        ts = f"2024-01-{seq:02d}T14:30:00Z"
        underlying = template["underlying"]
        expected = template["expected"]
        rc = template["regime_context"]
        regime = template["regime_tag"]
        wtype = template["window_type"]
        move_pct = (expected["next_underlying_price"] / S0 - 1.0) * 100.0
        iv = round(0.18 + rc["iv_effect"] * 0.2, 4)
        next_iv = round(max(0.05, iv + rc["iv_effect"] * 0.15), 4)
        liq = float(rc["liquidity_quality"])
        spread_pct = round(0.02 + float(rc["spread_penalty"]), 4)
        oi = int(5000 + liq * 40000)
        vol = int(800 + liq * 9000)
        chain = _chain(iv, spread_pct, vol, oi)
        window = {
            "window_id": template["window_id"],
            "window_type": wtype,
            "timestamp": ts,
            "sequence_id": seq,
            "regime_tag": regime,
            "underlying_snapshot": {"symbol": "SPY_FIXTURE", "asset_class": "equity",
                                    "price": S0, "currency": "USD",
                                    "prev_close": round(S0 - 0.5, 2),
                                    "realized_vol_20d": round(iv, 4), "regime_score": round(liq, 4)},
            "option_chain": chain,
            "expected_outcome": {
                "next_underlying_price": expected["next_underlying_price"],
                "next_iv": next_iv,
                "days_to_exit": expected.get("days_to_exit", 5),
                "exit_reason": expected.get("exit_reason", "expiry_time_decay"),
                "favorable_move": expected.get("favorable_move", 0.0),
                "adverse_move_pct": expected.get("adverse_move_pct", 0.0),
                "notes": template.get("notes", ""),
            },
            "family_outcome_hints": template["family_hints"],
            "regime_context": rc,
            "notes": template.get("notes", ""),
        }
        wf = OUT / f"{template['window_id']}.json"
        wf.write_text(json.dumps(window, indent=2), encoding="utf-8")
        af = OUT / f"{template['window_id']}_analysis.json"
        af.write_text(json.dumps(_analysis(regime, rc["iv_effect"], liq, rc["spread_penalty"],
                                            rc["slippage_penalty"], rc["macro_contradiction"],
                                            rc["technical_fakeout"], rc["pattern_confidence"],
                                            rc.get("direction", "neutral"),
                                            rc.get("vol_bias", "neutral")), indent=2), encoding="utf-8")
        written += 1
    print(f"wrote {written} additional windows + analysis fixtures to {OUT}")
    return written


if __name__ == "__main__":
    build()
