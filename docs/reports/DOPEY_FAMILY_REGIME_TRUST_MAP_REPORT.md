# DOPEY Family / Regime Trust Map Report

## Family trust ranking

The family trust map scores each strategy family from aggregated proof profiles, ensemble
allocation weights, overfit, failure pressure, and Greek/IV/macro/liquidity fit. Trust
rewards low overfit, low failure pressure, ensemble support, and robust fit.

Current deterministic ranking (from the latest meta-governor run):

| Family | Trust | Attention | Mutation intensity | Ensemble weight |
|---|---|---|---|---|
| directional_convexity | 0.607 | hold | low | ~1.0 |
| short_duration_defined_risk | 0.277 | starve | none | 0.0 |
| volatility_compression | 0.254 | starve | none | 0.0 |
| volatility_expansion | 0.178 | starve | none | 0.0 |

Directional convexity is the only family carrying adequate walk-forward consistency and low
overfit; the other families are starved due to higher overfit / failure pressure and modest
fixture scores.

## Best / worst regimes by family

- **directional_convexity**: best `bullish_breakout`, `bearish_breakdown`, `trend_vol_expansion`; regime specialist for trend.
- **short_duration_defined_risk**: best `chop_vol_compression`, range/pin regimes.
- **volatility_compression**: best `chop_vol_compression`, `post_event_iv_crush`.
- **volatility_expansion**: best `event_vol_expansion`, `macro_shock_risk_off`.

## Recommended paper attention

- directional_convexity: hold / modest increase in confirmed trend regimes
- volatility_expansion: starve until overfit and IV-crush failure pressure fall
- volatility_compression: starve until macro-shock contradiction pressure falls
- short_duration_defined_risk: starve until liquidity / theta-decay pressure falls

## Dominant failure modes by regime

The regime trust map records the dominant failure modes mined for each regime tag (e.g.
`macro_shock_against_compression` in macro-shock regimes,
`IV_crush_against_vol_expansion` in post-event regimes,
`high_spread_bad_fill_failure` in low-liquidity regimes).

## Required next evidence

- `stronger_walk_forward_consistency` — the dominant missing-evidence priority in the
  current corpus; non-directional families need higher walk-forward consistency before they
  can leave the starved/research-only band.
- `complete_evidence_layer_coverage` and `cross_layer_champion_agreement` for any future
  paper-candidate promotion.
- Broader regime coverage so the ensemble can diversify beyond the trend-specialist family.

## Safety boundaries

The trust map is consumed only by the offline meta-governor in RESEARCH mode. It never
emits live promotion, real capital allocation, or broker action. All trust scores are
deterministic fixture aggregation, not live performance evidence.
