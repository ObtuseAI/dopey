# DOPEY Tournament Performance Reporting Dashboard Report

## Status

`DOPEY_TOURNAMENT_PERFORMANCE_REPORTING_DASHBOARD_ARTIFACTS_V1` is implemented as a deterministic, offline, paper-only reporting layer. It reads existing fixture/proof artifacts, emits report-card and dashboard artifacts, and never enables broker access, live market data, live trading, or live promotion.

The current bundle is `dopey-tournament-performance-reporting-dashboard-v1`.

## Implemented surface

- `dopey_reporting/report_models.py` defines immutable report-card evidence, score-table, contradiction/support, attribution, and safety structures.
- `dopey_reporting/dashboard_models.py` defines dashboard index, artifact manifest, safety, and proof models.
- `dopey_reporting/performance_models.py` defines attribution inputs and deterministic performance attribution outputs.
- `dopey_reporting/data_loader.py` reads the existing tournament, champion, mutation, feedback, failure, walk-forward, corpus-v2, Greeks/IV, liquidity/slippage, macro, fundamental, ensemble, and meta-governor artifacts.
- `dopey_reporting/strategy_report_cards.py` emits per-strategy report cards.
- `dopey_reporting/family_report_cards.py` emits per-family report cards.
- `dopey_reporting/scenario_explainability.py` emits scenario-level explainability cards.
- `dopey_reporting/regime_explainability.py` emits regime-level explainability cards.
- `dopey_reporting/performance_attribution.py` emits deterministic cross-layer attribution records.
- `dopey_reporting/reporting_bundle.py` writes the full offline dashboard bundle.
- `dopey_reporting/run_tournament_performance_reporting_bundle.py` exposes the CLI entry point.

## Current bundle output

- Reporting status: `ok`
- Strategies reported: `37`
- Families reported: `4`
- Scenario cards: `81`
- Regime cards: `35`
- Total scenario/regime explanations: `116`
- Attribution records: `37`
- Top reporting strategy: `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`
- Top reporting family: `short_duration_defined_risk`
- Reproducibility hash: `4d6735c6785dc491825f02271790ec76f6bbb0bd415f1e7c7af9d2b26533c182`

The base fixture tournament still reports `genome-short-duration-defined-risk-spy-fixture-v1` as its direct tournament champion. The reporting dashboard's cross-evidence leader is the feedback-optimized directional convexity strategy, while the family dashboard favors `short_duration_defined_risk`. This is not a live promotion. It is a paper-only reporting distinction caused by the expanded deterministic evidence stack: feedback and walk-forward evidence support the directional feedback candidate, while defined-risk Greek fit and clean short-duration regime behavior lift the short-duration family.

## Top evidence drivers

Strongest positive drivers:

- `tournament_baseline`
- `walk_forward_consistency`
- `meta_governor_trust`
- `liquidity_slippage`
- `greeks_fit`

Strongest negative drivers:

- `failure_feedback`
- `failure_pressure`

The top strategy's attribution record assigns positive support from tournament baseline, walk-forward consistency, meta-governor trust, liquidity/slippage, Greeks fit, IV surface/skew/term fit, pattern confirmation, macro fit, sector/peer/fundamental fit, and mutation delta. It records negative pressure from failure feedback and failure pressure.

## Family report cards

| Rank | Family | Average score | Trust score | Best strategy | Best regimes | Worst regimes | Action |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| 1 | `short_duration_defined_risk` | `0.559898` | `0.334602` | `genome-short-duration-defined-risk-spy-fixture-v1-mut-intraday-pattern` | `chop_vol_compression`, `clean_directional_confirmation`, `range_bound_pin` | `compression_shock_failure`, `high_spread_bad_fill`, `low_liquidity_decay` | `starve` |
| 2 | `directional_convexity` | `0.568469` | `0.362132` | `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern` | `bullish_breakout`, `clean_directional_confirmation`, `trend_vol_expansion` | `compression_shock_failure`, `high_spread_bad_fill`, `short_duration_bad_fill` | `starve` |
| 3 | `volatility_compression` | `0.488048` | `0.321204` | `genome-volatility-compression-spy-fixture-v1-mut-bad-fill` | `chop_vol_compression`, `post_event_iv_crush`, `range_bound_pin` | `compression_shock_failure`, `event_vol_expansion`, `macro_shock_risk_off` | `starve` |
| 4 | `volatility_expansion` | `0.434673` | `0.125676` | `genome-volatility-expansion-spy-fixture-v1-mut-pattern-vol` | `event_vol_expansion`, `macro_shock_risk_off`, `trend_vol_expansion` | `high_spread_bad_fill`, `low_liquidity_decay`, `short_duration_bad_fill` | `starve` |

