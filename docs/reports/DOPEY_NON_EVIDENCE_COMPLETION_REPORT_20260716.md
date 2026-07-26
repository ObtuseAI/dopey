# DOPEY Non-Evidence Completion Report

Date: 2026-07-16

## Outcome

All currently actionable engineering and operational-hardening work identified for the
vNext build is implemented. Remaining blockers require forward evidence, mature settlement
horizons, or operator-controlled promotion decisions; they are not unfinished engineering.

DOPEY remains paper-only and live-blocked. No broker-order, credential, order-construction,
or self-permission path was added.

## Operational state

- The protected public history lake contains 335 validated symbols and 2,911,787 rows.
- The governed active universe starts at 200 symbols: 37 immutable core symbols and 163
  validator-passed probation symbols.
- Governed active capacity is 250 symbols, backed by a 339-symbol candidate registry.
- All 200 active history files share the 2026-07-15 frontier and the default history
  validator reports `valid_real_dataset`.
- The protected-lake guard reports `public_lake_clean` with no fixture residue.
- Four provider failures remain explicit (`SQ`, `IPG`, `BK`, and `MMC`) rather than being
  replaced with synthetic data.
- Research readiness remains `not_action_ready`.

## Completed engineering

- Constitution and protected-surface enforcement for truth, provenance, execution denial,
  held-out evaluation, settlement, readiness, and operator promotion.
- Typed agent/evidence protocols, deterministic organism runtime, adversarial and shadow
  controls, metacognitive confidence decomposition, abstention, and knowledge boundaries.
- Multi-timeframe technical evidence, world-model enrichment, causal evaluation, agent
  ablation, calibration, memory, genome, homeostasis, and bounded recursive evolution.
- Autonomous research challenger generation and independent promotion-evidence evaluation
  without allowing an optimizer to tune its judge.
- Governed 200-symbol activation, 250-symbol capacity, refresh-aware public-history intake,
  proof-required quarantine recovery, and scheduled 50-symbol provider batches.
- Resumable nightly shards and supervisor-soak subphases with content-addressed checkpoints.
  A timeout remains `inconclusive_timeout`; failed or incomplete checkpoints never become
  passes.
- Atomic staging-stack artifact replacement, eliminating cross-process truncate/read races
  while keeping malformed artifacts fail-closed.

## Validation evidence

The final nightly run completed with verdict `all_green`:

- 3,524 passed;
- 0 failed;
- 0 errors;
- 1 explicit skip;
- 8 resumable shards;
- suite status `complete_green`;
- soak status `complete`;
- no stack regressions;
- deterministic fitness scores `0.008974` and `0.008974`;
- honest-lane validation: 26 passed;
- paper-only `true`, live-blocked `true`.

The supervisor completed 29 of 31 stages with return code 0 and retained two incidents as
`degraded_with_incidents`. This is accepted by the soak because there were no stage
regressions; it is not represented as a fully healthy or action-ready market state.

The exact GitHub Actions fast subset also passed:

- shard 1: 230 passed;
- shard 2: 229 passed;
- shard 3: 223 passed;
- shard 4: 238 passed;
- total: 920 passed.

The staging/import integration pair passed 30 tests, and three concurrent staging-stack
processes completed with paper-only and live-blocked assertions intact. A prior single-process
attempt to execute the entire intentionally heavy suite exceeded 3,603 seconds and remains
recorded as `inconclusive_timeout`; it is not counted as a pass and is superseded for bounded
validation by the complete green resumable-nightly evidence above.

## Remaining evidence-only roadmap

- Settle the 74 point-in-time vNext predictions only after their verified horizons mature;
  the earliest valid settlement date is 2026-07-28.
- Increase resolved context decisions from 0 toward the protected 200-decision sample floor.
- Increase closed forward-paper trades from 21 toward the protected 100-trade sample floor.
- Recompute calibration, ablation, causal cohorts, contested truth, and transfer only after
  meaningful forward sample growth.
- Acquire fresh, licensed intraday and defensible options-positioning inputs where available;
  unavailable evidence must remain a typed data gap.
- Keep challengers experimental or shadow-only until isolated held-out, transfer, calibration,
  forward-evidence, and operator gates all pass.

None of these items authorizes live execution or lowers a constitutional threshold.
