# DOPEY Forward Paper Walk Report

## Evidence Class
Ex-ante, quote-priced paper trading: entries at the real ask on fresh signals, marks at
an executable real bid on later snapshots. Dislocated quotes defer exits. Zero lookahead is structurally possible. Evidence
accrues at the speed of reality - this is the honest track record lane.

- status: `forward_walk_marked` | last marking date: `2026-07-16`
- open positions: `0`
- closed trades: `21` (W `1` / L `20`)
- closed net P&L (premium units): `-50.233`
- entry policy: `dopey-forward-entry-quality-v2: fresh real signals; context snapshot aligned; OI>=25; volume>=5; relative spread<=10%; fill at ask plus commission`
- portfolio policy: `dopey-forward-portfolio-concentration-v1: open<=12; new/run<=8; sector<=3; direction<=8; one position/symbol`
- exit policy: `dopey-forward-exit-quality-v3: executable relative spread<=25%; stop -50% / target +100% / time 3 sessions / force-close dte<=5; dislocated quotes defer exits`
- pending exits awaiting executable quotes: `0`

## Open Positions

## Honest Limits
- Paper fills at ask/bid assume full size at quote; real fills can be worse.
- Sample accrues slowly by design; no claims until the truth layer's thresholds are met.
- paper_only: `true`; live_blocked: `true`; promotion blocked upstream.
