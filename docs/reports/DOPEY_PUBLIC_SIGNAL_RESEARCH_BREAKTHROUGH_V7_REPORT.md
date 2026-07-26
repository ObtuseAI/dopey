# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_REPORT

- repo path: `C:\Users\CH\dopey`
- orchestrator status: `watchlist_blockers_improved_requires_v8`
- next recommended target: `DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V8`

## Pipeline Steps

1. V7 preflight: ready_for_trade_active_breakthrough_repair
2. V6 baseline freeze: v6_baseline_frozen
3. No-trade contribution audit V7: no_trade_contribution_audit_complete_v7
4. V6 watchlist diagnosis V7: 
5. V6/V7 mutation executor: 50/50 executed
6. Trade-active repair policy V7: trade_active_repair_policy_defined_v7
7. Candidate generator V7: 30000 candidates
8. PF/holdout/split scorer V7: 30000 scored
9. Path simulator V7: 18000 trades
10. Tournament V7: 2 families / 8 subfamilies / 100 cohorts
11. Breakthrough gate V7: 0 breakthroughs / 0 watchlist
12. Mutation queue V7: 203 entries
13. Scoreboard V7: public_signal_research_scoreboard_complete_v7
14. Live gate V7: disabled_live_gate_locked

## Results

- improved vs V6 count: 0
- PF above 1.10 count: 7
- trade-active PF above 1.10 count: 0
- no-trade-only blocked: 0
- top family: `continuation`
- top subfamily: `continuation|pullback|relative_strength`
- top cohort: `continuation|long_put|trending|B`
- top net P&L: 1228.003691
- top PF: 1.399096
- top trade-active PF: 1.399096
- top sample count: 2780

## Known Gaps

- `v7_no_trade_dominance_partial_conversion`: V7 converts no-trade-dominant watchlist candidates into trade-active candidates; residual low trade-active sample counts may still block promotion.
- `v7_expensive_lane_timeout_risk`: V7 candidate generator and path simulator have larger targets; partial timeouts are recorded honestly and do not count as pass.
- `v6_baseline_snapshot_gap_acknowledged`: V6 baseline snapshot covers immutable summary/dashboard/doc sources; supporting JSONL records remain in live V6 directory.

## Validation

Validation summary: pending_watchdog_validation
