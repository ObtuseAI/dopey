# DOPEY Forward Book Risk Report

- as of snapshot: `2026-07-23` | open `9` | marked `9` | unmarkable `0`

## Book Dollar Greeks (1-contract paper positions)
- net delta$: `61051.04` | gamma$/1%: `7872.11` | vega$/vol-pt: `277.04` | theta$/day: `-387.98`
- top-symbol premium share: `0.4432`

## Why the Book Moved (premium units, entry -> now)
- direction (delta+gamma): `-21.787637`
- volatility (vega): `-0.176881`
- decay (theta): `-16.030947`
- residual (higher-order/smile): `-3.274535`
- friction (spreads+commissions): `-13.397`
- unrealized (bid side): `-54.667`
- identity gap (must be ~0): `0.0`

## Honest Limits
- Greeks are Black-Scholes at snapshot IV; no smile dynamics model is claimed.
- Attribution explains the paper book only; it is not a profitability claim.
- paper_only: `true`; live_blocked: `true`.
