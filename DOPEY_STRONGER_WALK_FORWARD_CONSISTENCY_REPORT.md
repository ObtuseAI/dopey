# DOPEY STRONGER WALK-FORWARD CONSISTENCY EXPANSION REPORT

## Purpose

The **stronger walk-forward consistency expansion** (`DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`)
extends the existing offline walk-forward replay harness to test strategies across more train / validation /
holdout splits and more diverse regimes. It answers the questions the audit layer
kept flagging as the top evidence gap (`insufficient_walk_forward_consistency`):

- Which strategies survive multiple walk-forward splits (rolling + blocked + anchored + regime + stress)?
- Which strategies only work in one window or one regime?
- Which families show real fixture consistency versus overfit bursts?
- Which candidates degrade on holdout windows?
- Which strategies have stable liquidity, slippage, Greek/IV, macro, and pattern behavior across time slices?
- Which mutation candidates remain improvements after rolling + blocked + regime + stress validation?
- Which family deserves paper attention after stronger consistency testing?

This pass remains **offline, fixture-based, paper-only, deterministic, and live-blocked**.

## Split model

`dopey_walk_forward/consistency_models.py` defines:

- `WalkForwardSplit` — single train/validation/holdout split with `split_id`, train/validation/holdout
  window ids, regime tags, split type, and notes. Constructed with a leak-free invariant: holdout
  windows must not appear in train or validation.
- `WalkForwardSplitSet` — collection of splits with a deterministic `plan_id`.
- `RollingWalkForwardPlan` — rolling-window plan, ≥ 3 rolling splits.
- `BlockedWalkForwardPlan` — blocked-window plan, ≥ 2 disjoint train/val/holdout splits.
- `HoldoutWindowSet` — distinct holdout windows used across plans.
- `ConsistencyReplayCase` — deterministic replay case for a (strategy, split) pair.

`split_type` is one of `rolling`, `blocked`, `anchored`, `regime_holdout`, `stress_holdout`.

The split builder (`dopey_walk_forward/split_builder.py`) ships:

| Function | Output |
| --- | --- |
| `build_rolling_splits` | ≥ 3 rolling splits (each = 2 train + 1 val + 1 holdout, ordered, leak-free) |
| `build_blocked_splits` | ≥ 2 blocked splits (disjoint train/val/holdout blocks per split) |
| `build_anchored_split` | 1 anchored split (first 2/3 train, 5/6 boundary, 1/6 holdout) |
| `build_regime_holdout_split` | 1 regime-holdout split (holdout = `target_regime` windows) |
| `build_stress_holdout_split` | 1 stress-holdout split (holdout = `high_spread_bad_fill`, `low_liquidity_decay`, `macro_shock_risk_off`, `macro_contradiction_pressure`, `surface_instability_fakeout`, `short_duration_bad_fill`, `vol_expansion_trap`, `compression_shock_failure`) |
| `build_stronger_walk_forward_splits` | the canonical 8+ split set (3 rolling + 2 blocked + 1 anchored + 1 regime + 1 stress) |
| `build_rolling_plan`, `build_blocked_plan` | high-level plan wrappers |

## Expanded fixture / holdout corpus

12 additional walk-forward windows (`window_013_train` … `window_024_holdout`) were generated
deterministically via `dopey_data/fixtures/walk_forward/build_stronger_corpus.py` and added to
the existing `dopey_data/fixtures/walk_forward/` corpus. Total corpus is now **24 windows across
18 regime tags**, satisfying the ≥ 24 target. The 12 new windows cover:

- additional bullish breakout (`window_023_holdout`)
- additional bearish breakdown (`window_021_holdout`)
- additional trend-vol expansion (`window_019_holdout`)
- additional chop/range (`window_020_holdout`)
- additional post-event IV crush (`window_022_holdout`)
- additional macro shock/risk-off (existing `window_012_holdout`, `window_007_validation`)
- additional high-spread bad-fill (existing `window_010_holdout`)
- additional low-liquidity decay (`window_024_holdout`)
- additional macro contradiction (`window_013_train`)
- additional surface instability/fakeout (`window_014_train`)
- additional short-duration bad-fill (`window_015_train`)
- additional vol-expansion trap (`window_016_validation`)
- additional compression shock failure (`window_017_validation`)
- additional clean directional confirmation (`window_018_validation`)

Each new window carries: regime tag, option chain, IV/skew/term scenario, macro scenario,
liquidity/slippage context, pattern signals, and family outcome hints.

