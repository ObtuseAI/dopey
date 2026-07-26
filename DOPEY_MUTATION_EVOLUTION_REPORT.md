# DOPEY Mutation Evolution Report

## Purpose

The offline mutation/evolution loop creates deterministic StrategyGenome variants, evaluates
them through the existing offline replay-compatible scoring path, compares child scores against
the current paper-only champion, writes a mutation registry, and appends a mutation ProofLedger
record.

No mutation can enable live trading, add broker paths, create undefined-risk selling, or bypass
validation gates.

## Model versions

- Mutation policy: `dopey-mutation-policy-v1`
- Mutation batch: `dopey-mutation-batch-v1`
- Mutation tournament: `dopey-mutation-tournament-v1`
- Mutation registry: `dopey-mutation-registry-v1`

## Mutation types

- adjust delta preference
- adjust DTE bucket
- adjust liquidity threshold
- adjust slippage tolerance
- adjust IV regime preference
- adjust pattern preference
- adjust invalidation sensitivity
- adjust regime filter
- adjust spread structure proxy
- adjust theta tolerance
- adjust vega tolerance
- adjust overfit penalty

## Latest mutation batch

- Batch id: `mutation-batch-dopey-offline-edge-v1`
- Parent champion: `genome-directional-convexity-spy-fixture-v1`
- Best mutation: `genome-directional-convexity-spy-fixture-v1-mut-liquidity-01`
- Parent score: 0.577118
- Best mutated score: 0.602118
- Score delta: +0.025000
- Best mutation decision: `offline_mutation_champion`

## Mutation outcomes

- Best/improved: `genome-directional-convexity-spy-fixture-v1-mut-liquidity-01`
- Rejected stress candidate: `genome-directional-convexity-spy-fixture-v1-mut-overfit-01`
- Other improved paper-only candidates: delta, slippage, IV, pattern, invalidation, regime,
  structure, theta, and vega variants.
- Research-only candidate: DTE adjustment.

Allowed mutation decisions are `rejected`, `degraded`, `research_only`,
`paper_research_candidate`, and `offline_mutation_champion`. No live decision is permitted.

## Artifact paths

- Mutation registry: `artifacts/dopey/mutations/mutation_registry.jsonl`
- Mutation ProofLedger: `artifacts/dopey/mutations/dopey_mutation_tournament.jsonl`

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- All mutated genomes preserve `live_allowed=false`.
- All mutated genomes preserve `defined_risk_only=true`.
- No mutation adds a broker path or live promotion state.

## Limitations

- Mutation scoring is deterministic fixture policy math, not performance proof.
- The current batch mutates the current champion only and is intentionally bounded.
- Larger populations and deeper structure mutations are deferred.
