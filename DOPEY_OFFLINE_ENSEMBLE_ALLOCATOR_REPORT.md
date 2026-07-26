# DOPEY Offline Ensemble Strategy Allocator Report

## Purpose

The offline ensemble strategy allocator is a **deterministic, offline, fixture-based,
paper-only** layer that recommends *simulated paper attention weights* across strategy
families and candidate genomes. It combines tournament, mutation, feedback, failure-mode,
macro, IV/Greeks, liquidity/slippage, and pattern evidence into a single recommendation
layer for offline analysis.

This is **not live portfolio management**. It does not size real capital, place broker
orders, or promote any strategy to a live state. Every weight is a simulated paper research
attention unit, deterministic and reproducible.

## Allocation candidate model

`StrategyAllocationCandidate` is the unit of allocation. Each candidate carries:

- `strategy_id`, `strategy_family`, `source_type` (tournament | mutation | feedback | champion)
- `base_score` (combined tournament / mutation / feedback score)
- `walk_forward_score`, `analysis_fusion_score`
- `macro_fit_score`, `iv_surface_fit_score`, `greek_fit_score`
- `liquidity_robustness_score`, `slippage_robustness_score`
- `pattern_score`
- `failure_pressure_score` (soft-saturated family failure pressure, 0..1)
- `overfit_level`, `overfit_rank`
- `mutation_delta`, `promotion_state`, `paper_only`
- `holdout_score`, `best_regimes`, `worst_regimes`

Candidates are built from the latest tournament `strategy_ranking`, plus the latest mutation
champion and feedback candidate when their registries exist.

## Scoring components

`AllocationScoreBreakdown` decomposes each candidate into deterministic weighted
contributions (stored as their weighted values so the overall score equals the clamped
component sum):

- `proof_component` (0.34 weight): walk-forward + analysis-fusion blend
- `regime_component` (0.18): base score * regime multiplier + regime breadth
- `liquidity_component` (0.16): liquidity + slippage robustness
- `greek_iv_component` (0.12): greek fit + IV surface fit
- `macro_component` (0.07): macro fit
- `pattern_component` (0.05): pattern score
- `diversification_component` (0.08): reserved for family-mix bonuses
- `failure_penalty` (0.25 * failure pressure): penalizes recurring failure modes
- `overfit_penalty` (0.04 * overfit rank): penalizes high overfit
- `mutation_bonus` (0.5 * positive mutation delta): rewards improvement
- `overall_score`: clamped [0,1] sum

## Allocation policy

The policy (`dopey_strategy_lab/allocation_policy.py`) rewards walk-forward consistency,
low overfit, liquidity/slippage robustness, Greek/IV fit, macro compatibility, pattern
confirmation, failure reduction, mutation improvement, multi-regime survival, and family
diversification. It penalizes high overfit, holdout collapse, repeated failure modes, low
liquidity, slippage sensitivity, macro contradiction, IV crush/expansion mismatch, premium
overpayment, fakeout risk, unsafe structures, and mutation drift.

### Decisions (all paper-only)

`increase_paper_attention`, `hold_paper_attention`, `reduce_paper_attention`,
`starve_weak_signal`, `quarantine_overfit`, `research_only`, `reject`.

Forbidden decisions (`live_allocate`, `micro_live`, `adaptive_live`, `real_capital`,
`broker_order`) are rejected by `assert_decision_safe` at runtime and produce no output.

### Conservative weight caps

- Max single strategy paper weight: **0.40**
- Max family paper weight: **0.60**
- High-overfit candidate max: **0.10**
- Rejected / unsafe candidate max: **0.0**
- Accepted candidate weights **sum to 1.0** (iterative proportional fitting with cap-respecting
  residual fill); rejected / starved / quarantined candidates receive **0.0**.

### Deterministic tie-breakers

1. lower overfit
2. higher holdout score
3. better liquidity robustness
4. better failure reduction
5. deterministic `strategy_id` sort

## Regime-specific allocation behavior

`dopey_strategy_lab/regime_allocator.py` defines five regime classes with deterministic
family preference multipliers:

- **Trend / breakout** (`bullish_breakout`, `bearish_breakdown`, `trend_vol_expansion`):
  prefers directional convexity; short-duration only if liquidity robust; penalizes
  compression.
