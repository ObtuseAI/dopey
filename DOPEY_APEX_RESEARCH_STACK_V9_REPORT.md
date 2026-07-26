# DOPEY_APEX_RESEARCH_STACK_V9_REPORT

- repo path: `C:\Users\CH\dopey`
- bundle: `DOPEY_APEX_RESEARCH_STACK_V9`
- date: 2026-07-09
- supervisor status: `all_stages_completed` (11/11 stages, 0 incidents)

## What V9 Is

The maximum-capability HONEST version of the "apex predator" upgrade request. Each demanded
capability was built in the form that survives contact with real data; each fantasy version
(bottom-ticking, zero failure states, real-time proprietary feeds without licenses) is
explicitly refused, because the V1-V7 lane already demonstrated where that path leads:
self-referential noise wearing a costume.

## Capability Map (demand -> what was actually built)

1. **"Infinite Engine"** -> `dopey_autonomy/run_resilient_research_supervisor.py`
   Full-chain supervisor: 11 stages in dependency order; failures are absorbed into
   structured incident + repair-queue artifacts; true dependents are skipped with reasons;
   independent stages always run; a failure is NEVER recorded as a pass, and the supervisor
   can never promote a strategy. "No dead ends" means every failure becomes an actionable
   work item - not that failure is hidden.

2. **"Omniscient Vision"** -> `dopey_analysis/market_structure_engine.py` +
   `dopey_chart_vision/real_structure_chart_renderer.py`
   Machine-readable market structure computed leak-free from the governed spine: 1,667 trap
   events (1,015 bull / 652 bear), 2,512 volume anomalies, swing/SR zones - plus rendered
   candlestick+volume+structure charts (SPY/QQQ/NVDA/TSLA) as the multimodal review surface.
   Verified by an actual vision read: trap markers land at the Jan-2026 top and the Nov-2025 /
   Mar-2026 lows on SPY.

3. **"Derivatives Domination"** -> `dopey_options/chain_analytics.py`
   GEX per strike + total (dealer convention), gamma-flip point, put/call OI and volume
   ratios, net delta-hedging pressure - math fixture-validated (9 tests) and GATED:
   `blocked_no_real_chain_data_staged` until an operator stages licensed chain data through
   `dopey_data/real/raw/options_chains/` + the options manifest. The module never fabricates
   chain data. Dark-pool prints have no license-clean lane in this envelope; not faked.

4. **"God-Tier Intuition" (trap avoidance / IV-crush)** -> the structure engine's blackout
   layer, and it is the ONE thing that measurably worked (see verdicts): excluding entries in
   trap windows and VRP-rich (expensive implied vol) days removed 1,193 trades averaging
   `-0.89` units each and improved net P&L by `+1,065` units. The variance-risk-premium proxy
   (VIX implied vs SPY realized variance, 237 rich days of 3,023) is the honest IV-crush
   detector available without chains.

5. **"Precision Execution"** -> the cost stack in `real_history_honest_backtester.py`
   (half-spread 2.5%/side + slippage 0.5%/side + $0.65/contract commission, mid-marked paths,
   fills pay the spread). Not a "buy the bottom" engine - the opposite: it prices what
   execution actually costs, which is the number that decides survival.

6. **"Savant Intellect"** -> `dopey_backtest/baseline_arbitration.py` (matched random-entry
   baselines through the identical pricing/exit/cost engine + two-sample bootstrap CIs) and
   `dopey_backtest/era_walk_forward.py` (2015-2019 / 2020-2022 / 2023-2026 regime-stability
   verdicts), on top of the existing bootstrap/deflated-Sharpe/multiple-testing truth layer.

## The Verdicts (real data, post-cost, model units)

| Question | Answer |
| --- | --- |
| Gross (mid-marked) P&L, 9,333 trades | -538.40 |
| Transaction costs | -2,519.19 |
| **NET P&L** | **-3,057.59** |
| Cohorts beating random-entry baseline (95% CI) | **0 of 10** |
| Cohorts significantly WORSE than random | 3 (breakout/momentum/market_regime long_put) |
| Regime-robust cohorts across all 3 eras | **0** |
| Structure/VRP blackout filter value | +1,065.10 net improvement (loss avoidance) |
| Chain analytics | blocked awaiting licensed real chain data |

**The one-line truth: after costs, the current signal set has NO entry edge over random
timing - the only measurable skill in the system today is in NOT trading.** The V8 long-call
"edge" (PF 1.26 at mid) was bull-market drift: indistinguishable from random entries run
through the same engine. This negative result is produced and defended by the machine itself -
bootstrap CIs, baselines, era splits - and it is exactly what stands between this system and
incinerating real money.

## Validation

- `tests/test_v9_apex_research_stack.py`: 9 passed (cost math incl. winner->loser marker flip,
  swings/SR, leak-free bull-trap detection, volume z-score, VRP math, GEX/flip/put-call/delta
  math, chain gate blocked, supervisor absorb/skip/never-pass semantics)
- `tests/test_real_history_lane.py`: 9 passed (now asserting cost fields)
- Supervisor end-to-end: 11/11 stages, 0 incidents, honest per-stage statuses

## What Was Refused, And Why That Is The Upgrade

- "Buys the absolute bottom, sells the absolute top": not a property any system can have;
  optimizing toward it produces overfit artifacts. Refused.
- "Zero failure states": a system that cannot fail cannot learn; failures are now structured
  work items instead. Refused in favor of absorb-record-continue.
- Real-time options flow / dark pool without licensed feeds: no credential-free, license-clean
  lane exists in this envelope; the tested, gated consumption machinery is built and waiting.
- "Aggressive prompt injections for sub-agents": this system's edge-search is deterministic
  code with truth gates, not vibes-prompted LLM agents; a prompt cannot make noise into edge.

## Next Target

`DOPEY_REAL_CHAIN_DATA_STAGING_AND_QUOTE_PRICED_UNLOCK_V10` - the binding constraint is
unchanged: licensed real options-chain data. On staging, chain analytics activate, quote-priced
records become possible, and the truth layer's `real_sample_size` can finally move off zero.

## Safety State

- paper_only: `true`; live_blocked: `true`; strategy_promotion_allowed: `false`
- no broker, credentials, `.env`, orders, scheduler, real sizing, or network fetch by DOPEY
- long_call / long_put / no_trade only, enforced end-to-end
