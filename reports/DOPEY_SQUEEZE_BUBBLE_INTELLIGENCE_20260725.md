# DOPEY Squeeze and Bubble Intelligence

Observed 2026-07-25 America/Chicago. This report describes the current
research capability and its verified boundaries.

## Outcome

DOPEY now runs a daily, point-in-time short-squeeze and bubble-fragility
research lane. The implementation separates:

- actual open short interest from daily short-sale flow;
- squeeze pressure from price/volume/options ignition;
- bubble fragility from the later unwind trigger;
- recent-IPO reflexivity from extreme valuation;
- research rankings from execution authority.

The current cycle is
`complete_research_only_with_typed_evidence_gaps`. It is paper-only,
constructs no orders, permits no undefined-loss expression, and does not
bypass DOPEY's existing action-readiness or paper-twin gates.

## Current Real-Data Readout

| Evidence or queue | Current result |
| --- | ---: |
| Locally historied symbols assessed | 225 |
| Symbols with actual open-short snapshots | 180 |
| Fresh issuer fundamental snapshots | 184 |
| Priced IPO records staged, trailing 24 months | 720 |
| Operating IPO candidates in governed staging queue | 409 |
| Official Nasdaq threshold securities staged | 54 |
| FINRA aggregate-margin monthly observations | 13 |
| Squeeze action candidates | 0 |
| Squeeze watches | 162 |
| Bubble unwind action candidates | 0 |
| Bubble fragility monitors awaiting unwind | 0 |
| Bubble watches | 53 |

Top squeeze watches are CLSK, CHTR, MARA, LCID, and SOUN. They remain
watches because pressure and ignition are not jointly above policy
thresholds. Top bubble watches are ARM, DDOG, NET, CRWD, and PANW. Their
extreme-valuation evidence is visible, but fragility and a confirmed unwind
are not jointly sufficient.

No profit or edge is claimed. Forward evidence is
`unrated_insufficient_forward_observations`; the 2-, 5-, and 10-session
settlement ledger will remain non-promotional until each bucket has the
required observations.

## Intelligence Design

### Short squeeze

Pressure uses actual short percent of float, days to cover, month-over-month
short growth, float scarcity, borrow fee, utilization, fails-to-deliver
stress, and official threshold-list evidence.

Ignition is independent. It uses 5- and 20-session return, 20-session
breakout, volume expansion, RSI pressure, daily short-sale flow, call
pressure, quote-derived negative gamma, and dollar liquidity.

Daily FINRA short volume is always labeled flow and can never satisfy the
open-short-interest gate. This follows FINRA's published distinction between
twice-monthly short-interest positions and daily short-sale volume.

### Bubble and leverage

Fragility uses:

- trailing P/E and forward P/E extremes;
- price-to-sales, price-to-book, and enterprise-value-to-revenue extremes;
- negative free cash flow and balance-sheet leverage;
- recent-listing age, offer-price appreciation, and IPO deal size;
- price extension and acceleration;
- quote-derived call crowding, implied volatility, and gamma;
- aggregate FINRA margin-debit growth and debit-to-free-credit pressure;
- attention/liquidity reflexivity.

An unwind requires separate downside confirmation: negative 5-session
return, SMA breaks, 20-session breakdown, volume confirmation, put pressure,
and negative gamma. An expensive or newly listed company is therefore not
treated as an automatic short.

Recent IPOs enter the governed universe staging queue from the Nasdaq IPO
calendar. Blank-check, acquisition, unit, ETF, warrant, rights, and other
obvious non-operating offerings are filtered. A new listing can enter
technical research after 21 sessions, with unavailable longer-horizon
features explicitly reducing evidence completeness.

### Expression and execution boundaries

- A qualified squeeze can propose long equity for review by the existing
  live/action gates.
- A qualified bubble unwind can propose only a long put or bear put debit
  spread, and only after the options-control switch and existing gates allow
  it.
- Naked short equity, naked options, undefined loss, same-session round
  trips, and direct order construction are disabled.
- Every live review still requires a paper twin. The current system
  readiness remains `not_action_ready`.

## Daily Operation

The existing macro operator refresh now stages actual short interest,
issuer valuation/listing metadata, the Nasdaq IPO calendar, official Nasdaq
threshold securities, and FINRA aggregate margin statistics. The resilient
research supervisor runs `squeeze_bubble_intelligence` after validated
history, macro context, and quote-derived chain analytics.

The runtime emits:

- `symbol_assessments.jsonl`;
- `candidate_rankings.json`;
- `forward_signal_ledger.jsonl`;
- `forward_settlement_ledger.jsonl`;
- `forward_evidence_report.json`;
- `squeeze_bubble_summary.json`.

Signal identities are stable across same-evidence reruns, so repeated daily
invocations do not duplicate forward observations.

## Typed Gaps

The current cycle retains three explicit gaps:

- `missing_borrow_cost_and_utilization_lane`;
- `missing_sec_fails_to_deliver_lane`;
- `official_threshold_coverage_nasdaq_only`.

DOPEY does not infer borrow pressure, invent SEC data, or treat the Nasdaq
list as NYSE coverage. SEC fails-to-deliver remains blocked until an
operator-owned SEC-compliant user agent is configured. Borrow utilization
requires a licensed source.

The broader DOPEY snapshot is consistent with 200 active symbols, but remains
`not_action_ready`. Storage pressure is `CRITICAL` and write backpressure is
active; no cleanup was performed because this session did not authorize
deleting existing artifacts.

## Verification

- Focused and affected-suite validation: `147 passed`.
- Ruff validation over all changed Python surfaces: passed.
- Scoped bytecode compilation: passed.
- Scoped `git diff --check`: passed.
- Real macro gate: `macro_context_computed`.
- Real universe governor: `universe_governed`, paper-only and live-blocked.
- Real squeeze/bubble cycle: completed with the typed gaps above.

## Primary Data Semantics

- FINRA short interest:
  https://www.finra.org/investors/insights/short-interest
- FINRA margin statistics:
  https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics
- SEC fails-to-deliver data:
  https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data
- Nasdaq Regulation SHO threshold list:
  https://www.nasdaqtrader.com/Trader.aspx?id=RegSHOThreshold
- Nasdaq IPO calendar:
  https://www.nasdaq.com/market-activity/ipos
