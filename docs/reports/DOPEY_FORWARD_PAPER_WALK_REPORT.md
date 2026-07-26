# DOPEY Forward Paper Walk Report

## Evidence Class
Ex-ante, quote-priced paper trading: entries at the real ask on fresh signals, marks at
an executable real bid on later snapshots. Dislocated quotes defer exits. Zero lookahead is structurally possible. Evidence
accrues at the speed of reality - this is the honest track record lane.

- status: `forward_walk_marked` | last marking date: `2026-07-23`
- open positions: `17`
- closed trades: `4` (W `1` / L `3`)
- raw closed records preserved: `24` | censored `17` | quarantined `3`
- closed net P&L (premium units): `-18.452`
- entry policy: `dopey-forward-entry-quality-v2: fresh real signals; context snapshot aligned; OI>=25; volume>=5; relative spread<=10%; fill at ask plus commission`
- portfolio policy: `dopey-forward-portfolio-concentration-v3: open<=20; new/run<=8; sector<=4; direction<=13; symbol premium share<=25% or concentration-repair-only; one position/symbol`
- exit policy: `dopey-forward-exit-quality-v3: executable relative spread<=25%; stop -50% / target +100% / time 3 sessions / force-close dte<=5; dislocated quotes defer exits`
- missing quote policy: `after 3 consecutive missing exact-contract observations, archive as censored_missing_quote_continuity with no exit fill and no win/loss`
- pending exits awaiting executable quotes: `0`

## Open Positions
- `fw-AMD-long_call-2026-07-17-00001` AMD long_call K=500.0 exp=2026-08-14 entry_fill=47.5065 last_bid=66.8
- `fw-BAC-long_call-2026-07-17-00002` BAC long_call K=61.0 exp=2026-08-14 entry_fill=1.7865 last_bid=1.58
- `fw-IONQ-long_put-2026-07-17-00004` IONQ long_put K=35.0 exp=2026-08-14 entry_fill=4.2065 last_bid=3.4
- `fw-JPM-long_call-2026-07-17-00005` JPM long_call K=340.0 exp=2026-08-14 entry_fill=10.0565 last_bid=14.05
- `fw-MA-long_call-2026-07-17-00006` MA long_call K=550.0 exp=2026-08-14 entry_fill=15.6065 last_bid=14.4
- `fw-MSTR-long_put-2026-07-17-00008` MSTR long_put K=94.0 exp=2026-08-14 entry_fill=9.0065 last_bid=7.25
- `fw-MU-long_put-2026-07-20-00009` MU long_put K=870.0 exp=2026-08-21 entry_fill=107.8565 last_bid=54.95
- `fw-NET-long_call-2026-07-20-00010` NET long_call K=250.0 exp=2026-08-21 entry_fill=38.6065 last_bid=27.3
- `fw-ORCL-long_put-2026-07-20-00011` ORCL long_put K=120.0 exp=2026-08-21 entry_fill=8.7065 last_bid=8.6
- `fw-ADBE-long_call-2026-07-23-00013` ADBE long_call K=215.0 exp=2026-08-21 entry_fill=10.3565 last_bid=9.65
- `fw-ADP-long_call-2026-07-23-00014` ADP long_call K=170.0 exp=2026-08-21 entry_fill=80.4065 last_bid=76.8
- `fw-ADSK-long_call-2026-07-23-00015` ADSK long_call K=200.0 exp=2026-08-21 entry_fill=14.4065 last_bid=13.4
- `fw-C-long_put-2026-07-23-00016` C long_put K=140.0 exp=2026-08-21 entry_fill=10.1565 last_bid=9.2
- `fw-SMH-long_put-2026-07-23-00017` SMH long_put K=580.0 exp=2026-08-21 entry_fill=34.2565 last_bid=31.65
- `fw-USO-long_call-2026-07-23-00018` USO long_call K=139.0 exp=2026-08-21 entry_fill=11.1565 last_bid=10.45
- `fw-XLK-long_put-2026-07-23-00019` XLK long_put K=175.0 exp=2026-08-07 entry_fill=3.4565 last_bid=3.4
- `fw-XBI-long_call-2026-07-23-00020` XBI long_call K=136.0 exp=2026-08-21 entry_fill=18.3565 last_bid=16.9

## Honest Limits
- Paper fills at ask/bid assume full size at quote; real fills can be worse.
- Sample accrues slowly by design; no claims until the truth layer's thresholds are met.
- paper_only: `true`; live_blocked: `true`; promotion blocked upstream.
