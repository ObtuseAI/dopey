# DOPEY Active Policy Artifact Ledger

Session date: 2026-07-03

All artifacts are offline, fixture-only, paper-only, and live-blocked.

| Artifact path | Artifact type | SHA256 | Record count | Policy layer | Safety status |
|---|---|---|---:|---|---|
| `artifacts/dopey/governor/active_policy_integration_map.json` | active_policy_integration_map | `F8D0509C13C804C010274EA03F1B0C8AB83FBA005576387DC72A9E4907BB96DD` | 1 | integration map | live_blocked |
| `artifacts/dopey/governor/active_policy_order_validation_proof.jsonl` | active_policy_order_validation_proof | `8E70357A225D269A4D8926D22CF22A0D27BD156D47C990401910B309218A49AA` | 141 | order intent validator | live_blocked |
| `artifacts/dopey/governor/active_policy_position_lifecycle_proof.jsonl` | active_policy_position_lifecycle_proof | `55CBE48A0CA1F9847AC9428DC1F415B6E660CA275FC1BD89DEC974F24BDAADFB` | 141 | position lifecycle | live_blocked |
| `artifacts/dopey/governor/active_policy_paperbroker_proof.jsonl` | active_policy_paperbroker_proof | `AD068C10BCB611B273831F56F7331CEBF284B337BA0264A68A15633BE81A71B2` | 141 | PaperBroker | live_blocked |
| `artifacts/dopey/governor/zero_dte_lifecycle_proof.jsonl` | zero_dte_lifecycle_proof | `739E8B68E510D39BAD1EBAA1E2E2C34152C0969743B8FDC2688D76FED3601E83` | 141 | 0DTE lifecycle | live_blocked |
| `artifacts/dopey/governor/no_day_trade_guard_proof.jsonl` | no_day_trade_guard_proof | `839EC52083AF6DCB07C02F27E3F968217525E15AAB641D35F0E81979A1160FE6` | 141 | no-day-trade guard | live_blocked |
| `artifacts/dopey/audit/active_policy_audit.jsonl` | active_policy_audit | `5B4B4A7C8D945275A0172D27E3556626700FC913E50C2A81422A21DA1CBC9C1A` | 159 | audit | live_blocked |
| `artifacts/dopey/validation/full_suite_stabilizer_summary.json` | full_suite_stabilizer_summary | `0C209FB60195A1EAEA5FB7B5636E91555147ED929E2719BB09D66E88EE0002B8` | 1 | validation stabilizer | no_pass_on_timeout |
| `artifacts/dopey/validation/text_encoding_guard_report.json` | text_encoding_guard_report | `4F35CCB2A721AD010DBDFC72426F68D2E4B8684BF994F4CD026EEB9FD086537C` | 1 | encoding guard | non_mutating |

## Report Paths

- `ACTIVE_POLICY_INTEGRATION_MAP.md`
- `DOPEY_ACTIVE_TRADING_POLICY_INTEGRATION_REPORT.md`
- `DOPEY_ACTIVE_POLICY_ARTIFACT_LEDGER.md`
- `DOPEY_FULL_VALIDATION_STABILIZER_REPORT.md`
- `DOPEY_TEXT_ENCODING_GUARD_REPORT.md`

## Export Visibility

The export verifier selected active policy artifacts in the latest handoff
bundle:

- bundle id: `dopey-export-handoff-shared-folder-53dcaade8c8a`
- shared export path: `Z:\dopey-export-handoff-shared-folder-53dcaade8c8a`
- active forbidden live decisions: `0`
- credential findings: `0`
- copy status: `verified`

## 0DTE Risk Model Artifacts

The active policy proof stack now includes the dedicated 0DTE special lifecycle
risk model artifact family:

- `artifacts/dopey/zero_dte_risk/zero_dte_risk_thresholds.json`
- `artifacts/dopey/zero_dte_risk/zero_dte_risk_decisions.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_risk_summary.json`
- `artifacts/dopey/zero_dte_risk/zero_dte_risk_proof.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_blocked_candidates.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_approved_candidates.jsonl`

These artifacts remain fixture-only, paper-only, live-blocked, and broker-free.
