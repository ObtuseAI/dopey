# DOPEY Offline Evidence Replay Audit Harness Report

## Purpose

`DOPEY_OFFLINE_EVIDENCE_REPLAY_AUDIT_HARNESS_V1` adds a local, deterministic, offline,
paper-only proof-chain auditor. It reloads DOPEY's existing ProofLedger + registry
artifacts, replays selected deterministic computations, compares stored hashes/scores/decisions,
and reports whether the evidence chain is reproducible and internally consistent.

This is **not live performance evidence**, **not a live-readiness system**, and **not a
broker or market-data connection**. It never enables live trading, places trades, fetches
network data, or uses credentials.

## What the harness audits

The harness inventories and replays evidence from:

- paper pipeline ProofLedger
- walk-forward replay ProofLedger
- tournament ProofLedger + champion registry
- mutation registry + mutation tournament ProofLedger
- failure-mode registry
- failure-feedback registry + feedback optimizer ProofLedger
- source/data-inflow registry
- pattern fixture records (carried inside tournament/champion registries)
- IV surface registry + IV surface ProofLedger
- macro event registry + macro event ProofLedger
- ensemble allocator registry + ensemble replay ProofLedger
- meta-governor registry + decisions + ProofLedger
- validation reports (referenced indirectly via configuration and state assertions)
- safety state fields embedded in records

## Audit passes

1. **Safety-state verification** — confirms `mode=RESEARCH`, `live_trading_enabled=false`,
   `funded_broker_connections_enabled=false`, `allow_unofficial_robinhood_api=false`,
   `PaperBroker` refuses `live_allowed=true`, Robinhood/Alpaca/Tradier stubs raise
   `LiveTradingDisabledError`, and no active forbidden live decision/tier appears.
2. **Evidence inventory** — scans 20 expected artifact paths, records path, type, count,
   latest run id, hash, model version, safety state, parse status, and completeness.
3. **Replay / hash audit** — recomputes canonical reproducibility hashes for strict
   single-record artifacts (ensemble registry, meta-governor registry, meta-governor
   decisions) and verifies no hash drift; re-runs score invariants on ensemble records;
4. **Cross-layer consistency audit** — links champions to tournament records, mutation
   champions to mutation registries, meta-governor decisions to proof profiles,
   references to known strategy IDs, and checks for forbidden live decisions.
5. **Evidence gap planner** — converts audit findings into prioritized next-proof tasks.
6. **Registry + summary artifact generation** — writes JSONL audit registries and a
   human-readable markdown summary.

## Commands run

```text
python -m pytest
python -c "from dopey_audit.evidence_models ...; print('AUDIT_HARNESS_IMPORT_OK')"
python -m dopey_tournament.run_fixture_tournament
python -m dopey_strategy_lab.run_mutation_population_bundle
python -m dopey_strategy_lab.run_failure_feedback_optimizer
python -m dopey_options.run_iv_surface_skew_bundle
python -m dopey_analysis.run_macro_event_bundle
python -m dopey_strategy_lab.run_offline_ensemble_allocator
python -m dopey_governor.run_offline_meta_governor
python -m dopey_audit.run_offline_evidence_replay_audit
Blunder SHA256 manifest check via audit harness
```

## Artifact inventory

| Artifact type | Path | Status |
|---|---|---|
| paper pipeline ledger | `artifacts/dopey/proof_ledger/dopey_paper_pipeline.jsonl` | present |
| walk-forward ledger | `artifacts/dopey/walk_forward/dopey_walk_forward.jsonl` | present |
| tournament ledger | `artifacts/dopey/tournaments/dopey_tournament.jsonl` | present |
| mutation registry | `artifacts/dopey/mutations/mutation_registry.jsonl` | present |
| mutation population ledger | `artifacts/dopey/mutations/dopey_mutation_population_bundle.jsonl` | present |
| mutation tournament ledger | `artifacts/dopey/mutations/dopey_mutation_tournament.jsonl` | present |
| failure-mode registry | `artifacts/dopey/failure_modes/failure_mode_registry.jsonl` | present |
| failure-feedback registry | `artifacts/dopey/failure_feedback/failure_feedback_registry.jsonl` | present |
| feedback optimizer ledger | `artifacts/dopey/failure_feedback/feedback_optimizer.jsonl` | present |
| source registry | `artifacts/dopey/source_registry/data_inflow_registry.jsonl` | present |
| IV surface registry | `artifacts/dopey/iv_surface/iv_surface_registry.jsonl` | present |
| IV surface ledger | `artifacts/dopey/iv_surface/iv_surface_skew_bundle.jsonl` | present |
| macro event registry | `artifacts/dopey/macro_events/macro_event_registry.jsonl` | present |
| macro event ledger | `artifacts/dopey/macro_events/macro_event_bundle.jsonl` | present |
| ensemble registry | `artifacts/dopey/ensemble_allocator/ensemble_allocation_registry.jsonl` | present |
| ensemble replay ledger | `artifacts/dopey/ensemble_allocator/ensemble_replay.jsonl` | present |
| meta-governor registry | `artifacts/dopey/meta_governor/meta_governor_registry.jsonl` | present |
| meta-governor decisions | `artifacts/dopey/meta_governor/meta_governor_decisions.jsonl` | present |
| meta-governor proof ledger | `artifacts/dopey/meta_governor/meta_governor_proof.jsonl` | present |
| champion registry | `artifacts/dopey/champion_registry/champion_registry.jsonl` | present |

