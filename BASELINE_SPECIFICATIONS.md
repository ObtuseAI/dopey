# Baseline Specifications

Canonical vocabulary is implemented in `dopey/ascendancy/baselines.py` and frozen
in environment v1: no trade, risk-matched underlying, fixed defined-risk option,
delta-targeted long option, fixed vertical, naive immediate and limit paper-price
policies, fixed-fraction and volatility-matched allocation, and the market-implied
distribution.

`dopey/ascendancy/paired_evaluation.py` enforces exact opportunity matching,
complete-cost declarations, unique candidate/baseline pairs, canonical IDs, minimum
sample thresholds, and a positive one-sided lower confidence bound for every
required baseline. It is evaluation mechanics, not evidence that any baseline or
candidate is profitable. Constructing payoff observations still requires qualifying
point-in-time market and settlement data.

Shared provenance: `ARTIFACT_PROVENANCE.json`.
