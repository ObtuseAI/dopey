"""Regime/holdout corpus v2 fixture persistence + summary (paper-only).

Workstream B + F of `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`.

The v2 corpus is built deterministically by `holdout_window_builder.build_regime_holdout_corpus_v2`
and persisted to `artifacts/dopey/regime_holdout_corpus_v2/` as JSONL records. Each window
gets its own fixture file plus a `_analysis.json` mirror for the analysis layer.

All output is fixture-only, paper-only, deterministic, and offline.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from dopey_options.ontology import OptionChain, OptionContract, Underlying
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .holdout_window_builder import (
    V2_WINDOW_TEMPLATES,
    build_regime_holdout_corpus_v2,
)
from .regime_holdout_models import (
    CORPUS_V2_VERSION,
    RegimeHoldoutCorpus,
    RegimeHoldoutWindow,
)


V2_CORPUS_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dopey" / "regime_holdout_corpus_v2"
V2_REGISTRY_PATH = V2_CORPUS_ARTIFACT_DIR / "corpus_registry.jsonl"
V2_REPLAY_PATH = V2_CORPUS_ARTIFACT_DIR / "corpus_v2_replay.jsonl"
V2_COVERAGE_PATH = V2_CORPUS_ARTIFACT_DIR / "corpus_coverage.jsonl"
V2_PROOF_PATH = V2_CORPUS_ARTIFACT_DIR / "corpus_v2_proof.jsonl"
V2_SUMMARY_PATH = V2_CORPUS_ARTIFACT_DIR / "corpus_v2_summary.md"
V2_FIXTURE_DIR = V2_CORPUS_ARTIFACT_DIR / "fixtures"

S0 = 450.0
STRIKES = [440.0, 450.0, 460.0]
EXPIRY = "2024-02-23"


def _build_chain(underlying: str, iv: float, spread_pct: float, volume: int, oi: int) -> OptionChain:
    contracts = []
    for otype in ("call", "put"):
        for k in STRIKES:
            v = volume if otype == "call" else int(volume * 0.8)
            o = oi if otype == "call" else int(oi * 0.75)
            base = {
                ("call", 440.0): 13.40, ("call", 450.0): 8.25, ("call", 460.0): 4.50,
                ("put", 440.0): 3.25, ("put", 450.0): 7.05, ("put", 460.0): 12.10,
            }[(otype, k)]
            iv_scale = 1.0 + (iv - 0.18) * 1.5
            mid = round(max(0.05, base * iv_scale), 2)
            half = round(max(0.02, mid * spread_pct / 2.0), 2)
            bid = round(max(0.01, mid - half), 2)
            ask = round(mid + half, 2)
            delta = {
                ("call", 440.0): 0.72, ("call", 450.0): 0.52, ("call", 460.0): 0.34,
                ("put", 440.0): -0.28, ("put", 450.0): -0.48, ("put", 460.0): -0.68,
            }[(otype, k)]
            contracts.append(OptionContract(
                symbol=f"V2FIX240223{otype[0].upper()}{int(k*1000):08d}",
                underlying_symbol=underlying,
                option_type=otype, strike=k, expiry=EXPIRY,
                bid=bid, ask=ask, last=mid, volume=v, open_interest=o,
                iv=round(iv, 4),
                delta=delta, gamma=0.022, theta=-0.12, vega=0.23, rho=0.06,
                defined_risk=True,
            ))
    return OptionChain(
        underlying=Underlying(symbol=underlying, asset_class="equity", price=S0, currency="USD"),
        as_of=f"2024-02-01T14:30:00Z",
        contracts=contracts,
    )


def _build_analysis(window: RegimeHoldoutWindow) -> dict:
    risk_on = 0.82 if window.macro_context.risk_on_off == "risk_on" else (
        0.25 if window.macro_context.risk_on_off == "risk_off" else 0.5
    )
    event_risk = 0.75 if any(k in window.macro_context.event_label for k in ("cpi", "fomc", "shock", "jobs", "dollar")) else 0.30
    return {
        "macro": {
            "regime_tag": window.regime_tag, "risk_on_score": risk_on,
            "volatility_regime_score": round(min(1.0, 0.5 + window.iv_surface_context.iv_effect_signed), 4),
            "event_risk_score": event_risk, "sector_rotation_score": round(risk_on * 0.9, 4),
            "breadth_score": round(risk_on * 0.95, 4), "liquidity_regime_score": round(window.liquidity_context.liquidity_quality, 4),
            "notes": f"{window.regime_tag}: deterministic v2 macro placeholder (no real data)",
        },
        "microstructure": {
            "spread_quality_score": round(1.0 - window.liquidity_context.spread_penalty, 4),
            "liquidity_score": round(window.liquidity_context.liquidity_quality, 4),
            "slippage_sensitivity_score": round(window.liquidity_context.slippage_penalty, 4),
            "volume_oi_anomaly_score": round(1.0 - window.liquidity_context.liquidity_quality, 4),
            "quote_stability_score": round(1.0 - window.liquidity_context.slippage_penalty, 4),
            "contract_fillability_score": round(window.liquidity_context.liquidity_quality * 0.9, 4),
            "notes": f"{window.regime_tag}: deterministic v2 microstructure placeholder",
        },
        "technical": {
            "trend_score": round(window.sector_context.sector_trend_score, 4),
            "momentum_score": round(window.sector_context.sector_trend_score * 0.95, 4),
            "realized_volatility_score": round(min(1.0, 0.4 + abs(window.iv_surface_context.iv_effect_signed)), 4),
            "breakout_score": round(0.7 if "breakout" in window.regime_tag or "expansion" in window.regime_tag else 0.3, 4),
            "fakeout_risk_score": round(window.iv_surface_context.surface_instability, 4),
            "support_resistance_score": 0.6,
            "volume_confirmation_score": round(window.liquidity_context.liquidity_quality * 0.9, 4),
            "gap_behavior_score": round(1.0 - window.iv_surface_context.surface_instability, 4),
            "notes": f"{window.regime_tag}: deterministic v2 technical placeholder",
        },
        "fundamental": {
            "earnings_risk_score": round(event_risk, 4),
            "filing_event_score": 0.1,
            "valuation_context_score": round(risk_on, 4),
            "growth_quality_score": round(risk_on * 0.9, 4),
            "analyst_revision_score": round(risk_on * 0.85, 4),
            "sector_peer_score": 0.6,
            "fundamental_support_score": round(risk_on * 0.9, 4),
            "notes": f"{window.regime_tag}: deterministic v2 fundamental placeholder",
        },
        "patterns": [dict(window.pattern_context, notes="deterministic v2 pattern placeholder")],
    }


def _fixture_dict(window: RegimeHoldoutWindow) -> dict:
    """Materialize a RegimeHoldoutWindow as a JSONL fixture dict (loadable by WalkForwardWindow-like model)."""
    # We deliberately emit a dict that matches the existing WalkForwardWindow schema,
    # so the walk-forward engine and audit can consume v2 windows directly.
    iv = max(0.05, 0.18 + window.iv_surface_context.iv_effect_signed * 0.2)
    next_iv = max(0.05, iv + window.iv_surface_context.iv_effect_signed * 0.15)
    liq = window.liquidity_context.liquidity_quality
    spread_pct = round(0.02 + window.liquidity_context.spread_penalty, 4)
    oi = int(5000 + liq * 40000)
    volume = int(800 + liq * 9000)
    chain = _build_chain("SPY_FIXTURE_V2", iv, spread_pct, volume, oi)
    # Derive a friendly regime tag and notes for the analysis layer.
    next_price = S0
    if window.sector_context.sector_trend_score > 0.55:
        next_price = S0 * 1.012
    elif window.sector_context.sector_trend_score < 0.40:
        next_price = S0 * 0.988
    return {
        "window_id": window.window_id,
        "window_type": "validation",
        "timestamp": f"2024-02-{1 + (window.sequence_id % 27):02d}T14:30:00Z",
        "sequence_id": window.sequence_id,
        "regime_tag": window.regime_tag,
        "underlying_snapshot": {
            "symbol": "SPY_FIXTURE_V2", "asset_class": "equity",
            "price": S0, "currency": "USD",
            "prev_close": round(S0 - 0.5, 2),
            "realized_vol_20d": round(iv, 4), "regime_score": round(liq, 4),
        },
        "option_chain": {
            "underlying": {"symbol": "SPY_FIXTURE_V2", "asset_class": "equity", "price": S0, "currency": "USD"},
            "as_of": "2024-02-01T14:30:00Z",
            "contracts": [
                {
                    "symbol": c.symbol, "underlying_symbol": c.underlying_symbol,
                    "option_type": c.option_type, "strike": c.strike, "expiry": c.expiry,
                    "bid": c.bid, "ask": c.ask, "last": c.last,
                    "volume": c.volume, "open_interest": c.open_interest,
                    "iv": c.iv, "delta": c.delta, "gamma": c.gamma, "theta": c.theta, "vega": c.vega, "rho": c.rho,
                    "defined_risk": c.defined_risk,
                }
                for c in chain.contracts
            ],
        },
        "expected_outcome": {
            "next_underlying_price": round(next_price, 2),
            "next_iv": round(next_iv, 4),
            "days_to_exit": 5,
            "exit_reason": "target_profit_reached" if window.sector_context.sector_trend_score > 0.55 else (
                "invalidation_triggered" if window.sector_context.sector_trend_score < 0.40 else "expiry_time_decay"
            ),
            "favorable_move": round(abs(next_price / S0 - 1.0) * 100, 4),
            "adverse_move_pct": round((S0 - next_price) / S0 * 100, 4),
            "notes": window.holdout_purpose,
        },
        "family_outcome_hints": {k: round(1.0 - v, 4) for k, v in window.expected_family_pressure.items()},
        "regime_context": {
            "liquidity_quality": round(window.liquidity_context.liquidity_quality, 4),
            "spread_penalty": round(window.liquidity_context.spread_penalty, 4),
            "slippage_penalty": round(window.liquidity_context.slippage_penalty, 4),
            "iv_effect": round(window.iv_surface_context.iv_effect_signed, 4),
            "macro_contradiction": round(window.macro_context.macro_contradiction, 4),
            "technical_fakeout": round(window.iv_surface_context.surface_instability, 4),
            "pattern_confidence": round(window.pattern_context.get("confidence", 0.5), 4),
            "invalidation_quality": round(0.5, 4),
            "direction": ("bull" if next_price >= S0 else "bear"),
            "vol_bias": ("expansion" if window.iv_surface_context.iv_effect_signed > 0.05 else
                          "crush" if window.iv_surface_context.iv_effect_signed < -0.05 else "neutral"),
        },
        "v2_context": window.to_dict(),
        "notes": window.holdout_purpose,
    }


def persist_corpus_v2_fixtures(
    fixture_dir: Path | str | None = None,
    corpus: RegimeHoldoutCorpus | None = None,
) -> int:
    """Materialize each v2 window as a JSONL fixture file + a matching _analysis.json. Returns the count written."""
    target = Path(fixture_dir) if fixture_dir else V2_FIXTURE_DIR
    target.mkdir(parents=True, exist_ok=True)
    if corpus is None:
        corpus = build_regime_holdout_corpus_v2()
    written = 0
    for window in corpus.windows:
        fixture = _fixture_dict(window)
        path = target / f"{window.window_id}.json"
        path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        analysis_path = target / f"{window.window_id}_analysis.json"
        analysis_path.write_text(json.dumps(_build_analysis(window), indent=2), encoding="utf-8")
        written += 1
    return written