## Consistency scoring

`dopey_walk_forward/consistency_score.py` rolls up 14 deterministic components into a single
`StrategyConsistencyScore.overall`:

| Component | Description |
| --- | --- |
| `split_pass_rate` | fraction of splits where validation and holdout both pass |
| `validation_stability` | mean validation pass rate across splits |
| `holdout_survival` | mean holdout pass rate across splits |
| `regime_coverage` | fraction of distinct regimes that passed |
| `family_consistency` | agreement with the dominant family pass-rate |
| `score_variance` | 1 − stdev of split consistency |
| `drawdown_proxy_stability` | 1 − normalized drawdown proxy dispersion |
| `liquidity_slippage_stability` | mean of (1 − slippage penalty) over splits |
| `greek_iv_stability` | mean greek/IV stability over splits |
| `macro_stability` | mean of (1 − macro contradiction) over splits |
| `pattern_stability` | mean of pattern confidence over splits |
| `failure_recurrence` | 1 − mean of recurring failure penalty |
| `overfit_penalty` | 1 − max(0, train − holdout) − holdout collapse |
| `improvement_persistence` | fraction of splits with consistent improvement |

`consistency_verdict.py` maps a `StrategyConsistencyScore` to one of:
- `strong_consistency`
- `acceptable_consistency`
- `fragile_consistency`
- `overfit_warning`
- `holdout_failure`
- `reject`

## Stronger walk-forward replay runner

`dopey_walk_forward/consistency_runner.py` orchestrates the full pipeline:

1. Verify safety state (RESEARCH mode, all live flags off).
2. Load expanded fixture windows.
3. Build rolling/blocked/anchored/regime/stress splits.
4. Load strategy candidates: base genomes, mutation champions, feedback candidates,
   ensemble-selected candidates, meta-governor paper candidates.
5. Replay each candidate across each split (deterministic).
6. Score each strategy, then derive per-strategy and per-family consistency verdicts.
7. Compute `FamilyConsistencyProfile` and `HoldoutRobustnessScore`.
8. Write registries (`consistency_registry.jsonl`, `consistency_replay.jsonl`,
   `consistency_holdout.jsonl`, `family_consistency_profile.jsonl`, `consistency_strongest.jsonl`).
9. Append ProofLedger record.
10. Print concise JSON summary.

CLI:

```
python -m dopey_walk_forward.run_stronger_walk_forward_consistency
```

## Integration with the rest of DOPEY

- **Meta-governor**: `dopey_governor.proof_evidence_loader.EvidenceBundle` now carries a
  `stronger_consistency` field, and `dopey_governor.proof_quality.score_evidence_layers` adds the
  `stronger_walk_forward_consistency` evidence layer. `build_strategy_proof_profiles` reads each
  strategy's per-registry consistency overall / holdout survival / overfit penalty.
- **Ensemble allocator**: `dopey_strategy_lab.allocation_policy.score_candidate` now adds
  `consistency_component` and `consistency_penalty` components. The ensemble reads the
  `consistency_registry.jsonl` to stamp each candidate with its consistency score and verdict;
  weak consistency (< 0.30) is penalized.
- **Failure feedback optimizer**: `dopey_strategy_lab.constraint_tuning` now adds a
  `holdout_consistency_guard` recommendation to both `overfit_train_only` and `holdout_collapse`
  failure modes.
- **Evidence replay audit**: `dopey_audit.artifact_loader.ARTIFACT_SPECS` recognizes
  `walk_forward_consistency_registry`, `walk_forward_consistency_proof`, `family_consistency_profile`,
  and `champion_consistency` artifact types. The audit reports the stronger consistency summary in
  the registry record and the gap planner recognizes `weak_stronger_consistency_evidence` and
  `consistency_evidence_missing` categories.
- **Champion registry**: `dopey_strategy_lab.champion_consistency` writes a per-champion
  `champion_consistency.jsonl` record that records the consistency verdict + holdout robustness
  for the latest paper champion and runner-up.

## Registry / proof artifacts

