# DOPEY_REAL_DATA_ACTIVATION_V8_REPORT

- repo path: `C:\Users\CH\dopey`
- bundle: `DOPEY_REAL_DATA_ACTIVATION_V8`
- date: 2026-07-09
- orchestrator status: `real_data_spine_active_honest_lane_live`
- operator: manual staging performed by the operator's agent outside the DOPEY pipeline

## Objective

Answer the V8 research question and end fixture theater:

> Why did the top V7 trade-active PF 1.399096 cohort fail breakthrough promotion, and can its
> blocker set be repaired without lowering thresholds?

## The V8 Answer (final)

**The V7 cohort cannot be repaired because its edge never existed.** A code-level provenance
audit proved the entire V1-V7 public-signal-research lane is procedurally generated with no
market data of any kind:

- candidate "features" are modular arithmetic on the row index
  (`research_candidate_generator_v7.py::_feature_vector`)
- entry prices are SHA1 hashes of `symbol|sector` strings
  (`research_path_simulator_v7.py::_entry_spot_for`; verified: `sha1("BRK_B|Energy") -> 320.776`
  exactly matches the artifact trade record)
- price paths come from a hand-rolled glibc-constant LCG + Box-Muller generator, seeded by
  SHA1 of `symbol|idx|subfamily`
- the breakthrough gate scores those trades against a leaderboard, holdout, and V6 baseline all
  derived from the same PRNG stream: a fully closed self-referential loop
- records carried FALSE labels: `market_data_source_type: "public_ohlcv"`,
  `future_ohlcv_used: true`, `public_data_only: true`

The exact V7 blocker set for `continuation|long_put|trending|B` (drawdown -3076.97 > 2500 cap,
win rate 0.4259 < 0.55, no_improvement_vs_v6, trade-active split fail) was arithmetic of the
PRNG. 7 of 8 synthetic subfamilies produced PF > 1.10 - a multiple-comparisons artifact.

**Real-data verdict on the V7 thesis:** on validated real history, long-put continuation-style
cohorts are the worst performers on the board (momentum|long_put PF 0.651, market_regime|long_put
PF 0.577, breakout|long_put PF 0.272). The synthetic "edge" pointed in the wrong direction.

## What V8 Built

### 1. Real data spine - ACTIVE for the first time

- 24-symbol required universe staged through the governed operator lane:
  SPY QQQ IWM DIA AAPL MSFT NVDA AMD TSLA META AMZN GOOGL NFLX JPM BAC XLF XLK XLE XLY XLI
  XLU XLP XLV + VIX (market context)
- 185,453 real daily OHLCV rows, 1973-02-21 -> 2026-07-08, provider yahoo_finance via the
  yfinance library, fetched by the operator's agent OUTSIDE the DOPEY pipeline
  (`not_network_fetched_by_dopey: true` is literally true)
- gate 1 (governed import): `local_ohlcv_validation_pass` - schema, quality, license
  (`reviewed_allowed_internal_research`, redistribution false), provenance, sha256 per file
- gate 2 (hash-pinned history spine): `valid_real_dataset` - manifest-pinned sha256 per file,
  full universe coverage, zero stale symbols
- history spine activation: `real_ohlcv_history_spine_activation_pass`
- real signal validation gate: `real_signal_validation_pass`

### 2. Real-history signal engine (new: `dopey_analysis/real_history_signal_engine.py`)

Computes the existing signal families (momentum, breakout, fakeout, trend_pullback,
volatility_regime, relative_strength vs SPY, market_regime) over real bars.
Leak policy: signals at a date use bars through that date only. VIX is context-only.
Grid: 2015-01-01 onward, every 10 trading days, lookback 20.

- evaluation points: 6,670 | directional setups: 46,690
- long_call candidates: 4,575 | long_put candidates: 4,758 | no_trade: 37,357 (80.0%)

### 3. Real-history honest backtester (new: `dopey_backtest/real_history_honest_backtester.py`)

Replaces the round-robin path pairing with per-intent pricing along the SAME symbol's actual
forward bars: entry next trading day's open (no same-bar lookahead), ATM strike, 30-day tenor,
Black-Scholes marks with daily time decay, IV proxy = trailing 20d realized vol x 1.10
(clamped 0.08-2.00), exits premium_stop -50% / premium_target +100% / time_stop 3 steps.
Adjusted price units (split-safe). Labels truthful: real_history_used=true, fixture_only=false,
pricing stays model_priced, quote_priced stays 0.

### 4. First honest result on real data (model units, BEFORE costs)

| Metric | Value |
| --- | ---: |
| trades | 9,333 (4,575 long_call / 4,758 long_put) |
| net P&L | -538.40 |
| average per trade | -0.0577 (bootstrap CI [-0.1238, +0.0113]) |
| win rate | 40.7% (CI [39.8%, 41.7%]) |
| max drawdown | -731.69 |
| deflated Sharpe | -0.087 |

