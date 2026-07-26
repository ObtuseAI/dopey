# DOPEY Football Program Translation

What the most successful NFL / NCAAF organizations actually do, translated
into DOPEY's research-and-evidence machinery. Sources are the well-documented
public practices of championship programs: Belichick's Patriots (6 Super
Bowls), Saban's Alabama (7 national titles), Andy Reid's Chiefs, the
Shanahan/McVay scheme tree, Kirby Smart's Georgia, and the analytics-forward
front offices (Eagles, Browns, Ravens).

Goal: adopt what transfers, name what already exists, refuse what violates the
constitution. "Any means necessary" here means maximum rigor and completeness -
never fabricated evidence, weakened gates, or terms-violating data acquisition
(the sign-stealing analogues stay refused, as they were in V21).

| # | Elite-program practice | Who exemplifies it | DOPEY translation | Status |
|---|---|---|---|---|
| 1 | "Do Your Job" - bounded roles, no hero-ball | Belichick | Supervisor stages and agents with bounded jobs and permissions; research cannot reach the control plane (AST guard) | PRESENT |
| 2 | The Process - execute the step, ignore the scoreboard | Saban | Evidence-first discipline: outcomes never claimed, only settled; L0 posture held under pressure | PRESENT |
| 3 | Turnover-margin obsession - the ball is the program | Every champion | V9's core finding: loss avoidance (trap+VRP blackout) is the ONLY measurable skill; protected as such | PRESENT |
| 4 | Quality control staff - chart every play | Saban's QC analysts | Append-only ledgers, journals, incidents, per-stage telemetry | PRESENT |
| 5 | Recruiting board - tiered, constantly re-ranked, cut candidates fast | Saban / Kirby Smart | Universe governor: core / candidate / probation / quarantined / retired tiers with promotion-on-evidence and rollback | PRESENT |
| 6 | Scout team - practice against a simulation of the opponent | Everyone | Adversarial stress engine, distributional stress, adversarial signal panel, negative controls | PRESENT |
| 7 | Depth chart / next man up | Everyone | Champion/challenger registries (screener elite archive, evolution loops) | PRESENT |
| 8 | In-game EV models (4th down, 2-pt) - math overrides gut | Eagles/Browns/Ravens | Deterministic kernels for pricing, Greeks, costs, breakevens; LLMs never compute execution-relevant numbers | PRESENT |
| 9 | Offseason capacity program (Fourth Quarter Program) | Saban | Weekend soak, nightly suite, scheduled full passes | PRESENT |
| 10 | Two-minute drill - pre-decided time-critical playbook | Everyone | Expiry-week force-close rules, discipline halts, latched cooldowns | PRESENT |
| 11 | Film study tendency database - down/distance/situation splits | Belichick, Manning-era prep | Trade Memory Graph: 321k trades sliced by point-in-time context (stretch, rvol); worst-context surfacing | PRESENT (built 2026-07-23) |
| 12 | Penalties lose championships - track and coach discipline errors | Every champion | **Operational Penalty Ledger (NEW)**: every missed marking session, failed ritual step, failed/skipped stage, stale lane, red nightly = a penalty with severity yards; weekly totals and trend | BUILT (this session) |
| 13 | Weekly opponent-specific game plan - attack THIS week | Belichick | **Weekly Game Plan (NEW)**: Monday synthesis of regime state + cross-lane convergence + memory worst-contexts + trust into per-family stances, situational watch items, probe emphasis, and falsifiers | BUILT (this session) |
| 14 | Film session - grade the plan against the tape, correct, repeat | Everyone | **Film Review (NEW)**: the prior plan graded against what actually settled; surprises and penalty totals recorded to a film-room ledger | BUILT (this session) |
| 15 | Scripted openers - first 15 plays probe the defense | Andy Reid | Probe emphasis in the game plan: thinnest-evidence families named as "develop depth" targets so accrual balances cohorts | BUILT (inside #13) |
| 16 | Self-scouting - break your own tendencies before others exploit them | Belichick | Signal calibration contested-truth (46.5% = the system's own tendency exposed); convergence conflicts flagged for review | PRESENT |
| 17 | Scheme adaptation when the era changes | Saban (defense-first to spread) | Constitution v2 amendments, evolvable surfaces with held-out fitness - change is gated but possible | PRESENT |
| 18 | Coaching tree / institutional knowledge transfer | Belichick/Saban trees | Memory files, canon documents, reports, this translation doc | PRESENT |
| 19 | Special teams - hidden yards in overlooked phases | Championship staffs | Niche lanes others skip: FINRA short flow, congressional trades, attention, liquidity impulse | PRESENT |
| 20 | Injury/load management | Modern programs | Capacity annotations, thin-liquidity flags, resource-conscious stage design (foundry compaction) | PRESENT |
| 21 | Sign-stealing / injury-report gamesmanship analogues | (the cheaters) | Terms-violating scraping, unofficial APIs, information acquired against platform rules | REFUSED (constitutional) |

## The three gaps that were real, and what was built

**Penalties (12).** Elite teams review every flag on Monday; DOPEY graded
outcomes but never graded its own operational discipline. The 07-16/17
provider glitch, the 07-21 missed marking day, last night's suite timeout -
those are penalties, and untracked penalties repeat.
`dopey_autonomy/penalty_ledger.py` now charts them with severity yards from
the artifacts the system already writes.

**Game plan (13, 15).** DOPEY had dashboards (state) but no plan (stance):
nothing said "this week, given the regime and the evidence, these families are
favored / blocked / contested, watch these situations, and here is what would
change our mind." `dopey/strategy_engineering/game_plan.py` builds that every
week from the convergence engine, trade memory, forward trust, and macro
state - deterministic, advisory, falsifiable.

**Film review (14).** A plan nobody grades is a wish. The film room replays
last week's plan against what actually settled and appends the lessons to a
ledger the next plan reads. Plan -> execute -> grade -> correct, weekly.

All three are advisory research instruments: they never gate, size, or promote.
Forward settlement remains the only path