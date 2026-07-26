# DOPEY Elite Trader Hardening V3

Date: 2026-07-12  
Status: `paper_research_complete_context_evidence_blocked_pending_history`  
Engine: `equity_first_mtf_cross_asset_news_swing_v3`

## Outcome

This session repaired every immediately actionable P1 defect found in the cross-asset/news review and added the evidence machinery required for future calibration. It does not claim DOPEY is the greatest trader or that any strategy has proven edge. Positive context promotion and context-based sizing remain disabled until real forward evidence clears explicit thresholds.

Live trading, broker connectivity, credentials, real orders, and order authority remain blocked.

## Repairs completed

1. Future-dated news is rejected instead of clamped to age zero.
2. Incomplete news or cross-asset manifests now fail closed.
3. Manifest row/event counts and duplicate symbol/date rows are validated.
4. Every asset series is checked against a class-specific calendar freshness limit.
5. Required stale, future, or latest-discontinuity series abort context construction.
6. Generic futures are explicitly labeled continuous proxies with unavailable contract metadata.
7. Robust median/MAD shock scoring replaces standard-deviation sensitivity to stitched futures outliers.
8. Historical and latest suspected roll/extreme-move discontinuities are surfaced; suspect latest moves cannot enter shock scoring.
9. Cross-asset network retries now cover yfinance, requests, and curl transport errors.
10. GDELT 429 handling now waits at least eight seconds and increases the delay on repeated throttles.
11. Cross-asset and news runs create immutable timestamped data snapshots and archived manifests.
12. News events accrue in a unique append-only event ledger.
13. Only immutable snapshots with an embedded `complete` manifest count toward evidence.
14. News corroboration now requires three independent identities plus a minimum source-quality score.
15. Official sources receive primary-source authority; unranked GDELT domains cannot form an alert by domain count alone.
16. News categories map to affected themes, assets, and selected company symbols.
17. Theme-specific news tone replaces a single global scalar where corroborated evidence exists.
18. Context confidence is labeled supported, mixed, or contradicted without acquiring direction authority.
19. An explicit evidence gate requires 60 joint snapshot days, 200 resolved decisions, and three purged walk-forward eras.
20. Positive context promotion and sizing are disabled while the evidence gate is blocked.
21. Actionable context decisions accrue in an immutable forward ledger.
22. Decision IDs are semantic and idempotent by symbol, market date, and base intent.
23. Duplicate and non-evaluable decision rows were repaired before any outcomes existed.
24. Matured outcomes append to a separate outcome ledger; decisions are never rewritten.
25. Same-bar target/invalidation collisions remain explicitly inconclusive.

## Failure behavior proven

- A synthetic future headline is excluded from 24h/72h/7d context.
- A five-day-old futures series is marked stale and blocked.
- Three low-quality domains cannot satisfy corroboration; three high-quality independent domains can.
- A GDELT timeout/429 run produced `partial_explicit_source_failures`, and the engine refused to consume it.
- A later successful retry restored `complete` with all seven sources.
- Repeated engine runs append zero duplicate market decisions.
- Current decisions append zero outcomes because their forward windows have not matured.

## Current real-data state

- Cross-asset rows: 10,527.
- Cross-asset series: 20 usable, 0 blocked.
- Continuous futures proxies: 15.
- Historical discontinuities flagged: 6.
- Immutable complete joint snapshot days: 1.
- News events in current snapshot: 339.
- Unique news events in append-only ledger: 587.
- News sources: 7 total, 6 official.
- Corroborated current alerts: 0.
- Future current-snapshot events rejected: 0.
- Canonical evaluable context decisions: 2 (AMD and LCID).
- Resolved context outcomes: 0.
- Context evidence gate: `blocked_insufficient_point_in_time_history`.
- Positive context promotion allowed: false.
- Context sizing allowed: false.
- Defensive veto allowed: true.

## Current shadow result

- AMD remains a bullish equity-first shadow setup and the only strategically tracked contract selection.
- LCID remains a bearish equity-first shadow setup; its contract selection remains blocked by the earnings-window rule.
- No external-context veto fired.
- No reverse-engineered rule cleared the two-era screen.
- No live-readiness or profitability claim is made.

## Validation

Command:

`.venv\Scripts\python.exe -m pytest tests\test_equity_first_swing_engine.py tests\test_sharpness_tuning.py tests\test_proof_weighted_aggression_gate.py tests\test_live_trading_disabled_by_default.py tests\test_no_live_artifact_bindings.py -q`

Result: `34 passed in 7.06s`.

The suite includes a real staged-data integration test, future-event leak regression, stale-market regression, immutable evidence-gate test, source-quality corroboration test, outcome-ordering test, and ledger idempotency test.

## Remaining honest limitations

- Only one complete joint snapshot day exists; context edge cannot yet be tested honestly.
- Contract-level futures and explicit roll calendars remain unavailable from the current provider.
- News classification is deterministic headline metadata, not verified full-text causal analysis.
- BLS automated calendar retrieval returned HTTP 403 under its bot policy and was not bypassed.
- No historical point-in-time fundamentals or option-chain panel exists.
- Intraday market structure remains unavailable because no local intraday dataset is staged.

## Required evidence before promotion

Accumulate at least 60 complete joint snapshot days and 200 matured decisions, then run purged walk-forward ablations across at least three eras. Context may earn influence only if it improves precision/calibration without weakening drawdown, stability, or honest no-trade behavior.

## Canonical artifacts

- `artifacts/dopey/equity_swing/equity_first_swing_summary.json`
- `artifacts/dopey/equity_swing/cross_asset_regime.json`
- `artifacts/dopey/equity_swing/news_intelligence.json`
- `artifacts/dopey/equity_swing/context_evidence_gate.json`
- `artifacts/dopey/equity_swing/context_decision_ledger.jsonl`
- `artifacts/dopey/equity_swing/context_outcome_ledger.jsonl`
- `dopey_data/real/raw/cross_asset/snapshots/`
- `dopey_data/real/raw/news/snapshots/`
- `dopey_data/real/raw/news/news_event_ledger.jsonl`

## Honest terminal state

`elite_research_hardening_complete_context_edge_not_yet_earned_live_blocked`
