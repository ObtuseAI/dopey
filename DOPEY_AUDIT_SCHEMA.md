# DOPEY Audit Schema

## Purpose

This document defines the deterministic schema used by the `dopey_audit` offline evidence
replay audit harness. All audit artifacts are paper-only, fixture-only, and offline. They do
not contain live orders, broker credentials, or real market data.

## Audit artifact types

| Artifact type | Kind | Required version field | Location |
|---|---|---|---|
| `paper_pipeline_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/proof_ledger/dopey_paper_pipeline.jsonl` |
| `walk_forward_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/walk_forward/dopey_walk_forward.jsonl` |
| `tournament_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/tournaments/dopey_tournament.jsonl` |
| `mutation_registry` | registry | `mutation_registry_version` | `artifacts/dopey/mutations/mutation_registry.jsonl` |
| `mutation_population_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/mutations/dopey_mutation_population_bundle.jsonl` |
| `mutation_tournament_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/mutations/dopey_mutation_tournament.jsonl` |
| `failure_mode_registry` | registry | `version` (alias `failure_mode_registry_version`) | `artifacts/dopey/failure_modes/failure_mode_registry.jsonl` |
| `failure_feedback_registry` | registry | `feedback_optimizer_version` | `artifacts/dopey/failure_feedback/failure_feedback_registry.jsonl` |
| `feedback_optimizer_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/failure_feedback/feedback_optimizer.jsonl` |
| `source_registry` | registry | `registry_version` (aliases `source_registry_version`, `registry_id`) | `artifacts/dopey/source_registry/data_inflow_registry.jsonl` |
| `iv_surface_registry` | registry | `iv_surface_expansion_version` | `artifacts/dopey/iv_surface/iv_surface_registry.jsonl` |
| `iv_surface_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/iv_surface/iv_surface_skew_bundle.jsonl` |
| `macro_event_registry` | registry | `macro_event_expansion_version` | `artifacts/dopey/macro_events/macro_event_registry.jsonl` |
| `macro_event_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/macro_events/macro_event_bundle.jsonl` |
| `ensemble_registry` | registry | `ensemble_allocator_version` | `artifacts/dopey/ensemble_allocator/ensemble_allocation_registry.jsonl` |
| `ensemble_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/ensemble_allocator/ensemble_replay.jsonl` |
| `meta_governor_registry` | registry | `meta_governor_version` | `artifacts/dopey/meta_governor/meta_governor_registry.jsonl` |
| `meta_governor_decisions` | registry | `meta_governor_version` | `artifacts/dopey/meta_governor/meta_governor_decisions.jsonl` |
| `meta_governor_ledger` | ledger | `run_id`, `final_status` | `artifacts/dopey/meta_governor/meta_governor_proof.jsonl` |
| `champion_registry` | registry | `champion_strategy_id` | `artifacts/dopey/champion_registry/champion_registry.jsonl` |

**Kind definitions**

- `ledger` — a run-level append-only `ProofLedger` entry. Schema requires `run_id` and
  `final_status` at minimum.
- `registry` — a state-level append-only registry. Schema requires a model/version field
  that identifies the record format.

**Version aliases**

The harness tolerates known aliases for version fields so existing records remain
schema-compatible:

- `failure_mode_registry` `version` may also appear as `failure_mode_registry_version`.
- `source_registry` `registry_version` may also appear as `source_registry_version` or
  `registry_id`.

## Audit verdicts

| Verdict | Meaning |
|---|---|
| `pass` | All audited layers are reproducible, consistent, and live-blocked. |
| `pass_with_notes` | Pass with informational findings only. |
| `warning` | Non-blocking replay or consistency findings; safe to continue research. |
| `fail_reproducibility` | Stored reproducibility hash or score does not replay deterministically. |
| `fail_safety` | Live safety boundary drift or active forbidden live decision detected. |
| `fail_schema` | Required schema/version fields missing from present artifacts. |
| `fail_missing_evidence` | More than half of expected artifacts missing or empty. |

Severity escalation:

1. Any safety error or active forbidden live decision → `fail_safety`.
2. Else any hash mismatch → `fail_reproducibility`.
3. Else any schema warning → `fail_schema`.
4. Else completeness < 0.5 → `fail_missing_evidence`.
5. Else any score drift or consistency warning → `warning`.
6. Else `pass`.

