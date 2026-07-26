# DOPEY Epistemic Hardening and Market Intelligence

Date: 2026-07-26  
Base: `7c69a97bc758a29549507d7d857c72c4ada6fe9a`  
Branch: `codex/dopey-epistemic-hardening-20260726`  
State: implemented, validated, and approved for publication

## Executive result

| Objective | Production result | Authority |
|---|---|---|
| Durable short-squeeze detection | Independent crowding, ignition, persistence, robustness, liquidity, freshness, and contradiction gates | Research only |
| Bubble and leverage detection | Valuation breadth, IPO reflexivity, balance-sheet stress, market margin leverage, extension, options pressure, and independent unwind confirmation | Research only |
| Hidden-liquidity analysis | Observable borrow, turnover, short-flow, options, gamma, and signed-volume proxies; no claim of hidden intent or consolidated order-book visibility | Measure only |
| Epistemic supervision | 39th supervisor stage challenges targeting and squeeze/bubble outputs and can only preserve or downgrade claims | No promotion or execution |
| Mutation integrity | Contained hash chain, immutable IDs, semantic re-verification, pinned head, truncation detection, and explicit rollback on measured fitness loss | Operator review required |
| CI stability | Content-addressed shard membership, exact collection proof, node-ID uniqueness, and strict pre/post worktree cleanliness | Validation only |

## Market intelligence mutations

| Lane | Evidence | Admission logic | Fail-closed conditions |
|---|---|---|---|
| Short crowding | Open short interest, percent float, days to cover, two-period short growth, borrow fee/utilization/availability, FTD stress, threshold-list evidence | Pressure must clear its floor | Missing actual open short interest, low liquidity, insufficient sources |
| Squeeze ignition | 5-day and 20-day returns, breakout, volume expansion, RSI, daily short-sale flow, call pressure, gamma, dollar liquidity | Ignition must independently clear its floor | Crowding alone cannot qualify |
| Squeeze durability | Two-period short interest, multi-session short flow, consecutive settlement stress, multi-horizon price ignition | Persistence and robustness must clear independent floors | Sparse, stale, future, contradictory, or weakly sourced evidence |
| Liquidity stress | Float turnover, borrow scarcity, persistent short flow, call turnover, negative gamma, signed volume | Observable proxy score only | `direct_hidden_liquidity_observed=false` |
| Bubble fragility | Trailing/forward P/E, P/S, P/B, EV/revenue, cash burn, net leverage, margin debit, price extension, options crowding, IV, attention | Fragility and valuation/IPO anchor required | A high multiple alone cannot qualify |
| IPO reflexivity | Listing age, offer-price appreciation, offer amount, float constraints | Mechanical IPO effects are separated from durable evidence | Recent IPO without nonmechanical evidence and unwind confirmation |
| Bubble unwind | Negative returns, SMA breaks, 20-day breakdown, volume confirmation, put flow, gamma, liquidity air pocket | Unwind trigger required for candidate status | Fragility without unwind remains monitor-only |

## Primary-source semantic constraints

