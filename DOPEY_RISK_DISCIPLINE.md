# DOPEY RISK DISCIPLINE

## CURRENT STATE (2026-07-22): Live Branch risk discipline (owner-authorized equities)

The sections below describe the original options-research risk model and the legacy
`MICRO_LIVE`/`ADAPTIVE_LIVE`/`LiveOrderGate` design; they remain accurate for those
components. The active live-equity branch (`dopey_live/`, constitution v2) adds its
own discipline on top:

- **Position risk caps** (enforced in `dopey_live/signals.py` at intent build time):
  gross stock allocation <= 50% of spendable funds, single name <= 10%, risk per
  position <= 0.5%, quote freshness <= 60s, spread <= 50bps.
- **Settled-funds-only sizing** (`dopey_live/settlement.py`): the account is a CASH
  account; unsettled T+1 sale proceeds are never spent, unknown order history means
  zero spendable. This is what makes a good-faith violation structurally impossible
  from the system side.
- **No day trading** (`no_day_trading_enforced: true`) and a **mandatory paper twin**
  staged before every live order.
- **Research maturity gates entries**: with the truth layer at L0 (no demonstrated
  edge), research-derived entries stay blocked; the branch can still reconcile,
  observe, and exit.
- **LLM boundary**: trade decisions (symbol/side/size/price) are computed by
  deterministic Python; the ephemeral Codex agent only transports the reviewed order
  to the official Robinhood MCP and its transcript is re-validated afterward.
- **Fail-closed everywhere**: expired MCP OAuth, ambiguous placements, unexplained
  position disappearances, and invalid broker data each block the cycle with a named
  status rather than proceeding.

---

## Options can lose the full premium

A long option can expire worthless (100% loss of premium). A short undefined-risk option can
lose multiples of the premium received. DOPEY therefore defaults to **defined-risk structures
only** (`default_structure_policy: defined_risk_first`). The `ExecutionIntent` carries
`defined_risk: true` by default, and undefined-risk intents are rejected by the validator and
the `LiveOrderGate`.

## Automation can malfunction

An autonomous loop that can also place live orders can compound a bug into a catastrophic loss
faster than a human can intervene. DOPEY keeps the autonomy loop's fail-closed human-gate model
(from Blunder) **and** adds the `LiveOrderGate` on top: live orders are blocked unless every
gate passes, and the default is blocked.

## Adaptive risk intelligence, not guarantees

The Dummy doctrine is adaptive: proof-weighted aggression, weak-signal starving, capital
redeployment, and fast invalidation are all *intelligence* mechanisms, not profit mechanisms.
They reduce the chance of acting on a decayed or overfit edge; they do not guarantee a profit.

## No profit guarantees

DOPEY makes **no profit claims**. Past or simulated performance is not indicative of future
results. The proof ledger records *what happened* in research/paper; it is not a forecast.

## Defined-risk default for future micro-live

Any future micro-live tier requires defined-risk structures. Undefined-risk selling (naked
calls, naked short straddles, etc.) is blocked by the `LiveOrderGate` and the intent validator.

## Live needs an explicit future mode

Live trading requires: `mode` ∈ {`MICRO_LIVE`, `ADAPTIVE_LIVE`}, `live_trading_enabled: true`,
`funded_broker_connections_enabled: true`, a supported credentialed broker with discovered
options-exec capability, a sufficient proof bundle, a defined-risk structure, budget approval,
and `ExecutionIntent.live_allowed: true`. All must hold simultaneously.

## No safety boundary weakening

The defaults in `configs/dopey.default.yaml` and the `LiveOrderGate` must not be weakened. The
`adaptive_threshold_kernel` self-operation doctrine explicitly lists "placing live trades" and
"connecting a funded broker" as gate-required, and "weakening validators / deleting safety gates"
as human-gate-required.

## The proof ledger is the source of truth

The append-only `ProofLedger` records every autonomy-loop run, every mock/execute/validate/repair
step, and every promotion/rejection. It is the auditable source of truth for what Dopey actually
did. Research and paper claims must trace back to ledger entries.
