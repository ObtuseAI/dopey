# DOPEY Artifact Compaction Export Verifier Report

## Purpose

`DOPEY_ARTIFACT_COMPACTION_EXPORT_VERIFIER_V1` packages DOPEY proof, report, dashboard, registry, audit, and safety artifacts into deterministic portable handoff bundles. It is an offline artifact discipline layer, not deployment, not a live dashboard, not broker integration, and not performance evidence.

## Export profiles

- `minimal_proof`
- `reporting_dashboard`
- `full_offline_evidence`
- `handoff_shared_folder`
- `audit_only`

The default profile is `handoff_shared_folder`.

## Implemented modules

- `dopey_export/export_models.py`
- `dopey_export/artifact_selector.py`
- `dopey_export/export_manifest.py`
- `dopey_export/artifact_compactor.py`
- `dopey_export/export_safety_scanner.py`
- `dopey_export/copy_verifier.py`
- `dopey_export/export_verifier.py`
- `dopey_export/run_artifact_compaction_export_verifier.py`

## Artifact selection rules

The selector includes required safety and review documents, latest reporting dashboard artifacts, audit summaries and registries, meta-governor records, ensemble records, tournament/champion records, walk-forward/consistency/corpus-v2 records, macro/IV/fundamental registries, failure/mutation/feedback records, paper proof records, and a generated Blunder integrity status reference.

The selector excludes `.env`, credentials, `.git`, caches, virtual environments, `__pycache__`, build outputs, previous export bundles, and original Blunder source trees. Original Blunder source is not exported; only a hash status reference is included.

## Compaction approach

Oversized JSONL ledgers are summarized into deterministic `jsonl_ledger_summary_v1` files under `artifacts/dopey/exports/compacted/<bundle_id>/`. Each summary records source hash, record count, first and last record hashes, schema keys, model versions, strategy ids, safety fields, forbidden-live decision count, and top-level metrics. Source artifacts are not modified.

The final default handoff exported compacted summaries for `36` large JSONL ledgers and preserved smaller reports/artifacts raw.

## Safety scanner

The export scanner detects active forbidden live decisions, credential/API-key-like strings, environment dumps, `.env` export attempts, and active live-order terms. Documentation that lists forbidden terms as blocked is allowed. If active forbidden content appears, export verification fails and no verified handoff bundle is produced.

Final scan:

- `scan_status=pass`
- `artifacts_scanned=69`
- `active_forbidden_live_decisions=0`
- `credential_findings=0`
- `env_file_findings=0`
- `verification_blocked=false`

## Manifest format

The manifest records bundle id, profile, artifact count, required/optional counts, total size, bundle hash, per-artifact metadata, safety state, and reproducibility hash. Full manifest registry:

`artifacts/dopey/exports/export_manifest.jsonl`

Latest manifest:

- `bundle_id=dopey-export-handoff-shared-folder-15a10b368ab1`
- `profile=handoff_shared_folder`
- `artifact_count=69`
- `required_artifacts_present=15`
- `optional_artifacts_present=54`
- `total_size_bytes=495066`
- `bundle_sha256=3b0f0f5730610da4148961afb7d342535ff07c2f8490f56739a691c6135b5c18`
- `reproducibility_hash=c08db17a62917f401b425dbea6f195ed935e9936f6b0871ef286ec959e5116e1`

## Copy verification

The verifier builds the local bundle, writes `EXPORT_MANIFEST.json`, verifies local file count/bytes/hashes, copies to the first available shared target, then verifies the copied files by hash.

Final copy proof:

- `source_dir=C:\Users\CH\dopey\artifacts\dopey\exports\dopey-export-handoff-shared-folder-15a10b368ab1`
- `target_dir=Z:\dopey-export-handoff-shared-folder-15a10b368ab1`
- `files_expected=70`
- `files_copied=70`
- `files_verified=70`
- `bytes_expected=530830`
- `bytes_verified=530830`
- `hash_mismatches=[]`
- `missing_files=[]`
- `extra_files=[]`
- `verification_status=verified`

## Audit integration

The offline evidence replay audit now recognizes:

- `export_registry`
- `export_manifest`
- `export_verification`
- `export_safety_scan`
- `export_copy_proof`
- `export_compaction_summary`

Strict hash replay covers `export_manifest` and `export_copy_proof`. The consistency audit verifies the manifest live-blocked state, safety scan status, copy proof status, and registry/manifest bundle id link.

Final export-aware audit:

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

## Shared-folder status

Shared copy succeeded and verified at:

`Z:\dopey-export-handoff-shared-folder-15a10b368ab1`

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- `live_blocked=true`
- No broker connection
- No credentials
- No live market data
- No live orders
- No scheduler
- No live promotion path
- PaperBroker still rejects `live_allowed=true`
- Robinhood/Alpaca/Tradier adapters still raise `LiveTradingDisabledError`
- Blunder integrity: `BLUNDER_INTEGRITY_OK checked=78 mismatches=0`

## Limitations

- Export bundles are deterministic handoff packages, not runtime deployments.
- Compacted summaries are review aids; full source hashes remain the integrity anchors.
- Shared-folder availability is optional. If unavailable, local export still completes and reports copy skipped.
- Exports are not live performance evidence and carry no live execution authority.

## Command

```text
python -m dopey_export.run_artifact_compaction_export_verifier
```

## Next recommended build target

`export_bundle_review_assistant_artifacts`

## Review Assistant Integration

`DOPEY_EXPORT_BUNDLE_REVIEW_ASSISTANT_ARTIFACTS_V1` now consumes the export manifest, export safety scan, copy proof, export registry, dashboard artifacts, audit artifacts, and reporting cards to generate deterministic static review artifacts.

The review assistant does not modify the exported bundle and does not create a chat agent, server, scheduler, deployment path, broker path, credential path, or live execution path. It writes review packets under `artifacts/dopey/export_reviews/` and links back to the source bundle id `dopey-export-handoff-shared-folder-15a10b368ab1`.

Current review status:

- `review_status=ok`
- `review_id=dopey-export-review-0194874ce083`
- `manifest_status=pass`
- `copy_proof_status=verified`
- `hash_status=pass`
- `safety_status=pass`
- `credential_status=pass`
- `active_forbidden_live_decisions=0`
- `safety_errors=0`
- `findings_count=9`
- `warnings=6`
- `review_artifacts_written=16`

The review packet uses the export manifest and copy proof as its source-of-truth inputs, then produces checklist, executive summary, findings, evidence map, priority queue, safety summary, next steps, and dependency graph artifacts for offline human review.
