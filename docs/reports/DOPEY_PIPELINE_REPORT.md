# DOPEY PIPELINE REPORT

## Pipeline purpose
The **offline paper research pipeline** (`dopey_research_pipeline`) is the first complete,
executable Dopey loop. It proves DOPEY can take a fixture option chain, rank/select a paper
candidate, generate a paper execution intent, simulate a `PaperBroker` fill, log execution
quality, and append a structured proof/outcome record to the `ProofLedger` — fully offline,
deterministic, and live-blocked. No broker connection, no credentials, no live order placement,
no network access.

## Files added
- `dopey_research_pipeline/__init__.py`
- `dopey_research_pipeline/fixtures.py` — fixture chain loader (SPY_FIXTURE).
- `dopey_research_pipeline/ranker.py` — extended deterministic contract ranking (liquidity,
  spread, volume, OI, delta band, IV context, slippage estimate).
- `dopey_research_pipeline/strategy_fixture.py` — deterministic defined-risk
  `StrategyGenome` ("directional_convexity", long-call vertical) + proof bundles.
- `dopey_research_pipeline/aggression.py` — maps the `ProofWeightedAggressionGate` onto
  paper-only promotion targets (`paper_candidate`/`research_only`/`rejected`); never live.
- `dopey_research_pipeline/intent_builder.py` — builds a paper `ExecutionIntent`
  (`live_allowed=false`, `broker_preference="paper"`, defined-risk, max_loss, target_profit,
  invalidation rule, proof score, aggression tier).
- `dopey_research_pipeline/fill_simulator.py` — deterministic paper fill (mid ± 0.2% slippage)
  via `PaperBroker`; refuses live intents.
- `dopey_research_pipeline/quality_ledger.py` — execution-quality object + `ProofEntry`
  assembly + reproducibility hash.
- `dopey_research_pipeline/pipeline.py` — orchestrator (`run_pipeline`).
- `dopey_research_pipeline/run_fixture_pipeline.py` — `python -m` entry point.
- `dopey_data/fixtures/spy_fixture_chain.json` — deterministic fixture chain.
- `tests/test_pipeline.py` — 10 new tests.
- `DOPEY_PIPELINE_REPORT.md` (this file).

## Files modified
- `dopey_execution/execution_intent.py` — additive paper-pipeline fields; `validate()` now
  rejects `live_allowed=true` and non-paper `broker_preference`. Backward compatible.
- `dopey_execution/order_intent_validator.py` — derives `supports_structure` from
  `supported_structures`, requires `max_loss > 0`, supports `fixture_symbols` chain check.

## Fixture data description
`dopey_data/fixtures/spy_fixture_chain.json`:
- Underlying: `SPY_FIXTURE`, price 450.0 USD.
- 9 option contracts across 2 expiries (`2024-01-19`, `2024-02-16`):
  - calls at strikes 440/450/460 (Jan) and 450/460 (Feb)
  - puts at strikes 440/450 (Jan) and 440/450 (Feb)
- Varied bid/ask spreads (e.g. 8.10/8.35 tight vs 4.30/4.70 wide), varied IV (0.15–0.20),
  varied volume (2 200–9 800) and open interest (4 100–42 000), and Greeks
  (delta/gamma/theta/vega/rho) populated per contract.
- No external data calls; no real-time dependency.

## How to run the pipeline
```
python -m dopey_research_pipeline.run_fixture_pipeline
```
(Also importable: `from dopey_research_pipeline import run_pipeline; run_pipeline()`.)

## Sample JSON output
```json
{
  "mode": "RESEARCH",
  "live_trading_enabled": false,
  "pipeline_status": "ok",
  "strategy_id": "genome-directional-convexity-spy-fixture-v1",
  "execution_intent_id": "paper-intent-genome-directional-convexity-spy-fixture-v1",
  "paper_order_id": "paper-1",
  "proof_record_path": "C:\\Users\\CH\\dopey\\artifacts\\dopey\\proof_ledger\\dopey_paper_pipeline.jsonl",
  "live_blocked": true,
  "promotion_decision": "paper_candidate",
  "aggression_score": 1.0,
  "validation_valid": true,
  "paper_fill_ok": true,
  "simulated_fill_price": 5.21825,
  "simulated_slippage": 0.04325
}
```

## Proof ledger output path
`artifacts/dopey/proof_ledger/dopey_paper_pipeline.jsonl` — append-only JSONL; one
`ProofEntry` per run. Each record includes: `run_id`, `task_id` (= strategy id),
`input_hash` (reproducibility hash), `execution_result.fill` + `execution_quality`,
`validation_result`, `test_results.validation_verdict` + `promotion_decision`, and
`final_status`. The ledger is a local artifact only; no network.

## Safety state
- `mode` = `RESEARCH`; `live_trading_enabled` = `false`;
  `funded_broker_connections_enabled` = `false`;
  `allow_unofficial_robinhood_api` = `false`.
- `ExecutionIntent.live_allowed` defaults to `false`; the builder never sets it true.
- `PaperBroker` and the fill simulator refuse `live_allowed=true` (raise
  `LiveTradingDisabledError`).
- Robinhood/Alpaca/Tradier adapters still raise `LiveTradingDisabledError` for live orders.
- No broker connection, no credentials, no network access, no Blunder modification.
- Original Blunder sources on `Z:` verified unchanged via SHA256 (78/78, 0 mismatches).
- No profit claims; fill quality is explicitly "simulated_paper_only".

## Tests run
```
python -m pytest -q   -> 27 passed (17 bootstrap + 10 pipeline), 0 failures
```
New pipeline tests (`tests/test_pipeline.py`):
1. `test_01_fixture_chain_loads`
2. `test_02_contract_ranker_is_deterministic`
3. `test_03_strategy_genome_fixture_is_defined_risk`
4. `test_04_aggression_gate_allows_paper_only`
5. `test_05_execution_intent_builder_sets_live_allowed_false`
6. `test_06_order_intent_validator_rejects_live_intent`
7. `test_07_paper_broker_simulates_fill_only`
8. `test_08_pipeline_appends_proof_ledger_record`
9. `test_09_pipeline_does_not_enable_live_trading`
10. `test_10_robinhood_alpaca_tradier_stubs_still_block_live`

## Known gaps
- The pipeline runs a single deterministic fixture genome (one family: directional convexity).
  Multi-strategy paper tournaments are a future target.
- The fill simulator uses a fixed 0.2% slippage heuristic; it does not model real market impact
  or queue dynamics (and must not imply real execution quality).
- Execution-quality metrics are naive (avg spread, avg liquidity); richer Greeks validation is
  a future target.
- The proof ledger is a local JSONL artifact; no walk-forward replay harness consumes it yet.
- No network data adapter performs real fetches (all offline fixtures).

## Next recommended build target
**Offline walk-forward replay harness** — consume the `ProofLedger` records produced by this
pipeline, replay recorded strategy genomes over historical fixture windows, and score
walk-forward consistency / overfit without any live or network path. This builds directly on the
proof-ledger + genome + aggression-gate foundation now in place.