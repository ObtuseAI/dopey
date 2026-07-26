# DOPEY No-Day-Trade Account Ledger And Rotation Planner Report

Session date: 2026-07-03

## Objective

`DOPEY_NO_DAY_TRADE_ACCOUNT_LEDGER_AND_PDT_SAFE_ROTATION_PLANNER_V1`
adds an offline account-level ledger and rotation planner for active
long-premium equity-options trading. It preserves the canon: buy long calls
for bullish exposure, buy long puts for bearish exposure, allow swing and
multi-day rotation, reject normal same-day open/close churn, and keep 0DTE as
special lifecycle handling.

## Account Ledger Model

`dopey_execution.account_ledger` writes a deterministic `PaperAccountLedger`
with paper-only open positions, orders, day-trade events, rotation events,
policy snapshots, and a stable ledger hash. Positions record option type,
expiry, strike, open date, close eligibility, same-day close block state,
0DTE flags, and live-blocked state.

## No-Day-Trade Policy

`dopey_execution.day_trade_policy` provides a configurable conservative offline
policy. Default behavior blocks normal same-day round trips, allows
next-trading-day closes, allows overnight holds and multi-day rotation, tracks
day-trade-like events for audit, and does not claim legal sufficiency.

## PDT-Safe Configurable Policy

`dopey_execution.pdt_safe_policy` wraps the same conservative policy as an
offline PDT-safe planning facade. It is audit-visible and configurable, but it
is not legal advice and does not enable live trading.

## Rotation Planner Behavior

`dopey_execution.rotation_planner` turns candidate entries/exits into explicit
decisions: `open_allowed`, `close_allowed`,
`close_delayed_until_next_trading_day`, `rotate_allowed_after_delayed_exit`,
`blocked_same_day_round_trip`, `blocked_policy_violation`,
`blocked_zero_dte_missing_lifecycle`, `blocked_risk_throttle`,
`blocked_liquidity`, and `blocked_live_path`.

The planner allows new compliant long-call/long-put entries while delaying
same-day exits that would violate policy.

## Hybrid V3 Swing Replay

The hybrid swing/0DTE V3 corpus uses the same no-day-trade discipline for multi-day swing alternatives. Swing candidates are long-call/long-put only, opened with `buy_to_open`, closed with `sell_to_close`, and normal same-day swing closes are blocked. Next-trading-day and later closes remain eligible in the offline lifecycle, while 0DTE same-day closes require the special lifecycle path.

## 0DTE Account Lifecycle

0DTE positions are tracked separately from normal day-trade events. Opening
requires special lifecycle state plus liquidity and risk-cap approval.
Same-day special close requires explicit reason code and 0DTE lifecycle proof.

## PaperBroker Integration

`PaperBroker` now owns a `PaperAccountLedger` for active-policy paper orders.
On active opens it creates ledger positions. On closes it consults the ledger,
rejects same-day normal closes, allows next-day-or-later closes, records
day-trade rejection events, and keeps `live_allowed=true` blocked.

## Audit Integration

`dopey_audit.active_policy_audit` recognizes account-ledger, day-trade policy,
PDT-safe policy, rotation plan, rotation proof, day-trade event log, 0DTE
account lifecycle proof, and PaperBroker account-ledger proof artifacts.

## Reporting And Export Integration

Reporting surfaces account ledger summary, open position counts, close-eligible
counts, same-day blocked counts, delayed exits, rotation decisions, 0DTE counts,
and live-blocked state. Export and review selection include the new reports and
proof artifacts as static offline files only.

## Tests

Targeted coverage includes account ledger policy, rotation planner, PaperBroker
account ledger, 0DTE account lifecycle, active policy regression tests, audit
recognition, reporting/export visibility, shard-plan generation, and live
safety regressions.

## Limitations

- Fixture-only and paper-only.
- No broker connection, credentials, real market data, live orders, scheduler,
  deployment, profit claim, or live-readiness claim.
- Full pytest remains timeout-prone and must not be reported as pass unless it
  actually completes.

## Safety State

- mode: `RESEARCH`
- live_trading_enabled: `false`
- funded_broker_connections_enabled: `false`
- allow_unofficial_robinhood_api: `false`
- paper_only: `true`
- live_blocked: `true`

## 0DTE Risk Model Integration

`DOPEY_0DTE_SPECIAL_LIFECYCLE_RISK_MODEL_V1` now feeds the account ledger and
rotation planner before any 0DTE paper open can be recorded. A 0DTE candidate
must carry a deterministic risk decision of `approved_for_paper_open` or
`approved_with_throttle`; otherwise the ledger rejects the entry. Throttled
0DTE candidates carry explicit paper premium and contract caps.

The rotation planner consumes the same decision snapshot. If the risk model
returns `prefer_non_zero_dte_alternative`, the planner records the 0DTE action
as blocked for 0DTE and routes the opportunity toward a later-expiry paper
alternative. Same-day special close remains an expiry-managed lifecycle path
with explicit reason, liquidity approval, risk-cap approval, and audit proof.

## 0DTE Replay Feedback Integration

The account ledger can now store `zero_dte_replay_feedback` as advisory policy
metadata on paper positions. This metadata records fixture outcome type,
risk-model alignment, threshold feedback, and recursive improvement tags.

Replay feedback does not override the 0DTE risk model. Blocked 0DTE candidates
remain blocked even when replay labels them `blocked_maybe_too_strict`.

The rotation planner can consume replay feedback that recommends
`prefer_later_expiry_more_often` and route future paper simulations toward a
later-expiry alternative. This remains offline paper planning and does not
create live allocation or broker execution authority.
## Proof-Weighted Allocation Context

The account ledger and rotation planner now read proof-weighted allocation context from the offline paper allocation plan when it exists.

Recorded context:

- allocation plan loaded: `true`
- allocator role: `advisory_paper_attention_only`
- paper attention priority available: `true`
- delayed rotation reserves advisory only: `true`
- allocator can force same-day close: `false`
- PaperBroker override allowed: `false`

The allocator can recommend paper opens and paper attention priority, but it cannot bypass the no-day-trade guard, cannot force same-day close, cannot override PaperBroker, and cannot create broker instructions.

## Portfolio-Level Delayed Rotation Replay

The portfolio replay bundle now tests delayed rotations at portfolio level. It records 10 delayed-rotation cases and 10 same-day close blocked cases.

Portfolio replay confirms:

- normal same-day open/close remains blocked
- delayed rotations are advisory until executable
- delayed rotations cannot force same-day close
- next-day delayed execution can be represented as paper replay only
- PaperBroker override remains `false`

The portfolio replay cannot create broker instructions, live orders, real sizing, buying-power logic, account-balance dependency, or scheduler behavior.