Cohorts (signal_family x strategy):

| cohort | n | win% | PF | net |
| --- | ---: | ---: | ---: | ---: |
| relative_strength long_call | 2,252 | 48.0 | 1.262 | +409.96 |
| momentum long_call | 1,975 | 47.1 | 1.211 | +324.52 |
| breakout long_call | 217 | 45.6 | 1.180 | +34.95 |
| fakeout long_call | 98 | 55.1 | 1.077 | +7.93 |
| fakeout long_put | 108 | 44.4 | 1.118 | +6.46 |
| market_regime long_call | 31 | 38.7 | 0.964 | -2.54 |
| trend_pullback long_call | 2 | 50.0 | 0.016 | -3.06 |
| relative_strength long_put | 2,050 | 37.4 | 0.900 | -153.43 |
| breakout long_put | 262 | 26.3 | 0.272 | -216.14 |
| momentum long_put | 1,215 | 32.3 | 0.651 | -454.60 |
| market_regime long_put | 1,123 | 30.9 | 0.577 | -492.47 |

Interpretation (honest): the long-call side is positive in model units largely because
2015-2026 was a secular bull market - much of it is drift/beta, not proven alpha; the baseline
comparison layer must arbitrate. The long-put side loses consistently (fighting drift while
paying theta). Bid/ask spread, slippage, and commissions are NOT modeled and would materially
reduce every number above. **This is not a profitability claim; it is the first honest
measurement.**

### 5. Statistical truth layer + fitness on real records

- truth_status: `insufficient_real_sample`; decision: `insufficient_real_evidence`
  (real-history branch acknowledged; real_sample_size stays 0 because zero trades are
  quote-priced - no real options chain exists)
- significance / real-alpha / profitability / live-readiness claims: all BLOCKED
- promotion_allowed: false; proxy fitness remains quarantined

### 6. Honesty repairs

- V7 synthetic lane now tells the truth at the source: generator and simulator emit
  `market_data_source_type: "synthetic_deterministic_hash_lcg"`,
  `synthetic_provenance: "index_derived_features_sha1_entry_spots_lcg_paths"`,
  `future_ohlcv_used: false`, `synthetic_path_used: true`, `public_data_only: false`.
  The V7 gate's own fixture detector now counts every synthetic trade, making synthetic
  "public-data breakthroughs" permanently impossible.
- gate-1 quality validator falsy-zero bug fixed: legitimate volume=0 rows (VIX, early equity
  sessions) were wrongly blocked as "negative_volume"
  (`local_ohlcv_quality_validator.py::_volume_value`).
- 9 stale tests that hardcoded the "repo is empty" state now assert label/state CONSISTENCY in
  both empty and populated worlds.

## Safety State (unchanged and verified)

- paper_only: `true`; live_blocked: `true`
- no broker connection, no credentials, no `.env`, no orders, no scheduler, no real sizing
- long_call / long_put / no_trade only - policy holds across generator, mapper, simulator, gate
- promotion blocked by the statistical truth layer; no claim gates weakened in this bundle

## Validation

- `tests/test_real_history_lane.py`: 9 passed (new - leak-freedom, mark construction,
  BS pricing parity, relabel+rehash, cohort math, live-summary claims)
- `tests/test_local_free_ohlcv_import_validator_and_history_activation.py`: 9 passed
- `tests/test_public_signal_research_breakthrough_v7.py`: 52 passed (truthful labels)
- `tests/test_real_signal_engines.py` + `tests/test_honest_backtester.py`: 59 passed
- `tests/test_statistical_truth_layer.py` + `tests/test_fitness_function_replacement.py`: 59 passed
- full-suite `inconclusive_timeout` remains a known, honestly-recorded issue (pre-existing)

## Known Gaps (next bundle candidates)

1. **No real options chains** - the binding constraint on all claims. Until quote-priced data
   exists, everything stays model-priced and promotion stays blocked. Candidate lanes: operator
   staging of reviewed historical chain data through a chain-quote contract
   (`dopey_data_ingestion/options_chain_quote_contract.py` exists), or delayed official
   provider data with license review.
2. **No cost model** - add spread/slippage/commission haircuts to the real lane so model units
   stop flattering long-premium results.
3. **Baseline arbitration** - random-entry long-call baseline over the same period to separate
   signal alpha from bull-market beta before any cohort is taken seriously.
4. **Walk-forward splits on the real lane** - train/validate/holdout by era (2015-2019 /
   2020-2022 / 2023-2026) to test regime robustness.
5. Full-suite stabilizer timeout (pre-existing) - shard or parallelize the 2,936-test suite.

## Next Target

`DOPEY_REAL_COST_MODEL_AND_BASELINE_ARBITRATION_V9`
