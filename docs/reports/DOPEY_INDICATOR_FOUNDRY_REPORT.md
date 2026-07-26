# DOPEY Indicator Foundry Report

## Classic Battery
- 12 primitives computed leak-free per symbol; latest values in the dashboard artifact.

## Meta-Discovery
- candidates generated: `144` (enumerated composition grammar)
- IC bar (scaled for multiple testing): `0.06238` | empirical circular-shift null bar: `0.01271`
- era hygiene: `train-era-only standardization; boundary-straddling forward windows excluded`
- observations: train `119049` / validation `84103`
- PROMOTED: `0`

## Quote-Derived Lane (grows with the chain archive)
- status: `quote_lane_evaluated` | joinable obs: `161`/`120` | archive days: `10`

## Macro-Derived Lane (VIX term structure / SKEW, SPY-only join)
- status: `macro_lane_evaluated` | joinable obs: `162`/`120`
- feature ICs: `{'skew_level': -0.19894, 'vix_level': 0.3047, 'vix_ts_slope_9d_3m': -0.23947}` | cleared bar: `['skew_level', 'vix_level', 'vix_ts_slope_9d_3m']`

## Honest Limits
- IC survival across eras is a research signal, not tradable edge; promoted indicators
  must still pass the full honest lane (costs, baselines, truth layer) as signal families.
- paper_only: true; live_blocked: true.
