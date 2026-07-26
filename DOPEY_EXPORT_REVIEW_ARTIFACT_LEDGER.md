# DOPEY Export Review Artifact Ledger

## Source Bundle

- Source bundle id: `dopey-export-handoff-shared-folder-15a10b368ab1`
- Source export path: `C:\Users\CH\dopey\artifacts\dopey\exports\dopey-export-handoff-shared-folder-15a10b368ab1`
- Shared export path: `Z:\dopey-export-handoff-shared-folder-15a10b368ab1`
- Review root: `artifacts/dopey/export_reviews/`
- Review folder: `artifacts/dopey/export_reviews/dopey-export-review-0194874ce083/`
- Safety note: static offline review artifacts only; no credentials, broker access, live trading, scheduler, server, or chat agent.

## Generated Artifacts

| Artifact | Type | Records | Bytes | SHA256 |
| --- | --- | ---: | ---: | --- |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_EXECUTIVE_SUMMARY.md` | executive_summary | 1 | 1703 | `5d86cd90635e5eff9152d88d23cd5c609b6042c9096c41033bcd6dc86824bd31` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_CHECKLIST.md` | checklist | 1 | 2618 | `bcbb4225b259e017a1a37980502bed8f3bca8b4edf8aed8284b935578abe1519` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_FINDINGS.jsonl` | findings | 9 | 4716 | `7e825ce04f56cfce96b95708acacca0730aa2ee8d6b7c62639f8543e56027a22` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_EVIDENCE_MAP.json` | evidence_map | 1 | 52087 | `1153de330d1402d8041a682edef64d31d285c456c6bb2966de87490cb7275aa5` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_PRIORITY_QUEUE.md` | priority_queue | 1 | 2724 | `fbc90618fd08041e11462adf0bdf28f21f99c1b763ffa46664e1c14f596960b3` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_SAFETY_SUMMARY.md` | safety_summary | 1 | 629 | `a2c7617bbd61fa8a72de63e91c012ea13f6a7fa396b2e1ea4514f94cc471af4a` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_NEXT_STEPS.md` | next_steps | 1 | 350 | `2f9eafa4fee169de33f5b5eb29bcd6140b8447d4f1537075de84513c83d883c9` |
| `artifacts/dopey/export_reviews/EXPORT_REVIEW_DEPENDENCY_GRAPH.md` | dependency_graph | 1 | 597 | `24e922f44b57aec001a13dfe1a1d8d4962b1db5d043107cbcd9f60f2747b9ae3` |
| `artifacts/dopey/export_reviews/export_review_registry.jsonl` | review_registry | 14 | 38556 | `afeedb9651cb368e0a63d492c925fce2a3d71c87b22c34d173f4a73c886e859a` |
| `artifacts/dopey/export_reviews/export_review_findings.jsonl` | findings_registry | 9 | 4716 | `7e825ce04f56cfce96b95708acacca0730aa2ee8d6b7c62639f8543e56027a22` |
| `artifacts/dopey/export_reviews/export_review_proof.jsonl` | proof_ledger | 14 | 147658 | `0afa3475b70225df29a39594307f42734f37100891b48785ffdc7ac70e723969` |

## Review Summary

- Review status: `ok`
- Manifest status: `pass`
- Copy proof status: `verified`
- Hash status: `pass`
- Safety status: `pass`
- Credential status: `pass`
- Active forbidden live decisions: `0`
- Safety errors: `0`
- Warnings: `6`
- Findings count: `9`
- Review id: `dopey-export-review-0194874ce083`
- Review artifacts written: `16`
- Audit verdict: `pass`
- Audit records scanned: `3176`

## Evidence Map Summary

- Exported files mapped: `69`
- Copied files mapped: `70`
- Missing references: `0`
- Report links: `2`
- Dashboard links: `1`
- Audit specs mapped: `51`

## Reproduction Command

```text
python -m dopey_export_review.run_export_bundle_review_assistant
```

## Audit Command

```text
python -m dopey_audit.run_offline_evidence_replay_audit
```

## Active Policy Export Artifact Update

Session date: 2026-07-03

The export selector now includes active policy reports and proof artifacts:

- `active_policy_integration_map`
- `active_policy_order_validation_proof`
- `active_policy_position_lifecycle_proof`
- `active_policy_paperbroker_proof`
- `zero_dte_lifecycle_proof`
- `no_day_trade_guard_proof`
- `active_policy_audit`

Latest export verifier smoke:

- bundle id: `dopey-export-handoff-shared-folder-586b67ff474a`
- artifacts_selected: `77`
- artifacts_exported: `77`
- files_verified: `78`
- copy_status: `verified`
- credential_findings: `0`
- active_forbidden_live_decisions: `0`
- shared_export_path: `Z:\dopey-export-handoff-shared-folder-586b67ff474a`
