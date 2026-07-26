# DOPEY Forward Book Risk Report

- as of snapshot: `2026-07-16` | open `0` | marked `0` | unmarkable `0`

## Book Dollar Greeks (1-contract paper positions)
- net delta$: `0.0` | gamma$/1%: `0.0` | vega$/vol-pt: `0.0` | theta$/day: `0.0`
- top-symbol premium share: `0.0`

## Why the Book Moved (premium units, entry -> now)
- direction (delta+gamma): `0`
- volatility (vega): `0`
- decay (theta): `0`
- residual (higher-order/smile): `0`
- friction (spreads+commissions): `-0`
- unrealized (bid side): `0`
- identity gap (must be ~0): `0.0`

## Honest Limits
- Greeks are Black-Scholes at snapshot IV; no smile dynamics model is claimed.
- Attribution explains the paper book only; it is not a profitability claim.
- paper_only: `true`; live_blocked: `true`.