## Latest audit summary

- audit_harness_version: `dopey-offline-evidence-replay-audit-v1`
- verdict: `pass`
- mode: `RESEARCH`
- live_trading_enabled: `false`
- live_blocked: `true`
- artifacts_scanned: `20`
- records_scanned: `929`
- replay_cases_run: `6`
- hash_mismatches: `0`
- score_drift_findings: `0`
- schema_warnings: `0`
- consistency_errors: `0`
- safety_errors: `0`
- forbidden_live_decisions_active: `0`
- evidence_completeness: `1.0`
- top_next_proof_priority: `insufficient_walk_forward_consistency`
- recommended_next_build_target: `stronger_walk_forward_consistency_expansion`

## Replay / hash audit

- Verdict: `pass`.
- All strict single-record reproducibility hashes verified successfully:
  - ensemble allocation registry
  - meta-governor registry
  - meta-governor decisions
- Ensemble weight-invariants hold: accepted weights sum to ~1.0, recomputed allocation
  policy normalizes to ~1.0.
- No stored score drift detected.
- No schema drift detected after applying required-field aliases
  (`registry_version` / `registry_id`, `version` / `failure_mode_registry_version`).

## Cross-layer consistency audit

- Champion registry champion aligns with tournament/ensemble champion record.
- Mutation champion appears in mutation registry ranking.
- Meta-governor decisions reference strategies with proof profiles.
- No referenced strategy ID is missing from known genome/mutation/ensemble/champion records.
- No active forbidden live decision (`live_candidate`, `micro_live`, `adaptive_live`,
  `real_capital`, `broker_order`, `enable_live`, `live_allocate`, `funded_execution`)
  appears in any artifact.

## Safety-boundary drift audit

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- `PaperBroker` refuses `live_allowed=true` (`LiveTradingDisabledError`).
- Robinhood/Alpaca/Tradier stubs raise `LiveTradingDisabledError` on live intents.
- No hidden live promotion tier, broker credential path, network-required active source,
  scheduled run, or autonomous daemon detected.
- Original Blunder source integrity: **`BLUNDER_INTEGRITY_OK checked=78`**

## Evidence gap plan

| Gap | Severity | Message |
|---|---|---|
| high_overfit_family | warning | high overfit pressure in families blocks promotion (volatility_expansion) |
| insufficient_walk_forward_consistency | warning | non-directional families need stronger walk-forward consistency |
| macro_contradiction_pressure | warning | macro contradiction pressure affects all four families |
| weak_cross_family_evidence | warning | ensemble concentrates on a single family; cross-family evidence weak |
| deterministic_fixture_only_limitation | info | all evidence is deterministic fixture math, not live performance evidence |
| missing_source_backed_data | info | network/credential data sources remain deferred; only offline internal sources active |

## Next proof priorities

1. `insufficient_walk_forward_consistency` — non-directional families need stronger
   walk-forward consistency to escape starve pressure.
2. `high_overfit_family` — volatility expansion family still carries high overfit
   pressure and remains quarantined.
3. `macro_contradiction_pressure` — macro contradiction pressure affects all families,
   especially compression and short-duration.
4. `weak_cross_family_evidence` — ensemble allocator concentrates on directional
   convexity; broader cross-family evidence is required before diversification improves.

## Recommended next build target

`stronger_walk_forward_consistency_expansion` is the top next target because it directly
addresses the dominant missing-evidence priority flagged by the meta-governor and the
audit gap planner.

## Files added

