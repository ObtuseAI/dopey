# DOPEY TOURNAMENT REPORT

## Purpose
The **offline multi-strategy paper tournament** (`dopey_tournament`) is the fourth executable
Dopey pass. It extends the walk-forward replay harness to run multiple `StrategyGenome`
candidates across the same deterministic fixture windows, computes S-tier analysis fusion
(macro/microstructure/technical/fundamental/pattern) per window, ranks candidates by a combined
walk-forward + analysis-fusion score, records a champion registry, and feeds summary into the
`ProofWeightedAggressionGate`. Fully offline, paper-only, fixture-based, deterministic,
live-blocked: no broker, no credentials, no network, no live promotion.

## Strategy families added
4 deterministic defined-risk `StrategyGenome` candidates (`dopey_tournament/genome_set.py`):

1. **directional_convexity** — long-call vertical on trend; prefers `low_vol_bull`.
2. **volatility_expansion** — long convexity on IV expansion; prefers `trend_vol_expansion`.
3. **volatility_compression** — defined-risk long-call vertical on a vol-compression breakout
   setup; prefers `chop_vol_compression`.
4. **short_duration_defined_risk** — short-DTE defined-risk long-call vertical; prefers
   `neutral`.

All paper-only (`live_allowed=False`), all defined-risk (`structure_risk: defined`), no naked
undefined-risk selling, no live eligibility. Each genome carries thesis/entry/exit/
contract-selection/spread-construction/sizing/invalidation/regime/liquidity/event/
analysis-layer-preferences rules + proof-score placeholder + promotion tier.

## Analysis layers implemented (S-tier architecture)
`dopey_analysis/` package — first-class analysis interfaces. **Deterministic offline fixture
interfaces, NOT real market-data integrations.** No single layer is final authority.

- `macro_analysis.py` — risk-on/off, volatility-regime, event-risk shock handling (penalize),
  sector rotation, breadth, liquidity regime. DEFERRED real data: rates/yields, CPI/PPI/FOMC
  calendar, dollar strength, VIX/VVIX feeds, futures/overnight pressure.
- `microstructure_analysis.py` — spread quality, liquidity, slippage sensitivity, volume/OI
  anomalies, quote stability, contract fillability, execution-quality attribution. DEFERRED:
  live quote pressure, order-book imbalance, intraday liquidity-window feed.
- `technical_analysis.py` — trend structure, momentum, realized volatility, range
  compression/expansion, breakout/fakeout detection, support/resistance zones, MA regime,
  volume confirmation, gap behavior. DEFERRED: live OHLCV feed, intraday pattern state.
- `fundamental_analysis.py` — earnings/filing event risk, valuation context, growth quality,
  analyst revisions, sector/peer, fundamental regime, company event risk. DEFERRED: earnings
  calendar, SEC filing feed, analyst revision feed, sector/peer comparison.
- `pattern_recognition.py` — volatility patterns, price-action patterns, options-chain
  anomalies, IV skew/term-structure patterns, unusual volume/OI patterns, regime-transition
  patterns, failed-breakout patterns, continuation/reversal patterns, strategy outcome
  patterns, recurring failure-mode patterns. DEFERRED: large ML pattern recognition model.
- `analysis_fusion.py` — combines all five layers into one `AnalysisFusionScore`. Rule: no
  single layer dominates. Contradictions (large spread between layers) incur a penalty. Any
  layer below 0.25 caps the overall toward it. Replay confirmation lifts the overall.

## How scoring works
- **Per-layer scores** (0..1) derived from each context via its `score_*` function.
- **AnalysisFusionScore**: balanced weights (macro 0.20, micro 0.20, technical 0.20,
  fundamental 0.15, pattern 0.15, replay-confirmation 0.10) minus contradiction penalty; a
  weak layer (<0.25) drags the overall toward `min_layer + 0.25`.
- **Combined tournament score**: `0.6 * walk_forward_overall + 0.4 * analysis_fusion_overall`.
- **Ranking**: strategies sorted by combined_score descending; rank 1 = champion, rank 2 =
  runner-up.
- **Family scorecard**: per-family avg combined/walk-forward/analysis-fusion, pass rate,
  overfit rate, failure modes.

## Champion registry path
`artifacts/dopey/champion_registry/champion_registry.jsonl` — append-only JSONL; one
`ChampionRegistryEntry` per tournament run (champion, runner-up, family ranking,
walk-forward/analysis-fusion summaries, overfit summary, paper-only promotion status, run id,
reproducibility hash).

## ProofLedger tournament path
`artifacts/dopey/tournaments/dopey_tournament.jsonl` — append-only JSONL; one reproducibility-
hashed `ProofEntry` per tournament run (strategy rankings, family scorecard, overfit summary,
promotion decisions, strategy scores, champion/runner-up).

## Command to run
```
python -m dopey_tournament.run_fixture_tournament
```