| Path | Purpose |
| --- | --- |
| `artifacts/dopey/walk_forward_consistency/consistency_registry.jsonl` | per-run registry: plan, splits, replays, strategy scores, family profiles, verdicts |
| `artifacts/dopey/walk_forward_consistency/consistency_replay.jsonl` | per-split replay results |
| `artifacts/dopey/walk_forward_consistency/consistency_holdout.jsonl` | plan-level holdout robustness |
| `artifacts/dopey/walk_forward_consistency/family_consistency_profile.jsonl` | per-family profile |
| `artifacts/dopey/walk_forward_consistency/consistency_strongest.jsonl` | strongest split result per strategy |
| `artifacts/dopey/walk_forward_consistency/consistency_proof.jsonl` | ProofLedger record |
| `artifacts/dopey/walk_forward_consistency/consistency_summary.md` | human-readable summary |
| `artifacts/dopey/champion_registry/champion_consistency.jsonl` | per-champion consistency verdict + holdout robustness |

## Limitations

- All scores are deterministic fixture math, not real execution quality. They measure whether
  a strategy *consistently* matches its family hints across the fixture corpus, not whether it
  would have made money.
- The consistency replay is regime-aware, but every fixture window is engineered (no real
  market data).
- The 24-window corpus is not exhaustive. Broader regime/holdout coverage would strengthen
  the consistency signal further (recommended as a follow-up target).
- Live promotion is impossible from this path. The runner runs only in `RESEARCH` mode, performs
  no broker connection, no credentials, no network access, and no scheduled run.

## Safety state

- `mode` = `RESEARCH`; `live_trading_enabled` = `false`;
  `funded_broker_connections_enabled` = `false`;
  `allow_unofficial_robinhood_api` = `false`.
- `ReplayEngine` rejects any `live_allowed=true` intent (`LiveTradingDisabledError`).
- `PaperBroker` is the only execution adapter used; refuses live intents.
- Robinhood/Alpaca/Tradier stubs still raise `LiveTradingDisabledError`.
- No broker connection, no credentials, no network, no Blunder modification.
- Original Blunder sources on `Z:` verified unchanged via SHA256 (78/78, 0 mismatches).
- No profit claims; consistency PnL is explicitly simulated/paper-only.

## Files added
- `dopey_walk_forward/consistency_models.py`
- `dopey_walk_forward/split_builder.py`
- `dopey_walk_forward/consistency_score.py`
- `dopey_walk_forward/consistency_verdict.py`
- `dopey_walk_forward/consistency_runner.py`
- `dopey_walk_forward/run_stronger_walk_forward_consistency.py`
- `dopey_data/fixtures/walk_forward/build_stronger_corpus.py` (and 24 fixture files
  `window_013_train.json` … `window_024_holdout.json` + matching `*_analysis.json` files)
- `dopey_strategy_lab/champion_consistency.py`
- `tests/test_stronger_walk_forward_consistency.py` (31 tests)

## Files modified
- `dopey_walk_forward/__init__.py` — exports the new symbols.
- `dopey_walk_forward/family_outcome.py` — extended `REQUIRED_REGIME_TAGS` and `REGIME_FAMILY_HINTS`
  with the 6 additional regime tags from the corpus expansion.
- `dopey_strategy_lab/ensemble_models.py` — `StrategyAllocationCandidate` now carries
  `consistency_score` and `consistency_verdict`. `AllocationScoreBreakdown` adds `consistency_component`
  and `consistency_penalty`.
- `dopey_strategy_lab/allocation_policy.py` — `score_candidate` adds the consistency components;
  `apply_caps` skips the family cap when only one family is present and uses a soft fallback so
  that the policy can always reach sum-to-1.0. Reason codes now mention weak consistency.
- `dopey_strategy_lab/ensemble_allocator.py` — loads the stronger consistency lookup and stamps each
  candidate with `consistency_score` and `consistency_verdict`.
- `dopey_strategy_lab/constraint_tuning.py` — `overfit_train_only` and `holdout_collapse` modes now
  include the `holdout_consistency_guard` recommendation.
- `dopey_strategy_lab/__init__.py` — exports `champion_consistency`.
- `dopey_governor/proof_evidence_loader.py` — `EvidenceBundle` carries a `stronger_consistency` field
  and `layers_present()` reports it.
- `dopey_governor/proof_quality.py` — `EVIDENCE_LAYER_NAMES` includes
  `stronger_walk_forward_consistency`; `score_evidence_layers` produces a layer for it;
  `build_strategy_proof_profiles` reads per-strategy consistency from the registry.
- `dopey_audit/artifact_loader.py` — `ARTIFACT_SPECS` recognizes the new artifact types; aliases
  `consistency_verdict` for `champion_consistency`.
- `dopey_audit/hash_auditor.py` — `STRICT_HASH_TYPES` includes
  `walk_forward_consistency_registry` (recomputable from the stored record).