- **Event-vol / macro-shock** (`event_vol_expansion`, `pre_fomc_vol_expansion`): prefers
  volatility expansion **only when IV surface confirms expansion** (gated); penalizes
  compression and short-duration; directional only with macro confirmation.
- **Post-event IV crush / range** (`post_event_iv_crush`, `chop_vol_compression`): prefers
  compression; penalizes vol-expansion and directional fakeout.
- **Bad-fill / low-liquidity** (`low_liquidity_decay`, `high_spread_bad_fill`): starves
  short-duration and fragile multi-leg structures; only high-liquidity candidates survive.
- **Macro contradiction** (`macro_shock_risk_off`, `gap_reversal`): reduces directional and
  shock-exposed allocation; research-only observation.

## Ensemble replay comparison

`dopey_strategy_lab/ensemble_replay.py` compares four variants in deterministic paper units
(no real account balance or PnL):

- **single champion** (best base-score candidate)
- **equal-weight family basket** (mean of accepted candidate base scores)
- **allocator-weighted ensemble** (weight-normalized base scores)
- **overfit-adjusted ensemble** (overfit + concentration penalty applied)

It also records `EnsembleRobustnessScore` (mean/min/spread/drawdown proxy),
`FamilyDiversificationScore` (effective family count / Herfindahl), and
`RegimeCoverageScore` (covered vs known fixture regimes).

## Capital redeployment recommendations

`dopey_edge/capital_redeployment_engine.py` emits **simulated paper-only** redeployment
recommendations from the allocation decisions and family failure pressure:

- `increase` directional attention in confirmed trend regimes
- `reduce` vol-expansion attention after a post-event IV crush
- `quarantine` high-overfit vol-expansion variants
- `reduce` / tighten liquidity threshold for short-duration candidates in bad-fill regimes
- `starve` candidates with recurring failure modes
- `hold` research-only candidates with stable but insufficient proof
- `research_only` for candidates below the proof threshold

Every recommendation is `paper_only=True`, `live_allowed=False`, `proof_level=paper_only`.

## Files added

- `dopey_strategy_lab/ensemble_models.py`
- `dopey_strategy_lab/allocation_policy.py`
- `dopey_strategy_lab/regime_allocator.py`
- `dopey_strategy_lab/ensemble_replay.py`
- `dopey_strategy_lab/ensemble_allocator.py`
- `dopey_strategy_lab/run_offline_ensemble_allocator.py`
- `tests/test_offline_ensemble_allocator.py`
- `DOPEY_OFFLINE_ENSEMBLE_ALLOCATOR_REPORT.md`
- `DOPEY_CAPITAL_REDEPLOYMENT_REPORT.md`

## Files modified

- `dopey_edge/capital_redeployment_engine.py` (added paper-only redeployment layer; original
  `redeploy_capital` preserved)
- `dopey_strategy_lab/__init__.py` (exports ensemble interfaces)
- `DOPEY_TOURNAMENT_REPORT.md`, `DOPEY_FAILURE_FEEDBACK_OPTIMIZER_REPORT.md`,
  `DOPEY_VALIDATION_REPORT.md`, `DOPEY_CANON.md`

## Tests run

- `python -m pytest` -> **292 passed** (255 prior + 37 ensemble allocator tests)
- Ensemble allocator tests cover: model serialization, score breakdown, paper-only defaults,
  forbidden live decisions, weight normalization, caps (single/family/overfit), failure
  pressure, mutation bonus, deterministic tie-breakers, all five regime classes, ensemble
  replay comparison, regime coverage, family diversification, overfit concentration,
  redeployment (starve / reduce / tighter liquidity / paper-only), registry + proof ledger +
  reproducibility hash, and six safety regression tests.

## Ensemble allocator smoke

`python -m dopey_strategy_lab.run_offline_ensemble_allocator` -> `allocator_status: ok`,
`mode: RESEARCH`, `live_trading_enabled: false`, `candidates_loaded: 6`,
`weights_sum: 0.999999`, `live_blocked: true`, top strategy
`genome-directional-convexity-spy-fixture-v1`, top family `directional_convexity`,
`single_champion_score: 0.609797`, `equal_weight_score: 0.581136`,
`allocator_weighted_score: 0.581136`, `overfit_adjusted_score: 0.561136`,
`best_ensemble_variant: single_champion`.