## Sample JSON summary
```json
{
  "mode": "RESEARCH",
  "live_trading_enabled": false,
  "tournament_status": "ok",
  "champion_strategy_id": "genome-directional-convexity-spy-fixture-v1",
  "runner_up_strategy_id": "genome-volatility-expansion-spy-fixture-v1",
  "windows_replayed": 4,
  "strategies_evaluated": 4,
  "champion_registry_path": "artifacts/dopey/champion_registry/champion_registry.jsonl",
  "proof_record_path": "artifacts/dopey/tournaments/dopey_tournament.jsonl",
  "live_blocked": true,
  "promotion_decisions": {
    "genome-directional-convexity-spy-fixture-v1": "paper_candidate",
    "genome-volatility-expansion-spy-fixture-v1": "paper_candidate",
    "genome-volatility-compression-spy-fixture-v1": "paper_candidate",
    "genome-short-duration-defined-risk-spy-fixture-v1": "paper_candidate"
  },
  "overfit_summary": { "...": "none" },
  "family_scorecard": { "...": { "avg_combined_score": 0.573, "pass_rate": 1.0 } },
  "reproducibility_hash": "63016f4a..."
}
```

## Safety state
- `mode` = `RESEARCH`; `live_trading_enabled` = `false`;
  `funded_broker_connections_enabled` = `false`;
  `allow_unofficial_robinhood_api` = `false`.
- All genomes are paper-only (`live_allowed=False`) and defined-risk.
- `PaperBroker` is the only execution adapter; refuses live intents.
- Robinhood/Alpaca/Tradier stubs still raise `LiveTradingDisabledError`.
- Promotion is paper-only: allowed targets are `rejected`, `research_only`, `paper_candidate`,
  `tournament_champion_paper_only`; live promotion is impossible from this path.
- No broker connection, no credentials, no network, no Blunder modification.
- Original Blunder sources on `Z:` verified unchanged via SHA256 (78/78, 0 mismatches).
- No profit claims; tournament PnL is explicitly simulated/paper-only.

## Files added
- `dopey_analysis/` package (8 modules): `models.py`, `macro_analysis.py`,
  `microstructure_analysis.py`, `technical_analysis.py`, `fundamental_analysis.py`,
  `pattern_recognition.py`, `analysis_fusion.py`, `enrichment.py`, `__init__.py`.
- `dopey_tournament/` package (7 modules): `genome_set.py`, `models.py`,
  `aggression_tournament.py`, `ledger_tournament.py`, `runner.py`,
  `run_fixture_tournament.py`, `__init__.py`.
- `dopey_data/fixtures/walk_forward/window_*_analysis.json` (4 per-window analysis contexts).
- `tests/test_tournament.py` (15 new tests).
- `DOPEY_TOURNAMENT_REPORT.md` (this file).

## Files modified
- `dopey_walk_forward/window_model.py` — `load_walk_forward_windows` now skips
  `*_analysis.json` files (so analysis fixtures don't get parsed as windows).
- (docs) `DOPEY_CANON.md`, `DOPEY_VALIDATION_REPORT.md`, `DOPEY_WALK_FORWARD_REPORT.md`.

## Tests run
```
python -m pytest -q   -> 54 passed (39 prior + 15 tournament), 0 failures
```
New tournament tests (`tests/test_tournament.py`):
1. `test_01_analysis_context_models_serialize`
2. `test_02_analysis_fusion_penalizes_contradictions`
3. `test_03_tournament_loads_multiple_genomes`
4. `test_04_all_tournament_genomes_are_defined_risk_or_paper_safe`
5. `test_05_tournament_is_deterministic`
6. `test_06_tournament_uses_paper_broker_only`
7. `test_07_tournament_rejects_live_allowed_intent`
8. `test_08_tournament_ranks_by_walk_forward_and_analysis_fusion`
9. `test_09_champion_registry_written`
10. `test_10_proof_ledger_tournament_record_written`
11. `test_11_aggression_gate_cannot_promote_live_from_tournament`
12. `test_12_existing_live_stubs_still_block_after_tournament`
13. `test_13_paper_broker_still_refuses_live_allowed_after_tournament`
14. `test_14_config_still_research_after_tournament`
15. `test_15_blunder_source_integrity_if_manifest_available`

## Known gaps
- The replay engine only constructs long-call verticals, so all 4 genomes replay identically
  (the combined scores tie; stable sort ranks by insertion order → directional_convexity wins).
  Differentiating family-level replay (put verticals, calendars, iron flies) is a future target.
- Analysis layers are deterministic fixture stubs; no real market-data feeds.
- Crude deterministic exit model + fixed 0.2% slippage heuristic.
- Small 4-window corpus; larger regime corpus would strengthen coverage.
- No schedule/daemon; the tournament is invoked manually only.
- Champion earned `paper_candidate` (not `tournament_champion_paper_only`) because the
  gap-reversal window drags analysis-fusion overall below the 0.55 champion threshold — this
  is correct behavior (the fusion gate is working), not a bug.

## Next recommended build target
**Larger offline regime fixture corpus** — expand the walk-forward windows across more regime
tags and differentiated outcomes so the analysis fusion + walk-forward scoring can distinguish
strategy families and the champion threshold becomes meaningful. This builds directly on the
tournament + analysis architecture now in place.
