# DOPEY Dynamic Evidence Sentinel

Date: 2026-07-19  
Repository: `C:\Users\CH\dopey-hourly-coverage`  
Branch: `agent/dopey-hourly-dynamic-coverage`  
Mode: paper research only; live execution blocked

## Result

DOPEY now has a downgrade-only Dynamic Evidence Sentinel that combines:

- past-only adaptive conformal miscoverage monitoring;
- a non-overlapping empirical distribution-shift diagnostic;
- an anytime-valid bounded-mean e-process for settled correctness;
- e-LOND online false-discovery control for externally valid candidate e-values;
- metacognitive confidence caps, abstention, adversarial escalation, and evidence-expansion controls;
- homeostatic telemetry and interventions; and
- a four-hour, local-only scheduled lane with an explicit evidence contract.

The sentinel cannot promote a symbol, strategy, organism, or readiness state. It cannot bypass minimum sample gates. Candidate e-values are never manufactured from ordinary scores. Missing forward evidence selects `EXPAND_EVIDENCE`; detected calibration decay or distribution shift selects `ABSTAIN`.

## Operational truth

The current active calibration artifact reports zero settled vNext probability records. A read-only validation against that artifact therefore returned:

```text
cycle_status: complete
sentinel_status: insufficient_forward_evidence
selected_control: EXPAND_EVIDENCE
settlement_count: 0
readiness_effect: none
positive_promotion_allowed: false
live_blocked: true
```

This is a capability implementation, not evidence of predictive edge or action readiness.

## Additional hardening

Scheduler command integrity now canonicalizes CRLF to LF before hashing the three allowlisted Windows text launchers. This fixes a verified Windows false-fault condition while retaining content-addressed tamper detection.

The desktop metacognitive field now exposes the sentinel's status, selected control, settled sample, combined risk, recent miscoverage, distribution-shift risk, and terminal e-value whenever vNext emits the state.

## Scientific basis and limits

- Adaptive conformal control follows the online adjustment idea in [Adaptive Conformal Inference Under Distribution Shift](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html). DOPEY does not claim a coverage theorem for dependent market series; it requires empirical validation.
- Online false-discovery control uses e-LOND as described in [Online multiple testing with e-values](https://proceedings.mlr.press/v238/xu24a.html). Inputs must already be valid e-values.
- The distribution diagnostic is intentionally not labeled a proven change-point detector. Future expansion may compare it with the exact probabilistic model in [Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742), after market-specific likelihood and calibration work.

## Validation

```text
ruff: pass
compileall: pass
git diff --check: pass
dynamic evidence + settlement + vNext integration: 15 passed
acceleration control plane + autonomous trader completion: 17 passed
desktop control center: 12 passed
code release deployment: 3 passed
desktop TypeScript/Vite production build: pass
```

Publication state is recorded by the repository commit and GitHub pull request that contain this report.
