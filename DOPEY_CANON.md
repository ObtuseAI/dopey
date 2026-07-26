# DOPEY CANON

## Current operational truth (2026-07-25)

DOPEY autonomously operates bounded, paper-only research lanes. The executable
recursive evaluation loop currently supports the `technical_momentum` and
`structural_trend` experiment lineages with pinned-history verification,
visible/private/external partitions, after-cost scoring, append-only findings,
and idempotency by cycle hash. The remaining experiment lineages, coach
proposals, activated genomes, and shadow challengers are evidence-producing or
reporting-only until each has an explicit evaluator and dispatch path.

Live execution is not self-authorizing. It requires a separate, explicitly
armed, machine-bound operator control and broker-reviewed evidence. Research
promotion, scheduling, MCP output, and self-improvement artifacts cannot enable
live trading. Aspirational language elsewhere in this canon describes intended
architecture; this section states the current executable boundary.

## What Dopey is

DOPEY is an autonomous options-trading **research** agent. It is a forked-and-renamed copy of the
**Blunder** Recursive Work Engine (autonomy loop, proof ledger, promotion gate, self-operation
recommend-only doctrine), onto which Dopey layers:

- **Dummy** aggressive-adaptive-edge doctrine (proof-weighted aggression, weak-signal starving,
  capital redeployment, fast invalidation, recursive data expansion).
- An **options-specific quant stack** (greeks, IV surface, skew, term structure, liquidity,
  contract ranking, defined-risk spread construction, assignment/exercise risk).
- A **broker-agnostic execution architecture** with runtime capability detection.
- **Robinhood MCP compatibility** (discovery-only in the first pass; no unofficial private API).

## Why research-only by default

Options can lose the full premium; automation can malfunction; and a research agent that can
also trade live can ruin an account faster than a human can intervene. The first pass therefore
ships in a research-only configuration where the autonomy loop, the proof ledger, and all
research modules run, but no live order can be placed. The `LiveOrderGate` is the hard boundary
that enforces this.

## Proof-weighted aggression

The `ProofWeightedAggressionGate` (Dummy doctrine) converts a `StrategyGenome` + `ProofBundle` +
liquidity + regime + broker capability into an `AggressionScore` and a `PromotionDecision`. It
**penalizes** overfit, low liquidity, bad slippage, weak proof, unsupported broker, drawdown
acceleration, and signal decay; it **rewards** OOS edge, walk-forward consistency, paper-fill
quality, regime alignment, capital efficiency, and family proof. The gate is deterministic ?
identical inputs always yield the same score ? so it is testable with fixtures.

## Weak-signal starving

The `WeakSignalStarver` downgrades decayed or repeatedly-failed signals and marks them for
demotion. It never deletes them (history is preserved for the proof ledger).

## Capital redeployment

The `CapitalRedeploymentEngine` recommends reallocating **paper** capital toward stronger
proof-backed families. It is recommend-only; it never mutates a live account.

## Broker capability detection

`BrokerCapabilityDetector` returns disabled/unknown for Robinhood options exec unless an explicit
future live mode has discovered capability. Dopey never *assumes* options execution; it
*discovers* it at runtime.

## Why Robinhood MCP over private APIs

The unofficial Robinhood private API is fragile, rate-limited, and against terms of service;
using it risks credential loss, bans, and unpredictable behavior. The official MCP path is the
sustainable discovery interface. Dopey forbids the unofficial API entirely in the first pass.

## Why paper/sandbox before live

Paper trading proves the order path, fill simulation, validation, and ledger integration without
risking capital. Live trading is gated behind an explicit future mode AND proof AND capability
AND budget AND defined-risk AND `live_allowed=true`.

## Future promotion tiers

1. `RESEARCH` (default) ? no exec, no broker.
2. `PAPER` ? `PaperBroker` simulated fills, no funded account.
3. `MICRO_LIVE` (template only, disabled) ? very small defined-risk live, requires every gate.
4. `ADAPTIVE_LIVE` (future) ? adaptive sizing, requires sustained proof + capability.

No tier is auto-promoted; each requires explicit operator enablement and passing the
`LiveOrderGate`.

## Offline Paper Research Pipeline

The **offline paper research pipeline** (`dopey_research_pipeline`) is the first *executable*
Dopey loop. It is fully offline, deterministic, and paper-only:

fixture option chain ? contract ranker ? `StrategyGenome` candidate ?
`ProofWeightedAggressionGate` ? paper `ExecutionIntent` ? `OrderIntentValidator` ?
`PaperBroker` simulated fill ? `ExecutionQualityLogger` ? `ProofLedger` append.

The aggression gate's promote/hold/demote is re-mapped onto paper-only promotion targets
(`paper_candidate`, `research_only`, `rejected`); **live promotion is impossible from this
path**. The pipeline never connects to a broker, uses no credentials, places no live order, and
appends a reproducibility-hashed `ProofEntry` to a local append-only ledger. It still has **no
live execution** ? it proves the research loop end-to-end without crossing any live boundary.

## Offline Walk-Forward Replay

The **offline walk-forward replay harness** (`dopey_walk_forward`) is the third executable
Dopey pass. It replays a fixture-based `StrategyGenome` over multiple deterministic historical
fixture windows (train / validation / holdout), scores walk-forward consistency, detects
overfit/fragility, and feeds the summarized results back into the `ProofWeightedAggressionGate`
as proof.

The aggression gate maps replay results onto paper-only promotion targets:
`research_only`, `paper_candidate`, `replay_promoted_paper_candidate`, `rejected`. **Replay
promotes only research/paper eligibility ? it cannot enable live trading.** Live targets
(`micro_live`, `adaptive_live`) are explicitly disallowed and impossible from this path.
Overfit gating forces rejection on high overfit and caps moderate overfit at `research_only`.

The harness never connects to a broker, uses no credentials, places no live order, and is
invoked manually only (no schedule/daemon). DOPEY becomes aggressive through **replay-proven
edge**, not through unsafe execution.

## S-Tier Multi-Layer Market Analysis

DOPEY's recursive edge engine now treats five analysis layers as first-class, S-tier
intelligence:

- **Macro** ? risk-on/off, volatility regime, event-risk shock handling, sector rotation,
  breadth, liquidity regime.
- **Microstructure** ? spread quality, liquidity, slippage sensitivity, volume/OI anomalies,
  quote stability, contract fillability, execution-quality attribution.
- **Technical** ? trend structure, momentum, realized volatility, range compression/expansion,
  breakout/fakeout detection, support/resistance zones, volume confirmation, gap behavior.
- **Fundamental** ? earnings/filing event risk, valuation context, growth quality, analyst
  revisions, sector/peer, fundamental regime.
- **Pattern recognition** ? volatility/price-action/chain-anomaly/IV-skew/unusual-OI/regime-
  transition/failed-breakout/continuation-reversal/strategy-outcome/failure-mode patterns.

These are currently **deterministic offline fixture interfaces, not real market-data
integrations** (real-data feeds are deferred pending explicit future confirmation). No single
analysis layer is final authority: `AnalysisFusionScore` combines all five with balanced
weights, penalizes contradictions between layers, and drags the overall down when any layer is
weak. The fused score feeds the multi-strategy paper tournament ranking alongside walk-forward
consistency. **Live promotion remains impossible** ? the tournament may only award
`paper_candidate` or `tournament_champion_paper_only` (both paper-only); `micro_live` and
`adaptive_live` are forbidden and unreachable.

## Expanded Regime Corpus and Differentiated Strategy Families

DOPEY now evaluates **multiple strategy families against multiple offline regimes**. The
walk-forward fixture corpus expanded from 4 to 12 deterministic windows covering 12 required
regime tags (trend/vol expansion, chop/compression, gap reversal, liquidity decay, event vol,
post-event IV crush, bearish breakdown, bullish breakout, range-bound pin, high-spread bad
fill, low-liquidity decay, macro-shock risk-off).

Each strategy family now constructs a **distinct defined-risk paper structure** so the
tournament produces differentiated replay outcomes rather than identical results:

- **directional convexity** ? long call vertical (bullish) / long put vertical (bearish)
- **volatility expansion** ? long strangle (buy OTM call + buy OTM put)
- **volatility compression** ? iron condor (defined-risk credit pair)
- **short-duration defined-risk** ? call butterfly (defined-risk debit)

A **family-aware deterministic outcome model** replaces the prior one-size exit model: it
scores each window per family from regime match, liquidity quality, spread/slippage
penalties, IV crush/expansion, macro contradiction, technical fakeout, pattern confidence,
and invalidation quality. This is explicitly a **deterministic fixture simulation**, not real
execution quality ? it makes no performance or profit claims. Analysis fusion now includes a
`family_regime_alignment` term that rewards family/regime fit without overriding walk-forward
results.

Tournament ranking combines walk-forward score, analysis fusion, overfit level, family-specific
regime survival, liquidity robustness, invalidation quality, paper-fill quality, and holdout
score, with deterministic tie-breakers (lower overfit ? better holdout ? better liquidity ?
better invalidation ? strategy_id sort) so the champion is **never chosen by insertion-order
tie**. The champion registry records per-family strengths/weaknesses, best/worst regimes,
overfit level, replay score, analysis-fusion score, a reproducibility hash, and the safety
state.

**All results remain paper-only fixture simulation.** Live promotion remains impossible: the
allowed promotion decisions are `rejected`, `research_only`, `paper_candidate`, and
`tournament_champion_paper_only`; `live_candidate`, `micro_live`, and `adaptive_live` are
forbidden and unreachable. PaperBroker is the only execution adapter and refuses
`live_allowed=true`; the Robinhood/Alpaca/Tradier stubs still raise
`LiveTradingDisabledError`. DOPEY becomes S-tier by proving which strategy families work
under which regimes ? not by pretending fixture simulation is real execution.

## Deterministic Slippage and Liquidity Intelligence

DOPEY now scores strategy families against deterministic fixture fill-quality conditions instead
of applying fixed 0.2% slippage to every paper fill. The slippage/liquidity upgrade adds:

- contract-aware liquidity scoring from bid, ask, mid, spread width, spread percentage, volume,
  open interest, quote stability, fillability, liquidity decay, strategy family, structure type,
  DTE bucket, and leg count;
- regime-aware slippage scoring for high-spread, low-liquidity, event-vol, macro-shock,
  short-duration, directional fakeout, compression breakout, and multi-leg structure pressure;
- PaperBroker fill records with expected slippage pct/amount, fill quality, liquidity score,
  liquidity verdict, slippage verdict, paper-only flag, and `live=false`;
- replay/tournament scoring that rewards liquidity robustness and stable fill quality while
  penalizing strategies that only work under unrealistically cheap paper fills.

This is still deterministic paper simulation. It is not real execution quality, real market
impact, queue-position modeling, live quote pressure, or calibrated options microstructure. It
uses fixture inputs only and makes no profit or execution-quality claims.

Live promotion remains impossible from this path. `mode` remains `RESEARCH`,
`live_trading_enabled=false`, PaperBroker refuses `live_allowed=true`, and the
Robinhood/Alpaca/Tradier stubs still raise `LiveTradingDisabledError`.

## Deterministic Greeks/IV Validation

DOPEY now evaluates paper option structures with deterministic fixture-only Greeks and IV
context:

- `GreekVector`, `GreekExposureSummary`, `GreekRiskVerdict`, `GreekAttributionResult`, and
  `StrategyGreekProfile`
- `IVContext`, `IVSurfaceSummary`, `SkewSummary`, and `TermStructureSummary`
- Greeks validation model version: `dopey-greeks-validation-v1`
- IV fixture model version: `dopey-iv-fixture-model-v1`

The replay engine nets delta/gamma/theta/vega/rho by paper leg, scores each strategy family
against its Greek preferences, evaluates IV expansion/crush context, skew, and term structure,
and records deterministic attribution components for delta, gamma, theta, vega, IV, and
residual fixture effect. Tournament ranking now consumes Greek fit, IV/skew/term fit, and
attribution quality alongside walk-forward, analysis fusion, liquidity, slippage, invalidation,
holdout, and overfit signals.

The champion registry and ProofLedger record average Greek fit, IV context, best/worst Greek
regimes, Greek strengths/weaknesses, attribution quality, high-theta/high-vega survival, and
model versions. Current tournament proof keeps the champion as
`genome-directional-convexity-spy-fixture-v1` and runner-up as
`genome-short-duration-defined-risk-spy-fixture-v1`.

This remains deterministic paper simulation. It is not calibrated live IV-surface math, live
pricing, broker execution quality, or a profit claim. Live promotion remains impossible from
this path; `mode` remains `RESEARCH`, `live_trading_enabled=false`, PaperBroker refuses
`live_allowed=true`, and live broker stubs raise `LiveTradingDisabledError`.

## Recursive Data Inflow Scoring

DOPEY now ranks future data sources with a deterministic offline source scorecard and data
inflow registry. The first source registry is fixture-only: it scores 16 candidates across
freshness, reliability, latency, coverage, ontology fit, expected edge contribution,
cost/complexity, compliance, and paper-research value.

Only local/offline sources can be promoted in the current pass:

- `champion_registry_internal`
- `pattern_fixture_corpus_internal`
- `proofledger_internal`
- `realized_volatility`

Network-only and credentialed sources are recorded as deferred, not fetched. This includes
OpenBB, SEC/EDGAR, earnings and macro calendars, VIX/VVIX, Alpaca, Tradier, Robinhood MCP
discovery, options-chain placeholders, IV-surface placeholders, unusual-options activity, and
future broker fill history. The scorecard is therefore an input-prioritization model, not a
market-data integration. No credentials, broker connections, or network fetches are part of
this canon state.

## Pattern Fixture Intelligence

DOPEY now carries a richer offline pattern fixture corpus and pattern scorecard into analysis
fusion and tournament scoring. The fixture corpus covers 16 deterministic pattern types:
bullish and bearish continuations, failed breakout/breakdown reversals, range pins,
volatility expansion, post-event IV crush, liquidity traps, high-spread false signals, gamma
squeeze proxy, theta decay, macro shock reversal, chop fakeout, trend-vol continuation,
low-liquidity decay, and skew warning.

Pattern scoring remains explicit fixture math. It rewards family/pattern fit, penalizes known
failure modes, and nudges analysis fusion through `pattern_fixture_score` without overriding
walk-forward, Greeks/IV, liquidity, slippage, overfit, or invalidation evidence. Tournament
records and champion-registry entries now include pattern summaries, family pattern scores,
supporting pattern ids, and penalizing pattern ids.

## Offline Strategy Mutation and Evolution

DOPEY now has a deterministic offline mutation loop for paper-only strategy genomes. Mutation
instructions can adjust delta preference, DTE bucket, liquidity threshold, slippage tolerance,
IV regime preference, pattern preference, invalidation sensitivity, regime filter, spread
structure proxy, theta tolerance, vega tolerance, and overfit penalty.

