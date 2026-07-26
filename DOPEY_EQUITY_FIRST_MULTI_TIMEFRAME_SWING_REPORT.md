# DOPEY Equity-First Multi-Timeframe Swing Engine

Status: `paper_research_complete`
As of: `2026-07-15`
Reproducibility hash: `85cdebfecf5cd629e6b7abed87c9291fffd795236f1c961bebfa5152b0349df1`

## Result

The engine analyzed 23 stocks with daily/weekly/monthly structure, produced 0 actionable shadow theses, and selected 0 strategically tracked option contract(s).

Direction is now stock-first: 78% technical confirmation, 22% fundamental confirmation, and 0% option data. Options can select strike/expiry/contract quality only after the equity direction is fixed.
Cross-asset and news context can confirm, contradict, or jointly veto a setup but receive zero primary direction weight.

## Cross-asset and news coverage

- Cross-asset series: 20 across commodity, crypto, currency, futures.
- Risk appetite=0.151561; inflation pressure=0.012853; systemic stress=0.26211.
- Cross-asset quality: usable=20; blocked=0; historical discontinuities flagged=6.
- Treasury context includes the current 3m/2y/5y/10y/30y curve, 2s10s/3m10y/5s30s slopes, daily yield changes, and ZN/ZB momentum.
- News events=104 from 7 staged sources (7 official).
- Fresh 7-day events=21; corroborated risk alerts=0; context vetoes=0.
- Future headlines rejected at decision time: 0.
- Context evidence gate: blocked_insufficient_resolved_context_decisions; joint snapshot days=5; snapshot history is telemetry rather than a duration gate; positive promotion and sizing remain disabled.
- Forward context decisions appended this run: 0; outcomes remain pending until their holding windows mature.
- News sources: Federal Reserve, SEC, CFTC, EIA official RSS feeds and GDELT DOC 2 global coverage.

## Actionable shadow theses

- No symbol cleared every technical, fundamental, structure, and reward/risk gate.

## Strategically tracked contracts

- No strategic contract cleared the earnings, DTE, quote, liquidity, and payoff gates.

## Reverse-engineered rule screen

Retrospective observations: 45342; qualified missed swings: 13263.
- No reverse-engineered rule cleared the minimum two-era shadow screen.

## Guardrails and limitations

- All output is paper research. Live trading, broker connectivity, sizing, and orders remain blocked.
- Pivots are usable only after confirmation; weekly and monthly bars are resampled from validated daily history.
- Intraday structure remains honestly unavailable because no local intraday dataset was supplied.
- Reverse-engineered rules are shadow hypotheses, not promoted strategies or edge claims.
- Past option backtest fingerprints remain model-priced, not quote-priced real option-chain evidence.

## Artifact paths

- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\multi_timeframe_structure.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\equity_fundamental_confirmation.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\equity_swing_theses.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\strategic_option_contracts.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\missed_trade_events.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\reverse_engineered_strategy_candidates.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\past_trade_strategy_fingerprints.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\cross_asset_regime.json`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\news_intelligence.json`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\context_evidence_gate.json`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\context_decision_ledger.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\context_outcome_ledger.jsonl`
- `C:\Users\CH\dopey\artifacts\dopey\equity_swing\equity_first_swing_summary.json`
