# DOPEY Indicator Foundry Report

## Classic Battery
- 12 primitives computed leak-free per symbol; latest values in the dashboard artifact.

## Meta-Discovery
- candidates generated: `144` (enumerated composition grammar)
- IC bar (scaled for multiple testing): `0.06238` | empirical circular-shift null bar: `0.02578`
- era hygiene: `train-era-only standardization; boundary-straddling forward windows excluded`
- observations: train `32511` / validation `24626`
- PROMOTED: `0`

## Quote-Derived Lane (grows with the chain archive)
- status: `insufficient_sample_accruing` | joinable obs: `0`/`120` | archive days: `5`

## Macro-Derived Lane (VIX term structure / SKEW, SPY-only join)
- status: `macro_lane_evaluated` | joinable obs: `163`/`120`
- feature ICs: `{'skew_level': -0.20247, 'vix_level': 0.31496, 'vix_ts_slope_9d_3m': -0.23158}` | cleared bar: `['skew_level', 'vix_level', 'vix_ts_slope_9d_3m']`

## Honest Limits
- IC survival across eras is a research signal, not tradable edge; promoted indicators
  must still pass the full honest lane (costs, baselines, truth layer) as signal families.
- paper_only: true; live_blocked: true.