Every mutated genome preserves `live_allowed=false`, `defined_risk_only=true`, and
`structure_risk=defined`. Mutation output is written to a mutation registry and a mutation
ProofLedger, then summarized back into the tournament and champion registry. The latest offline
mutation champion is
`genome-directional-convexity-spy-fixture-v1-mut-liquidity-01`, which improves the deterministic
fixture score from `0.577118` to `0.602118`. The overfit stress mutation is rejected.

Allowed mutation decisions are limited to `rejected`, `degraded`, `research_only`,
`paper_research_candidate`, and `offline_mutation_champion`. Live decisions such as
`live_candidate`, `micro_live`, `adaptive_live`, and `live` remain forbidden and unreachable.

## Bounded Mutation Population

DOPEY now builds a deterministic offline mutation population across all current strategy
families. The population version is `dopey-mutation-population-v1`; the bundle version is
`dopey-mutation-population-bundle-v1`.

The latest population generates `36` mutation records: `32` valid paper-research mutations and
`4` intentionally unsafe probes that are rejected. Covered families are
`directional_convexity`, `volatility_expansion`, `volatility_compression`, and
`short_duration_defined_risk`.

The latest offline mutation champion is
`genome-directional-convexity-spy-fixture-v1-mut-delta-bull`, selected against parent
`genome-directional-convexity-spy-fixture-v1`. The deterministic fixture score moves from
`0.577118` to `0.591118`, a delta of `0.014`.

Allowed mutation decisions remain limited to offline and paper-research categories. No mutation
can emit `live_candidate`, `micro_live`, `adaptive_live`, or `live`.

## Family-Specific Mutation Limits

DOPEY now validates mutations against family envelopes before scoring. The family mutation limits
version is `dopey-family-mutation-limits-v1`.

Directional convexity rejects non-directional, compression-only, and iron-condor drift.
Volatility expansion rejects short-vol, IV-crush-only, and positive-vega-removal drift.
Volatility compression rejects unlimited-risk, undefined-risk, and positive-vega expansion drift.
Short-duration defined-risk rejects low-liquidity, wide-illiquid, and live-scalping drift.

The validator also hard rejects `live_allowed=true`, non-defined risk, live promotion labels, and
naked or undefined-risk structures.

## Defined-Risk Structure Builder

DOPEY now has a deterministic option-structure builder for replay intent. The structure builder
version is `dopey-structure-builder-v1`.

Supported structures include long call verticals, long put verticals, long straddle proxies, long
strangle proxies, iron-condor proxies, credit-spread-pair proxies, butterfly proxies, and
short-DTE debit-spread proxies. The builder records leg count, max loss, max reward, net debit or
credit, directional bias, volatility bias, Greek exposure, liquidity score, slippage pressure, and
safety verdict.

The tournament summary records defined-risk structures for every family: `vertical`,
`strangle`, `iron_condor`, and `butterfly`. Unsafe naked or undefined-risk structures are rejected
before scoring.

## Failure-Mode Mining

DOPEY now mines deterministic failure modes from tournament rows, mutation rows, and unsafe
rejections. The failure-mode miner version is `dopey-failure-mode-miner-v1`; the registry version
is `dopey-failure-mode-registry-v1`.

The latest registry records `28` family-specific failure-mode records. Detected classes include
bad fills, liquidity decay, IV crush against vol expansion, macro shock against compression,
directional fakeout, short-duration theta decay, wrong delta direction, train-only overfit,
holdout collapse, poor Greek fit, pattern contradiction, slippage oversensitivity, regime
mismatch, mutation drift, and unsafe structure rejection.

Failure modes feed small deterministic constraint penalties back into mutation scoring and record
mitigation hints in the registry. They do not promote live trading, alter broker configuration, or
launch any scheduled process.

## Failure-Mode Feedback Optimizer

DOPEY now converts mined failure evidence into deterministic replay-only mutation and constraint
recommendations. The optimizer version is `dopey-failure-feedback-optimizer-v1`.

The optimizer reads `artifacts/dopey/failure_modes/failure_mode_registry.jsonl`, aggregates
failures by family, structure, regime, pattern, Greek/IV context, liquidity/slippage condition,
overfit class, mutation type, severity, and recurrence, then writes feedback evidence to
`artifacts/dopey/failure_feedback/failure_feedback_registry.jsonl` and
`artifacts/dopey/failure_feedback/feedback_optimizer.jsonl`.

The first feedback run generated `65` bounded recommendations and `16` valid replay-only
feedback mutations. It selected
`genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern` as the best replay-only
candidate over the previous mutation champion, with no overfit regression. This is still
fixture-only paper research. It is not a profit claim and not live readiness.

All feedback remains deterministic, offline, fixture-based, and paper-only. Live promotion stays
impossible: feedback decisions may be `accepted_replay_only`, `accepted_research_only`,
`rejected_no_improvement`, `rejected_overfit_worse`, `rejected_safety`,
`rejected_failure_regression`, or `advisory_only`; they may not be `live_candidate`,
`micro_live`, `adaptive_live`, or `live`. Broker execution remains blocked by config,
PaperBroker, and live broker stubs.

## IV Surface, Skew, And Term-Structure Fixture Intelligence

DOPEY now includes deterministic IV surface, skew, term-structure, and volatility-regime fixture
intelligence for paper replay. The model covers IV expansion opportunity, IV crush danger,
premium overpayment traps, front-expiry event bumps, backwardation, contango, wing elevation,
put-skew and call-skew pressure, surface instability, compression opportunity, expansion traps,
and theta/vega mismatch.

This intelligence is wired into walk-forward replay, tournament scoring, mutation-compatible
rows, failure-mode mining, failure-feedback recommendations, champion registry records, and
ProofLedger records. The current surface bundle emits all nine requested IV surface failure modes
and keeps their recommended actions replay-only.

All of this remains deterministic, offline, fixture-based, and paper-only. Live promotion remains
impossible: DOPEY still runs in `RESEARCH` mode with `live_trading_enabled=false`,
`funded_broker_connections_enabled=false`, and `allow_unofficial_robinhood_api=false`. Broker
execution remains blocked by PaperBroker and live broker stubs.

## Macro-Event Fixture Intelligence

DOPEY now includes deterministic macro-event fixture intelligence for paper replay. It models
CPI/PPI/FOMC/jobs/rate-shock/dollar/VIX/VVIX/breadth/sector/liquidity/overnight/risk-on/risk-off
regimes as offline fixtures, not as real macro data integration.

The layer computes family-specific macro fit (`directional_convexity`, `volatility_expansion`,
`volatility_compression`, `short_duration_defined_risk`) against 14 deterministic macro scenarios.
The macro score nudges `AnalysisFusionScore`, contributes to tournament combined scoring, feeds
the failure-mode miner and feedback optimizer, and is recorded in the champion registry and
ProofLedger. It is explicitly deterministic fixture math ? not a real macro calendar, FRED feed,
VIX stream, futures data, or live market input.

Live promotion remains impossible from this path. The macro-event bundle runs only in
`RESEARCH`/`PAPER` modes, never promotes to `micro_live`/`adaptive_live`/`live_candidate`, and
never connects to a broker, network data source, or real execution venue.

## Offline Ensemble Strategy Allocator

Dopey now allocates **simulated paper attention** across strategy families and candidate
genomes via a deterministic offline ensemble allocator. It consumes tournament, mutation,
feedback, failure-mode, macro, IV/Greeks, liquidity/slippage, and pattern evidence and emits
paper-only weights that sum to 1.0 across accepted candidates, with conservative single /
family / overfit caps and deterministic tie-breakers.

This is **not real capital allocation**. It does not size a live account, place broker
orders, or compute real PnL. Every weight is a simulated paper research attention unit,
deterministic and reproducible from fixture inputs.

The allocator stays fully offline, fixture-based, and paper-only. Live promotion remains
impossible: the only decisions emitted are `increase_paper_attention`,
`hold_paper_attention`, `reduce_paper_attention`, `starve_weak_signal`,
`quarantine_overfit`, `research_only`, and `reject`. Forbidden live decisions are rejected
at runtime. PaperBroker still refuses `live_allowed=true`, the Robinhood / Alpaca / Tradier
stubs still raise `LiveTradingDisabledError`, and no broker connection, credentials,
network market data, scheduled run, or Blunder modification occurs.

## Offline Meta-Governor for Proof-Weighted Promotion

Dopey now has a deterministic **paper-only** strategy governance layer: an offline
meta-governor that consumes all current evidence layers and emits proof-weighted
promotion, demotion, and quarantine decisions across paper/research tiers. It scores proof
quality, family/regime trust, and promotion eligibility, and records explicit (but
documentation-only) live-migration conditions for any future human review.

It **never enables live trading**. The only tiers it can emit are `offline_mutation_champion`,
`paper_champion`, `offline_ensemble_member`, `paper_candidate`, `paper_watchlist`,
`research_only`, `quarantine`, and `rejected`. Forbidden live tiers are rejected at runtime.

It is **not real performance evidence** ? all scores are deterministic fixture math.

Live promotion remains impossible from this path. The governor runs only in `RESEARCH`
mode, performs no broker connection, credentials, network access, scheduled run, or real
capital deployment, and creates no auto-live migration path. PaperBroker still refuses
`live_allowed=true`, the Robinhood / Alpaca / Tradier stubs still raise
`LiveTradingDisabledError`, and the original Blunder remains unchanged.


## Larger Regime/Holdout Corpus V2

Dopey now tests strategies across a broader deterministic regime + holdout corpus
(`DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`). The v2 corpus adds 32 new fixture windows
across 5 categories ? sector-specific, macro-shock, IV/volatility-transition, liquidity/
fill-stress, and cross-family-challenge ? on top of the 24-window stronger-walk-forward
v1 corpus (56 total). The v2 runner (`dopey_walk_forward/run_regime_holdout_corpus_v2.py`)
replays every strategy candidate across the v2 corpus, scores v2 consistency, produces
a v1-vs-v2 consistency delta, and writes registries to
`artifacts/dopey/regime_holdout_corpus_v2/`. The meta-governor now reads the v2
registry as a new evidence layer; the ensemble allocator stamps each candidate with
`corpus_v2_consistency_score` and applies a corpus-v2 consistency component and penalty
to the allocation breakdown; the audit recognizes the
`regime_holdout_corpus_v2_*` artifact types; the champion registry writes a
`champion_corpus_v2.jsonl` record.

This remains deterministic fixture evidence, not live performance evidence. The v2
corpus is engineered to be punishing: every family is challenged by at least 5
high-uncertainty windows. The strongest tier remains `directional_convexity` even
under broader stress. Live promotion remains impossible: the runner runs only in
`RESEARCH` mode, performs no broker connection, credentials, network access, scheduled
run, or real capital deployment, and creates no auto-live migration path. PaperBroker
still refuses `live_allowed=true`; live stubs still raise `LiveTradingDisabledError`;
the original Blunder remains unchanged. See
`DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2_REPORT.md` and
`DOPEY_REGIME_HOLDOUT_CORPUS_V2_LEDGER.md`.



## Stronger Walk-Forward Consistency Expansion

Dopey now validates strategies across rolling, blocked, anchored, regime-holdout, and
stress-holdout splits via the **stronger walk-forward consistency layer**
(`dopey_walk_forward/consistency_models.py`, `split_builder.py`, `consistency_score.py`,
`consistency_verdict.py`, `consistency_runner.py`,
`run_stronger_walk_forward_consistency.py`). The expanded corpus is **24 windows across
18 regime tags**; the runner builds 8+ deterministic splits, replays every strategy
candidate (base, mutation, feedback, ensemble, meta-governor, champion) across every
split, computes a 14-component consistency score, emits per-strategy verdicts, per-family
profiles, and a plan-level holdout robustness score, and writes registries to
`artifacts/dopey/walk_forward_consistency/`. The meta-governor now consumes the stronger
consistency as an evidence layer; the ensemble allocator stamps each candidate with its
consistency score and penalizes weak consistency; the failure-mode feedback optimizer
emits a `holdout_consistency_guard` recommendation for `overfit_train_only` and
`holdout_collapse` modes; the evidence replay audit recognizes the new artifact types and
includes a stronger consistency summary in its registry record; the champion registry
records the consistency verdict and holdout robustness.

This remains deterministic fixture evidence, not live performance evidence. Live
promotion remains impossible: the runner runs only in `RESEARCH` mode, performs no
broker connection, credentials, network access, scheduled run, or real capital
deployment, and creates no auto-live migration path. PaperBroker still refuses
`live_allowed=true`; live stubs still raise `LiveTradingDisabledError`; the original
Blunder remains unchanged. See `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_REPORT.md` and
`DOPEY_WALK_FORWARD_SPLIT_LEDGER.md`.


## Offline Evidence Replay Audit Harness

Dopey now audits its own proof chain. The **offline evidence replay audit harness**
(`dopey_audit`) reloads all existing ProofLedger records and registries, replays selected
deterministic computations, recomputes reproducibility hashes, checks cross-layer
consistency, scans for safety-boundary drift, and produces an evidence gap plan.

The audit is:

- **Deterministic** ? same artifacts always produce the same audit output (timestamps
  aside, which are not used for reproducibility verdicts).
- **Offline** ? it never fetches market data, connects to a broker, or uses network access.
- **Paper/research governance only** ? it reports but never emits live promotion,
  real-capital allocation, or broker orders.
- **Not live performance evidence** ? it verifies reproducibility and internal consistency
  of DOPEY's own fixtures and records; it does not validate any live market claim.

The harness answers: Are stored records reproducible? Do tournament, mutation, feedback,
ensemble, and meta-governor layers agree? Are champions consistent with supporting
evidence? Are forbidden live decisions absent? Is the safety state unchanged? It writes
audit registries to `artifacts/dopey/audit/` and is executed with:

```text
python -m dopey_audit.run_offline_evidence_replay_audit
```

Live promotion remains impossible. The harness will raise a `fail_safety` verdict if any
active forbidden live decision appears, if live trading becomes enabled, or if safety
boundaries change. The current audit verdict is `pass` with identified evidence gaps;
the top gap is `insufficient_walk_forward_consistency`, so the next recommended build
target is `stronger_walk_forward_consistency_expansion`.


Dopey now has a deterministic **paper-only** strategy governance layer: an offline
meta-governor that consumes all current evidence layers and emits proof-weighted
promotion, demotion, and quarantine decisions across paper/research tiers. It scores proof
quality, family/regime trust, and promotion eligibility, and records explicit (but
documentation-only) live-migration conditions for any future human review.

