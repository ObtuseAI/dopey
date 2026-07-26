# DOPEY Durability, Resilience, and Intelligence Review

- Date: 2026-07-26
- Branch: `agent/dopey-audit-targeting-2026w30`
- Baseline specification: `docs/superpowers/specs/2026-07-26-dopey-full-audit-and-per-symbol-targeting-design.md`
- Current posture: paper research only, live blocked, not action ready
- Current system snapshot: `snapshot:51a469854ba9edc36b0f0330`

## Outcome

The critical supervisor defect and the highest-value measurement, data,
storage, and process-resilience defects are closed. DOPEY now has a
gate-blind per-symbol targeting lane, immutable candidate-registry
generations, stricter source contracts, corrected scanner and trade-memory
measurement, safer process control, and durable evidence writes.

The result is intentionally not described as profitable, live ready, or
fully autonomous. Current evidence supports none of those claims:

- Action readiness remains `not_action_ready`.
- Validated forward closes remain 13 of the required 100.
- Resolved context decisions remain 1 of the required 200.
- No playbook family has 30 independent effective contested clusters.
- Targeting has 225 candidates but zero verified candidates.
- No phantom or real targeting position was opened.

## Current evidence state

### Per-symbol targeting

Every symbol in the validated history spine remains represented:

- Validated symbols: 225
- Validated bars: 1,808,325
- Candidate registry entries: 225
- Candidate state: 225 `blocked_invalid_or_stale_upstream_evidence`
- Verified candidates: 0
- Stale or mismatched evidence consumed: false
- Gate inputs read: none
- Live-book inputs read: none
- Order capability: absent

The sole blocker is `no_current_policy_settlements`. The new playbook v2 pass
has already recorded 572 current-policy detections across all 225 symbols,
and a second pass appended zero duplicates. Those detections must mature
before the targeting lane can earn current v2/v4 settlement evidence.

The 727 prior settlement rows are preserved, not rewritten. They predate the
new scan/trust provenance contract and are excluded from targeting. Stable
forecast and shadow-evidence aliases now contain explicit blocked records, so
direct readers cannot accidentally consume the older forecast artifact.

Each registry is stored immutably at
`artifacts/dopey/targeting/registry_generations/<reproducibility_hash>.json`
before the stable alias is replaced. Shadow signals embed the decisive
candidate fields and deduplicate by immutable source detection ID, not by a
mutable registry hash. The append path enforces positive selected weights,
the 20-symbol limit, a 10-symbol per-direction limit, and one selected signal
per symbol.

### Scanner fitness v5

The corrected scanner baseline uses one unique symbol-date as the pooled
event unit:

- Unique symbol-date events: 8,015
- Raw detector firings: 11,800
- Co-fire duplicates exposed: 3,785
- Symbols: 40, selected by deterministic SHA-256 spread
- Detector exceptions: 0
- Deduplicated mean excess over drift: -0.001436
- Deflated mean excess: -0.000703
- Deduplicated hit rate: 0.4901
- Fitness score: 0.471880

Four detector-level means are positive, but the pooled result is negative and
no edge is claimed. The artifact is versioned, freshness-stamped, source
hashed, and records its point-in-time drift and event-deduplication policies.

### Playbook trust v4

The trust layer now separates raw, policy-eligible, and effective clustered
samples. Daily overlapping settlement windows are connected within each
symbol and count as one effective cluster.

- Graded historical settlements summarized: 687
- Rating-eligible historical rows after direction/framing quarantine: 42
- Mean-reversion effective contested clusters: 13
- Momentum-trend effective contested clusters: 11
- Flow-positioning effective contested clusters: 0
- Rated families: 0

Legacy hard-coded squeeze direction rows and legacy big-mover dual-framing
rows are preserved but ineligible. New big-mover scans evaluate both
hypotheses and record only the independently selected framing.

### Trade memory v3

The active packet was rebuilt from the verified source ledger:

- Generation: `20260726T053825067407Z-5c5809ef1363`
- Source rows: 321,768
- Indexed rows: 321,768
- Unique economic trades: 186,640
- Row fanout ratio: 1.724003
- Duplicate-content rows: 0
- Quarantined corrupt rows: 0
- SQLite integrity: `ok`
- Indexed parity: true
- Packet validation: passed

Outcome statistics now use fractional model returns. Indexable long-premium
rows require finite PnL, finite positive entry premium, a return above the
total-loss floor, and PnL/entry identity agreement. The audit's original
claim that every premium-dollar PnL below -1 was impossible was too broad;
the identity-based rebuild found no actually impossible row in the current
source.

Internal consumers now resolve the atomically replaced and hash-validated
`active_generation.json` pointer. Immutable generation files are authoritative;
the four root-level packet files remain compatibility copies.

## Audit fixes implemented

### Supervisor and operations

- L3-1: corrected kaizen stage topology after `adversarial_stress`.
- L3-2/L3-5: made weekend soak compatible with real run duration, process-tree
  termination, tombstones, and matching run IDs.
- L3-3: synchronized all supervisor status keys.
- L3-4: hardened acceleration locks against PID reuse and ownership races.
- L3-7: restored the forecast-card upper bound.
- L3-8: process-tree termination now covers cycle, nightly shard, nightly
  fitness, and soak timeouts.
