# DOPEY Proof-Weighted Promotion Policy

## Allowed paper / research tiers (best -> worst within a run)

- `offline_mutation_champion`
- `paper_champion`
- `offline_ensemble_member`
- `paper_candidate`
- `paper_watchlist`
- `research_only`
- `quarantine`
- `rejected`

## Forbidden live tiers (never emitted)

- `live_candidate`
- `micro_live`
- `adaptive_live`
- `real_capital`
- `broker_enabled`

## Allowed governance decisions

`promote_to_paper_watchlist`, `promote_to_paper_candidate`, `promote_to_paper_champion`,
`mark_offline_ensemble_member`, `mark_offline_mutation_champion`, `hold_research_only`,
`reduce_paper_attention`, `starve_weak_signal`, `quarantine_overfit`, `reject_unsafe`,
`request_more_fixture_evidence`.

## Forbidden decisions (rejected at runtime)

`live_candidate`, `micro_live`, `adaptive_live`, `real_capital`, `broker_order`,
`enable_live`.

## Evidence requirements

Promotion is gated on proof strength bands **plus** candidate-specific walk-forward
consistency floors so a strategy cannot ride global evidence coverage alone:

| Tier | Min proof strength | Min walk-forward consistency | Role flag |
|---|---|---|---|
| `promote_to_paper_champion` | 0.65 | 0.60 | top strategy |
| `mark_offline_mutation_champion` | 0.55 | 0.45 | mutation champion + improvement |
| `mark_offline_ensemble_member` | 0.55 | 0.50 | ensemble member |
| `promote_to_paper_candidate` | 0.55 | 0.50 | — |
| `promote_to_paper_watchlist` | 0.45 | 0.40 | — |

Below these thresholds the candidate is `hold_research_only` or
`request_more_fixture_evidence`.

## Disqualifying failures

A candidate is blocked from higher tiers (or rejected / quarantined) when:

- any live-enabling flag is present (`paper_only=False`) → `reject_unsafe` / tier `rejected`
- high overfit (rank 3) → `quarantine_overfit` / tier `quarantine`
- family failure pressure >= 0.40 → `starve_weak_signal`
- low liquidity robustness (< 0.40) blocks `paper_champion` / `offline_mutation_champion`

## Missing-evidence logic

A candidate with evidence coverage < 0.5 or proof strength < 0.30 receives
`request_more_fixture_evidence`. The governor aggregates required-missing-evidence codes
(e.g. `complete_evidence_layer_coverage`, `cross_layer_champion_agreement`,
`stronger_walk_forward_consistency`, `higher_proof_strength`) into a prioritized list of
next evidence priorities.

## How future human review could use this (without enabling live)

The governor emits explicit `live_migration_conditions` for promoted strategies. These are
**documentation only** and describe the separate, human-operated steps that would be
required before any live discussion — they are never auto-applied:

1. human review and explicit written approval
2. an operator explicitly enabling `live_trading_enabled` (never by the governor)
3. changing mode to `MICRO_LIVE` or `ADAPTIVE_LIVE` (never `RESEARCH`)
4. a funded broker capability detector confirming options execution support
5. the `LiveOrderGate` approving a defined-risk intent with `live_allowed=true`
6. additional OOS / live-paper equivalence evidence beyond this offline proof

None of these conditions are wired, triggered, or scheduled by this pass. The governor only
records them so a future human review has a checklist; it performs no live action and creates
no auto-live migration path.
