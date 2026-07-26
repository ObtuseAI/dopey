# DOPEY Dynamic Evidence OS - S-Tier V3 Recommendation

Review date: 2026-07-12  
Scope: architecture recommendation only; no strategy, sizing, broker, or live-gate changes.

## Verdict

The next S-tier expansion should be a Dynamic Evidence Operating System around the existing cohort, tournament, ensemble, stress, and sharpness layers. More raw indicators would add multiple-testing pressure without solving the current problems: zero baseline winners, zero era-robust survivors, four quote-priced closes, an active discipline halt, and only two archived quote-snapshot days.

The objective should be faster, safer evidence acquisition rather than more paper risk.

## Recommended components

### 1. Probabilistic regime router with online change-point detection

Replace single hard regime labels with posterior probabilities over latent states built from volatility-surface factors, breadth, rates, liquidity, trend, attention, and event context. Emit `route`, `abstain`, `drift`, and `reset` decisions. A detected structural break should reset or decay cohort evidence rather than letting stale success dominate.

Research basis: Bayesian change-point bandits explicitly address unknown shifts in non-stationary environments: https://proceedings.mlr.press/v189/alami23a.html

### 2. Adaptive conformal uncertainty and abstention

Wrap every forecast and filter with calibrated prediction intervals or sets that adapt under distribution shift. Route wide or miscalibrated predictions to abstention. Calibration should affect research attention and paper sizing but never override baseline, era, or forward gates.

Research basis: Adaptive Conformal Inference Under Distribution Shift: https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html

### 3. Anytime-valid sequential evidence ledger

Add per-cohort e-processes for superiority to baseline, forward expectancy, calibration, and decay. This permits early starvation and continuous monitoring without invalidating evidence through repeated peeking. Promotion should still retain minimum sample floors and require all current gates. Apply online false-discovery control across the mutation stream.

Research basis: Online Multiple Testing with E-values: https://proceedings.mlr.press/v238/xu24a.html

### 4. Counterfactual shadow-policy laboratory

Log every shadow decision with context, chosen action, candidate probabilities, rejected alternatives, and realized outcome. Use overlap diagnostics plus doubly robust off-policy evaluation with shrinkage. This can compare filters and routers from logged evidence while explicitly blocking claims when overlap is insufficient.

Research basis: Doubly Robust Off-policy Evaluation with Shrinkage: https://proceedings.mlr.press/v119/su20a.html

### 5. Information-gain experiment scheduler

Use a non-stationary contextual bandit only to select which hypothesis receives the next shadow observation. Its reward should be confidence-bound contraction, regime coverage, novelty, and information gain - never trading P&L or capital. Begin with the four current positive-delta filter/cohort pairs.

Research basis: An Information-Theoretic Analysis of Nonstationary Bandit Learning: https://proceedings.mlr.press/v202/min23c.html

### 6. Arbitrage-aware volatility-surface state engine

Build level, skew, term, curvature, convexity, tear velocity, and event-decay factors from validated option snapshots. Start with transparent SVI/PCA-style factors; defer neural latent surfaces until the archive is materially larger. Add explicit static-arbitrage and quote-quality rejection.

Research basis: Arbitrage-free SVI Volatility Surfaces: https://arxiv.org/abs/1204.0646

### 7. Hierarchical cohort evidence pooling

Use partial pooling across variant, setup, family, regime, and symbol-cluster IDs. Child cohorts retain their own records, while sparse cohorts borrow strength only through explicit shrinkage with uncertainty. This attacks sample fragmentation without manufacturing champions.

### 8. Multi-objective champion frontier

Replace one weighted score with a Pareto frontier over OOS lower-bound expectancy, worst-era performance, calibration, CVaR/expected shortfall, liquidity efficiency, IV-crush resilience, decay, and evidence age. A candidate can be research-novel without being promotion-eligible.

## First implementation wave

Build one new `dopey_dynamic_evidence` package with these deterministic paper-only outputs:

- `regime_posterior.jsonl`
- `change_point_events.jsonl`
- `adaptive_conformal_calibration.jsonl`
- `anytime_evidence_ledger.jsonl`
- `online_fdr_budget.json`
- `shadow_policy_log.jsonl`
- `off_policy_evaluation.jsonl`
- `experiment_priority_queue.json`
- `iv_surface_state.jsonl`
- `s_tier_v3_gate.json`

## Acceptance criteria

- No live or broker authority.
- No promotion from conformal, bandit, OPE, or neural scores alone.
- Missing propensities, weak policy overlap, calibration failure, or change-point uncertainty fail closed.
- Sequential evidence may starve early; it cannot bypass the existing sample minimum for promotion.
- All state transitions are deterministic, replayable, hashed, and auditable.
- Tests use the repository isolation layer and never overwrite the active public lake.
- Initial outcome may honestly be no survivor and zero new paper risk.

## Recommended order

1. Anytime-valid evidence ledger and online FDR budget.
2. Probabilistic regime/change-point router.
3. Shadow-policy logging contract and doubly robust OPE.
4. Information-gain experiment scheduler.
5. Volatility-surface state engine.
6. Adaptive conformal wrapper and Pareto champion frontier.

This order improves evidence integrity first, then adaptivity, then model richness.