- `dopey_audit/` package: `__init__.py`, `evidence_models.py`, `evidence_inventory.py`,
  `artifact_loader.py`, `replay_auditor.py`, `hash_auditor.py`, `score_replay.py`,
  `consistency_auditor.py`, `safety_auditor.py`, `evidence_gap_planner.py`,
  `audit_runner.py`, `run_offline_evidence_replay_audit.py`.
- `tests/test_offline_evidence_replay_audit.py` (37 new tests).
- `DOPEY_OFFLINE_EVIDENCE_REPLAY_AUDIT_REPORT.md`.
- `DOPEY_AUDIT_SCHEMA.md`.
- Audit artifacts under `artifacts/dopey/audit/`:
  - `evidence_inventory.jsonl`
  - `replay_audit.jsonl`
  - `consistency_audit.jsonl`
  - `safety_audit.jsonl`
  - `evidence_gap_plan.jsonl`
  - `evidence_replay_audit_proof.jsonl`
  - `evidence_replay_audit_summary.md`

## Files modified

- `pyproject.toml` — added `dopey_audit` to packages list.
- `dopey_audit/artifact_loader.py` — fixed required-field alias handling so multiple
  required fields are checked individually instead of treating all spec fields as aliases.
- `dopey_audit/replay_auditor.py` — schema audit now uses the same alias-aware missing-field
  helper as the inventory builder.
- `dopey_governor/meta_governor.py` — meta-governor decisions record now computes its own
  reproducibility hash rather than copying the registry hash.
- `DOPEY_VALIDATION_REPORT.md` — appended this pass.
- `DOPEY_CANON.md` — appended audit harness canon section.

## Known limitations

- Governance scores remain deterministic fixture math, not live performance evidence.
- The governor still concentrates trust on `directional_convexity` because the other families
  carry modest fixture scores, higher overfit, and higher failure pressure.
- Live-migration conditions remain documentation-only checklists for future human review;
  the audit harness does not create or apply any auto-live migration path.
- Some artifact types use multi-part or bundle-level reproducibility hashes that are not
  recomputed from the stored record alone; the audit treats these as informational and
  focuses strict hash replay on records that expose a canonical single-record hash.

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker refuses `live_allowed=true`; live broker stubs raise `LiveTradingDisabledError`.
- No broker connection, credentials, network market data, live trades, live promotion,
  autonomous scheduled run, or Blunder source modification.
- Blunder integrity: `BLUNDER_INTEGRITY_OK checked=78`.

## Update: stronger walk-forward consistency registry recognized

The audit harness now recognizes four additional artifact types produced by the stronger
walk-forward consistency runner:

- `walk_forward_consistency_registry` (registry) at
  `artifacts/dopey/walk_forward_consistency/consistency_registry.jsonl`. Required field
  `stronger_wf_consistency_version`. `reproducibility_hash` is strictly hashable (single
  record).
- `walk_forward_consistency_proof` (ledger) at
  `artifacts/dopey/walk_forward_consistency/consistency_proof.jsonl`.
- `family_consistency_profile` (registry) at
  `artifacts/dopey/walk_forward_consistency/family_consistency_profile.jsonl`.
- `champion_consistency` (registry) at
  `artifacts/dopey/champion_registry/champion_consistency.jsonl`. Required field
  `consistency_verdict` (alias-allowed: `champion_consistency_verdict`).

The gap planner now recognizes the categories `weak_stronger_consistency_evidence` and
`consistency_evidence_missing`. The audit's registry record includes a
`stronger_consistency_summary` block with windows_loaded, splits_built,
strategies_evaluated, families_evaluated, top_consistent_strategy, top_consistent_family,
holdout_failures, overfit_warnings, and strong_consistency_count. The audit's
recommended next build target may now also flip to `larger_regime_holdout_corpus` once
the stronger consistency registry reports holdout failures or overfit warnings.

## Update: regime/holdout corpus v2 registry recognized

The audit harness now recognizes four additional artifact types produced by the
regime/holdout corpus v2 runner:

- `regime_holdout_corpus_v2_registry` (registry) at
  `artifacts/dopey/regime_holdout_corpus_v2/corpus_registry.jsonl`. Required fields
  `corpus_v2_version` and `corpus_id`. `reproducibility_hash` is strictly hashable
  (single record).
- `regime_holdout_corpus_v2_replay` (registry) at
  `artifacts/dopey/regime_holdout_corpus_v2/corpus_v2_replay.jsonl`.
- `regime_holdout_corpus_v2_coverage` (registry) at
  `artifacts/dopey/regime_holdout_corpus_v2/corpus_coverage.jsonl`.
- `regime_holdout_corpus_v2_proof` (ledger) at
  `artifacts/dopey/regime_holdout_corpus_v2/corpus_v2_proof.jsonl`.

