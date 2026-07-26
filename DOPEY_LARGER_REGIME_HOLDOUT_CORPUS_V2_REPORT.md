# DOPEY LARGER REGIME/HOLDOUT CORPUS V2 REPORT

## Purpose

`DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2` broadens DOPEY's deterministic fixture corpus
beyond the 24-window stronger-walk-forward baseline. It adds **32 new v2 holdout
windows** across 5 categories (sector-specific, macro-shock, IV/volatility-transition,
liquidity/fill-stress, cross-family-challenge) so the stronger walk-forward consistency
evidence becomes more durable and less concentrated around a narrow fixture corpus.

This pass must remain **offline, fixture-based, paper-only, deterministic, and
live-blocked**.

## Windows added

| Category | Count | Examples |
| --- | --- | --- |
| Sector-specific | 8 | tech_growth_risk_on_breakout, financials_rate_spike_rotation, energy_oil_shock_vol_expansion, healthcare_defensive_rotation, small_caps_liquidity_decay, semiconductor_momentum_fakeout, consumer_discretionary_risk_off_breakdown, tech_growth_rate_shock_reversal |
| Macro-shock | 6 | hot_cpi_gap_down_risk_off, cool_cpi_gap_up_risk_on, hawkish_fomc_vix_spike, dovish_fomc_iv_crush, jobs_surprise_yield_spike, dollar_squeeze_liquidity_contraction |
| IV / vol transition | 6 | pre_event_iv_expansion_trap, post_event_iv_crush_continuation, front_iv_backwardation_panic, normal_contango_chop_decay, wing_elevation_breakout, skew_collapse_reversal |
| Liquidity / fill stress | 6 | wide_spread_opening_gap, low_oi_chain_decay, multi_leg_fill_fragility, late_day_liquidity_fade, short_duration_bad_fill_cluster, macro_gap_slippage_cluster |
| Cross-family challenge | 6 | directional_fakeout_macro_contradiction, vol_expansion_post_event_crush_trap, compression_breakout_shock_failure, short_duration_theta_liquidity_failure, all_family_high_uncertainty_stress, clean_multi_signal_directional_confirmation |

Total: **32 new v2 windows**. Combined with the 24-window stronger-walk-forward v1
corpus, the full deterministic walk-forward corpus is **56 windows**.

## Category coverage

| Coverage | Fraction | Notes |
| --- | --- | --- |
| Sector coverage | 1.0 (8/8 required) | broad_market, tech_growth, financials, energy, healthcare, small_caps, semiconductors, consumer_discretionary |
| Macro-shock coverage | 1.0 (6/6 required) | hot/cool CPI, hawkish/dovish FOMC, jobs surprise, dollar squeeze |
| IV transition coverage | 1.0 (6/6 required) | pre-event, post-event, backwardation, contango, wing elevation, skew collapse |
| Liquidity stress coverage | 1.0 (6/6 required) | wide spread, low OI, multi-leg fill, late-day fade, short-duration cluster, macro gap |
| Cross-family challenge coverage | 1.0 (6/6 required) | directional fakeout, vol expansion trap, compression shock failure, short-duration theta failure, all-family stress, clean confirmation |
| Overall coverage fraction | 1.0 | average of regime/sector/stress with weighting 0.30 / 0.20 / 0.50 |

## V1 vs V2 consistency comparison

The v2 runner reads the latest v1 `consistency_registry.jsonl` and stamps each strategy's
v1 overall / holdout survival / overfit penalty. After replaying every strategy across the
v2 corpus, the runner produces a per-strategy delta:

| Strategy | v1 overall | v2 overall | Δ | trend |
| --- | --- | --- | --- | --- |
| (deterministic per run; see `consistency_score` records) | … | … | … | … |

The current v2 replay shows the v2 corpus challenges every family simultaneously —
all four families (`directional_convexity`, `volatility_expansion`,
`volatility_compression`, `short_duration_defined_risk`) are flagged as `is_challenged`
under the v2 stress (mean pressure > 0.10 or high_uncertainty_windows ≥ 2). The mean
overall consistency overall scores remain deterministic and reproducible across runs.

## Family consistency impacts

The v2 corpus is intentionally more punishing than v1. Key observations from the
v2 runner:

- `volatility_compression` (mean pressure 0.142) and `short_duration_defined_risk`
  (mean pressure 0.155) carry the highest mean pressure; the v2 corpus is dominated
  by liquidity-stress and cross-family-challenge windows, which historically punish
  these families.
- `directional_convexity` (mean pressure 0.030) and `volatility_expansion` (mean
  pressure 0.012) carry the lowest mean pressure; the v2 corpus still has windows
  that support both (e.g. clean_multi_signal_directional_confirmation supports all
  families).
- All 4 families are challenged by ≥ 5 high-uncertainty windows.

## Top consistent strategy and family

- Top consistent strategy: `genome-directional-convexity-spy-fixture-v1` (deterministic
  fixture output).
- Top consistent family: `directional_convexity`.

These match the v1 baseline, demonstrating that the strongest fixture-family signal is
still directional convexity even under broader stress.

## Limitations

- All v2 windows are deterministic fixture math, not real market data.
- The v2 scoring is a relative stress test: it tells us how strategies fare under broader
  sector / macro / IV / liquidity / cross-family stress, not whether they would make money
  in real life.
