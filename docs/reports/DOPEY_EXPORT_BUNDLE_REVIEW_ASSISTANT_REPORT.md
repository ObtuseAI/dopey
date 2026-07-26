# DOPEY Export Bundle Review Assistant Report

## Purpose

`DOPEY_EXPORT_BUNDLE_REVIEW_ASSISTANT_ARTIFACTS_V1` creates deterministic static review artifacts for verified DOPEY export bundles. It is an offline handoff-review layer, not a chat agent, not a live dashboard, not a deployment system, and not broker integration.

## Review Assistant Artifact Model

The review layer adds `ExportReviewBundle`, `ExportReviewChecklist`, `ExportReviewFinding`, `ExportReviewPriority`, `ExportReviewEvidenceMap`, `ExportReviewDecision`, and `ExportReviewRunResult`.

All models serialize through deterministic dictionaries and use reproducibility hashes compatible with the existing export/audit hash discipline.

## Checklist Generation

The checklist is written to `artifacts/dopey/export_reviews/EXPORT_REVIEW_CHECKLIST.md`.

It includes bundle identity, completeness, safety, evidence quality, strategy/family summary, and reviewer priorities. The checklist explicitly records `mode=RESEARCH`, `live_trading_enabled=false`, `funded_broker_connections_enabled=false`, `allow_unofficial_robinhood_api=false`, and `live_blocked=true`.

## Executive Review Packet

Latest root copies are written under `artifacts/dopey/export_reviews/`, and the review-specific packet is copied under `artifacts/dopey/export_reviews/dopey-export-review-0194874ce083/`.

Generated artifacts:

- `EXPORT_REVIEW_EXECUTIVE_SUMMARY.md`
- `EXPORT_REVIEW_CHECKLIST.md`
- `EXPORT_REVIEW_FINDINGS.jsonl`
- `EXPORT_REVIEW_EVIDENCE_MAP.json`
- `EXPORT_REVIEW_PRIORITY_QUEUE.md`
- `EXPORT_REVIEW_SAFETY_SUMMARY.md`
- `EXPORT_REVIEW_NEXT_STEPS.md`
- `EXPORT_REVIEW_DEPENDENCY_GRAPH.md`

## Evidence Map

The evidence map links reports, dashboard artifacts, top strategy, top family, export manifest entries, copy proof target files, and audit artifact specs.

Current evidence map:

- exported files mapped: `69`
- copied files mapped: `70`
- missing references: `0`
- report links: `2`
- dashboard links: `1`
- audit specs mapped: `51`

## Priority Queue

The clean-state queue directs reviewers to inspect manifest, copy proof, audit summary, dashboard index, strategy/family cards, evidence gaps, and next build target.

## Safety Summary

The safety summary states offline only, fixture only, paper only, no broker connection, no credentials, no live trades, no live promotion, no scheduler, and no live path enabled.

## Audit Integration

The offline evidence replay audit recognizes `export_review_registry`, `export_review_findings`, `export_review_proof`, `export_review_checklist`, `export_review_executive_summary`, `export_review_evidence_map`, `export_review_priority_queue`, and `export_review_safety_summary`.

Strict hash replay covers `export_review_registry`, `export_review_evidence_map`, and `export_review_checklist`.

## Current Run

- Review status: `ok`
- Review id: `dopey-export-review-0194874ce083`
- Source bundle id: `dopey-export-handoff-shared-folder-15a10b368ab1`
- Source export path: `C:\Users\CH\dopey\artifacts\dopey\exports\dopey-export-handoff-shared-folder-15a10b368ab1`
- Shared export path: `Z:\dopey-export-handoff-shared-folder-15a10b368ab1`
- Manifest status: `pass`
- Copy proof status: `verified`
- Hash status: `pass`
- Safety status: `pass`
- Credential status: `pass`
- Active forbidden live decisions: `0`
- Findings count: `9`
- Safety errors: `0`
- Warnings: `6`
- Review artifacts written: `16`
- Audit verdict after review integration: `pass`
- Audit artifacts scanned: `51`
- Audit records scanned: `3176`

## Validation

- `python -m pytest` -> `585 passed`
- `python -m pytest tests/test_export_bundle_review_assistant.py -q` -> `42 passed`
- `python -m dopey_export_review.run_export_bundle_review_assistant` -> `review_status=ok`, `review_id=dopey-export-review-0194874ce083`
- `python -m dopey_export.run_artifact_compaction_export_verifier` -> `export_status=ok`, `copy_status=verified`, `hash_mismatches=0`
- `python -m dopey_reporting.run_tournament_performance_reporting_bundle` -> `reporting_bundle_status=ok`
- `python -m dopey_audit.run_offline_evidence_replay_audit` -> `verdict=pass`, `hash_mismatches=0`, `consistency_errors=0`, `safety_errors=0`

## Limitations

- The review assistant generates static files only.
- It does not compare multiple historical exports yet.
- It is not a chat loop, web server, scheduler, live dashboard, deployment artifact, or broker adapter.
- It does not create live performance evidence.

## Safety State

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- `live_blocked=true`
- PaperBroker rejects `live_allowed=true`
- Robinhood, Alpaca, and Tradier adapters raise `LiveTradingDisabledError`

## Next Recommended Build Target

`export_review_comparison_diff_artifacts`

## Active Policy Export Review Integration Update

Session date: 2026-07-03

Export review artifacts now surface active policy state in the executive and safety summaries. The review packet states the active policy is long-call/long-put-only, has a no-day-trade guard, treats 0DTE as a special lifecycle, and remains paper-only/live-blocked.

Latest smoke:

- `python -m dopey_export_review.run_export_bundle_review_assistant` passed.
- review_status: `ok`
- safety_status: `pass`
- credential_status: `pass`
- safety_errors: `0`
- active_forbidden_live_decisions: `0`