| Source fact | Enforced interpretation |
|---|---|
| [FINRA short interest](https://www.finra.org/investors/insights/short-interest) | Twice-monthly open-position snapshot |
| [FINRA short-sale volume](https://www.finra.org/filing-reporting/trf/finra-equity-short-sale-volume-files) | Daily reported flow; never substituted for open short interest |
| [SEC fails-to-deliver data](https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data) | Aggregate net balance; not proof of naked or abusive shorting |
| [FINRA OTC transparency](https://www.finra.org/filing-reporting/otc-transparency) | Delayed off-exchange activity proxy; not hidden intent |
| [FINRA margin statistics](https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics) | Aggregate market leverage context; not symbol-level leverage |
| [SEC IPO bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-17) | Lock-up, limited float, support, dilution, and market-overhang context |
| [Investor.gov P/E definition](https://www.investor.gov/introduction-investing/investing-basics/glossary/price-earnings-pe-ratio) | Valuation input relative to history/peers; never a standalone short signal |

## Epistemic attack surface

| Attack | Detection | Result |
|---|---|---|
| Stale or future evidence | Point-in-time timestamp and artifact-cycle checks | Block |
| Prior-run artifact reuse | Producer summary, assessment, ranking, registry, and forecast coherence | Block |
| Duplicate contribution | Evidence ID, canonical fingerprint, and source-hash relabel checks | Block |
| Contradictory evidence | Within-family direction and claim/effect-sign checks | Block |
| Missing denominator | Explicit denominator floor for statistical rate/effect evidence | Block |
| Outlier domination | Maximum normalized weight and contribution share | Block |
| Simpson/regime inversion | Denominator-bearing regime cells and direction stability | Block or inconclusive |
| Crowding without catalyst | Independent catalyst identity required | Block |
| Mechanical recent IPO | Nonmechanical evidence plus unwind required | Block |
| Sector-mismatched valuation | Issuer/peer sector identity required | Block |
| Execution contamination | Research claims reject simulated, live, broker, and order-capable inputs | Block |
| Fitness laundering | Holdout, evidence reuse, parent hash, positive delta, and promotion-state checks | Block |
| Existing degraded status | Exact blocked/missing/insufficient/invalid/timeout/inconclusive string preserved | Never upgraded |

## Supervisor topology

| Stage relationship | Current state |
|---|---|
| Supervisor size | 39 stages |
| `symbol_targeting` | Hard producer for epistemic supervision |
| `squeeze_bubble_intelligence` | Hard producer for epistemic supervision |
| `epistemic_supervision` | Runs after both; atomically writes one content-addressed summary |
| `adversarial_signal_panel` | Retains its separate forward-paper mandate |
| `agentic_account_reconciliation` | Intentional independent root |
| `action_readiness_gate` | Intentional independent root |
| Research-to-execution dependency | None |

## CI and ledger hardening

| Control | Proof |
|---|---|
| Stable shard assignment | `SHA-256(test path) mod shard_count` |
| Manifest reorder | Does not change membership |
| Incremental test addition | Does not move existing tests |
| Path containment | Absolute paths, traversal, backslashes, and non-test entries rejected |
| Shard completeness | Every assigned file must collect at least one node |
| Cross-shard uniqueness | Duplicate node IDs fail the validator |
| Worktree purity | Exact porcelain check before and after pytest; no scratch exclusion |
| Ledger chain | Sequence, predecessor, entry hash, immutable mutation ID |
| Ledger head | Separately content-addressed record count and head hash |
| Fitness regression | `rollback_required`; baseline artifact hash retained |
| Corruption/crash | Future appends blocked; no silent anchor rebuild or history rewrite |

## Validation evidence

| Proof | Result |
|---|---:|
| Focused market/targeting/adversarial/supervisor integration | 50 passed |
| Focused CI and ledger integration | 13 passed |
| Deterministic CI manifest | 70 files |
| CI shard collection | 1,245 unique nodes; 0 duplicates |
| CI shard 1 execution | 332 passed |
| CI shard 2 execution | 272 passed |
| CI shard 3 execution | 305 passed |
| CI shard 4 execution | 336 passed |
| Full repository collection | 4,334 collected; 0 collection errors |
| Full repository execution | 4,332-test run was `inconclusive_timeout` at 15 minutes; no captured failure trace |
| Ruff | Passed on changed Python surfaces |
| Python compilation | Passed |
| Diff whitespace | Passed |
| Protected/live diff | Empty against base SHA |

The first local Bash manifest run selected the system Python and failed
collection because that interpreter lacked `exchange_calendars` and `tzdata`.
The same validator passed under DOPEY's canonical project environment. This is
recorded as an environment-selection failure, not erased or relabeled.

## Capability boundaries

| Allowed | Forbidden |
|---|---|
| Measure, rank, challenge, abstain, settle, and record research evidence | Claim probability, profit, hidden intent, or action readiness |
| Propose loss-limited research expressions for later governed review | Construct an order, naked short, or undefined-loss position |
| Preserve and audit mutation evidence | Rewrite history or auto-promote a mutation |
| Produce paper-only/live-blocked overlays | Import broker/live/readiness authority into epistemic supervision |

## Newly identified target scopes

1. Point-in-time ATS/non-ATS volume, securities-lending transaction, and
   consolidated order-book feeds with licensing and provenance contracts.
2. Sector- and lifecycle-matched valuation cohorts, including non-earnings
   valuation regimes for negative-EPS issuers.
3. Machine-readable catalyst identity tied to filings, earnings revisions,
   corporate actions, and news availability timestamps.
4. Regime-stratified forward settlement for squeeze and bubble claims with
   independent effective-cluster counts.
5. Empirical calibration of static thresholds only after minimum settled
   cohorts pass hidden and external holdouts.
6. Explicit operator reconciliation for interrupted ledger-anchor persistence.
7. Independent or WORM anchoring for protection against a privileged writer
   capable of reforging both local ledger and local head.
8. A bounded full-suite partition that reports exact progress before the
   current 15-minute hard limit.

## Immediate next steps

1. Accumulate real forward settlements; do not lower minimum samples.
2. Add catalyst and peer-cohort identities to producer schemas.
3. Bind legacy mutation producers to the new ledger only when they expose
   honest baseline and candidate fitness measurements.
4. Add licensed microstructure feeds as optional, provenance-gated lanes.
5. Run a full 39-stage production soak in a controlled artifact workspace.
6. Publish through the verified branch, pull-request, merge, and default-branch
   validation workflow.
