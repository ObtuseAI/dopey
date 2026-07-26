# DOPEY Export Artifact Ledger

## Current bundle

- Bundle id: `dopey-export-handoff-shared-folder-15a10b368ab1`
- Profile: `handoff_shared_folder`
- Local export: `artifacts/dopey/exports/dopey-export-handoff-shared-folder-15a10b368ab1`
- Shared export: `Z:\dopey-export-handoff-shared-folder-15a10b368ab1`
- Manifest registry: `artifacts/dopey/exports/export_manifest.jsonl`
- Copy proof registry: `artifacts/dopey/exports/export_copy_proof.jsonl`
- Export proof ledger: `artifacts/dopey/exports/export_verifier_proof.jsonl`
- Artifact count: `69`
- Total manifest artifact bytes: `495066`
- Verified bundle bytes including manifest: `530830`
- Bundle SHA256: `3b0f0f5730610da4148961afb7d342535ff07c2f8490f56739a691c6135b5c18`

The full per-artifact SHA256 ledger is the latest record in `artifacts/dopey/exports/export_manifest.jsonl`.

## Exported artifact classes

- Required reports: validation, canon, risk discipline, broker boundaries.
- Optional review reports: reporting dashboard, audit, meta-governor, ensemble, fundamental, corpus, consistency, macro, IV, failure, mutation, Greeks, slippage, tournament, walk-forward.
- Raw small artifacts: reporting dashboard metadata, audit summary, walk-forward ledger, coverage records, paper pipeline proof, Blunder integrity status.
- Compacted large artifacts: large JSONL proof/registry ledgers represented by deterministic summaries.

## Key raw exported artifacts

| Artifact id | Relative export path | Bytes | SHA256 prefix |
| --- | --- | ---: | --- |
| `report-dopey_validation_report` | `reports/DOPEY_VALIDATION_REPORT.md` | 84182 | `294d3351d96e6268` |
| `report-dopey_canon` | `reports/DOPEY_CANON.md` | 35957 | `1997576fc78ba34a` |
| `reporting_dashboard_index` | `artifacts/reporting/dashboard_index.json` | 12683 | `036951e1a3dd9f80` |
| `reporting_dashboard_markdown` | `artifacts/reporting/dashboard_index.md` | 2647 | `3e7af67d5e8a81c5` |
| `family_report_cards` | `artifacts/reporting/family_report_cards.jsonl` | 6441 | `454c725141ce507f` |
| `regime_report_cards` | `artifacts/reporting/regime_report_cards.jsonl` | 23802 | `078405034a48a8e8` |
| `reporting_bundle_summary` | `artifacts/reporting/reporting_bundle_summary.json` | 2461 | `c070990b1e5ebfe3` |
| `static_dashboard` | `artifacts/reporting/static_dashboard.html` | 3725 | `3e07b92734f7b1b0` |
| `audit_summary` | `artifacts/audit/evidence_replay_audit_summary.md` | 6171 | `2d47ac7ce9ef213b` |
| `blunder_integrity_status` | `integrity/blunder_integrity_status.json` | 466 | `f96e4dcd25c2d581` |

## Compacted artifacts

The current export wrote `36` compacted summaries. Each summary preserves the original source hash and records first/last record hashes.

| Source artifact | Source bytes | Summary bytes | Source SHA prefix | Summary SHA prefix |
| --- | ---: | ---: | --- | --- |
| `strategy_report_cards` | 213205 | 3718 | `8cbbf18904ca9df4` | `2f3eb199782039fa` |
| `scenario_report_cards` | 58192 | 866 | `aa7c84568cc574e7` | `a55acf3e81f1fb70` |
| `performance_attribution` | 41273 | 3573 | `e876f6ed6c23495b` | `4413a4da2befb340` |
| `reporting_bundle_proof` | 87528 | 1177 | `afb639515d9232ce` | `e5be54ed7f014a0d` |
| `audit_inventory` | 65439999 | 958 | `9c20e40f52519968` | `2c924bb1df3102c2` |
| `audit_replay` | 423591 | 1000 | `d7e33761a123a9df` | `09ff067302e37e56` |
| `audit_consistency` | 236695 | 954 | `0ea75e08059d45cf` | `cce1a8738b2a1c1b` |
| `audit_safety` | 49290 | 840 | `fc9ea9b679007507` | `dff01c1f6a922cbc` |
| `audit_gap_plan` | 637066 | 904 | `499c2fffedd386e9` | `a9a7abb0f8c0fd4b` |

The complete compacted artifact list is in `artifacts/dopey/exports/export_compaction_summary.jsonl`.

## Skipped artifacts

- `optional_operator_export_notes` skipped because `artifacts/dopey/exports/operator_export_notes.json` is optional and absent.
- Large raw JSONL ledgers that were compacted are intentionally not copied raw into the portable handoff bundle.
- `.env`, `.git`, caches, virtual environments, `__pycache__`, build outputs, previous export bundles, and original Blunder source trees are excluded by rule.

## Verification

- Local verification status: `verified`
- Shared copy status: `verified`
- Files expected: `70`
- Files copied: `70`
- Files verified: `70`
- Bytes expected: `530830`
- Bytes verified: `530830`
- Hash mismatches: `0`
- Missing files: `0`
- Extra files: `0`

## Safety findings

- Safety findings: `0`
- Active forbidden live decisions: `0`
- Credential findings: `0`
- Env file findings: `0`
- Live blocked: `true`
