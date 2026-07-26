# DOPEY Capital Redeployment Report

## Simulated paper-only redeployment logic

The capital redeployment engine (`dopey_edge/capital_redeployment_engine.py`) produces
**simulated paper-only redeployment recommendations** from the ensemble allocator's
decisions and family failure pressure. It is recommend-only: it does not mutate any account,
place broker orders, or size real capital.

Two interfaces exist:

- `redeploy_capital(...)` — original Dummy-doctrine family reallocation stub (preserved).
- `build_capital_redeployment_recommendations(...)` — the new paper-only redeployment layer
  consumed by the offline ensemble allocator.

Each `CapitalRedeploymentRecommendation` carries:

- `recommendation_id`, `target_strategy_family`, `target_strategy_id`
- `action` (one of `increase | hold | reduce | starve | quarantine | research_only`)
- `reason_codes`, `source_evidence`, `failure_mode_evidence`, `regime_evidence`
- `proof_level = paper_only`, `paper_only = True`, `live_allowed = False`

## Reason codes

The engine selects an action from the allocation decision, the family failure pressure, and
the dominant regime class. Reason codes explain each transition:

- `"recurring failure-mode pressure starves the family"` (family failure pressure >= 0.40)
- `"high-overfit candidate quarantined from paper attention"`
- `"reduce vol-expansion attention after post-event IV crush"`
- `"increase liquidity threshold for short-duration candidates"`
- `"proof + regime fit reward paper attention"`
- `"stable but mixed proof holds paper attention"`
- `"stable but insufficient proof; observation only"`

## Examples

### Increase

A directional candidate in a confirmed trend regime with `increase_paper_attention` ->
`action=increase`, reason `"proof + regime fit reward paper attention"`.

### Hold

A candidate with `hold_paper_attention` in a non-shock regime -> `action=hold`, reason
`"stable but mixed proof holds paper attention"`.

### Reduce

A `volatility_expansion` candidate whose dominant regime class is `post_event_crush` ->
`action=reduce`, reason `"reduce vol-expansion attention after post-event IV crush"`.

A `short_duration_defined_risk` candidate in a `bad_fill` regime -> `action=reduce`, reason
`"increase liquidity threshold for short-duration candidates"`.

### Starve

A candidate whose family failure pressure >= 0.40 -> `action=starve`, reason
`"recurring failure-mode pressure starves the family"`, with `failure_mode_evidence`
recording the pressure value. A `starve_weak_signal` decision also maps to `starve`.

### Quarantine

A `quarantine_overfit` decision -> `action=quarantine`, reason
`"high-overfit candidate quarantined from paper attention"`.

### Research-only

A candidate below the proof threshold -> `action=research_only`, reason
`"stable but insufficient proof; observation only"`.

## Failure-mode evidence usage

Family failure pressure is computed from the latest failure-mode registry via
`aggregate_failure_modes` + `build_family_failure_profiles`. The pressure sum is
soft-saturated (`pressure / (pressure + 30)`) so only genuinely pressured families cross the
starve threshold; the saturated value is recorded as `failure_mode_evidence` when an action
is driven by failure pressure.

## Safety boundaries

- Every recommendation is `paper_only=True` and `live_allowed=False`.
- Forbidden actions (`live_allocate`, `micro_live`, `adaptive_live`, `real_capital`,
  `broker_order`) raise `ValueError` if ever encountered.
- No broker connection, credentials, network access, account mutation, real capital sizing,
  scheduled run, or live promotion is performed.
- The engine is consumed only by the offline ensemble allocator (RESEARCH mode).
