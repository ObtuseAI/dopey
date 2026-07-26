# DOPEY Aggressiveness and Sharpness Review

Review date: 2026-07-12  
Scope: read-only review of the current `C:\Users\CH\dopey` working tree and latest artifacts. No strategy code, thresholds, data, or live/broker settings were changed.

## Executive verdict

DOPEY should not increase raw paper exposure yet. The highest-value aggressive move is to become more selective: starve losing cohorts, route capital only to evidence-positive cohorts, improve exit-policy acceptance semantics, and separate research-edge scoring from execution readiness.

Current evidence is negative:

- Statistical truth: 46,904 model-priced trades, average P&L `-0.125966`, total P&L `-5908.304685`, win rate `0.380458`, promotion blocked.
- Baseline arbitration: `0` cohorts beat the matched random-entry baseline at 95% confidence.
- Era walk-forward: `0` cohorts are regime robust.
- Quote-priced forward walk: `4` closed trades, `0` wins, net P&L `-24.862`; 17 positions remain open.
- Signal calibration: contested hit rate `0.4647`, below chance; this lane is correctly advisory-only.
- Indicator foundry: 144 candidates tested and `0` promoted. Macro and attention lanes contain research leads, not edge proof.
- Forward book: premium at risk `206.7405`; AMD is `24.87%` of the book, just under the `25%` concentration limit. IV crush is the dominant risk: the 50% crush scenario loses `117.5325`, or `56.85%` of premium.

## Highest-priority improvements

### P0 - Fix exit-policy promotion semantics

`dopey_evolution/exit_policy_walkforward_search.py` promotes a candidate when it is merely less bad than the current policy in train and validation. The promoted 5-session / -70% stop / +200% target policy still loses `-1047.06` in train and `-2995.87` in validation. Label this `relative_improvement_only`, not promoted. Require positive validation expectancy after costs, a confidence interval above zero, and minimum trade coverage before promotion.

### P0 - Separate edge score from execution capability

`dopey_edge/proof_weighted_aggression_gate.py` subtracts `0.50` when broker option execution is unsupported. That contaminates research-edge ranking with infrastructure state. Produce two independent outputs: `edge_conviction_score` from market evidence and `execution_eligibility` from broker/live gates. A strong paper hypothesis should remain visible even while execution stays blocked.

### P0 - Make aggression relative, not absolute

The allocator uses fixed proof thresholds (`0.60`, `0.78`, `0.84`) but the current truth artifacts show no demonstrated edge. Add a portfolio-level aggression multiplier whose maximum is determined by evidence state:

- no baseline winner or no era-robust cohort: shadow-only, minimum sizing;
- baseline winner but insufficient forward sample: normal paper sizing;
- baseline winner plus era robustness plus positive forward lower confidence bound: aggressive paper sizing;
- discipline halt, decay, or adverse drawdown slope: immediate starvation.

Do not loosen the current 0DTE share, concentration, liquidity, or spread caps to simulate progress.

### P1 - Optimize selection before sizing

The latest baseline report shows most named cohorts are statistically worse than random. Add a deterministic loser-starvation pass before allocation: quarantine cohorts whose 95% upper confidence bound is below baseline; require same-sign benefit across eras; rank survivors by net expectancy lower bound, stability, liquidity, and IV-crush efficiency. This should reduce trade count and improve signal density.

### P1 - Attack the long-premium failure mode

The book is dominated by theta and IV-crush risk: theta is `-345.56` dollars/day and the IV-crush stress consumes `56.85%` of premium. Sharpen entries with IV-rank/term-structure filters, event-aware overpayment rejection, and expected-move-to-premium ratios. Prefer structures or expiries with more favorable convexity-to-decay economics while preserving defined risk and the paper-only boundary.

### P1 - Validate the new exit candidate honestly

The 5/-70%/+200% candidate is materially better than the old 3/-50%/+100% policy but still negative. Treat it as a shadow challenger. Run purged, rolling walk-forward comparisons by cohort and volatility regime, including spread/commission sensitivity. Promote only cohorts for which the exit change has positive out-of-sample expectancy, not the whole book globally.

### P2 - Use the promising foundry lanes as filters

VIX level, skew level, VIX term slope, and Wikipedia-attention reversal cleared their local IC bars, but none passed the full two-era promotion rule. Use them as conditional filters or sizing suppressors in shadow experiments rather than standalone alpha. The attention result is contrarian/put-side and should be tested with strict timestamp and publication-lag controls.

### P2 - Improve experiment economics

Track each mutation's marginal contribution against the identical random baseline and current champion. Stop evaluating raw trade count as progress. Optimize for lower-bound net expectancy, probability of ruin, drawdown recovery time, turnover-adjusted return, and evidence gained per market session.

## Recommended tuning order

1. Correct promotion labels and decouple edge scoring from broker readiness.
2. Add cohort loser starvation and confidence-bound ranking.
3. Shadow-test volatility/attention filters and cohort-specific exits.
4. Accumulate at least the existing 100 quote-priced forward closes without weakening gates.
5. Increase paper aggression only after a cohort beats baseline, survives all eras, and has positive forward evidence.

## Safety and workspace notes

- Live trading remains blocked; no broker connection or order path was exercised.
- The working tree was already heavily dirty, including active market-data, options-chain, fundamentals, earnings, fixture, log, and report changes. Those files were preserved.
- No full test suite was run because this was a read-only review and the active data lake is user state.