## Limitations

- All allocation scores are deterministic fixture math, not live performance evidence.
- The allocator concentrates on the strongest family in the current fixture corpus because
  the other families carry genuinely modest walk-forward / overfit / failure pressure; this
  is an honest deterministic outcome, not a tuning failure.
- Weights are simulated research attention, not real capital sizing or broker order sizing.
- No real market-data dependency, broker connection, credentials, network access, scheduled
  run, or live promotion exists.

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker rejects `live_allowed=true`
- Robinhood / Alpaca / Tradier stubs raise `LiveTradingDisabledError`
- All allocation decisions are paper-only; no live decision is emitted
- No broker connection, credentials, network market data, live trades, live promotion,
  autonomous scheduled run, heavy dependency, commit, or Blunder source modification
- Blunder integrity: **`BLUNDER_INTEGRITY_OK checked=78`**

## Next recommended build target

Offline meta-governor for proof-weighted strategy promotion.

## Update: stronger walk-forward consistency integration

The ensemble allocator now integrates the stronger walk-forward consistency layer:

- `StrategyAllocationCandidate` carries new fields `consistency_score` and `consistency_verdict`.
- `AllocationScoreBreakdown` exposes new components `consistency_component` (positive weight on
  the strategy's registry overall) and `consistency_penalty` (penalty for weak consistency
  below 0.30).
- `score_candidate` includes both components in the overall score: `0.05 * max(0, consistency_score)`
  bonus and `0.10 * (0.30 - consistency_score)` penalty when `0 < consistency_score < 0.30`.
- Reason codes now include `weak stronger-walk-forward consistency penalizes paper attention`
  when the consistency score falls in the penalty band.
- The ensemble allocator loads the latest
  `artifacts/dopey/walk_forward_consistency/consistency_registry.jsonl` to stamp each
  candidate with its consistency score + verdict. The lookup is graceful: missing registry
  → all consistency scores default to 0.0 (no bonus, no penalty).
- `apply_caps` skips the family cap when only one family is represented, and uses a soft
  per-candidate fallback so the policy can always reach sum-to-1.0 even in single-family
  accepted sets.

This means that after the stronger walk-forward consistency pass:
- Strategies with strong rolling + blocked + regime + stress holdout survival are
  rewarded in the allocator.
- Strategies that fail multiple holdout windows are starved or quarantined.
- The family-level cross-strategy consensus is preserved.

Live promotion remains impossible: every decision is paper-only; no live tier is emitted;
PaperBroker still refuses `live_allowed=true`; live stubs still raise
`LiveTradingDisabledError`. See `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_REPORT.md`.

## Update: regime/holdout corpus v2 integration

The ensemble allocator now also reads the regime/holdout corpus v2 registry:

- `StrategyAllocationCandidate` carries new fields `corpus_v2_consistency_score` and
  `corpus_v2_consistency_verdict`.
- `AllocationScoreBreakdown` exposes new components `corpus_v2_component` (positive
  weight on registry overall) and `corpus_v2_penalty` (penalty for weak v2 consistency
  below 0.30).
- `score_candidate` includes both components in the overall score: `0.04 * max(0,
  corpus_v2_consistency_score)` bonus and `0.08 * (0.30 - corpus_v2_consistency_score)`
  penalty when `0 < corpus_v2_consistency_score < 0.30`.
- Reason codes now include `weak regime/holdout corpus v2 consistency penalizes paper
  attention`.
- The ensemble allocator loads
  `artifacts/dopey/regime_holdout_corpus_v2/corpus_registry.jsonl` to stamp each
  candidate with its v2 consistency score + verdict. The lookup is graceful: missing
  registry → all corpus-v2 scores default to 0.0 (no bonus, no penalty).

Live promotion remains impossible: every decision is paper-only; no live tier is
emitted; PaperBroker still refuses `live_allowed=true`; live stubs still raise
`LiveTradingDisabledError`. See `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2_REPORT.md`.

## Update: fundamental fit integration

The ensemble allocator now consumes the new
amily_fundamental_scores block from the tournament. The allocation logic still
concentrates paper attention on the strongest family, but the fundamental fit
provides an additional reason to demote families that carry extreme peer-contradiction
or valuation-trap pressure on the deterministic fixtures. All allocation decisions
remain paper-only; live promotion is impossible.
