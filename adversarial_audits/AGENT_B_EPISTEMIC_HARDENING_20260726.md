# Agent B Epistemic Hardening Audit

## Supervisor truth

| Surface | Verified state | Adversarial conclusion |
|---|---|---|
| Supervisor size | 39 stages | The 36-stage premise was stale; the dedicated epistemic stage is now stage 30. |
| Stage topology | Topologically ordered | Structural order is valid. |
| Symbol targeting | Stage 28; depends on playbook research and model-IV calibration | Its output is now a hard input to epistemic supervision. |
| Squeeze/bubble intelligence | Stage 29; depends on history, macro context, and chain analytics | Its output is now a hard input to epistemic supervision. |
| Epistemic supervision | Stage 30; depends on targeting and squeeze/bubble intelligence | Downgrade-only challenge is wired into the production supervisor. |
| Existing adversarial panel | Stage 31; depends on forward paper walk, forward-book risk, and market-context fusion | Its separate forward-paper mandate is preserved. |
| Account reconciliation | Independent root | Research and execution evidence remain deliberately separated. |
| Action-readiness gate | Independent root | Research supervision cannot grant or rewrite execution authority. |

## Implemented adversarial attacks

| Attack surface | Enforced mutation |
|---|---|
| Stale, future, unavailable, or non-point-in-time evidence | Blocks with timestamp-specific reason codes. |
| Duplicated or relabeled evidence | Detects duplicate IDs, duplicate contributions, and one content hash presented under multiple source IDs. |
| Contradictory features | Blocks unresolved support/opposition inside a feature family and claim/effect sign conflicts. |
| Missing denominators | Blocks ratio, rate, and effect evidence below the explicit denominator floor. |
| Outlier domination | Blocks excessive normalized weight and excessive contribution share. |
| Simpson or regime inversion | Requires denominator-bearing regime cells, flags mixed direction, and blocks denominator-weighted inversion. |
| Crowding without catalyst | Blocks squeeze claims based on crowding without an independent catalyst. |
| Mechanical post-IPO effects | Blocks recent-IPO bubble claims without both nonmechanical evidence and an independent unwind. |
| Valuation-sector mismatch | Blocks missing or mismatched issuer/peer sectors for valuation evidence. |
| Execution contamination | Blocks simulated-execution, live, broker, or order-capable inputs inside research claims. |
| Fitness and promotion laundering | Blocks evidence reuse, missing hidden/external holdouts, unbound evaluation evidence, nonpositive fitness change, and missing parent hashes. |
| Fitness regression | Sets `automatic_rollback_required=true` and `mutation_retention_allowed=false`. |
| Existing blocked/inconclusive states | Preserves the upstream status string exactly and never upgrades it. |

## Artifact contract

`evaluate_epistemic_claim(claim, evidence, regime_effects, policy)` is pure and
returns a deterministic content-addressed record. The record is research-only,
requires all existing gates, exposes no order capability, never permits
promotion, and carries a parent artifact hash for append-only ledger binding.

`audit_supervisor_topology(stages, expected_stage_count)` is import-free and
returns the current stage truth, ordering proof, critical lineage, and detected
epistemic gaps.

`run_epistemic_supervision(paths, policy, evaluated_at)` consumes the actual
squeeze/bubble and targeting artifacts, verifies containment, hashes,
freshness, and same-cycle lineage, then atomically publishes one downgrade-only
summary.

## Validation

| Command | Result |
|---|---|
| `python -m ruff check dopey_validation/epistemic_adversary.py tests/test_epistemic_adversarial_supervision.py` | Passed |
| `python -m ruff format --check dopey_validation/epistemic_adversary.py tests/test_epistemic_adversarial_supervision.py` | Passed after deterministic formatting |
| `python -m pytest tests/test_epistemic_adversarial_supervision.py tests/test_epistemic_runtime_integration.py -q` | 14 passed |
| `python -m compileall -q dopey_validation/epistemic_adversary.py` | Passed |
| `git diff --check -- dopey_validation/epistemic_adversary.py tests/test_epistemic_adversarial_supervision.py` | Passed |
| Broader targeting/squeeze/boundary contract run | 35 passed |

## Remaining integration risks

1. Account reconciliation and action readiness remain intentional independent
   roots so research evidence cannot grant execution authority.
2. Append-only persistence must bind `content_hash` and
   `parent_artifact_hash`; this module intentionally performs no writes.
3. Missing point-in-time regimes, catalyst identities, or peer cohorts remain
   typed blockers until real source artifacts provide them.
