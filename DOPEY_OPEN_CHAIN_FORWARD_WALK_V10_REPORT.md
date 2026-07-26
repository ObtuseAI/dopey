# DOPEY_OPEN_CHAIN_FORWARD_WALK_V10_REPORT

- bundle: `DOPEY_OPEN_CHAIN_FORWARD_WALK_V10`
- date: 2026-07-09
- supervisor: `all_stages_completed` (13/13, 0 incidents)

## The Idea

V9's binding constraint was real options-chain data, and the operator's directive was
"completely open source and license free." You cannot buy chain HISTORY license-free -
so DOPEY now GROWS its own: current public chain snapshots (same yfinance lane as the
OHLCV spine, personal-research use, non-redistributable) are staged daily through a
governed archive, and a forward paper walk converts them into the strongest evidence
class that exists: **ex-ante, quote-priced trades**. Entries are decided before the
future happens; lookahead bias is structurally impossible. Data compounds even while
returns do not.

## What Went Live Today (first snapshot: 2026-07-09)

### 1. Chain snapshot lane (operator tool + governed loader)
- `operator_tools/operator_fetch_option_chains.py` (operator-run ONLY; no pipeline
  module invokes it) staged 23 symbols, 2,069 contract rows at ~29 DTE with real
  bid/ask/volume/OI/IV; options manifest finalized with sha256 pins.
- `dopey_options/chain_snapshot_loader.py` gates every row: manifest license review,
  hash pins, exact schema, quality rules, credential/live-marker scans.

### 2. Real positioning analytics (quote-derived, first ever)
`chain_analytics` now computes from real quotes (greeks derived from chain IV via the
Black-Scholes engine):
- SPY: GEX **-$74.5M per 1% move** (dealer short-gamma regime), put/call OI 1.97
- NVDA: GEX +$6.1M/1%, gamma flip 220; TSLA: +$14.5M/1%, put/call OI 0.44
- Per-symbol artifacts: total GEX, gamma-flip strike, put/call OI+volume ratios,
  net delta-hedging pressure, ATM IV.

### 3. Model-vs-market calibration (771 ATM contracts)
- median chain-IV / realized-vol = **0.976** vs the simulator's 1.10 multiplier
- model premium error vs market mid: median **+14.5%** (p25 +0.7%, p75 +36.4%)
- Verdict: the historical simulator's IV proxy is measurably miscalibrated; V11 should
  recalibrate the multiplier toward ~0.98 and add skew awareness. This is what honest
  compounding looks like: the market just graded DOPEY's pricing model, in writing.

### 4. Forward paper walk (the ex-ante lane) - LIVE
- 20 paper positions opened from fresh real-history signals, filled at the REAL ask
  plus commission (e.g. JPM 335C @ 11.8065, NVDA 205P @ 9.8065, TSLA 405P @ 21.1565).
- Marking policy: real bid on each new snapshot; stop -50% / target +100% / time stop
  3 sessions / forced close at DTE<=5. Closed trades accumulate a quote-priced,
  ex-ante track record - the first evidence class the truth layer can ever accept.

### 5. Open-source packaging
- `LICENSE` (MIT) scoped to original DOPEY code; forked/vendored dirs keep upstream
  licenses; market data explicitly excluded.
- `DATA_NOTICE.md`: the code is open source; the DATA is bring-your-own. Strip
  `dopey_data/` from any public release (manifests record redistribution_allowed:
  false); every user regenerates their spine with the operator tools. "License free"
  is guaranteed for code; pretending it's true for market data would be theater.

## The Daily Ritual (grows the archive and the track record)

1. `.venv\Scripts\python operator_tools\operator_fetch_option_chains.py`  (operator)
2. `.venv\Scripts\python -m dopey_autonomy.run_resilient_research_supervisor`

Each day this adds: one chain snapshot to the archive, fresh positioning metrics, a
new calibration reading, marks/exits on open forward-walk positions, and new ex-ante
entries from fresh signals.

## Honest Limits

- Snapshots are delayed public quotes; fills assume full size at bid/ask.
- The forward walk accrues evidence at the speed of reality; no significance claims
  until the truth layer's thresholds are met with quote-priced samples.
- Historical model-priced results remain what V9 proved: no entry edge over random
  after costs. The forward walk is how that claim gets tested, not overturned by fiat.
- paper_only: true; live_blocked: true; promotion blocked; not investment advice.

## Validation

- `tests/test_v10_open_chain_stack.py`: 7 passed (parser accept/reject, schema gate,
  greeks enrichment + real metrics math, live-state consistency, conservative fill
  math, ledger defaults, honest summary)
- `tests/test_v9_apex_research_stack.py`: 9 passed (chain gate now state-aware)
- Supervisor: 13/13 stages, 0 incidents

## Next Target

`DOPEY_SIMULATOR_RECALIBRATION_AND_FORWARD_TRACK_ACCUMULATION_V11` - recalibrate the
IV proxy from accumulated calibration rows, add IV-skew awareness, keep the daily
snapshot ritual until the forward track record reaches judgeable sample size.
