# DOPEY action-readiness hardening V8

Date: 2026-07-13
Scope: paper-market research and readiness evidence only
Live trading: blocked

## Outcome

This pass removed three avoidable readiness hazards without lowering sample, freshness, stress, context, confidence, or walk-forward requirements:

1. A single unstable supplemental global-news index could block the entire equity engine even when six official feeds were healthy.
2. Four legacy open paper positions do not meet the new contract-liquidity policy, but this was not visible in the action-readiness gate.
3. A completed discipline cooldown could immediately re-trigger on the same historical losses, creating a permanent evidence-collection deadlock.

## News-context reliability

The existing GDELT request returned HTTP 429 during a live read-only diagnostic and explicitly requested a lower request rate. Query sharding would increase request count and is therefore not the correct reliability fix.

The intake now uses `dopey-news-source-coverage-v2`:

- Seven authoritative sources are required: the existing Federal Reserve, SEC, CFTC and EIA feeds plus the official U.S. Treasury press-release index.
- GDELT remains a supplemental global-news index. Its failures remain explicit in the manifest and are never relabeled as successful.
- `pipeline_status=complete` requires every V2 authoritative source to stage successfully.
- The manifest records required and supplemental source IDs, staged counts, failure IDs, and the coverage-policy version.
- GDELT maximum records were reduced from 250 to 100 to lower endpoint load.
- The Treasury HTML parser was validated live against 16 current press-release entries without writing intake artifacts.

The deterministic news classifier now rejects common geopolitical false positives such as "gangs go to war", "war medals", "wartime atrocities", "culture war", "price war", and "bidding war". It retains actual conflict and energy-disruption combinations such as a collapsed ceasefire with an oil waiver or blockade.

The existing manifest remains `partial_explicit_source_failures` until the next authorized or scheduled intake produces a V2 snapshot. No old manifest was rewritten to claim completion.

## Open-paper-book quality

`forward_book_quality.py` reconstructs entry quotes from immutable chain archives when V2 provenance was not frozen on a legacy position. It audits only and never closes, marks, or rewrites positions.

Current result:

- Open paper positions: 17
- Conforming with the new entry policy: 13
- Nonconforming: 4
- Missing entry evidence: 0
- Nonconforming symbols: XLF, XLK, XLU, XLP

The action-readiness gate now includes `open_book_entry_quality_green`. It cannot pass while a legacy position fails the current spread, volume, or open-interest requirements.

## Discipline-halt lifecycle

The forward walk now records the closed-trade count and policy version when a discipline halt begins. After the five-session cooldown, the halt can rearm only from newly closed trade evidence. Historical losses remain in every performance and readiness calculation; they are not deleted, reset, or excluded from net results.

This fixes a state-machine deadlock while preserving risk discipline:

- During cooldown: new entries remain blocked.
- After cooldown with no new losses: the same old evidence cannot re-trigger the latch.
- After cooldown with new adverse closed evidence: the loss-streak or drawdown halt can trigger again.

## Readiness telemetry

The V6 acceleration plan now reports:

- recorded context decisions: 2
- pending maturity or settlement: 2
- resolved context outcomes: 0 / 200 required
- observed decision rate: 1 per joint snapshot day
- current news pipeline status and failed source IDs
- whether required news coverage is complete

The action gate remains honestly `not_action_ready`. Its current missing requirements are:

- `any_cohort_beats_baseline_95ci`
- `any_cohort_regime_robust`
- `forward_track_net_positive`
- `forward_track_sample_sufficient`
- `no_active_discipline_halt`
- `open_book_entry_quality_green`
- `statistical_truth_promotion_allowed`

## Validation

- Focused V8 regression: 21 passed.
- Expanded strategy, chain, context, readiness, and acceleration regression: 69 passed, 1 deselected.
- The deselected real staged-news integration test is expected to stay blocked until a new V2 manifest is generated.
- Python compilation: passed.
- Git diff whitespace validation: passed.
- Live read-only Treasury parser validation: 16 events parsed.
- Protected public lake: `public_lake_locked_clean`, 160 symbols, 1,292,545 rows, zero fixture symbols.
- No paper-research execution cycle, equity-engine run, universe seeding, forward mark, broker connection, or order operation was performed.

## Remaining path to action readiness

1. Generate a V2 news snapshot on the normal cadence and verify all seven authoritative sources staged.
2. Run the equity-first engine only after both cross-asset and news manifests are complete and aligned.
3. Let the current discipline cooldown and legacy paper positions resolve from new market snapshots; do not force synthetic closes.
4. Expand governed equity coverage so independent context decisions accumulate faster without forcing trades.
5. Resolve at least 200 real forward context decisions and run the required three-era purged walk-forward ablation.
6. Reach at least 100 real closed forward paper trades with positive net evidence, then clear baseline, regime, statistical-truth, and stress checks.

The thresholds above are unchanged. This pass improves the system's ability to reach them honestly; it does not claim that they have been reached.

## Primary evidence

- `artifacts/dopey/forward_walk/forward_book_quality.json`
- `artifacts/dopey/broker_readiness/action_readiness_gate.json`
- `artifacts/dopey/acceleration/readiness_acceleration_plan.json`
- `artifacts/dopey/equity_swing/context_evidence_gate.json`
- `dopey_data/real/manifests/news_context_manifest.json`
- `artifacts/dopey/public_signal_deepening/public_lake_final_state_lock_v2_summary.json`