The gap planner now recognizes the categories `weak_regime_holdout_corpus_v2_evidence`
and `regime_holdout_corpus_v2_missing`. The audit's registry record includes a
`regime_holdout_v2_summary` block with total_windows, new_windows_added, splits_built,
strategies_evaluated, families_evaluated, top_consistent_strategy_v2,
top_consistent_family_v2, holdout_failures, overfit_warnings, and coverage_score.

## Update: fundamental registry / artifact recognition

The audit harness now recognizes three new artifact types:
undamental_registry, undamental_coverage, and undamental_ledger. The
fundamental registry is added to STRICT_HASH_TYPES so the audit can recompute its
canonical single-record hash. Two new gap categories,
weak_sector_peer_fundamental_evidence and sector_peer_fundamental_missing, are
recorded when the registry is missing or its coverage categories are below 0.50. The
audit still produces a erdict: pass result when the fundamental bundle is present
and the safety state is preserved.

## Update: reporting dashboard artifact recognition

The offline evidence replay audit now recognizes the tournament performance reporting dashboard artifacts:

- `reporting_dashboard_index`
- `strategy_report_cards`
- `family_report_cards`
- `scenario_report_cards`
- `performance_attribution`
- `reporting_bundle_proof`

The audit loader now handles single-object `.json` artifacts in addition to `.jsonl` registries. Strict reproducibility hash replay covers the dashboard index, strategy report cards, and family report cards. The consistency auditor verifies that reporting cards reference known strategy ids and remain paper-only/live-blocked.

Final reporting-aware audit result:

- `audit_status=ok`
- `verdict=pass`
- `artifacts_scanned=37`
- `records_scanned=2514`
- `replay_cases_run=13`
- `hash_mismatches=0`
- `schema_warnings=0`
- `consistency_errors=0`
- `safety_errors=0`
- `forbidden_live_decisions_active=0`
- `live_blocked=true`

The reporting dashboard does not alter safety posture. It is fixture-only evidence presentation and emits no live promotion, broker action, credential access, market-data request, or scheduled run.

## Update: artifact compaction/export verifier recognition

The audit harness now recognizes six export artifact types:

- `export_registry`
- `export_manifest`
- `export_verification`
- `export_safety_scan`
- `export_copy_proof`
- `export_compaction_summary`

Strict hash replay covers `export_manifest` and `export_copy_proof`. The consistency audit checks that the export manifest parses, keeps `live_blocked=true`, the export safety scan reports no active forbidden live decisions, the copy proof is verified or cleanly skipped, and the export registry bundle id matches the manifest bundle id.

Final export-aware audit result:

- `audit_status=ok`
- `verdict=pass`
- `artifacts_scanned=43`
- `records_scanned=2884`
- `replay_cases_run=19`
- `hash_mismatches=0`
- `schema_warnings=0`
- `consistency_errors=0`
- `safety_errors=0`
- `forbidden_live_decisions_active=0`
- latest export bundle: `dopey-export-handoff-shared-folder-15a10b368ab1`
- latest export profile: `handoff_shared_folder`
- latest export copy status: `verified`

The export verifier remains offline, fixture-only, paper-only, and live-blocked. It exports no credentials and creates no live execution authority.

## Update: export review artifact recognition

The audit harness now recognizes eight export review artifact types:

- `export_review_registry`
- `export_review_findings`
- `export_review_proof`
- `export_review_checklist`
- `export_review_executive_summary`
- `export_review_evidence_map`
- `export_review_priority_queue`
- `export_review_safety_summary`

Strict hash replay covers `export_review_registry`, `export_review_evidence_map`, and `export_review_checklist`. The consistency audit validates that the review registry references the source bundle id, the checklist includes research/live-blocked safety state, the evidence map marks exported-file references, review findings contain no safety errors, and the review proof references the source bundle id.

Final export-review-aware audit result:

- `audit_status=ok`
- `verdict=pass`
- `artifacts_scanned=51`
- `records_scanned=3176`
- `replay_cases_run=25`
- `hash_mismatches=0`
- `schema_warnings=0`
- `consistency_errors=0`
- `safety_errors=0`
- `forbidden_live_decisions_active=0`
- latest review id: `dopey-export-review-0194874ce083`
- latest review status: `ok`
- latest review source bundle: `dopey-export-handoff-shared-folder-15a10b368ab1`

The export review assistant remains offline, fixture-only, paper-only, static, and live-blocked. It creates no chat agent, server, scheduler, broker connection, credential path, or live execution authority.
