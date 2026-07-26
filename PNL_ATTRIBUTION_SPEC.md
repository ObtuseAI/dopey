# PnL Attribution Specification

`dopey/ascendancy/attribution.py` defines finite, reconcilable components for total
PnL: direction, delta, gamma, theta, vega, implied-volatility change, realized
volatility, skew, term structure, vanna, charm, vomma, correlation, carry, funding,
dividends, borrow, spread, commissions, slippage, impact, exercise, assignment, and
residual. Reconciliation fails when components do not sum to total within the frozen
tolerance.

The same module implements a closing-line-value analogue that converts a later
consensus fair value back to an entry-equivalent reference using declared underlying,
time, surface, event, rates, dividends, and borrow adjustments, then subtracts model
uncertainty. This scores process price independently of final PnL.

No attribution is market-validated because no eligible forward paper fills and
settlements exist. Shared provenance: `ARTIFACT_PROVENANCE.json`.