- L3-9: disk/lock early returns are journal-visible and nonzero.
- L3-13: degraded classification uses explicit statuses and safe scoped
  prefixes/suffixes.
- Healthy `within_error_budget` status is no longer inverted to failure.

The current topology has 38 stages. `symbol_targeting` is stage 28, after
`playbook_research` and `model_iv_calibration`.

### Measurement truth

- L1-1: discipline-halt re-arm uses validated closed trades.
- L2-1: scanner drift accumulation is point-in-time and maturity lagged.
- L2-2: removed history symbols force a full signal recompute.
- L2-11: detector exceptions are counted and invalidate measurement.
- L2-12: alphabetical first-40 selection was replaced by hash-spread selection.
- L2-13: pooled co-fired events are deduplicated by symbol-date.
- L5-1: trade-memory returns use fractional units.
- L5-2: accounting-identity corruption guard and unique-trade reporting.
- L5-3: big-mover dual-framing is independently selected.
- L5-4/L5-7: trust is rated on effective contested clusters.
- L5-6: negative-GEX and crowded-short contexts are non-directional until
  independent price confirmation.

### Data durability

- Atomic fsync-and-replace writes cover macro, IPO, short-interest,
  threshold, margin, scan, manifest, IV-calibration, playbook-stage, and
  acceleration JSON outputs.
- L4-2/L4-5: XNYS-aware gap detection makes real missing sessions fatal and
  no longer treats exchange holidays as gaps. The reported 37-symbol gap
  condition contained zero true XNYS gaps.
- L4-7/L4-8/L4-9: atomic macro writes, bounded Yahoo retries/adaptive lookback,
  and owner-safe stale-lock takeover.
- L4-16: manifest paths reject absolute and parent traversal.
- L4-6/L4-13: active-lake summaries validate actual CSV bytes and reject
  nonfinite, nonpositive, negative-volume, and OHLC-inconsistent rows.
  Failed-quality files cannot inflate active symbol, row, or tier counts.

### Storage and cleanup

The session began at approximately 22.55 GB free (4.42 percent) with write
backpressure active. Eighteen stale pytest isolation trees were removed
during the initial cleanup. The final state retains only the newest three
trees:

- Free space: 31,682,756,608 bytes (29.51 GiB, 6.20 percent)
- Pressure: `ELEVATED`
- Write backpressure: false
- Artifact size: 12,856,132,557 bytes

Cleanup now handles a missing temp root as a successful no-op, rechecks for
new pytest processes before every recursive deletion, rejects reparse points
and path escapes, and labels removed-byte values as estimates rather than
filesystem free-space deltas.

### Autonomy and safety

- Unknown cognitive policy operations raise instead of defaulting to
  `EMPHASIZE`.
- Resolved readiness bottlenecks are no longer reported as unresolved.
- Claim-compiler transport errors redact API keys.
- Targeting source contracts validate history bytes/hashes, playbook policy
  provenance, scanner version/source/freshness, and IV version/freshness.
- Candidate, forecast, shadow, scanner, memory, and trust artifacts retain
  paper-only, live-blocked, no-promotion semantics.

## Verification

- Integrated affected regression suite: 252 passed in 98.61 seconds.
- Repository collection: 4,307 tests collected with zero collection errors.
- Focused trade-memory active-pointer and targeting tests: passed.
- Production scanner v5 rebaseline: completed.
- Production IV calibration v1 refresh: 10,037 contracts across 205 symbols.
- Production trade-memory v3 rebuild: packet validation and parity passed.
- Production playbook v2 scan: 572 detections, zero detector errors; second
  pass appended zero duplicates.
- Production targeting source validation: one explicit blocker, zero stale
  evidence consumed.
- Ruff: passed for all scoped source and test files.
- Compileall: passed for all scoped source files.
- Scoped `git diff --check`: passed; only line-ending notices were emitted.
- Protected roots: no changes.

The full 4,307-test execution and a full 38-stage production supervisor run
were not performed. The newest production supervisor journal predates the
38-stage topology, so this report claims topology/unit/direct-stage proof,
not a completed end-to-end supervisor soak.

## Remaining work

The most valuable remaining work is:

1. Let the 572 current-policy detections mature and settle; targeting remains
   blocked until this real evidence exists.
2. Implement the governed adjusted-close overlap/restatement policy. It was
   not guessed because historical rewrites need an explicit divergence and
   provenance contract.
3. Add stable repair-queue item IDs and an append-only resolution producer
   before making its SLI green.
4. Complete the performance program: shared validated-spine cache, streaming
   large directional JSONL readers, sort-once/bisect signal evaluation,
   causal O(n) foundry primitives, and market-lake byte deduplication.
5. Extend per-symbol skill beyond current playbook settlements to
   point-in-time scanner event rows and trade-memory cases. Rank IC remains
   explicitly unavailable until detections carry a continuous point-in-time
   score.
6. Replace fixed close-to-close phantom settlement with the walk's exact
   injected selection, marking, and exit-policy path, then add point-in-time
   sector classification for sector concentration caps.
7. Run the full test suite and one complete 38-stage supervisor soak when the
   machine can remain available for the approximately 7-11 hour window.

No gate, threshold, sentinel, live-book path, credential path, broker path, or
order path was weakened or enabled.
