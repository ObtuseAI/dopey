# DOPEY Constitution

Version: `dopey-constitution-v2`
Effective mode: `LIVE`
Owner authorization: `owner-confirmation-2026-07-19-live-branch`

## Two-branch authority

DOPEY has two explicit branches with different jobs:

1. The protected research branch under `dopey/constitution/`, `dopey/truth/`,
   `dopey/settlement/`, `verifier/`, and `sealed_evaluator_client/` remains a sealed
   paper/evidence laboratory. Its historical assertions continue to describe that branch.
2. The production `dopey_live/` branch may read immutable research outputs and operate the
   dedicated Robinhood Agentic account through Robinhood's official Trading MCP. It may
   review and place eligible live long-equity orders now. It may review and place eligible
   long-premium or defined-risk option orders only while the owner-controlled options gate
   is enabled.

No other package receives broker authority. OAuth and broker credentials remain in the
official client credential store and never enter repository files or artifacts.

## Execution law

1. Every live order requires an exact, content-addressed paper twin staged first.
2. Every review, placement, rejection, broker warning, cancellation, and twin linkage is
   append-only and hash-chained.
3. An immutable intent ID makes scheduler retries idempotent. The same source decision may
   not create a duplicate filled order.
4. `LIVE` is the operating-mode name. Research maturity and live connectivity are reported
   separately and may not be cosmetically upgraded.
5. Long equities are enabled. Options execution capability is present but its user-scoped
   switch is initially disabled. Enabling it does not authorize naked or undefined-loss
   exposure.
6. A same-session round trip is prohibited. An opening fill cannot be closed before a
   later trading session. The rule applies to equities, options, live orders, and twins.
7. The allocator may use the complete available Agentic-account balance as its capital
   base. It may not exceed current buying power or fabricate missing account values.
8. A failed or warning-bearing broker review does not become a placement by inference.
9. Missing authentication, account ambiguity, stale or malformed inputs, unavailable
   buying power, untradable instruments, invalid option identity, or ledger corruption
   fails closed.
10. The standing owner authorization above replaces per-order confirmation for eligible
    Live Branch actions. It does not authorize unofficial APIs, credential extraction,
    transfers, withdrawals, or non-trading account changes.

## Evidence law

- Synthetic mechanics, replay, backtests, model prices, paper fills, and shadow decisions
  remain distinct from realized broker outcomes.
- Live authority is an operating decision, not a claim that the current model has a proven
  edge. The UI must show research maturity, realized Live Branch results, and paper-twin
  results as separate fields.
- Observed quote, review output, submitted order, broker status, fill, and later P&L retain
  separate timestamps and provenance.
- Negative or failed outcomes remain visible. No strategy may rewrite its source thesis or
  remove an intent after observing the result.

## Risk and instrument law

- Stocks use supported long-equity orders. A bearish equity thesis abstains unless an
  enabled, loss-limited option expression exists; the system does not synthesize a short
  stock order.
- Options are limited to long-premium or explicitly defined-risk structures supported by
  the official broker review. Naked short options, undefined loss, martingale sizing, loss
  chasing, and automatic limit expansion are prohibited.
- Quote staleness, crossed markets, zero bids, excessive spreads, insufficient liquidity,
  unverified adjustments, or future-dated evidence force abstention.
- Broker review and broker-side account eligibility remain mandatory even after DOPEY's
  local gates pass.

## Current operating state

The official Robinhood Trading MCP is registered and authenticated against the dedicated
Agentic account. Stock execution is enabled in the Live Branch. Options execution is
implemented and disabled in user-scoped control until the owner enables it. The paper twin,
append-only execution ledger, no-day-trade guard, desktop telemetry, and market-hours
scheduler are required production components, not optional research gates.
