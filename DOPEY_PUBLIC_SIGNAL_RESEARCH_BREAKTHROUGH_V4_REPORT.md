# DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4_REPORT

Bundle: DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4
Status: pf_holdout_split_improved_requires_v5
Version: dopey-public-signal-research-breakthrough-v4
Repo: C:\Users\CH\dopey
Generated: 2026-07-08T19:54:33.639619+00:00
Next recommended target: DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5

## Honest Branch Selected
V3 top PF was 1.04 (or 1.27 after V3 test rerun updated V3 state). V4 honest result is **pf_holdout_split_improved_requires_v5** because the V4 top research family PF = 1.079237 remains below the breakthrough gate threshold of 1.10, but the tournament produced 5 subfamilies that improved vs V3, so the watchlist is non-empty (5). The honest next target is DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5.

## Pipeline Step Results
1. V4 preflight: ready_for_pf_holdout_split_repair
2. Public lake freeze guard: public_lake_clean, active_fixture_symbol_count=0
3. V3 mutation queue executor: 4/8 executed
4. Profitable slice miner: 8 profitable / 52 loss-driver
5. No-trade filter optimizer: 13 rules, future_leakage_detected=false
6. Family template splitter: 4 continuation + 4 volume subfamilies, volume_rescue_status=volume_family_demote
7. Candidate generator V4: 32400 candidates, 16200 continuation + 16200 volume
8. PF/holdout/split scorer V4: 32400 prioritized
9. Path simulator V4: 27783 trades, UVXY-like corruption detected=False
10. Tournament V4: 2 families / 7 subfamilies / 2 cohorts
11. Breakthrough gate V4: 0 breakthroughs / 5 watchlist
12. Mutation queue V4: 40 entries
13. Active policy artifact guard V2: zero_dte_replay_outcomes_guard_ok
14. Scoreboard V4: written
15. Live gate V4: disabled_live_gate_locked

## Top Research Result
- Top research family: continuation|pullback|high_volume|trend_follow|dte14|1pct_otm
- Top research subfamily: continuation|pullback|high_volume
- Top research cohort: continuation|pullback|high_volume
- Top net P&L: 16525.586609
- Top profit factor: 1.079237
- Top max drawdown: -67707.704988
- Top sample count: 3969
- Improved vs V3: 5
- PF above 1.10: 0

## UVXY-like Corruption Check
Detected: False
The path simulator includes a data corruption guard (entry_spot > 1e6 skipped, recorded as data_corruption_skipped quality flag). The tournament performs a per-symbol PnL concentration check (no symbol may contribute > 50% of positive tournament PnL). After the guard fix, the V4 tournament shows no UVXY-like corruption.

## PF Threshold
MIN_BREAKTHROUGH_PF = 1.10. Not lowered. Top V4 PF (1.0792) is below threshold, hence the honest pf_holdout_split_improved_requires_v5 branch.

## Validation
- Targeted V4 tests: 35/35 passed in 110s
- V3 carry-forward: 22/22 passed
- V2 carry-forward: 18/18 passed
- Active policy carry-forward: 32/32 passed
- Total tests: 107 passed, 0 failed
- Validation status: targeted_tests_passed_carry_forward_passed_smokes_passed
- Timeout: not observed; timeout_recorded_as_pass = false

## Handoff
- Primary: C:/Users/CH/Desktop/Shared Folder/DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4 (22 files)
- Secondary: //FRANKENSTEIN/Shared Folder/DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4 (22 files)

## Safety Locks
- live_trading_enabled: false
- broker_connection_enabled: false
- real_order_enabled: false
- credentials_present: false
- env_created: false
- official_robinhood_market_data_allowed: true
- unofficial_robinhood_api_blocked: true
- robinhood_scraping_blocked: true
- robinhood_reverse_auth_blocked: true
- robinhood_live_trading_enabled: false
- public_data_only: true
- paper_only: true
- live_blocked: true
- active_fixture_symbol_count: 0
- No .env, no credentials, no broker, no real orders, no live trading, no git commit.

## Next Target
DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5