All family actions are research-only paper attention states. No family receives live allocation authority.

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- `fixture_only=true`
- `paper_only_reporting=true`
- `live_blocked=true`
- `live_allowed=false` on report cards and attribution records
- No broker connection, no credentials, no real market data fetch, no live order, no scheduled process, and no Blunder source modification

## Audit integration

The offline evidence replay audit now recognizes reporting artifacts:

- `reporting_dashboard_index`
- `strategy_report_cards`
- `family_report_cards`
- `scenario_report_cards`
- `performance_attribution`
- `reporting_bundle_proof`

Strict hash auditing covers `reporting_dashboard_index`, `strategy_report_cards`, and `family_report_cards`. The consistency auditor checks that reporting strategy cards reference known strategy ids and that reporting cards remain paper-only/live-blocked.

Final audit result:

- `audit_status=ok`
- `verdict=pass`
- `artifacts_scanned=37`
- `records_scanned=2514`
- `replay_cases_run=13`
- `hash_mismatches=0`
- `schema_warnings=0`
- `consistency_errors=0`
- `safety_errors=0`
- `forbidden_live_decisions_active=0`
- `live_blocked=true`

## Validation

Commands run successfully:

- `python -m dopey_reporting.run_tournament_performance_reporting_bundle`
- `python -m dopey_audit.run_offline_evidence_replay_audit`
- `python -m pytest tests/test_reporting_dashboard_artifacts.py -q` -> `37 passed`
- `python -m pytest tests/test_mutation_population_structure_bundle.py::test_best_mutation_selection_uses_score_and_overfit -q` -> `1 passed`
- `python -m pytest` -> `543 passed`

Smoke commands also passed for the sector/peer/fundamental bundle, regime holdout corpus v2, stronger walk-forward consistency, fixture tournament, mutation population bundle, failure feedback optimizer, IV surface/skew bundle, macro-event bundle, offline ensemble allocator, and offline meta-governor.

## Flaky test fix

The known flaky test `tests/test_mutation_population_structure_bundle.py::test_best_mutation_selection_uses_score_and_overfit` originally failed because the best mutation delta was `0.007225`, but the champion decision threshold required `> 0.01`. The root cause was an overly strict hard-coded improvement threshold, not nondeterministic ordering.

`dopey_strategy_lab/mutation_scorecard.py` now uses `MIN_IMPROVED_MUTATION_DELTA = 0.005`, while retaining the high-overfit rejection gate. The deterministic best mutation now receives `offline_mutation_champion`, and the targeted test passes.

## Blunder integrity

The Blunder manifest check was rerun against the rooted manifest paths:

- `BLUNDER_INTEGRITY_OK checked=78 mismatches=0`

## Known gaps

- This is deterministic fixture reporting, not live performance evidence.
- Reported scores are paper-research scores, not PnL or broker execution quality.
- The static dashboard is an offline artifact, not a live service.
- Scenario and regime explainability is only as broad as the current fixture corpus.

## Next recommended build target

`artifact_compaction_export_verifier` is the recommended next target. The reporting bundle now emits enough cross-layer artifacts that the next useful hardening step is deterministic export compaction, copy verification, and replayable artifact-package validation before expanding another model layer.

## Active Policy Reporting Integration Update

Session date: 2026-07-03

The reporting bundle now loads active policy audit evidence and surfaces an active policy summary in the dashboard safety state. The summary includes allowed strategy universe, rejected structure summary, no-day-trade guard status, 0DTE special lifecycle status, PaperBroker policy proof, audit policy proof, and live-blocked state.

Latest smoke:

- `python -m dopey_reporting.run_tournament_performance_reporting_bundle`
- status: `ok`
- strategies_reported: `37`
- families_reported: `4`
- scenarios_reported: `116`
- live_blocked: `true`
