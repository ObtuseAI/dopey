# DOPEY Offline Meta-Governor Report

## Purpose

The offline meta-governor is a **deterministic, offline, fixture-based, paper-only** layer
that evaluates proof quality, promotion eligibility, demotion pressure, quarantine rules,
and strategy-family trust levels across all current DOPEY evidence layers. It produces
governance decisions that allocate simulated paper research attention.

This is **not live approval**, **not broker execution**, and **not real performance
evidence**. It never enables live trading, real capital deployment, or any live migration.

## Evidence layers consumed

The governor loads the latest record from each DOPEY registry via
`dopey_governor/proof_evidence_loader.py` (graceful on missing layers):

- paper pipeline
- walk-forward replay
- tournament
- mutation population
- failure-mode miner
- feedback optimizer
- IV surface / skew / term
- macro-event fixtures
- liquidity / slippage
- Greeks / IV validation
- pattern fixture intelligence
- source scorecard
- ensemble allocator
- champion registry

Each layer is scored into an `EvidenceLayerScore` (score, confidence, freshness, coverage,
contradiction pressure, known limitations, status: strong / adequate / weak / missing).

## Proof quality scoring

`dopey_governor/proof_quality.py` builds a `StrategyProofProfile` per strategy and a
`ProofQualityResult` per strategy. Proof strength (0..1) is a deterministic weighted blend of:

- reproducibility, evidence coverage, cross-layer agreement
- walk-forward consistency, mutation improvement, failure-mode reduction
- overfit control, liquidity/slippage robustness, Greeks/IV fit
- macro fit, pattern support, ensemble allocation support
- source reliability, safety compliance

It penalizes missing evidence, contradictory layers, high overfit, holdout collapse, low
liquidity, high slippage, recurring failure modes, poor Greek/IV fit, macro contradiction,
IV/premium traps, unsafe structure rejection, source/network dependency, and any
live-enabling behavior.

## Paper-only promotion policy

`dopey_governor/promotion_policy.py` emits only paper/research governance decisions:
`promote_to_paper_watchlist`, `promote_to_paper_candidate`, `promote_to_paper_champion`,
`mark_offline_ensemble_member`, `mark_offline_mutation_champion`, `hold_research_only`,
`reduce_paper_attention`, `starve_weak_signal`, `quarantine_overfit`, `reject_unsafe`,
`request_more_fixture_evidence`. Forbidden live decisions are rejected at runtime.

Promotion tiers require both sufficient proof strength **and** candidate-specific
walk-forward consistency floors (a paper candidate must show genuine walk-forward edge, not
just rely on global evidence coverage).

## Demotion / quarantine logic

- `quarantine_policy`: high overfit (rank 3) → `quarantine_overfit`; any live-enabling flag
  (`paper_only=False`) → `reject_unsafe`.
- `demotion_policy`: family failure pressure >= 0.40 → `starve_weak_signal`; weak proof with
  no ensemble support → `reduce_paper_attention`.

## Family trust map

`dopey_governor/family_trust_map.py` builds `FamilyTrustProfile` per family: trust score,
best/worst regimes, overfit/failure/liquidity/Greek-IV/macro pressure, recommended
attention, allowed mutation intensity, and constraints. Trust rewards low overfit, low
failure pressure, ensemble support, and robust Greek/IV/liquidity fit.

## Regime trust map

Each known fixture regime gets a `RegimeTrustProfile` (preferred / penalized / starve
families, dominant failure modes, required evidence layers, trust score) derived from the
regime allocator + macro regime tags. For example, `bullish_breakout` prefers directional
convexity; `macro_shock_risk_off` penalizes compression; `low_liquidity_decay` starves
short-duration.

## Decision outputs

`MetaGovernorDecision` records decision, eligible tier, proof strength, risk pressure,
reason codes, required missing evidence, disqualifying failures, paper-only / live-allowed
flags, and (for promotion decisions) explicit live-migration conditions. Live-migration
conditions are documentation only — they describe what a **human operator** would need to
satisfy in a future, separate review; they are never auto-applied.

## Limitations

- All governance scores are deterministic fixture math, not live performance evidence.
- The governor concentrates trust on the strongest family because other families carry
  genuinely modest fixture scores, higher overfit, or higher failure pressure.
- No live promotion, real capital, broker order sizing, network access, scheduled run, or
  Blunder modification occurs.

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker rejects `live_allowed=true`
- Robinhood / Alpaca / Tradier stubs raise `LiveTradingDisabledError`
- No forbidden live decisions or tiers emitted; no live migration path created
- No broker connection, credentials, network market data, live trades, live promotion,
  autonomous scheduled run, heavy dependency, commit, or Blunder source modification
- Blunder integrity: **`BLUNDER_INTEGRITY_OK checked=78`**

## Next recommended build target

Offline evidence replay audit harness.

## Update: stronger walk-forward consistency evidence layer

The meta-governor's evidence bundle now carries a `stronger_consistency` field, and
`proof_quality.py` adds a `stronger_walk_forward_consistency` evidence layer. The bundle
loads the latest `artifacts/dopey/walk_forward_consistency/consistency_registry.jsonl`
when present and:

- Reports a per-strategy `walk_forward_consistency` overall, `holdout_survival`, and
  `overfit_penalty` from the registry (preferring registry values over the tournament's
  per-row `walk_forward_score`).
- Scores the layer based on the mean `overall` across all strategies, with contradiction
  pressure scaled by `0.05 * overfit_warnings + 0.10 * holdout_failures`.
- Records the layer's `stronger_wf_consistency_version` in the proof record.

The meta-governor's paper-only promotion policy continues to use only the proof-quality
+ risk-pressure blend; the stronger consistency evidence is an **advisory layer** that
strengthens (or downgrades) a strategy's `walk_forward_consistency` component but never
emits a live tier. See `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_REPORT.md` for the
runner, scoring, and integration details.

## Update: regime/holdout corpus v2 evidence layer

The meta-governor's evidence bundle now also carries a `regime_holdout_corpus_v2` field,
and `proof_quality.py` adds a `regime_holdout_corpus_v2` evidence layer. The bundle
loads the latest `artifacts/dopey/regime_holdout_corpus_v2/corpus_registry.jsonl`
when present and:

- Reports a per-strategy mean overall across the v2 corpus, scaled by `min(1.0, total_windows / 24.0)`.
- Records contradiction pressure scaled by `0.05 * overfit_warnings + 0.10 * holdout_failures`.
- Includes the v2 layer in the proof record's evidence layer scores.

The v2 corpus extends the stronger-walk-forward consistency evidence by adding sector,
macro-shock, IV-transition, liquidity, and cross-family challenge dimensions. The
meta-governor's promotion policy continues to be paper-only; the v2 evidence is
**advisory** and never emits a live tier. See
`DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2_REPORT.md` for details.

## Update: fundamental evidence layer

The meta-governor now consumes the new
sector_peer_fundamental_fixtures evidence layer. The
EvidenceBundle.fundamental_fixtures field carries the deterministic
sector/peer/fundamental registry into the proof-quality scoring. The
EVIDENCE_LAYER_NAMES list now includes sector_peer_fundamental_fixtures. The
layer is scored by the average family-level fundamental fit, with
undamental_contradiction_penalty as its contradiction pressure. The governor
remains paper-only; no live decision is emitted.