It **never enables live trading**. The only tiers it can emit are `offline_mutation_champion`,
`paper_champion`, `offline_ensemble_member`, `paper_candidate`, `paper_watchlist`,
`research_only`, `quarantine`, and `rejected`. Forbidden live tiers are rejected at runtime.

It is **not real performance evidence** ? all scores are deterministic fixture math.

Live promotion remains impossible from this path. The governor runs only in `RESEARCH`
mode, performs no broker connection, credentials, network access, scheduled run, or real
capital deployment, and creates no auto-live migration path. PaperBroker still refuses
`live_allowed=true`, the Robinhood / Alpaca / Tradier stubs still raise
`LiveTradingDisabledError`, and the original Blunder remains unchanged.

## Sector, Peer, and Fundamental Fixture Intelligence

DOPEY now scores deterministic sector / peer / fundamental / valuation /
earnings-quality / crowding fixture intelligence on top of every tournament window
and exposes it through the analysis fusion, tournament, walk-forward consistency,
corpus v2, ensemble allocator, meta-governor, failure-mode miner, failure-feedback
optimizer, evidence audit, and champion registry. Every score in this layer is a
deterministic 0..1 fixture score: it is not real fundamentals, not real SEC filings,
not real analyst data, not real sector ETF data, and not real institutional flow.
The fundamental expansion remains fixture evidence only and never becomes a live
performance claim. Live promotion remains impossible from any path.

## Tournament Performance Reporting Dashboard

DOPEY now has a deterministic, offline, paper-only reporting dashboard layer:
`DOPEY_TOURNAMENT_PERFORMANCE_REPORTING_DASHBOARD_ARTIFACTS_V1`.

The reporting layer reads the existing fixture/proof artifacts and writes:

- per-strategy report cards;
- per-family report cards;
- scenario and regime explainability cards;
- deterministic cross-layer performance attribution records;
- a dashboard index;
- a static offline dashboard HTML file;
- a reporting proof ledger.

The reporting bundle is invoked with:

```text
python -m dopey_reporting.run_tournament_performance_reporting_bundle
```

The current output reports `37` strategies, `4` families, `81` scenario cards,
`35` regime cards, and `37` attribution records. The dashboard's top reporting
strategy is `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`;
the top reporting family is `short_duration_defined_risk`. This is not a live
promotion and not real performance evidence. It is a fixture-only explanation of
the current paper evidence stack.

The audit harness recognizes the reporting artifacts and enforces strict hash
checks on the dashboard index, strategy report cards, and family report cards.
All reporting records remain `paper_only=true`, `live_allowed=false`, and
`live_blocked=true`. The live boundary remains unchanged: no broker connection,
credentials, real market-data fetch, order routing, scheduled process, or Blunder
source modification is introduced.
## Artifact Compaction and Export Verifier

DOPEY now has a deterministic artifact compaction and export verifier: `DOPEY_ARTIFACT_COMPACTION_EXPORT_VERIFIER_V1`.

The verifier packages proof, report, dashboard, audit, registry, and safety artifacts into portable handoff bundles with manifests, SHA256 hashes, compacted JSONL ledger summaries, file inventories, safety scans, local verification, shared-folder copy verification, and append-only export proof records.

Exports are offline and paper-only. They do not connect to brokers, request credentials, fetch market data, create a live dashboard server, schedule automation, or grant execution authority. Export bundles carry evidence for review only; they are not live performance evidence and cannot promote a strategy to any live state.

The verifier excludes credentials, `.env` files, `.git`, caches, virtual environments, original Blunder source trees, and previous export bundles. Original Blunder is represented only by a generated integrity status reference. Live promotion remains impossible from this path.
## Export Bundle Review Assistant Artifacts

DOPEY now creates deterministic offline review packets for exported handoff bundles through `DOPEY_EXPORT_BUNDLE_REVIEW_ASSISTANT_ARTIFACTS_V1`.

The review assistant is static artifact generation only. It reads the verified export manifest, copy proof, audit state, reporting artifacts, and safety state, then writes checklist, executive summary, findings, evidence map, priority queue, safety summary, next steps, dependency graph, registry, and proof records under `artifacts/dopey/export_reviews/`.

The review assistant is not a chat agent, web server, live dashboard, scheduler, deployment system, broker adapter, market-data connector, credential flow, or execution agent. Review artifacts are offline and paper-only. They summarize fixture evidence for human handoff review and do not claim live performance.

Live promotion remains impossible from this path: `mode=RESEARCH`, `live_trading_enabled=false`, `funded_broker_connections_enabled=false`, `allow_unofficial_robinhood_api=false`, and `live_blocked=true` remain the required state. PaperBroker and broker stubs still block live execution.
## Active Long-Premium Options Policy Kernel

Dopey now has a deterministic active-trading canon for long-premium equity and ETF options: `dopey-active-long-premium-options-policy-v1`.

The active policy converts the research report `C:\Users\CH\.codex\attachments\22557764-db5d-4d2f-9a07-c34bf81d122d\pasted-text.txt` into an offline governor kernel at `dopey_governor/active_trading_policy.py`. The kernel is paper-only and enforces:

- swing-first behavior rather than default same-day churn;
- 0DTE as a special catalyst sleeve with one of three declared lifecycle states: `hold_to_expiration_worthless_tolerant`, `exercise_capable`, or `forced_broker_liquidation_tolerant`;
- long-premium or net-debit options only;
- no uncovered, naked, undefined-risk, or short-vol premium-selling structures;
- equity and ETF underliers only;
- limit orders for openings, with market-style exits allowed only as explicit emergency sell-to-close fail-safes;
- liquidity, spread, open-interest, volume, forecast-move, convexity-value, surface-quality, and multi-signal confirmation thresholds;
- tighter size and spread caps for 0DTE;
- recursive improvement only in alpha layers such as signal ranking, regime weighting, execution thresholds, ensemble allocation, and surface-model calibration.

Recursive improvement cannot alter the hard safety layer. Any proposal that weakens safety rules, touches hard rules, requests live enablement, or leaves paper-only mode is rejected before scoring.

Offline fixtures live at `dopey_data/fixtures/active_trading_policy/long_premium_policy_cases.json` and cover approved swing premium, approved event 0DTE, rejected 0DTE put exercise, rejected same-day churn, rejected market openings, rejected undefined short vol, rejected illiquid chains, rejected premium overpayment, approved alpha-layer recursive improvement, rejected safety-layer mutation, and rejected overfit mutation.

Validation:

```text
python -m pytest tests/test_active_trading_policy.py
python -m pytest tests/test_pipeline.py tests/test_active_trading_policy.py
```

The active policy remains an offline research and paper-governance layer. It is not a live performance claim, broker connection, market-data feed, order router, or live promotion path.

## Active Policy System-Wide Integration

Dopey active trading policy is now system-wide for active-policy intents. The policy remains long-call/long-put-only, paper-only, and live-blocked.

The no-day-trade rule is enforced at multiple layers: order-intent validation, no-day-trade guard, position lifecycle, PaperBroker, audit, reporting, and export review. Normal same-day open/close round trips are rejected.

0DTE is not a normal day-trading loophole. It is modeled as a special lifecycle that requires explicit lifecycle state, liquidity approval, risk cap approval, and reason code for special same-day expiry handling.

PaperBroker independently enforces active policy for active-policy intents. It rejects sell-to-open, naked sale, unsupported active spreads, normal same-day close, and live flags even if upstream validation is bypassed.

Audit recognizes active policy artifacts and detects missing policy artifacts, same-day round-trip violations, undefined-risk active candidates, forbidden live decisions, credentials, broker paths, and scheduler drift.

Live remains blocked: `mode=RESEARCH`, `live_trading_enabled=false`, `funded_broker_connections_enabled=false`, `allow_unofficial_robinhood_api=false`, and `live_blocked=true`.

## Account-Level No-Day-Trade Rotation Canon

DOPEY may rotate and swing trade actively.
DOPEY cannot normally open and close the same position on the same trading day.
DOPEY tracks account-level position lifecycle before approving exits.
DOPEY delays exits and rotations when same-day close would violate policy.
0DTE remains special lifecycle handling, not normal day-trading behavior.

## 0DTE Special Lifecycle Risk Model Canon

- 0DTE is allowed only through the special lifecycle risk model.
- 0DTE candidates require stricter liquidity, spread, slippage, IV, Greeks, proof, and lifecycle controls.
- 0DTE cannot be used as normal day-trading churn.
- PaperBroker rejects 0DTE candidates without risk model approval.

## 0DTE Expiry Outcome Replay Canon

- DOPEY replays 0DTE paper outcomes through deterministic expiry/outcome fixtures.
- 0DTE replay feedback is advisory and does not approve live trading.
- Blocked candidates that perform well in fixture replay require more evidence, not automatic promotion.
- 0DTE special-close behavior remains controlled by explicit lifecycle rules.

## 0DTE Threshold Feedback Optimizer Canon

DOPEY can optimize 0DTE thresholds through fixture replay feedback.

Threshold optimization is advisory and promotion-gated.

Unsafe approvals reject threshold candidates.

Blocked candidates that perform well in replay require more fixture coverage, not automatic approval.

The threshold optimizer cannot enable live trading, broker execution, credential access, real market data, same-day churn, or live/default threshold mutation.

## 0DTE Adversarial Fixture Canon

- DOPEY expands 0DTE proof through adversarial deterministic fixtures.
- Adversarial replay is offline evidence only.
- Policy loophole attempts are explicitly tested and rejected.
- Threshold candidates must survive adversarial replay before stronger promotion.
- Adversarial corpus cannot enable live trading or broker execution.
## 0DTE Cross-Underlying V2 Canon

DOPEY tests 0DTE logic across synthetic underlying families and regime families.

Cross-underlying fixtures are deterministic offline evidence only.

Threshold candidates must survive cross-underlying stress before stronger promotion.

Policy loopholes must remain blocked in every synthetic underlying family.

Cross-underlying evidence cannot enable live trading, broker execution, credentials, same-day churn, or deployment.
## DOPEY Hybrid Swing 0DTE V3 Canon Addendum

Hybrid V3 compares 0DTE candidates with multi-day long-call/long-put swing alternatives using synthetic fixtures only. Swing entries are buy_to_open, exits are sell_to_close, normal same-day swing closes remain blocked, next-trading-day or later closes remain eligible, and 0DTE same-day exits still require the special lifecycle. Allocator tags are proof-only and real sizing is not allowed.

## Proof-Weighted Paper Allocation Canon

DOPEY uses proof-weighted paper allocation for long-premium options.

Allocation is paper-only and uses abstract risk units, not dollars.

0DTE allocation is stricter and capped.

Swing candidates may receive more paper allocation when hybrid replay favors them.

Allocation cannot override no-day-trade, PaperBroker, live-blocking, or broker-safety gates.

Allocation cannot enable live trading, broker execution, credentials, or real capital sizing.
## Portfolio-Level Paper Replay Canon

- DOPEY performs portfolio-level paper replay before broker readiness.
- Portfolio exposure replay uses abstract paper units only.
- 0DTE exposure is capped at portfolio level.
- Swing exposure is controlled at portfolio level.
- Paper-shadow states remain contained.
- Delayed-rotation states remain advisory until policy allows execution.
- Portfolio replay cannot override no-day-trade policy.
- Portfolio replay cannot override PaperBroker.
- Portfolio replay cannot override live blocking, broker safety, or credential boundaries.
- Portfolio replay cannot enable live trading, broker execution, real sizing, buying power, account balances, live orders, schedulers, deployment, or original Blunder modification.
## Portfolio Stress Ladder Canon

- DOPEY uses offline stress ladders before broker readiness.
- Crisis mode throttles paper allocation under escalating stress.
- Lockdown blocks new entries and preserves audit-only behavior.
- Crisis mode cannot force same-day close.
- Crisis mode cannot override no-day-trade policy, PaperBroker, live blocking, broker safety, or credential boundaries.
- Crisis mode cannot enable live trading, broker execution, real sizing, buying power, account balances, or deployment.

## Kill-Switch And Incident Response Canon

DOPEY rehearses kill-switch and incident response offline before broker readiness. Incident response can throttle, lock down, require manual review, or terminal-block unsafe paths. Incident response cannot force same-day close. Incident response cannot override no-day-trade policy, PaperBroker, live blocking, broker safety, credential boundaries, scheduler boundaries, or validation truth. Full-suite timeout is never a pass. Incident response cannot enable live trading, broker execution, real sizing, buying power, account balances, credentials, scheduler, or deployment.

## Active Option Lifecycle Canon

DOPEY simulates the complete active lifecycle of long calls and long puts before broker readiness. Lifecycle simulation is paper-only and fixture-only. PaperBroker and account ledger are authority gates in the lifecycle. Normal same-day open/close remains blocked. 0DTE requires special lifecycle proof. Swing exits require next-day-or-later eligibility. Lifecycle simulation cannot enable live trading, broker execution, real sizing, buying power, credentials, scheduler, deployment, or Robinhood integration.

## Broker-Readiness Preflight V1 Canon

- DOPEY has a broker-readiness preflight checklist and read-only boundary simulator.
- This is not broker integration.
- This is not Robinhood MCP integration.
- This is not credential setup.
- This is not live trading.
- Future read-only broker capability detection requires explicit manual approval.
- Write/execute/order-placement/cancel/credential/scheduler/network/live paths remain blocked.
- Broker-readiness simulation cannot enable live trading, broker execution, real sizing, buying power, credentials, scheduler, or deployment.

## Manual Approval Packet Canon - 2026-07-04

- DOPEY has a manual approval packet for a future read-only broker capability detector.
- The packet does not approve or run the detector.
- The future detector requires exact explicit human approval.
- The approval is scope-limited to read-only capability detection.
- Credentials, live orders, order placement, order cancellation, scheduler, broker execution, real sizing, and autonomous live trading remain forbidden.
- Any bypass attempt terminal-blocks.

## Read-Only Detector Dry-Run Fixture Validator Canon

DOPEY has a dry-run fixture validator for a future read-only broker capability detector. The dry-run validator is not broker integration. The dry-run validator does not run a detector. The dry-run validator does not connect, authenticate, trade, schedule, size, or use live market data. Approval remains missing until explicit exact approval is given. Any dry-run bypass attempt terminal-blocks.

## Read-Only Detector Dry-Run Fixture Validator Canon

DOPEY has a dry-run fixture validator for a future read-only broker capability detector. The dry-run validator is not broker integration. The dry-run validator does not run a detector. The dry-run validator does not connect, authenticate, trade, schedule, size, or use live market data. Approval remains missing until explicit exact approval is given. Any dry-run bypass attempt terminal-blocks.

## DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_V1
- DOPEY validates read-only detector approval text through an offline intake validator.
- Exact approval validation does not run the detector.
- Approval is not effective for broker connection, credentials, live orders, scheduler, real sizing, or live trading in this bundle.
- Invalid or scope-expanding approval terminal-blocks.
- A future detector run still requires a separate explicitly approved bundle.

## DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_V1

- status: `handoff_gate_validated`
- future_bundle_eligible_count: `12`
- current_detector_run_allowed_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- separate_future_bundle_required: `true`
- explicit_reapproval_required: `true`
- pre_run_safety_scan_required: `true`
- post_run_evidence_required: `true`

## DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_V1

- status: `pre_run_safety_scanner_validated`
- future_bundle_preparation_allowed_count: `16`
- detector_run_allowed_now_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- command_templates_disabled: `true`
- separate_future_bundle_required: `true`
- explicit_reapproval_required: `true`
- pre_run_safety_scan_required: `true`
- post_run_evidence_required: `true`
- pre_run_scanner_does_not_run_detector: `true`
- future_bundle_preparation_is_not_broker_connection: `true`
- boundary_leak_terminal_blocks: `true`

## DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_V1

- status: `human_approved_read_only_detector_validated`
- detector_status_distribution: `{'not_run_approval_missing': 31, 'not_run_manual_review_required': 1, 'not_run_terminal_block': 20, 'read_only_detector_fixture_completed': 68}`
- post_run_evidence_written: `true`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`

## DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_V1_FINAL_CANON

- DOPEY has a human-approved read-only broker capability detector framework.
- Approval is required before any detector path can run.
- Detector is read-only capability discovery only.
- Detector cannot place, cancel, or review live orders.
- Detector cannot use credentials, scheduler, real sizing, buying power, account balance, or broker write/execute tools.
- Detector output is not live readiness.
- Detector output cannot enable live trading.
- Final detector status distribution: `{'not_run_approval_missing': 31, 'not_run_manual_review_required': 1, 'not_run_pre_run_blocked': 1, 'not_run_terminal_block': 19, 'read_only_detector_fixture_completed': 68}`.

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_REAL_DATA_BACKTEST_SPINE_V1

DOPEY now has an offline local daily OHLCV history-data spine for real-data backtest preparation. The spine only reads local CSV or JSONL files under dopey_data/history/raw/ when they are pinned in dopey_data/history/history_dataset_manifest.json with SHA-256 hashes. Missing local files, placeholder manifests, malformed OHLCV rows, duplicate symbol/date rows, missing required symbols, stale symbols, and hash mismatches do not pass. The current repo state is missing_real_dataset with zero rows and no symbols covered.

This bundle does not fetch market data, connect to brokers, request or store credentials, place or review orders, enable live trading, create a scheduler, use account balance or buying power, or create real capital sizing. The next recommended target is DOPEY_MODEL_REPRICER_V1 after a valid local historical dataset is supplied.

## DOPEY_REAL_DATA_BACKTEST_SPINE_V1_CORRECTED_NOTE

DOPEY now has an offline local daily OHLCV history-data spine for real-data backtest preparation. The spine only reads local CSV or JSONL files under dopey_data/history/raw/ when they are pinned in dopey_data/history/history_dataset_manifest.json with SHA-256 hashes. Missing local files, placeholder manifests, malformed OHLCV rows, duplicate symbol/date rows, missing required symbols, stale symbols, and hash mismatches do not pass. The current repo state is missing_real_dataset with zero rows and no symbols covered.

This bundle does not fetch market data, connect to brokers, request or store credentials, place or review orders, enable live trading, create a scheduler, use account balance or buying power, or create real capital sizing. The next recommended target is DOPEY_MODEL_REPRICER_V1 after a valid local historical dataset is supplied.

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_MODEL_REPRICER_V1 Canon State - 2026-07-05

DOPEY_MODEL_REPRICER_V1 is an offline, paper-only model-pricing layer for long-premium call and put backtesting infrastructure. It provides Black-Scholes based pricing, implied-volatility solving, an offline volatility surface model, and deterministic mark-to-market path repricing. It is not live trading, not broker integration, not credential setup, not order execution, and not real capital sizing.

Current canonical pricing-source distribution is fixture_only=105, model_priced=15, quote_priced=0. No output may be labeled quote_priced until valid real options quote or chain data exists in a later authorized bundle.

Current dataset limitation remains history_dataset_status=missing_real_dataset, real_history_absent=True, real_option_chain_absent=True. Therefore this bundle creates model-pricer validation evidence only and does not create real historical backtest results or profitability claims. The next recommended target is DOPEY_REAL_SIGNAL_ENGINES_V1.
## DOPEY_HONEST_BACKTESTER_V1 Canon Note (2026-07-05 15:04:00-05:00)

- DOPEY's honest backtester is an offline, paper-only spine that maps computed directional setups into long-call/long-put/no-trade validation records.
- Model-priced P&L is abstract premium-unit validation only and must not be treated as real backtest validity, edge, profitability, or live readiness while real OHLCV and real options-chain data remain missing.
- Backtester artifacts live under rtifacts/dopey/backtest/; fixture math/policy cases live under dopey_data/fixtures/backtest/.
- The next build target after this spine is DOPEY_STATISTICAL_TRUTH_LAYER_V1.

## DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1 Canon Note (2026-07-05 16:18:50-05:00)

- DOPEY fitness is now truth-gated: strategy scoring/ranking/promotion must consume the statistical truth layer and cannot promote when the truth gate blocks promotion.
- Fixture/model diagnostics may produce a diagnostic score, but that score is not real edge, real alpha, profitability, live readiness, or strategy promotion evidence.
- Old proxy fitness concepts such as combined_score, proxy_score, expected_outcome, paper_shadow_candidate, promotion_candidate, and strategy_promoted are quarantined from promotion decisions.
- The next target is DOPEY_REAL_DATA_INGESTION_PLAN_V1.

## DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1 Canon Note (2026-07-05 16:44:32-05:00)
- DOPEY now has a truth-gated diagnostic fitness layer that consumes the statistical truth layer, metric set, bootstrap diagnostics, baselines, backtest summary, and trade records.
- Fitness scoring is diagnostic-only while real OHLCV/options-chain data is absent and cannot override the statistical truth gate.
- Promotion remains blocked: promotion_allowed=false, strategy_promoted=false, and itness_decision=hold_no_promotion.
- Old proxy/theater fitness references are quarantined; active proxy promotion inputs terminal-block if detected.
- Current state does not claim real edge, real alpha, profitability, live readiness, or strategy promotion.
- The next target is DOPEY_REAL_DATA_INGESTION_PLAN_V1.
## DOPEY_REAL_DATA_INGESTION_PLAN_V1 Canon

- This bundle is a planning and offline acquisition contract only.
- It defines required datasets, provider candidates, local staging folders, schema templates, license/provenance requirements, quality gates, and import-readiness decisions.
- It must not fetch market data, scrape market data, connect to brokers, create credentials, create .env, place orders, create a scheduler, size real capital, promote strategies, or claim real evidence.
- Current status remains real_data_ingestion_plan_ready, not real_data_ingested.
- Current decision remains plan_ready_import_not_started.
- Next allowed target is DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1 for manually staged local OHLCV only.

## DOPEY_REAL_DATA_VALIDATION_AND_OPTIONS_CONTRACT_STACK_V1

- local_ohlcv_status: missing_local_ohlcv_files
- history_spine_upgrade_status: blocked_missing_local_ohlcv
- real_signal_validation_status: blocked_missing_valid_real_history
- options_contract_status: options_import_contract_ready
- valid_real_dataset: false
- real_history_used: false
- real_signal_evidence: false
- options_data_validated: false
- quote_priced_backtest_allowed: false
- network_fetch_performed: false
- broker_connection_used: false
- credentials_created: false
- env_created: false
- paper_only: true
- live_blocked: true
- full_pytest_timeout_policy: inconclusive_timeout_is_not_pass
- next_recommended_target: DOPEY_MANUAL_REAL_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1

## DOPEY_OPEN_SOURCE_QUANT_STACK_AND_FREE_DATA_PATH_V1 Canon

This bundle permits open-source quant stack discovery as candidate/reference records only. It does not clone repositories, install dependencies, import external code, execute external code, fetch market data, scrape data, create credentials, create .env files, connect to brokers, place orders, create schedulers, use real capital, promote strategies, or claim real edge. Alpha Vantage is excluded from this path. Free/public data candidates are not evidence unless manually staged files pass license, provenance, schema, quality, and hash gates. The real OHLCV history spine activates only after local OHLCV validation passes.

## DOPEY_LOCAL_FREE_OHLCV_IMPORT_VALIDATOR_AND_HISTORY_ACTIVATION_STACK_V1

- recorded_at_utc: $stamp
- local_ohlcv_status: `missing_local_ohlcv_files`
- local_ohlcv_import_decision: `blocked_missing_local_ohlcv`
- real_data_files_present: `false`
- valid_real_dataset: `false`
- history_spine_activation_status: `blocked_missing_local_ohlcv`
- real_history_used: `false`
- real_signal_validation_status: `blocked_missing_valid_real_history`
- real_signal_evidence: `false`
- alpha_vantage_excluded: `true`
- network_fetch_performed: `false`
- broker_connection_used: `false`
- credentials_created: `false`
- env_created: `false`
- strategy_promotion_allowed: `false`
- export_verifier_status: `inconclusive_timeout`
- full_suite_status: `inconclusive_timeout`
- timeout_recorded_as_pass: `false`
- next_recommended_target: `DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1`
- recorded_at_utc_corrected: `2026-07-06T02:45:54Z`

## DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1

- Manual free/public OHLCV staging and local import fix bundle exists.
- Alpha Vantage remains excluded.
- DOPEY does not fetch, scrape, credential, or broker-connect market data for this bundle.
- Manifest draft artifacts are local-only operator aids and are not evidence or import approval.
- Current local real raw OHLCV file count remains 0; local validator stays blocked as missing_local_ohlcv_files.
- History activation remains blocked until the local OHLCV validator passes with reviewed license/provenance.
- Real signal validation remains blocked until valid real history exists.
- Strategy promotion, profitability claims, options evidence claims, and live readiness remain blocked.
- Explicit full pytest lane recorded inconclusive_timeout after 180.028 seconds; timeout is not pass.
- Next target: DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.

## DOPEY Autonomous Open Data Breakthrough Doctrine

- Unknown, ambiguous, credentialed, login-gated, paid, scrape-only, broker, Alpha Vantage, and TradingView sources are rejected by machine gates.
- Quote-priced options evidence is unavailable unless accepted open historical options chains or quotes pass license, provenance, schema, quality, and sample-size gates.
- Model-priced options research is allowed only as `model_priced_not_quote_evidence` and cannot claim profitability or live readiness.
- Missing admissible data is a successful blocked completion state when exhaustive discovery proof is written.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.

## DOPEY OpenBB Adapter Doctrine

- OpenBB is an open-source adapter/discovery layer, not automatic evidence.
- OpenBB providers requiring keys, login, payment, subscriptions, broker/account access, Alpha Vantage, Alpaca, Databento, or TradingView are rejected.
- OpenBB data can become evidence only after provider, source, license, provenance, schema, quality, and validator gates pass.
- Model-priced V2 and S-tier V2 outputs remain paper-only and cannot claim quote evidence, profitability, live superiority, or live readiness.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.

## DOPEY Wealth Engine Market Vision And Paper Tournament Canon
- Market vision, research sandbox, and paper-money tournaments do not require evidence-grade data.
- Data tiers are market_vision, research_sandbox, paper_trading, evidence_grade, with live_gate separate and disabled.
- Trade construction remains long_call, long_put, or no_trade only. Naked selling, short-vol, unsupported spreads, undefined risk, broker credentials, real orders, and automatic live deployment remain forbidden.
- P&L, drawdown, risk-adjusted survival, winner promotion, loser elimination, and mutation queue are the paper-money proof layer, not live-readiness claims.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.

## DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2 - Current Canon

- Dopey market vision and paper-money tournament may use public/no-key OHLCV as market_vision, research_sandbox, or paper_trading without evidence-grade promotion.
- Repo .venv\Scripts\python.exe is the canonical runtime for provider installs and public-data wealth reruns.
- Public OHLCV cache is authoritative ahead of fixture fallback; fixture rows must stay labeled fixture_fallback and cannot create unflagged public-data champions.
- Live trading remains disabled: no broker connection, no credentials, no real orders, no funded buying power, no automatic live deployment.
- Next money target after full primary public OHLCV load is DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1 unless a stronger public champion gate supersedes it.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.

## DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1 - Current Canon

- Public/no-key OHLCV is the active lake for public champion evolution; fixture fallback cannot overwrite active public lake files.
- Active public lake state for this bundle is 160 public symbols, 0 active fixture symbols, and 1,292,545 active public rows.
- Public-data paper champions require explicit gate survival: positive P&L and expectancy, minimum sample and symbol counts, profit factor above threshold, walk-forward persistence, stress survival, and no fixture derivation.
- No candidate cleared the champion gate in this bundle; the correct next money target is DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2.
- Live remains a separate future gate: no broker, no credentials, no `.env`, no real orders, no live trading, and no live readiness claim.

## DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2 (canonical addendum)

- Public lake final-state lock V2 keeps the lake public: 160 active public symbols, 0 fixture symbols, 1,292,545 public OHLCV rows.
- Strategy cohort canonicalizer attaches the seven cohort IDs (variant_id, micro_cohort_id, setup_cohort_id, family_cohort_id, regime_cohort_id, symbol_cluster_cohort_id, canonical_champion_id) across signals, trades, and scores.
- Dense signal mutation factory V4 produced 46,080 public-data candidates plus 32,750 near-champion expansions (target 50,000, minimum 25,000); all public-data, zero fixture signals.
- Model-priced path simulator V4 simulated 25,000 long-call / long-put / no-trade trades over realized future OHLCV paths; no short options, no spreads, no quote pricing, zero fixture trades.
- Cohort walk-forward tournament V4 scores every cohort level with sample counts, split pass rates, stress survival, child-variant dispersion, and durability.
- Champion gate V2 enforces cohort-aware sample minimums (30/30/60/100) and rejects tiny-sample and split-fragile winners; near-champion repair plans are emitted; thresholds are never lowered silently.
- 9 public paper champions promoted; live gate V2 remains locked: no broker, no credentials, no .env, no real orders, no live trading.
- Robinhood policy corrected: official agent/MCP market-data access allowed for research/paper scoring if official terms permit; unofficial access, scraping, reverse-engineering, and live trading blocked.
- Next recommended target: DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1.

## DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1 (canonical addendum)

- Champion hardening preflight verifies repo path, explicit venv, no `.env`, 9 public paper champions, clean decision artifacts, and locked live trading.
- Public signal artifact cleaner V1 removes stale SIM/TEST/FIXTURE/SYNTH rows from intermediate `public_signal_mutation_candidates_v4.jsonl` after safe backup; decision artifacts remain clean.
- Champion inventory freezes all 9 public paper champions with full evidence before stress testing.
- Deep stress matrix V1 applies slippage, theta, IV shock, entry/exit degradation, gap stress, outlier removal, concentration removal, recent-only, and regime-specific stress.
- Holdout expansion V1 retests champions across era partitions, symbol/sector holdouts, and sector exclusions.
- Decay monitor V1 tracks rolling expectancy, drawdown, losing streaks, and recent-vs-history degradation.
- Hardening gate V1 promotes hardened, conditional, or demoted statuses honestly; repair queue emits targeted mutations for failures.
- Hardening scoreboard V1 and live gate V3 keep live trading locked even for hardened champions.
- Robinhood policy: official agent/MCP market-data lane allowed; unofficial API, scraping, reverse-auth, and live trading blocked.
- Next recommended target depends on hardening outcome: extended paper shadow, repair/retune, signal research breakthrough, or public data repair.

## DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1 (canonical addendum)

- Artifact guard V1 backs up canonical tournament/gate/hardening artifacts and restores on shrinkage; test evaluators default to non-canonical write mode.
- Conditional repair planner diagnoses the 2 conditional champions and emits targeted repair plans without broad search.
- Targeted signal retune generator produces public-data-only repair candidates with full lineage for the 2 conditional champions.
- Retune path simulator replays model-priced long-call/long-put/no-trade paths over future OHLCV with stress dimensions preserved.
- Retune tournament compares before/after performance; retune hardening gate applies unchanged hardening thresholds.
- Demoted salvage analyzer classifies all 7 demoted champions as salvage_candidate, watchlist_only, permanent_demotion, or kill_confirmed.
- Live gate remains locked even if retuned champions harden. No threshold lowering.


## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1 (canonical addendum)

- Failed champion families quarantined before new discovery; repair-loop families not retuned again.
- Public feature miner builds multi-group features from public OHLCV only.
- Discovery signal family generator creates new families with quarantine overlap filtering.
- Research candidate generator spreads density across symbols/sectors/regimes.
- Research path simulator uses model-priced long-call/long-put/no-trade only over future OHLCV.
- Research tournament and breakthrough gate promote research breakthrough candidates without live promotion.
- Live gate remains locked. No profitability or live-readiness claim.


## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V2 (canonical addendum)

- V2 extracts V1 watchlist candidates and repairs generic labels into stable discovery family IDs.
- Symbol/sector density scheduler expands coverage beyond V1 six-symbol concentration.
- Watchlist mutation planner always emits non-empty mutation queue when watchlist exists.
- Tournament V2 applies coverage penalties for symbol/sector concentration.
- Breakthrough gate V2 requires stable family IDs and broader symbol/sector minimums.
- Live gate remains locked.


## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3 (canonical addendum)

- V3 executes the V2 mutation queue (31 entries) instead of only writing it.
- Stable family template repair fixes volume dry-up breakout under-generation (V1 contradictory dry-up + volume spike rules).
- Selective candidate generator V3 balances continuation and volume families with no-trade filters.
- Profit/holdout repair scorer prioritizes candidates before path simulation.
- Tournament V3 compares repair outcomes against V2 aggregate metrics.
- Breakthrough gate V3 requires improvement vs V2 on at least one repair axis.
- Active policy zero_dte_replay_outcomes artifact chain repair is paper-only.
- Live gate remains locked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


<!-- V5_PREFLIGHT_APPEND_MARKER -->
## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5 — Appended Recognition

V4 completed and routed honestly to V5. V4 final status: `pf_holdout_split_improved_requires_v5`. V4 validation: `107/107 pass`. V4 live gate remained `disabled_live_gate_locked`. V4 PF threshold was **not** lowered (`MIN_BREAKTHROUGH_PF = 1.10`).

V5 target: `DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5` (baseline-freezing, audit-completing, PF/holdout/split finishing loop).

Official Robinhood market-data lane is allowed; unofficial Robinhood API, scraping, and reverse-engineered auth are blocked. Live trading remains `false`.

Appended by `dopey_validation.safe_append_canon_validation_docs_v5` on 2026-07-08T20:28:02.832552+00:00.


<!-- V6_PREFLIGHT_APPEND_MARKER -->
## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6 - Preflight Acknowledgment

- public_signal_research_v6_preflight_status: `ready_for_watchlist_breakthrough_repair`
- v5_baseline_freeze_status: `v5_baseline_frozen`
- v5_watchlist_count: `6`
- v5_pf_above_110_count: `6`
- v5_mutation_queue_count: `132`
- live_gate_status: `disabled_live_gate_locked`
- v6_min_breakthrough_pf: `1.10` (hard floor, not lowered)
- public_data_only: `true`, paper_only: `true`, live_trading_enabled: `false`


<!-- V7_PREFLIGHT_APPEND_MARKER -->

## DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7 - Preflight Acknowledgment



- public_signal_research_v7_preflight_status: `ready_for_trade_active_breakthrough_repair`

- v6_baseline_freeze_status: `v6_baseline_frozen`

- v6_watchlist_count: `2`

- v6_pf_above_110_count: `6`

- v6_mutation_queue_count: `50`

- live_gate_status: `disabled_live_gate_locked`

- v7_min_breakthrough_pf: `1.10` (hard floor, not lowered)

- no_trade_only_breakthroughs: `blocked`

- trade_active_requirement: `trade_active_pf_above_110_and_sample_symbols_sectors_split_holdout`

- allowed_strategies: `long_call`, `long_put`, `no_trade` (model-priced only)

- pricing_model: `model_priced_only` over future OHLCV; no quote-priced unlock

- public_data_only: `true`, paper_only: `true`, live_trading_enabled: `false`

- robinhood_official_data_lane: `allowed`; unofficial Robinhood API, scraping, reverse-engineered auth: `blocked`

- integration_touch_points: `audit_loader`, `reporting_loader`, `export_selector`, `export_review`, `validation_stabilizer`




<!-- V8_REAL_DATA_ACTIVATION_APPEND_MARKER -->
## DOPEY_REAL_DATA_ACTIVATION_V8 - Provenance Correction and Real-Data Spine Activation (2026-07-09)

### Provenance disclosure (supersedes prior public-data claims in the signal-research lane)

- All `DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1..V7` candidates, trades, tournaments,
  gates, and scoreboards were generated from deterministic synthetic sources (index-derived
  feature vectors, SHA1-derived entry spots, LCG+Box-Muller price paths). No market data of any
  kind entered that lane. Prior labels `market_data_source_type: public_ohlcv`,
  `future_ohlcv_used: true`, and `public_data_only: true` in that lane were incorrect and are
  corrected at the source as of V8: the lane now emits
  `market_data_source_type: synthetic_deterministic_hash_lcg`, `synthetic_path_used: true`,
  `public_data_only: false`.
- V1-V7 results remain useful ONLY as machinery calibration; they are not signal evidence.
  The V7 top cohort PF `1.399096` was PRNG arithmetic, not edge.

### Real-data spine (ACTIVE)

- 24-symbol required universe staged by the operator (yahoo_finance via yfinance, fetched
  outside the DOPEY pipeline), 185,453 daily rows, 1973-02-21 -> 2026-07-08.
- gate 1 `local_ohlcv_validation_pass`; gate 2 `valid_real_dataset`; activation pass;
  real signal validation pass. Manifests carry reviewed license
  (`reviewed_allowed_internal_research`, redistribution false) and sha256 pins.

### Honest lane on real data (first run, model units, before costs)

- real-history signal engine: 46,690 directional setups (2015+, 10-trading-day cadence).
- real-history honest backtester: 9,333 long-premium trades along real forward bars;
  net `-538.40`, win rate `40.7%`, mean/trade `-0.0577` (bootstrap CI includes 0),
  max drawdown `-731.69`, deflated Sharpe `-0.087`.
- long_call cohorts positive (relative_strength PF 1.262, momentum PF 1.211 - drift/beta
  suspected, baseline arbitration required); long_put cohorts consistently negative.
- statistical truth layer: `insufficient_real_sample` (no quote-priced trades; real options
  chains absent); all significance/profitability/live-readiness claims BLOCKED;
  promotion_allowed `false`.

### Canonical honest-lane run order

`run_real_history_signal_engine` -> `run_real_history_honest_backtester` ->
`run_statistical_truth_layer` -> `run_fitness_function_replacement`
(fixture-lane runners overwrite shared artifacts; rerun the real lane after fixture runs).

### Binding constraint for all future promotion claims

Real options-chain (quote-priced) evidence. Until then: paper_only `true`,
live_blocked `true`, promotion blocked. Next target:
`DOPEY_REAL_COST_MODEL_AND_BASELINE_ARBITRATION_V9`.

<!-- V9_APEX_RESEARCH_STACK_APPEND_MARKER -->
## DOPEY_APEX_RESEARCH_STACK_V9 (2026-07-09)

- Cost stack live in the real lane (half-spread 2.5%/side, slippage 0.5%/side, commission):
  9,333 real trades -> gross(mid) `-538.40`, costs `-2,519.19`, **net `-3,057.59`**.
- Baseline arbitration (matched random-entry, identical engine, bootstrap CIs):
  **0 of 10 cohorts beat random at 95% CI**; 3 long_put cohorts significantly worse.
  The V8 long-call "edge" was bull-market drift.
- Era walk-forward (2015-19 / 2020-22 / 2023-26): **0 regime-robust cohorts**.
- Market-structure engine: 1,667 trap events, 2,512 volume anomalies, VRP proxy (VIX vs
  SPY realized). Trap+VRP blackout filter removed 1,193 trades averaging `-0.89` and
  improved net by `+1,065` - loss-avoidance is currently the system's only measurable skill.
- Chain analytics (GEX, gamma flip, put/call, delta pressure): math fixture-validated,
  activation gated on operator-staged licensed chain data (`blocked_no_real_chain_data_staged`).
- Resilient research supervisor: 11-stage full chain, absorb-record-continue failure policy,
  failures never recorded as pass; run `python -m dopey_autonomy.run_resilient_research_supervisor`.
- Canonical truth: after costs the current signal set has no entry edge over random timing;
  promotion remains blocked; next unlock is licensed real options-chain data (V10).

<!-- V10_OPEN_CHAIN_FORWARD_WALK_APPEND_MARKER -->
## DOPEY_OPEN_CHAIN_FORWARD_WALK_V10 (2026-07-09)

- Open-data chain lane live: operator-staged public chain snapshots (23 symbols, 2,069
  rows, ~29 DTE, manifest + sha256 pins) through `chain_snapshot_loader` gates.
- First quote-derived positioning metrics: SPY GEX -$74.5M/1% (dealer short gamma,
  put/call OI 1.97); per-symbol GEX/gamma-flip/put-call/delta-pressure artifacts.
- Model IV calibration vs 771 real ATM contracts: median IV/RV 0.976 vs simulator 1.10;
  model premium error vs mid median +14.5% -> V11 must recalibrate the simulator.
- Forward paper walk LIVE: 20 ex-ante quote-priced paper positions filled at real ask;
  marks at real bid on future snapshots; the only evidence class the truth layer can
  ever accept accrues from today at the speed of reality.
- Open-source posture: MIT LICENSE for original code; DATA_NOTICE.md - data is
  bring-your-own, never redistributed; strip dopey_data/ before publishing.
- Daily ritual: operator chain fetch, then the 13-stage resilient supervisor.

<!-- V11_APEX_FUSION_APPEND_MARKER -->
## DOPEY_APEX_FUSION_V11 (2026-07-09)

- Adversarial stress engine live: 7 shock scenarios vs the open forward book; survives
  all; worst enemy `iv_crush_50` (-54.2% of book); limits 60% book / 25% single-name.
- Gamma-regime + sector + VRP context fusion gates forward-walk entries (21/23 names
  short-gamma today; unfavorable contexts blocked). Tilt protection: entry halt on 5
  straight losses or 30% ledger drawdown.
- Multi-expiry vol surface live (skew slope, RR10, term slope); SPY put skew -1.03,
  RR10 +9.8pts; tear detection activates at 2 archive days.
- Exit-policy walk-forward search (27 cells, train 2015-21 / validate 2022-26): first
  run REFUSED its own best-train candidate (overfit caught autonomously); policy
  unchanged. Self-tuning promotes only on out-of-era improvement.
- Supervisor now 17 stages. Forward walk throughput 15/run. First judgeable ex-ante
  sample expected in 2-4 weeks of daily ritual. V9 verdict stands until forward
  evidence overturns it.

<!-- V12_ACTION_READINESS_GATE_APPEND_MARKER -->
## DOPEY_ACTION_READINESS_GATE_V12 (2026-07-09)

- "Ready for action" is now a machine-checked artifact (`dopey_broker_readiness/
  action_readiness_gate.py`, supervisor stage 18): 8 evidence checks (forward sample
  >= 100 closed ex-ante trades, forward net positive, beats-baseline at 95% CI, era
  robustness, truth-gate promotion, stress survival, no discipline halt, pricing model
  calibrated within 10%). All-green is necessary, NOT sufficient - human review is
  always the final gate.
- Robinhood MCP boundary codified: MCP registry has ZERO Robinhood connectors
  (2026-07-09); community servers use unofficial credential-based APIs - permanently
  blocked by this envelope. If an OFFICIAL read-only MCP ever exists: account
  snapshot/positions/balances for paper-mirroring only; auth in MCP client, never in
  repo; order/execution wiring blocked always.
- Data completeness note: market data needs are already met credential-free (governed
  OHLCV spine + daily chain snapshots). A broker link adds only account state and
  execution; execution is exactly what remains unearned until the gate opens.

<!-- V13_CALIBRATED_ACCELERATION_APPEND_MARKER -->
## DOPEY_CALIBRATED_ACCELERATION_V13 (2026-07-09)

- Market-supervised calibration loop CLOSED: backtester now resolves its IV multiplier
  from the latest chain calibration (1.10 -> 0.976, provenance recorded per run);
  model premium error vs real mids collapsed +14.5% -> +2.05% median; readiness check
  `pricing_model_calibrated` GREEN (gate 3/8). Recalibrated historical net: -2,327.59
  (verdicts unchanged: still no entry edge over random).
- Earnings IV-crush blackout lane live: operator tool stages upcoming earnings dates
  (11 rows staged); context fusion forces `unfavorable` bias within 3 days of a print;
  forward walk inherits the veto automatically. Weekend guard prevents stale marking
  sessions.
- Daily ritual automation: `operator_tools/daily_ritual.cmd` wrapper written; operator
  registers with: schtasks /create /tn DOPEY_DailyRitual /tr
  "C:\Users\CH\dopey\operator_tools\daily_ritual.cmd" /sc weekly /d MON,TUE,WED,THU,FRI
  /st 16:45 /f
- Remaining gate blockers are evidence-only: forward sample, forward net, baseline
  beat, era robustness, truth promotion. No code can flip them honestly - only the
  market can, through the ritual.

<!-- V13_OFFICIAL_ROBINHOOD_MCP_UPDATE_MARKER -->
## Official Robinhood Agentic Trading MCP - boundary update (2026-07-09)

- Robinhood launched an OFFICIAL MCP server (agent.robinhood.com/mcp/trading) with
  dedicated agentic accounts. The unofficial-API block no longer applies to this lane.
- Allowed now: read-only account state via the official MCP for paper-mirroring and
  reconciliation; auth in the operator's MCP client, never in-repo.
- EXECUTION stays sealed: blocked until the action-readiness gate is all-green AND a
  human explicitly approves; designated path if ever unlocked = official MCP into the
  dedicated agentic account at minimum sizing. Robinhood terms place full trade
  responsibility on the account holder; the truth layer reports no demonstrated edge.
- Daily ritual scheduled task registered by operator: forward evidence now accrues
  automatically every trading day.

## DOPEY_DEEP_HARDENING_V14 (2026-07-09, "no stones unturned" pass)

**The audit that saved the repo.** A four-agent layer audit (data spine / backtest+forward walk / options analytics / supervisor+infra) surfaced ~40 confirmed defects - and one emergency: the public-release branch dance had silently DELETED 2,124 files that were tracked on that branch but untracked on master (all of dopey_fitness, dopey_stats internals, 71 test files, fixtures, legacy sources, plus ~15.8k venv files incl. PIL). The system was running on stale bytecode and would have shattered on the next ritual. All files restored from sync commit 56776c7 and now TRACKED on master (commit b7420cd); two additional content regressions (dopey_tournament/runner.py, dopey_edge/capital_redeployment_engine.py) restored the same way. The new envelope-integrity sentinel re-verifies manifest sha256 pins every run so this class of loss is caught in minutes, not by luck.

**Three new stages (supervisor = 23):**
- `data_freshness_sentinel` (runs FIRST): trading-session staleness (weekend/holiday-aware market calendar) across OHLCV spine, chain archive, earnings calendar, forward-walk marks, and the daily-ritual heartbeat; red fails the stage. Readiness gate gains a 9th check: data_freshness_green.
- `envelope_integrity_sentinel`: credential/order-wiring source scan (assembled-fragment patterns so it never matches itself), execution-seal presence check, full manifest pin re-verification. First run: envelope_intact, 47 pins verified.
- `forward_book_risk`: portfolio dollar Greeks (delta$/gamma$ per 1%/vega$ per pt/theta$ per day) from the latest real snapshot + exact PnL attribution per open position (direction/volatility/decay/residual/friction; identity gap ~0 enforced by test).

**Truth-layer and engine fixes (audit-confirmed):** baseline arbitration now draws from each cohort's OWN (symbol, month) anchors - universe and era mix held constant, timing randomized (the old all-symbols/all-dates draw could manufacture or mask "beats baseline"). Stress engine now shocks CURRENT state (remaining DTE, latest spot/IV) instead of entry state, and an all-positive book can no longer trip the loss limit via abs(). Era walk-forward: an all-winning era is PF-passing (999.0 sentinel + flag), not PF=0-failing. Forward walk: atomic ledger writes with .bak + guarded recovery, entries idempotent per snapshot date, globally unique position ids (ledger counter), entry tenor pinned to ~30 DTE in a 21-45 band, expired-unquoted contracts settle at intrinsic, signals are one-shot (no re-entry churn), discipline halts LATCH for 5 marking sessions, signal age must be 0..7 (no future-dated signals). Chain gate glob fixed (dated subdirs), gamma-flip detects both crossing directions, put/call ratios return null (not 0.0) when undefined, earnings blackout widened to the true holding span (10d) with DictReader parsing + anchor-missing visibility, VRP exposes rich/not_rich/missing_or_stale, three log-return guards, volume-anomaly divide guard. Operator fetch: manifest hashes MERGE (prior snapshot days keep their pins - this was silently breaking archive history), snapshot dirs created only when a file lands, holiday-aware skip, empty earnings fetch preserves prior file, atomic manifest write. Ritual wrapper: %~dp0 root, exit-code capture, heartbeat JSON, log cap.

**Foundry v2 (meta layer hardened):** train-era-only standardization (full-sample z-scores leaked validation distribution into composite orderings), boundary-straddling forward windows excluded, tie-averaged Spearman ranks, and promotion now requires clearing BOTH the analytic multiple-testing bar AND a circular-shift empirical null (max-|IC| familywise, autocorrelation-preserving). A quote-derived lane (pc_oi / atm_iv / iv_skew) accrues from the chain archive and self-evaluates at 120 joinable observations - honest insufficient_sample until then.

**Supervisor upgrades:** blocked-status returns now count as completed_degraded (never green), true producer-consumer dependency edges declared (calibration->backtest, chain+surface->fusion, fusion->walk), concurrent runs blocked by a lockfile, every artifact written atomically, and an append-only run journal with per-run regression/recovery detection vs the previous run.

**Known open (queued, visible):** 38 restored legacy fixture-era tests fail on empty-repo-state assertions/API drift (repair task chip spawned); vol-surface sparse-strike metrics still default to 0.0 instead of null; market-structure filter-value analysis still collapses blackout windows to their start date; OHLCV validator lacks an OHLC-ordering warning counter. None touch the honest lane.

Verification: 12 new hardening tests + foundry tests green; focused honest-lane suite green (424 passed; all failures confined to restored legacy fixture-era files); full 23-stage supervisor run recorded in the run journal. GitHub untouched per standing privacy directive.

## DOPEY_RESOURCE_EXPANSION_V15 (2026-07-09, "review github and anywhere else" pass)

**Four new license-reviewed public data lanes** (operator-staged, sha256-pinned under `macro_context_manifest.json`, network strictly outside the pipeline):
1. **US Treasury daily par yield curve** (home.treasury.gov, US-gov public domain) - the hardcoded 4% risk-free rate is DEAD. `dopey_options/risk_free_rate.py` resolves the interpolated ~30d par yield (3.72% at activation) with provenance strings; wired into the honest backtester, IV calibration, forward-book risk, and stress engine.
2. **Volatility term structure + tail pricing** (^VIX9D/^VIX/^VIX3M/^VIX6M/^SKEW via the reviewed Yahoo lane) - ~2 years of history staged (2,492 rows), distilled to contango/backwardation state, 9d-3m slope, and SKEW 252d percentile.
3. **FINRA daily short-sale volume** (cdn.finra.org public-dissemination files, internal research) - per-symbol short-flow ratios for the whole 23-name universe, 5-session rolling stage.
4. **CFTC Commitments of Traders** (publicreporting.cftc.gov Socrata API, US-gov public data) - 104 weekly E-mini S&P legacy reports; non-commercial net z-scored vs trailing 52w (+2.26 z at activation).

**New stage 24 `macro_context_gate`**: chain-loader-grade gates (manifest, license, pins, schema) -> distilled per-run states. Policy: VISIBILITY AND FOUNDRY INPUT ONLY - no entry-bias change from these lanes until the foundry/truth layer earns one. Freshness sentinel gained a macro_context lane; the daily ritual now runs the macro fetch too.

**Foundry macro-derived lane**: vix_ts_slope_9d_3m / skew_level / vix_level joined to SPY-only forward returns (market-wide features test TIMING; pooling across symbols would fake sample size) - same rank-IC bar and 120-obs accrual gate as the quote lane.

**Truth layer upgraded to the real Bailey-Lopez de Prado statistic**: `dopey_stats/deflated_sharpe.py` now computes PSR (skew/kurtosis-aware) and DSR against the expected-max-Sharpe luck benchmark across effective trials (Euler-Mascheroni extreme-value form), replacing the linear-penalty placeholder. p_value = 1 - DSR probability. Still diagnostic_only / can veto, never promote.

**Hand-rolled IV inversion**: `greeks_engine.implied_vol_bisection` (deterministic bisection against the house BS pricer, arbitrage-band guarded, dependency-free) - chosen over adding py_vollib; zero new dependencies this pass.

**Refused acquisitions (governance)**: DoltHub community options databases (2019-2024 EOD chains) and similar unlicensed aggregations - provenance/license unreviewable, so they never enter the gates. Recorded in the macro manifest's refused_sources_note. Stooq remains refused (proof-of-work circumvention).

**Also fixed**: operator tools now self-insert the repo root on sys.path - the chains fetcher's dopey_core import would have crashed the FIRST scheduled ritual tonight (caught by running the new fetcher the same way the scheduler does).

Verification: 6 new tests green (interpolation, term-structure classification, COT z, IV round-trip, DSR properties, resolver band); macro gate live-computed on real staged data; full 24-stage supervisor run journaled.

## DOPEY_EVIDENCE_ACCELERATION_V16 (2026-07-09 night, arming Friday's session)

2-4 weeks to a judgeable sample was a POLICY artifact, not physics: the forward walk was signal-supply-bound (10-day emission cadence = ~33 fresh signals/10 sessions = ~6 weeks to 100 closed). Honest accelerators, none of which touch evidence semantics: signal cadence 10->3 trading days (155,365 setups regenerated; signals stay leak-free - denser emission just means more ex-ante bets), entry throughput 15->25/run, and the missing organ: `operator_tools/operator_fetch_daily_ohlcv.py` - a governed daily OHLCV spine updater (append-only, schema-exact, both staged copies, manifests re-pinned via the repo's canonical history_manifest_hash) wired FIRST into the daily ritual. Without it the spine could never grow past 2026-07-08 and entries would have starved within a week.

Hard lesson encoded as an invariant: yfinance's same-day ^VIX row carries zero O/H/L until finalized, and the history validator requires every symbol to reach the dataset end date (stale_symbol error). The updater therefore enforces UNIFORM ADVANCE - the spine only moves to the newest date EVERY symbol can reach; a lagging VIX holds the whole frontier for a day rather than corrupting validity. Verified live: partial advance rolled back, spine valid at 185,453 bars, frontier correctly held at 2026-07-08.

Expected accrual at the new settings: first stop/target closes possible Friday 2026-07-10; time-stop wave Tue 2026-07-14; ~100 closed trades in roughly 2 weeks of sessions. The weekend plan is hardening/calibration only - closed markets produce no ex-ante evidence and none will be fabricated.

## DOPEY_SIMULATION_AND_ATTENTION_V17 (2026-07-10, supervisor = 25 stages)

**Distributional stress (market simulation, the honest kind):** stationary block bootstrap over the governed spine's JOINT daily returns (date-blocks resampled together - cross-symbol correlation preserved exactly; seeded, deterministic). The open book re-prices along 500 counterfactual 5-day paths -> full P&L distribution instead of seven hand-picked scenarios. First live read on the 21-position book: median -20.1 premium units (theta+friction drag), 5% tail -65.9, ES5 -76.1, P(loss > 30% of premium) = 2.4%. HARD BOUNDARY: evidence_class=simulation_only, promotion_allowed=false, gate/truth layer never read it - simulation informs sizing and can only argue for SMALLER, never for readier. Synthetic paths graded as wins is the V1-V7 disease; this engine exists to measure risk, not to manufacture edge.

**Crowd-attention lane ("overhyped" made testable):** Wikimedia pageviews (OPEN data, credential-free - X/Twitter scraping refused on ToS; Reddit/StockTwits would need operator-owned creds outside the repo and are the user's call) staged for 11 single names, distilled to 60d attention z-scores + a crowded-attention research-flag list (threshold z>=2; today: none crowded, MSFT highest at 1.64). Foundry attention lane joins per (date,symbol) attention z to forward returns: first evaluation on 558 obs -> IC -0.041, clearing the base bar WITH the hypothesized negative sign (high attention -> weaker forward returns). Research input only: overlapping horizon, single window, no era split yet - it earns nothing until the full discipline passes, and per house rule it changes no entry bias.

New stages: macro-manifest now pins 5 files; `distributional_stress` (dep: forward_paper_walk). Attention state rides the macro gate artifact.

## DOPEY_CRYPTO_EXPANSION_V18 (2026-07-10)

**Universe 24 -> 27**: IBIT (BTC ETF), MSTR (BTC treasury), COIN (exchange) added to REQUIRED_HISTORY_UNIVERSE, full histories staged and pinned (IBIT 623 bars since 2024-01, MSTR 7,061 back to 1998, COIN 1,314 since IPO; spine valid at 194,451 bars, envelope 50 pins green). Chains snapshot daily from tonight; signals/backtests/forward-walk pick the names up automatically - these carry some of the most liquid high-IV options chains listed, which is where the "crypto opportunity" honestly lives for this system.

**Crypto context lane**: BTC-USD/ETH-USD daily closes (2y, weekends included - crypto trades 24/7) staged under the macro manifest; gate distills 1d/7d momentum. The leading-indicator hypothesis (weekend crypto moves -> Monday equities) is now DATA the foundry can test as it joins to forward returns; visibility and research input only, no bias change unearned. REFUSED: direct crypto exchange trading / credentialed crypto APIs - exposure via listed names only, per envelope.

## DOPEY_LEGENDS_TRIAGE_V19 (2026-07-10) - the "10 god-tier upgrades" list, honestly sorted

BUILT NOW: (8) Druckenmiller liquidity impulse - WALCL - RRP - TGA from FRED (keyless, public Fed data), weekly net-liquidity series with 4-week impulse classification (first read: $5.96T, +1.04%, "flooding"). Macro manifest = 7 lanes. Visibility/foundry input only; a sizing role must be EARNED through the discipline like everything else.

ALREADY RUNNING (the list re-invented the house): (3) Soros reflexivity = the GEX/gamma-flip/short-gamma regime engine (V9/V11) - dealer-hedging feedback is exactly what it measures; "predicting the snap point" remains fantasy. (6) Tudor Jones defense = latched discipline halts + drawdown governor + degraded!=green accounting; dynamic leverage is refused while sizing is 1-contract paper. (9) Thorp RV-vs-IV = the model-IV calibration lane (IV/RV ratios vs 771 real contracts) + VRP series; the cross-sectional IV-divergence matrix becomes computable as the chain archive deepens (atm_iv already accrues per symbol daily). (10) Meta-manager = supervisor + readiness gate + context fusion + forward-book Greeks; a book-aware entry filter (e.g. net-delta cap) is a small honest future step. (4) Taleb = a long-premium book IS positive convexity; the distributional-stress engine now quantifies the tails; a dedicated far-OTM tail cohort is a candidate signal family (roadmap). (7) Livermore = chart-vision S/R + trap detector; multi-year compression scan is a cheap extension (roadmap); intraday sweep tape requires licensed data (refused for now).

ROADMAP (real but not today): (1) Burry filings lane - SEC EDGAR is public domain and dopey_data/sec_filing_adapter.py exists; a filings-vs-IV research lane is the right shape, a "RAG that finds catastrophic flaws" is not a promise anyone can make. (2) Buffett moat scoring as a fundamentals lane; the WHEEL (selling cash-secured puts) is REFUSED - short-premium assignment risk is outside the long-premium envelope.

REFUSED: (5) Simons L3 microstructure/dark-pool ML - requires licensed microsecond order-book data and an HFT horizon this daily paper system does not have; pretending otherwise is the V7 disease in a lab coat.

## DOPEY_INSIDER_LANES_V20 (2026-07-10)

**Congressional STOCK Act lane (macro manifest = 8 files)**: senate-stock-watcher aggregate verified STALE (ends 2020-12) and rejected; kadoa-org/congress-trading-monitor (parses the official House Clerk + Senate eFD portals, current through 2026-06) adopted as source. 1,400 universe transactions staged since 2025-01-01; gate distills trailing-90d net buy-minus-sell counts + notable-flag lists (first read: notable buying AMD +6, JPM +4, META +3; no notable selling). HONEST LIMITS in the artifact itself: up to 45-day disclosure lag, amount ranges only, unknowable motives - an attention/positioning research flag, never a copy-trade, no bias change unearned.

**Burry adaptation verdict**: his public trail IS adaptable - Scion's 13F filings (SEC EDGAR, public domain, CIK 1649339, 45-day lag, put positions visible as listed options) are the designed next lane using the same pattern as the congress lane; his METHOD is partly native to the house already (deep-OTM asymmetric long premium = our only book shape; filings-footnote NLP = V19 roadmap item with the EDGAR adapter already in-repo).

## DOPEY_SANDBOX_STRATEGIES_TRIAGE_V21 (2026-07-10) - the "10 god-tier sandbox" list, honestly sorted

Meta-read: nearly every item smuggles in one or both of the exact two moves the whole DOPEY discipline exists to block - (a) touching LIVE markets / REAL capital (auto-push code to prod, unlock capital autonomously, fire orders at market makers, sell premium live, probe broker endpoints), and (b) letting SIMULATION manufacture edge or readiness instead of only bounding risk. Value = extract the honest kernel, discard the deployment fantasy wrapped around it.

ALREADY RUNNING (the list re-invented the house):
- (3) Black-swan stress chamber = V17 distributional-stress engine (joint block bootstrap, 500 paths) + adversarial stress engine. Honest by construction: sizing-only, evidence_class=simulation_only, gate never reads it. "Muscle memory that changes entry behavior" = fabricated edge -> refused. Cheap honest extension: named scenario classes (gap-down / liquidity-hole IV blowout / vol-spike) as extra risk probes.
- (8-detect) Retail honey-pot DETECTION = V17 attention lane (Wikimedia z) + IV-percentile screen; honest use is a FADE/AVOID filter ("don't buy premium when IV pctile >95 and attention crowded"), never selling it.
- (9-analysis) Greek topology = chain analytics already compute gamma-flip/pc_oi/skew; a dealer-GEX + skew-surface map is reasonable risk context. "Computer vision on a rendered image" is theater - the kink is already numeric.
- (5-partial) Multi-agent debate = truth gate + baseline arbitration + adversarial stress already ARE the skeptic.

ADAPTABLE (roadmap, with discipline):
- (1) Darwin-Godel mutation coliseum -> GOVERNED parameter tournament only: variants scored on HELD-OUT eras with deflated Sharpe (dopey_tournament/runner.py + OVERFIT_RANK exist), human-gated promotion. REFUSED: self-modifying code auto-pushing to any live/prod path = the V1-V7 overfitting disease in a genetic-algorithm hat, and "prod" here does not exist.
- (2) Ratchet trace-replay coach -> post-close diagnostic that reads CLOSED forward-walk losers and emits candidate hypotheses for the FOUNDRY to test on held-out data. REFUSED: rewriting logic to fit the replayed losers (in-sample curve-fit) or auto-committing changes.
- (5) Debate panel -> explicit bull/bear/risk adversarial panel over each candidate signal; Kelly as a sizing CEILING not a green light (Kelly on an unproven edge = 0).
- (7) Hedging rehearsal room -> per-open-position exit playbook via the existing bootstrap reprice (if spot hits X / IV craters Y -> planned adjustment). Honest as risk planning; "fast-forward time / zero-latency live execution" is out of envelope and the paths are risk scenarios, never predictions.

REFUSED (not merely off-strategy - legal / safety / statistics):
- (4) Order-book spoofing simulator - firing dummy orders to map/evade market makers is SPOOFING, criminal under Dodd-Frank s747 regardless of sandbox intent-to-cancel; doubly moot (paper-only, no execution). Honest cousin: model our OWN market impact so paper fills are not fantasy.
- (6) Permeable-membrane capital firewall - AUTONOMOUS unlocking of REAL capital on a rolling-7-day Sharpe is the most dangerous idea on the list: no human gate + a window far too short to separate skill from luck (deflated-Sharpe machinery exists precisely to prove 7 days is noise). Only honest kernel - a staged promotion LADDER with human approval and statistically meaningful thresholds - is already the gate/readiness design, minus any real money.
- (10) Recursive API/exploit hunter - probing broker/exchange endpoints for undocumented latency/rate-limit loopholes is ToS-violating and CFAA-adjacent, and latency arb is irrelevant to a ~30-DTE paper book. Only legitimate residue: reading official API DOCS to model documented limits realistically.
- (8-harvest / 9-short) the selling/short-premium halves - outside the long-premium-only envelope (unbounded 0DTE short-gamma risk = the Buffett-wheel refusal reason).

No pipeline code touched tonight: eve of the first live-close ritual (full 8-lane stack); disciplined call is to record the triage and tee the honest builds (named scenario classes, exit playbook, adversarial signal panel) for the weekend soak window, not inject an untested stage hours before the run.

## DOPEY_ORG_MOVE_AND_DOOFUS_REVIEW_V22 (2026-07-10)

**Repo moved**: cjharriskc-ai/dopey -> ObtuseAI/dopey (GitHub transfer; stays PRIVATE, old URL redirects, local origin re-pointed). Description rewritten positive-but-truthful (347 chars, was the defensive "No edge claimed" one). Standing privacy directive intact - private org, private repo, still only the data-free public-release branch on the remote.

**doofus reviewed for implementation** (ObtuseAI/doofus, MIT (c) Chris Harris, cloned to scratch, 586 files): an LLM-guided meta-evolution platform (GEPA / MAP-Elites / GEP / A-Evolve, arenas, promotion+proof+safety gates, elite archive, 24/7 supervisor). It IS the honest #1 (governed parameter tournament) and #2 (proof ratchet) of the V21 adaptable list, ALREADY built with the exact discipline V21 demanded: measure-only default, double/triple opt-in before any write, path containment (is_relative_to root + protected roots + doofus own workspace), secret-strip on the fitness subprocess (DOOFUS_*/OPENROUTER/OPENAI/CURSOR popped, shell=False), snapshot+rollback on any fitness drop, and a FORBIDDEN_TRAITS safety gate that already bans foundry_proven_claim / forced_promotion / public_deploy.

CRUCIAL mechanism fact: the external-target path (doofus/meta/codeevolve/external_evolver.py) is LLM-FREE and DETERMINISTIC - it perturbs exactly ONE declared top-level `NAME = <number>` constant (AST-verified, single-assignment line) via an adaptive hill-climber, re-runs the target project's fitness command, keeps the change iff fitness does not drop else rolls back. The OpenRouter/DeepSeek credential is only for doofus evolving its OWN engine. So pointing it at dopey needs NO credential and NO network - fully offline/deterministic, which suits dopey's seeded backtest.

THE WHOLE BALLGAME = the fitness function. The mechanism is safe; the danger is 100% in what "better" means. Fitness = in-sample backtest return/Sharpe -> the hill-climber curve-fits dopey's params to the spine = the V1-V7 disease mechanized. ONLY honest fitness = HELD-OUT deflated Sharpe / null-corrected foundry IC, penalized by cumulative trial count (multiple-testing on the holdout is real - dopey_stats/deflated_sharpe + era_walk_forward already take trial counts). Integration DESIGN (NOT built tonight - eve of first live-close ritual): doofus stays in its own workspace/venv, dopey is an external target, no doofus code or credential enters dopey (envelope: dopey still performs no network fetch, holds no creds); whitelist ONLY evidence-neutral hyperparameters (block-bootstrap block length, DTE target band edges, cooldown session counts, MIN_QUOTE_OBS) - NEVER truth layer / gate thresholds / forward-walk leak guards / sentinels / sizing / evaluation cadence; fitness = new operator_tools/operator_evolve_fitness.py doing an internal train/test split and printing OOS DSR as a 0..1 last line; measure-only first to confirm signal is deterministic; NEVER --apply into master - proposals reviewed and committed through dopey's gated review (doofus's own doc prescribes exactly this). Beyond param-tuning, doofus scoring/ + proof/ + evolution/ (candidate_scorecard, promotion_gate, proof_density_gate, promotion_regression/replay audits, MAP-Elites, elite_archive) are a far more mature tournament+ratchet than dopey_tournament/runner.py - the pattern to lift for #1's arena and #2's ratchet, re-pointed at held-out scoring.

## DOPEY_V23_BUILD_NIGHT (2026-07-10 pre-dawn, "build improve progress as much as possible"; supervisor = 28 stages)

**Evolution harness LIVE (V22 design built, commits 505ec2e/40a057e/e540d32):** `dopey_backtest/exit_policy_config.py` = the whitelisted evolvable surface (PREMIUM_STOP_PCT/-0.5, PREMIUM_TARGET_PCT/1.0, MAX_HOLDING_STEPS/3 - the research backtest's exit engine ONLY; forward walk pins its own constants so live evidence semantics never move). WHITELIST CORRECTION vs V22 design: MIN_QUOTE_OBS is an evidence gate and must NOT be evolvable; bootstrap block length has no fitness ground truth; DTE band + cooldowns are forward-walk discipline - the exit-policy trio is the entire v1 surface. `compute_real_history_trade_records()` extracted as a pure in-memory API (run function persists; harnesses never touch pipeline artifacts). `operator_tools/operator_evolve_fitness.py`: holdout = signal_date > 2021-12-31 ONLY; dedupe to unique (symbol,date,strategy) paths; equal-weight per-date series; fitness = skew/kurt-aware PSR vs 0 printed as last line; floors (>=100 dates, >=500 paths) so candidates cannot win by starving the sample; fp-dust variance guard (constant series would otherwise fake PSR 1.0 - caught by test); persistent trial ledger + review-time DSR (deflation applied to the SELECTED winner at review, NOT in-search: in-search deflation is a monotone shift that cannot change the argmax but breaks determinism); SELF-HEALS a fixture-polluted signals artifact by regenerating from the spine. First live eval: holdout 940 dates / 8,758 paths, SR -0.038, PSR 0.1293 - the search fitness AGREES with the no-edge verdict. dopey registered in doofus (C:\Users\CH\doofus, bare stdlib venv) as external target, 3 targets, auto_apply=false, timeout 1800s.

**V21 adaptable list BUILT (all four):** (#3ext) 5 named scenario probes in the distributional-stress artifact (gap_down_3sigma, liquidity_hole_iv_blowout +15% liquidation haircut, vol_spike/vol_crush_no_move, weekend_gap_monday) - deterministic per-symbol-sigma parametrics, risk-only. (#7) `dopey_risk_engine/exit_playbook.py` - per-position trigger GEOMETRY: bisection finds the spot level that puts the next mark at the pinned stop/target under 3 IV scenarios + spot-grid action table; changes no rule (first read: BAC 59C spot 59.33 -> stop 57.19 / target 62.39). (#5) `dopey_risk_engine/adversarial_signal_panel.py` - bull/bear/risk lenses per NEW entry, verdict RECORDED-never-enforced (enforcement must be earned by held-out underperformance of would_refuse entries); Kelly ceiling stated honestly as 0.0 on no-edge; first read: 21 entries -> 18 proceed / 3 refuse. (#2) `dopey_analysis/trade_loss_coach.py` - closed-trade loss taxonomy (theta_bleed/adverse_move_stop/expired_worthless/friction_scratch) -> foundry-testable hypotheses at zero weight until held-out pass; >=10 closed + >=60% loss-share gates; waiting on first closes.

**Weekend program:** per-symbol IV calibration - calibration lane now inverts EVERY contract mid via house `implied_vol_bisection` (771/771; vendor IV no longer trusted) and emits per_symbol_multipliers (>=6 contracts, clamped); backtester `_iv_proxy` resolves per-symbol with global fallback (dispersion proves the need: AAPL 0.73x vs BAC/AMZN ~1.23x; global recommendation shifted 0.976->0.9541 on bisection IV). Gate gained evidence_eta (estimate-only, stamped "nothing accelerates it but the market"). `operator_monday_preflight.py` (8 plumbing checks -> MONDAY_PREFLIGHT.md). `operator_weekend_soak.py` (N full-stack iterations: supervisor + journal regression diff + fitness determinism x2 + honest-lane tests; stops on first regression).

**Attention lane forensics (three stacked bugs fixed):** (1) naive CSV join split "Tesla,_Inc." across columns -> TSLA views literally "_Inc." (underscore commas); (2) non-200 pageview responses silently yielded zero rows AND the wholesale rewrite erased previously-good symbols (retry x2 + carry-forward merge for failed names - proved itself same-session when BAC 429'd); (3) ranges ending on unpublished days 404 for SOME articles (API inconsistency) - window now ends today-2. Result: 11/11 names fresh, and the distillation lit up: JPM/MSFT/META/BAC all crowded (z>=2) - a bank/megacap attention spike on the book's own entry day.

**Ops incident (root cause found):** the honest signals artifact was fixture-polluted by TEST RUNS invoking pipeline runners against live artifact paths (V8's documented hazard, triggered by the legacy-repair agent's full-suite baseline). Background agent is building the doofus-style isolation layer (autouse artifact-path redirect + closure test + before/after hash invariance) and repairing the ~38 legacy failures. Until it lands, artifact restores are futile while suites run - the fitness self-heal exists for exactly this.

## DOPEY_FUNDAMENTALS_SHORT_SCREEN_V24 (2026-07-10, macro manifest = 9 lanes; universe 27 -> 37)

User directive: screen for ridiculously high P/E + horrible fundamentals as SHORT prospects (EV/quantum/AI/crypto). Envelope translation: "short" = LONG PUTS only; the screen is a research flag feeding panel+foundry, never an entry bias ("expensive stays expensive, crowded shorts squeeze" stamped in honest_limits).

**Fundamentals lane (9th macro lane):** `fetch_fundamentals()` (yfinance info, personal research) over tradable single names + a themed speculative watchlist (ev/quantum/ai/crypto/financials); ACCRUES by (date,symbol) 400d for future point-in-time foundry joins. Gate `fundamentals_state()`: 5 excess flags per name - pe_extreme_or_no_earnings (triple-digit P/E and "no P/E because no E" = same disease), price_to_sales>20, price_to_book>15, margin<-20%, negative FCF; short-candidate at >=3 flags + cap>=1e9. Thresholds are documented HEURISTICS (module constants), not evidence. Panel bear lens gained `speculative_excess_fundamentals`.

**First live read (27 names): 10 candidates, ALL watchlist-only, none in the old universe** - screen correctly separates expensive-but-profitable megacaps (NVDA/MSFT score 0) from speculative excess: IONQ (P/E 115, P/S 89!), PLTR (P/E 150, P/S 59, P/B extreme), LCID (margin -240%), AI (-188%), BBAI (-227%), MARA/RIOT/CLSK (unprofitable miners), RIVN, SOUN.

**Universe expansion 27 -> 37 (V18 pattern):** all 10 flagged names staged full-history (truncated to frontier 2026-07-08 EXACTLY - uniform-advance; any name not reaching the frontier is auto-dropped by the staging script), both staged copies written, both manifests re-pinned (history manifest data_files = 37, required_universe trued up to 37 incl. the V18 names it had missed), REQUIRED_HISTORY_UNIVERSE = 37; spine VALID at 212,242 bars / 0 missing / 0 stale. Chains SYMBOLS = 36 (put-side chains + earnings dates for the cohort start snapshotting at tonight's ritual), FINRA short-flow UNIVERSE, congress list, fundamentals in_universe all propagated. Repair agent messaged mid-flight: count assertions must DERIVE from REQUIRED_HISTORY_UNIVERSE, never hardcode.

Effect: the put side can now express the screen EX-ANTE through normal signal+context gating from tonight; the foundry gains a testable hypothesis lane (fundamental extremity vs forward returns) as snapshots accrue.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.


## DOPEY Open Source Autonomous Options Trader Max Completion V1
- Autonomous source/data admissibility now replaces manual review for this lane.
- Ambiguous, unknown-license, credentialed, paid/proprietary, broker/live, scrape-only, sample, and fixture sources are not evidence.
- Live trading, broker access, credentials, `.env`, strategy promotion, profitability claims, and live readiness remain blocked.

## DOPEY_ADAPTIVE_SCREENER_AND_CONSOLE_V25 (2026-07-10, supervisor = 29 stages)

**User directive:** "state of the art adaptive elite recursively improving screener ... cohesive with the simulation and evolution" + "unique clean dashboard with a simple start and stop button."

**Adaptive elite target screener (`dopey_screener/`, stage 29 `target_screener`):**
- Five strategy ARCHETYPES (momentum-breakout calls, fundamental-rot puts, crowded-fade puts, quality-pullback calls, vol-expansion coil) rank the 36 screenable names each run; every archetype maps to long_call/long_put or is stamped `screen_only` - the envelope stays long-premium.
- Factor classes are STRICTLY SEPARATED: point-in-time spine factors (20d/60d momentum, rv20/rv120 compression - computable at any historical date without lookahead) vs snapshot factors (fundamentals rot flags, attention z, FINRA short-flow, quality, options overlay: gamma regime/VRP/surface tear/earnings blackout - today-only, NOT backcastable). Missing data contributes nothing; never a fabricated number.
- Weights live in `dopey_screener/screen_config.py` - the SECOND evolvable surface (30 top-level `NAME = <number>` constants, same doofus contract as the exit trio). `operator_tools/operator_screen_fitness.py` prints one 0..1 line (0.5 + 2.5*IC clipped) for the external evolver; measurement invalid -> exit 1, never a score.
- "Recursively improving" = ELITE ARCHIVE (`elite_archive.py`): each run evaluates the active config + 4 deterministically-seeded single-weight mutations of random elites on HELD-OUT rank-IC ONLY (dates > 2021-12-31, point-in-time factors only, direction-aware: put archetypes scored against negative forward returns); keeps top-8; RECOMMENDS a better config only at >=0.005 mean-IC improvement with sufficient sample - a human applies by editing the config. Mutation is RESTRICTED to fitness-evaluable families (momentum/structure): mutating weights the fitness cannot see would be an unfalsifiable random walk. Snapshot families ride the live screen as stamped research tilts until their accruing daily archives support true point-in-time evaluation.
- First live read: fundamental-rot puts = RIOT/CLSK/LCID/IONQ/PLTR (the V24 flag cohort emerging from an independent scoring path); momentum calls = BAC/JPM/MSFT; active config holdout mean-IC +0.0079 over 225 dates x 4,235 pairs/archetype; best mutation +0.0093 -> correctly NO recommendation (margin not met). Fitness CLI first line: 0.519730.
- Cohesion: targets are research flags consumed by the dashboard + reviewable next to the adversarial panel; entries stay owned by the forward walk's signal+context gates; the exit playbook / distributional stress cover whatever the book holds; doofus can evolve screen weights under the same measure-only ritual as the exit trio.

**Operator dashboard (`dopey_dashboard/operator_dashboard.py`, `operator_tools/dashboard.cmd`):** localhost-only (127.0.0.1:8787) single-page console - START spawns the research supervisor (subprocess, double-start guarded), STOP terminates the process tree and clears ONLY a supervisor lock whose pid matches the killed child. Panels: paper record (open/closed counts, win rate, realized + unrealized premium-unit P&L, evidence-sample progress bar toward the gate's 100-close bar), active positions (entry fill vs last bid), closed positions, screener targets per archetype ("research flags - not orders" stamped in the UI), readiness-gate 9-check pills + missing list, system health (journal, stages g/d/f, regressions, risk-free, VIX term state, rot flags). NO order path exists on the page; envelope stamps in the state payload and the footer. Everything inline (no external resources).

**Verification honesty note (same run):** the earlier "all 18 verified green" claim was PARTLY WRONG - it rested on `pytest | tail` masking pytest's exit code (tail exits 0). True state on unmasked re-verification: spine/repricer + paperbroker + operator-stage + export/mutation fixes WERE green; the broker-readiness aggregate trio was NOT (evidence-presence checks whose producers sort after the file), and the window_001 backfill was INCOMPLETE (missing family_outcome_hints made the expanded-corpus loader include a half-expanded window). Fixes: broker-readiness test fixture now MATERIALIZES missing checklist evidence through the real producing runners (existence-gated; the production preflight still only observes); window_001 completed with regime-consistent hints; the two delta-luck mutation tests rewritten to selection/earned-champion properties (36/36 + 47/47 green, exit codes checked). LESSON (standing): never pipe pytest through tail without capturing PYTEST exit - check `$?` of pytest itself.

## DOPEY_SELF_GOVERNING_UNIVERSE_V26 (2026-07-10, supervisor = 30 stages)

**User directive:** "the symbol universe needs to be self expanding and understanding and improving."

**Architecture (`dopey_universe/` + `operator_tools/operator_universe_ritual.py`):** discovery and judgment are OFFLINE (supervisor stage 30 `universe_governor`, deterministic over already-fetched lane files); network staging lives in the OPERATOR RITUAL through the exact gates every prior expansion used. The two may never merge.

- **Tiers:** core (the 37-name code floor - NEVER auto-added, auto-retired, or quarantined; changing core is a human code change) / candidate (discovered + scored, no data staged) / probation (staged through the gates, full research citizen) / quarantined (mechanically dead, excluded + reversible) / retired (human-confirmed, data kept forever).
- **Self-EXPANDING:** discovery sources = fundamentals watchlist excess-flags beyond the tradable set + a NEW FINRA whole-market scan (the fetcher already downloads the full daily file; it now also aggregates the most-active + short-ratio-extreme non-universe names - no extra network, same license posture). Governor scores + queues (<=4); the ritual probes each candidate (listed options REQUIRED, cap >= $1B, ADV >= $5M), stages full history truncated EXACTLY to the core frontier (uniform-advance preserved), appends the manifest data_files entry, re-pins both manifests with the canonical hash, and only promotes candidate->probation after the spine validator answers valid_real_dataset - a failed validation ROLLS THE NEWCOMER BACK OUT. Bounded 2 adds/run, 13 probation cap.
- **Self-UNDERSTANDING:** every active symbol carries a dossier - role (incl. context_only_volatility_index: VIX is useful BY not trading and is never nagged), why_in_universe (discovery evidence log), data health (frontier lag), 20d avg dollar volume, gated-signal production, best screener rank, forward-walk participation - refreshed every run, stamped not_edge_evidence.
- **Self-IMPROVING:** documented mechanical usefulness score -> probation names useless 5 consecutive runs = retire RECOMMENDATION (human confirms; quality retirement is never automatic); core flagged-only. Mechanical DEATH is different: the daily updater is now tier-aware - the uniform-advance frontier is computed over CORE ONLY, and a probation name that is unfetchable or lags the frontier is AUTO-QUARANTINED (registry-journaled, reversible) instead of freezing the spine. Core failures still hold the spine exactly as before.
- **Consumers registry-aware:** screener scores active_universe(); chains/macro/fundamentals fetch lists extend with probation names at runtime (fail-safe to base tuples). The elite-archive FITNESS panel deliberately stays PINNED to the core floor - trial-ledger comparability would break if the evaluation panel shifted with probation churn.
- **First live read:** 37 active / 0 discovered (honest: the market scan is born at the next macro fetch; every current watchlist flag is already tradable) / 1 recommendation that was exactly right - VIX at usefulness 0.0, which exposed the context-only classification gap, fixed same run. 45/45 tests green (PYTEST_EXIT checked). Daily ritual gained the universe step between macro fetch and supervisor.

Loop from tomorrow: ritual fetches -> governor discovers + queues -> next ritual probes + stages -> probation earns its dossier -> recommendations surface on the dashboard's universe line.

## DOPEY_DUMMY_HARVEST_V27 (2026-07-10, supervisor = 31 stages)

**User directive:** "is there anything from the dummy repo we can adapt or use?" `ObtuseAI/dummy` = the prediction-market sibling (Kalshi crypto/sports, paper-only, 4,299 py files) - reviewed clone at C:/Users/CH/dummy.

**ADAPTED AND BUILT (stage 31 `signal_calibration`, `dopey_calibration/signal_settlement.py`):** dummy's two sharpest disciplines, translated to directional options signals:
- **Phantom grading** - dummy settles ~1,000 forecasted markets per cycle whether traded or not; dopey now settles EVERY gated directional signal at its 10-trading-day horizon against the real spine, traded or not. No fills, no premium, no costs - direction-realization bookkeeping on real closes, stamped `signal_calibration_not_trade_evidence`; the readiness gate NEVER reads the lane (source-asserted in tests). Signal-quality evidence now accrues at signal velocity instead of position velocity.
- **Contested truth** - "agreeing with the market and being right proves nothing." A phantom is CONTESTED when its direction opposes the trailing 20d drift; per-family trust is earned ONLY on the contested record (multiplicative around 1.0, floor 30 contested settlements, else explicitly unrated), advisory-only, never enforced.
- **FIRST READ IS A MECHANISM DISCOVERY: 78,209 phantoms settled -> overall hit rate 49.64% (the coin flip the truth layer always said) but CONTESTED hit rate 46.47%** - the signal set's flatness decomposes into harmless drift-agreement plus actively-bad drift-fighting. The canonical no-edge verdict now has a mechanism attached.

**RECORDED FOR LATER (not built):** metabolic debias-curve refit (fit p(hit|score) once contested samples deepen - the summary already carries the sample floors); event-purged walk-forward (purge overlapping-event windows from era splits); capital-velocity ranking (edge per sqrt(time-to-expiry) as a screener tiebreak); dummy's dashboard promotion-gate ladder presentation.

**REFUSED:** `predator_mesh/` brokers+aggression machinery (execution-adjacent - dopey's sealed class regardless of asset); `repo_harvester/` auto-incorporation engine (license-gated but supply-chain risk class; any cross-repo lift stays HUMAN-reviewed, like this one); Kalshi adapters + sports/crypto verticals (different asset class, out of envelope).

Status-key note: dummy lane reports `signal_calibration_status` (the IV lane already owns `calibration_status`). 58/58 V25+V26+V27 tests green, PYTEST_EXIT checked.

**V27 COMPLETION (2026-07-10) - the calibration was cohesive, not just built.** The first V27 pass produced the artifact but nothing consumed the contested trust (the module docstring promised "adversarial-panel visibility"; the panel never read it). Completed the wire so adaptations 1+2 are genuinely cohesive with the stack, not dead-end artifacts:
- **Read-side accessors** on `signal_settlement.py`: `load_calibration_summary()`, `family_trust_for(family, summary=None)` (ALWAYS returns a record - an uncalibrated family is stamped `unrated_no_calibration_for_family`, never silently a pass/block), `calibration_context(summary=None)` (system-wide base rate, gate-blind, advisory).
- **Adversarial panel** (`dopey_risk_engine/adversarial_signal_panel.py`) now attaches a fourth CALIBRATION lens per record (contested-truth trust for the entry's family) + a summary-level `calibration_context` (the 46.47%-contested base rate the bull case must beat). Deliberately read AFTER the verdict and never fed into it - a wildly trusted vs distrusted family yields the SAME recorded verdict (test-locked). Recorded, never enforced; enforcement still must be EARNED on held-out evidence.
- **Honest namespace gap surfaced, not hidden:** the calibration grades the `directional_setup` signal engine (one coarse family); the forward-walk positions carry finer families (`relative_strength`/`market_regime`/`momentum`). Per-record lens honestly reads `unrated` for those; the panel-level context carries the true system-wide contested rate. No category error - the record says exactly what is and isn't individually calibrated.
- **Supervisor reorder:** `signal_calibration` moved to run BEFORE `adversarial_signal_panel` (dep-safe: its deps `real_signals`/`history_validation` run far earlier) so the panel reads a fresh base rate in the same pass. NOT added as a hard panel dependency - the panel degrades to `unrated`/`no_calibration_yet` if calibration fails, so a calibration failure must never skip the panel. Stage count unchanged at 31.
- **Verified:** panel run attached context to 21 real entries (78,209 settled, 46.47% contested); 66/66 (V27+V25+V26) and 41/41 (v22 panel + supervisor-integration) green, PYTEST_EXIT=0 both.

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_manual_review`
- completeness_score: `88`
- promotion_decision: `manual_review_required`
- terminal_block_count: `0`
- manual_review_count: `1`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_incomplete`
- completeness_score: `88`
- promotion_decision: `hold_review_only`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_incomplete`
- completeness_score: `88`
- promotion_decision: `hold_review_only`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`