## Finding severities

| Severity | Meaning |
|---|---|
| `info` | Documentation-only or intentionally tolerated condition. |
| `warning` | Data quality, coverage, or consistency issue; not a safety violation. |
| `error` | Reproducibility, schema, or reference inconsistency. |
| `safety_error` | Live boundary drift, active forbidden decision, or Blunder source modification. |

## Required model version fields

Each artifact record SHOULD expose a deterministic version or run identifier:

- **Ledgers** must contain `run_id` and `final_status`.
- **Registries** must contain one of the version fields listed in the artifact-type table
  above (aliases accepted).

The harness uses these fields to detect stale records, schema drift, and missing artifacts.

## Hash / reproducibility expectations

- The harness recomputes a canonical single-record hash for artifact types whose stored
  `reproducibility_hash` is expected to be the record's own hash:
  - `ensemble_registry`
  - `meta_governor_registry`
  - `meta_governor_decisions`
- The canonical hash is computed over the record excluding its own `reproducibility_hash`,
  using `dopey_research_pipeline.quality_ledger.reproducibility_hash` (sorted-JSON SHA256).
- Other artifact types may use multi-part or bundle-level hashes; the harness records them
  as informational "hash present" cases rather than enforcing strict single-record replay.
- Deterministic score replay verifies ensemble weight sums and accepted-weight invariants
  within a tolerance (`SCORE_DRIFT_TOLERANCE = 1e-3`, `WEIGHTS_SUM_TOLERANCE = 1e-2`).

## Safety audit expectations

The safety-boundary drift audit verifies the following invariants every run:

- `mode == RESEARCH`
- `live_trading_enabled == false`
- `funded_broker_connections_enabled == false`
- `allow_unofficial_robinhood_api == false`
- `PaperBroker` raises `LiveTradingDisabledError` when given `live_allowed=true`.
- `RobinhoodMCPAdapter`, `AlpacaOptionsAdapter`, and `TradierOptionsAdapter` raise
  `LiveTradingDisabledError` when asked to place live orders.
- No active forbidden live token appears as a decision/tier/status value in any artifact.
- Forbidden tokens may appear inside explicitly named documentation/list fields
  (`forbidden_live_decisions`, `blocked_tiers`, etc.) without triggering a safety error.
- Original Blunder source files match the SHA256 manifest when available.
- No hidden live promotion tier, broker credential path, network-required active source,
  scheduled run, or autonomous daemon is introduced.

## Evidence gap categories

| Category | Typical cause |
|---|---|
| `insufficient_walk_forward_consistency` | Non-directional families fail walk-forward consistency floors. |
| `small_regime_corpus` | Too few distinct fixture regimes to support cross-family promotion. |
| `missing_source_backed_data` | Network/credential sources remain deferred. |
| `deterministic_fixture_only_limitation` | All evidence is simulated fixture math. |
| `weak_cross_family_evidence` | Ensemble concentrates on a single family. |
| `high_overfit_family` | Family overfit pressure >= 0.9. |
| `low_liquidity_robustness` | Family liquidity pressure >= 0.6. |
| `iv_surface_trap_exposure` | Elevated IV-crush / premium-trap pressure. |
| `macro_contradiction_pressure` | Macro contradiction pressure >= 0.6. |
| `insufficient_holdout_windows` | Too few holdout windows for cross-family promotion. |
| `missing_audit_hash` | Present artifact lacks a reproducibility hash. |
| `stale_artifact` | Required schema/version fields missing. |
| `schema_drift` | Required schema fields missing from a present artifact. |
| `missing_proof_ledger_record` | Expected proof ledger is missing. |
| `missing_safety_proof` | Safety-state fields missing from a record. |

## Allowed next build targets

Only the following build targets may be emitted by the audit gap planner:

1. `stronger_walk_forward_consistency_expansion`
2. `larger_regime_holdout_corpus`
3. `tournament_performance_reporting_dashboard_artifacts`
4. `broker_capability_detector_hardening`
5. `deterministic_sector_peer_fundamental_fixture_expansion`
6. `artifact_compaction_export_verifier`

## CLI entry point

```text
python -m dopey_audit.run_offline_evidence_replay_audit
```

The CLI writes JSONL audit registries and a markdown summary to
`artifacts/dopey/audit/` and prints a JSON summary to stdout.
