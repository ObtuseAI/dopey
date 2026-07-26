# DOPEY Market Structure Engine Report

## Objective
Deterministic market-structure, trap, and volatility-regime features over validated real history.

## Feature Families
- swing levels: `35391` (k=3 fractals, confirmation lag recorded)
- support/resistance zones: `5340` (cluster tolerance 1.5%)
- trap events: `4337` (bull `2581` / bear `1756`)
- volume anomalies: `6740` (z >= 3.0)
- VRP observations: `3028` (rich days: `237`)
- entry blackout windows: `4574`

## Filter Value (blackouts applied to real trade records)
- status: `complete`
- trades excluded: `9134` of `74366`
- net P&L unfiltered: `-16192.387478`
- net P&L filtered: `-14911.545301`
- average excluded-trade P&L: `-0.140228`
- filter improved net: `True`

## Honest Limits
- Structure features are hypotheses, not edge evidence; arbitration happens in the truth layer.
- VRP proxy uses VIX vs SPY realized variance; per-symbol implied vol requires real chains.
- paper_only: `true`; live_blocked: `true`.
