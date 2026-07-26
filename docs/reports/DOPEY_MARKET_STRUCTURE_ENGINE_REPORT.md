# DOPEY Market Structure Engine Report

## Objective
Deterministic market-structure, trap, and volatility-regime features over validated real history.

## Feature Families
- swing levels: `126505` (k=3 fractals, confirmation lag recorded)
- support/resistance zones: `17955` (cluster tolerance 1.5%)
- trap events: `15432` (bull `9071` / bear `6361`)
- volume anomalies: `24347` (z >= 3.0)
- VRP observations: `3033` (rich days: `237`)
- entry blackout windows: `15669`

## Filter Value (blackouts applied to real trade records)
- status: `complete`
- trades excluded: `44877` of `321416`
- net P&L unfiltered: `-136440.479317`
- net P&L filtered: `-113849.308861`
- average excluded-trade P&L: `-0.503402`
- filter improved net: `True`

## Honest Limits
- Structure features are hypotheses, not edge evidence; arbitration happens in the truth layer.
- VRP proxy uses VIX vs SPY realized variance; per-symbol implied vol requires real chains.
- paper_only: `true`; live_blocked: `true`.