- The 32 windows are not exhaustive. The runner reports `recommended_next_windows` for
  any missing categories (none currently).
- Live promotion is impossible from this path. The runner runs only in `RESEARCH` mode,
  performs no broker connection, no credentials, no network access, no scheduled run,
  and creates no auto-live migration path.

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker refuses `live_allowed=true`
- Robinhood / Alpaca / Tradier stubs raise `LiveTradingDisabledError`
- No broker connection, credentials, network access, live trades, live promotion, or
  scheduled run
- Blunder integrity: **`BLUNDER_INTEGRITY_OK checked=78`**

## Files added

- `dopey_walk_forward/regime_holdout_models.py`
- `dopey_walk_forward/holdout_window_builder.py`
- `dopey_walk_forward/regime_holdout_corpus_v2.py`
- `dopey_walk_forward/corpus_coverage.py`
- `dopey_walk_forward/holdout_coverage_score.py`
- `dopey_walk_forward/regime_holdout_runner.py`
- `dopey_walk_forward/run_regime_holdout_corpus_v2.py`
- `dopey_strategy_lab/champion_corpus_v2.py`
- `tests/test_larger_regime_holdout_corpus_v2.py` (32 tests)
- `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2_REPORT.md`
- `DOPEY_REGIME_HOLDOUT_CORPUS_V2_LEDGER.md`
- `artifacts/dopey/regime_holdout_corpus_v2/corpus_registry.jsonl`
- `artifacts/dopey/regime_holdout_corpus_v2/corpus_v2_replay.jsonl`
- `artifacts/dopey/regime_holdout_corpus_v2/corpus_coverage.jsonl`
- `artifacts/dopey/regime_holdout_corpus_v2/corpus_v2_proof.jsonl`
- `artifacts/dopey/regime_holdout_corpus_v2/corpus_v2_summary.md`
- `artifacts/dopey/regime_holdout_corpus_v2/fixtures/window_*.json` (32 fixtures + analysis)
- `artifacts/dopey/champion_registry/champion_corpus_v2.jsonl`

## Files modified

- `dopey_walk_forward/__init__.py` — exports v2 models and runner.
- `dopey_strategy_lab/ensemble_models.py` — `StrategyAllocationCandidate` now carries
  `corpus_v2_consistency_score` and `corpus_v2_consistency_verdict`.
- `dopey_strategy_lab/allocation_policy.py` — `AllocationScoreBreakdown` adds
  `corpus_v2_component` and `corpus_v2_penalty`; reason codes include
  `weak regime/holdout corpus v2 consistency penalizes paper attention`.
- `dopey_strategy_lab/ensemble_allocator.py` — stamps the v2 consistency lookup onto
  every candidate.
- `dopey_strategy_lab/__init__.py` — exports `champion_corpus_v2`.
- `dopey_governor/proof_evidence_loader.py` — `EvidenceBundle` carries
  `regime_holdout_corpus_v2`.
- `dopey_governor/proof_quality.py` — `EVIDENCE_LAYER_NAMES` includes
  `regime_holdout_corpus_v2`; layer score based on v2 mean overall.
- `dopey_audit/artifact_loader.py` — recognizes the v2 artifact types
  (`regime_holdout_corpus_v2_registry`, `regime_holdout_corpus_v2_replay`,
  `regime_holdout_corpus_v2_coverage`, `regime_holdout_corpus_v2_proof`).
- `dopey_audit/hash_auditor.py` — `STRICT_HASH_TYPES` includes
  `regime_holdout_corpus_v2_registry`.
- `dopey_audit/evidence_gap_planner.py` — gap categories include
  `weak_regime_holdout_corpus_v2_evidence` and `regime_holdout_corpus_v2_missing`.
- `dopey_audit/audit_runner.py` — passes the v2 registry into the planner + summary.
- `DOPEY_WALK_FORWARD_REPORT.md`, `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_REPORT.md`,
  `DOPEY_OFFLINE_META_GOVERNOR_REPORT.md`, `DOPEY_OFFLINE_ENSEMBLE_ALLOCATOR_REPORT.md`,
  `DOPEY_OFFLINE_EVIDENCE_REPLAY_AUDIT_REPORT.md`, `DOPEY_VALIDATION_REPORT.md`,
  `DOPEY_CANON.md` — cross-references + updates.

## Tests run

- `python -m pytest -q` -> **424 passed** (392 prior + 32 larger-regime-holdout-corpus-v2),
  0 failures, 0 errors.

## Known gaps

- Governance scores remain deterministic fixture math, not live performance evidence.
- The 56-window corpus is broader but not exhaustive; even more cross-family
  challenge windows would further stress-test family-level evidence.
- The `directional_convexity` family still dominates the strongest tier; broader
  diversification would require a deeper mutator or family-mutation pass.
- Live migration is still documentation-only; no auto-live path is introduced.

## Next recommended build target

`deterministic_sector_peer_fundamental_fixture_expansion` — broaden the corpus with
sector-peer-relative + fundamental + valuation context so family consistency can
differentiate on a wider fundamental surface.

## Update: sector / peer / fundamental context integration

The corpus v2 runner now records the fundamental summary alongside the macro and
pattern summaries. Each strategy is scored against the sector/peer/fundamental
scenario library per regime, and the new amily_fundamental_scores block is
written into the v2 registry. The deterministic fixtures are offline, paper-only,
and live-blocked.
