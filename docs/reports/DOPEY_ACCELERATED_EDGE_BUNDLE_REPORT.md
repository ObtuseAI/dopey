# DOPEY Accelerated Offline Edge Bundle Report

## Purpose

`DOPEY_ACCELERATED_OFFLINE_EDGE_BUNDLE_V1` compounds three offline capability lanes:

1. Source scorecard / data inflow expansion.
2. Larger deterministic pattern-recognition fixture set.
3. Offline StrategyGenome mutation and tournament evolution loop.

Everything remains offline, fixture-based, paper-only, deterministic, and live-blocked.

## Source scorecard / data inflow

- Added source candidates, contribution hypotheses, promotion decisions, scorecards, ranking,
  and a local `DataInflowRegistry`.
- Seeded 16 future source candidates.
- Promoted only offline/internal sources: ProofLedger, champion registry, pattern fixture corpus,
  and realized-vol fixture metrics.
- Deferred every network or credential source.
- Source registry: `artifacts/dopey/source_registry/data_inflow_registry.jsonl`

## Pattern fixture library

- Added 16 deterministic pattern fixtures.
- Added pattern scorecards and summary output.
- Integrated pattern fixture score into analysis fusion and tournament scoring.
- Champion registry and ProofLedger now record pattern-recognition summaries.

## Mutation / evolution loop

- Added deterministic mutation policy with 12 mutation types.
- Generated a bounded mutation batch from the current base champion.
- Evaluated mutated genomes through the offline replay-compatible scoring path.
- Wrote mutation registry and mutation ProofLedger evidence.
- Best mutation: `genome-directional-convexity-spy-fixture-v1-mut-liquidity-01`
- Parent score: 0.577118
- Best mutated score: 0.602118
- Score delta: +0.025000

## Files added

- `dopey_data/source_candidate.py`
- `dopey_data/source_registry.py`
- `dopey_data/source_value_ranker.py`
- `dopey_analysis/pattern_fixture_library.py`
- `dopey_analysis/pattern_scorecard.py`
- `dopey_strategy_lab/genome_mutation.py`
- `dopey_strategy_lab/mutation_policy.py`
- `dopey_strategy_lab/evolution_tournament.py`
- `dopey_strategy_lab/mutation_registry.py`
- `dopey_strategy_lab/run_offline_mutation_tournament.py`
- `tests/test_accelerated_offline_edge_bundle.py`
- `DOPEY_SOURCE_INFLOW_REPORT.md`
- `DOPEY_PATTERN_RECOGNITION_REPORT.md`
- `DOPEY_MUTATION_EVOLUTION_REPORT.md`
- `DOPEY_ACCELERATED_EDGE_BUNDLE_REPORT.md`

## Files modified

- `dopey_data/__init__.py`
- `dopey_data/source_scorecard.py`
- `dopey_analysis/__init__.py`
- `dopey_analysis/models.py`
- `dopey_analysis/analysis_fusion.py`
- `dopey_strategy_lab/__init__.py`
- `dopey_tournament/models.py`
- `dopey_tournament/runner.py`
- `dopey_tournament/ledger_tournament.py`
- `dopey_tournament/run_fixture_tournament.py`
- `DOPEY_VALIDATION_REPORT.md`
- `DOPEY_CANON.md`

## Proof and registry paths

- Tournament ProofLedger: `artifacts/dopey/tournaments/dopey_tournament.jsonl`
- Champion registry: `artifacts/dopey/champion_registry/champion_registry.jsonl`
- Source registry: `artifacts/dopey/source_registry/data_inflow_registry.jsonl`
- Mutation registry: `artifacts/dopey/mutations/mutation_registry.jsonl`
- Mutation ProofLedger: `artifacts/dopey/mutations/dopey_mutation_tournament.jsonl`

## Validation

- `python -m pytest tests/test_accelerated_offline_edge_bundle.py` -> 25 passed
- `python -m pytest` -> 135 passed
- Import smoke -> `ACCELERATED_EDGE_IMPORT_OK 16 16 12`
- Tournament smoke -> `tournament_status: ok`
- Mutation smoke -> `tournament_status: ok`
- Blunder integrity -> `BLUNDER_INTEGRITY_OK checked=78`

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker rejects `live_allowed=true`.
- Robinhood/Alpaca/Tradier stubs raise `LiveTradingDisabledError`.
- No broker credentials, broker connection, network market data, live trades, live promotion,
  autonomous schedule, or commit.

## Limitations

- Source scoring is metadata-only and does not fetch real data.
- Pattern fixtures are static deterministic context, not predictive signals.
- Mutation scoring is deterministic paper-policy math, not empirical performance proof.
- The mutation population is intentionally bounded to 12 child genomes.

## Next recommended build target

Larger offline mutation population.
