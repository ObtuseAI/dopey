# DOPEY Action Readiness Gate Report

'Ready for action' is a checkable state, not a feeling. This gate evaluates every
condition the system requires before a broker connection could even be discussed.

- readiness_status: `not_action_ready`
- forward closed trades: `4` / `100` required

## Checklist
- [ ] `forward_track_sample_sufficient`
- [ ] `forward_track_net_positive`
- [x] `forward_evidence_integrity_current`
- [ ] `validated_multi_cohort_forward_sample`
- [x] `cohort_baseline_policy_current`
- [ ] `any_cohort_beats_matched_baseline_familywise`
- [x] `cohort_era_policy_current`
- [ ] `any_cohort_regime_robust`
- [ ] `statistical_truth_promotion_allowed`
- [x] `stress_evidence_integrity_valid`
- [ ] `stress_book_snapshot_current`
- [ ] `stress_valuation_inputs_current`
- [ ] `stress_book_survives_all_scenarios`
- [x] `no_active_discipline_halt`
- [x] `pricing_model_calibrated`
- [x] `data_freshness_green`
- [x] `open_book_entry_quality_green`
- [ ] `open_book_concentration_green`
- [ ] `hardened_champion_available`
- [ ] `full_nightly_validation_green`
- [x] `paper_twin_broker_reconciliation_green`

## Robinhood MCP Boundary (updated 2026-07-09)
- OFFICIAL Robinhood Agentic Trading MCP exists: agent.robinhood.com/mcp/trading
  (dedicated agentic account, MCP standard, Claude Code supported).
- Allowed now: read-only account state via the official MCP for paper-mirroring and
  reconciliation; auth lives in the operator's MCP client, never in this repo.
- Unofficial credential lanes remain permanently blocked.
- EXECUTION remains blocked until this gate is all-green AND a human explicitly
  approves; if ever unlocked, the designated path is the official MCP into the
  dedicated agentic account at minimum sizing. Robinhood's terms place full
  responsibility for agent trades on the account holder - and the truth layer
  currently reports no demonstrated edge.

## Invariants
- live_trading_enabled: `false`; paper_only: `true`; live_blocked: `true`.
- All-green here is necessary, NOT sufficient. A human operator decision is always
  the final gate.