- `dopey_audit/evidence_gap_planner.py` — gap categories include `weak_stronger_consistency_evidence`
  and `consistency_evidence_missing`.
- `dopey_audit/audit_runner.py` — passes the stronger consistency registry into the gap planner
  and includes a summary in the audit's registry record.
- `tests/test_offline_ensemble_allocator.py` — kept the original sum-to-1.0 invariant; the policy
  now reaches 1.0 in all cases via a soft cap fallback.

## Tests run

```
python -m pytest -q   -> 392 passed (361 prior + 31 stronger-walk-forward), 0 failures
```

The 31 new tests (`tests/test_stronger_walk_forward_consistency.py`) cover:

- Split model: deterministic serialization, rolling plan ≥ 3, blocked plan ≥ 2 with leak-free
  invariants, regime holdout contains target regime, stress holdout contains bad-fill or macro-shock.
- Corpus: loads, ≥ 24 windows, ≥ 12 additional, all required regimes present, macro/IV/liquidity/pattern
  context present on every window.
- Scoring: rewards stable validation+holdout; penalizes train-only improvement; penalizes holdout
  collapse; penalizes high split variance; penalizes recurring failure modes; verdicts are deterministic.
- Runner: runs offline; evaluates multiple strategies; writes registry with reproducibility hash;
  writes proof record; top consistent strategy is deterministic across runs.
- Integration: meta-governor consumes stronger consistency evidence; ensemble allocator penalizes
  weak consistency; failure feedback recommends holdout_consistency_guard; evidence audit recognizes
  the consistency registry; champion registry records consistency verdict.
- Safety: no live promotion possible; live stubs still block; PaperBroker still refuses
  `live_allowed=true`; config still RESEARCH after expansion; consistency runner does not modify
  live settings; Blunder source integrity preserved.

## Known gaps
- 24-window corpus is larger but not exhaustive; broader regime/holdout coverage is still
  desirable. This is also a recommended next build target.
- Some families (especially `volatility_expansion`, `volatility_compression`,
  `short_duration_defined_risk`) carry modest fixture scores and higher overfit pressure.
- Live migration is still documentation-only. No auto-live path is introduced.

## Next recommended build target
`larger_regime_holdout_corpus_v2` — broaden the regime + holdout coverage further with more
sector-specific and macro-shock windows, while keeping the build fully offline + paper-only.

> **Update (Pass 18 — `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`):** the stronger walk-forward
> consistency layer now consumes a broader deterministic regime + holdout corpus. The
> v2 corpus adds **32 new v2 holdout windows** across 5 categories
> (8 sector-specific, 6 macro-shock, 6 IV/volatility-transition, 6 liquidity/fill-stress,
> 6 cross-family-challenge). Combined with the 24-window stronger-walk-forward v1
> corpus, the full deterministic walk-forward corpus is **56 windows**. The v2 runner
> (`dopey_walk_forward/run_regime_holdout_corpus_v2.py`) replays every strategy
> candidate across the v2 corpus, scores v2 consistency, produces a v1-vs-v2 delta,
> and writes `artifacts/dopey/regime_holdout_corpus_v2/{corpus_registry,corpus_v2_replay,
> corpus_coverage,corpus_v2_proof,corpus_v2_summary}`. The meta-governor now reads
> `regime_holdout_corpus_v2` as a new evidence layer; the ensemble allocator stamps
> each candidate with `corpus_v2_consistency_score` and applies a corpus-v2 consistency
> component and penalty to the allocation breakdown; the audit recognizes the
> `regime_holdout_corpus_v2_*` artifact types; the champion registry writes a
> `champion_corpus_v2.jsonl` record. See
> `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2_REPORT.md` and
> `DOPEY_REGIME_HOLDOUT_CORPUS_V2_LEDGER.md`.

## Update: sector / peer / fundamental context

The stronger walk-forward consistency harness now records the per-strategy
fundamental summary (verage_fundamental_fit_score, verage_sector_fit_score,
verage_peer_confirmation_score, verage_fundamental_contradiction_penalty,
verage_valuation_risk_score, verage_earnings_quality_score,
verage_crowding_risk_score, undamental_risk_flags,
est_fundamental_scenario, worst_fundamental_scenario, est_fundamental_regime,
and worst_fundamental_regime) so the consistency verdict accounts for non-price
fundamental context. This remains offline, fixture-based, paper-only, and
live-blocked.
