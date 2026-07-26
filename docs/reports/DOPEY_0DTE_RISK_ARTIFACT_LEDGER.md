# DOPEY 0DTE Risk Artifact Ledger

This ledger tracks the dedicated offline 0DTE special lifecycle risk model
artifacts. It is static, fixture-only, paper-only, and live-blocked.

| Artifact path | Artifact type | Hash | Records | Threshold version | Proof layer | Safety state |
|---|---|---:|---:|---|---|---|
| `artifacts/dopey/zero_dte_risk/zero_dte_risk_thresholds.json` | zero_dte_risk_thresholds | `6D732616B51EB1F2B95CC7A9E4C5C1AD0FEFCEFC1C82C880FE6699AB85C4D96A` | 1 | dopey-zero-dte-risk-thresholds-v1 | thresholds | live_blocked |
| `artifacts/dopey/zero_dte_risk/zero_dte_risk_decisions.jsonl` | zero_dte_risk_decisions | `D282B1F6D64038B615C2F92EA6635C884CB9483CE3575B26D3883455D257ED9B` | 24 | dopey-zero-dte-risk-thresholds-v1 | decisions | live_blocked |
| `artifacts/dopey/zero_dte_risk/zero_dte_risk_summary.json` | zero_dte_risk_summary | `6209E06C6CE0C449C082155ECF40976E2FD951630D66977C5B4BE85C601DDD8B` | 1 | dopey-zero-dte-risk-thresholds-v1 | summary | live_blocked |
| `artifacts/dopey/zero_dte_risk/zero_dte_risk_proof.jsonl` | zero_dte_risk_proof | `C7848F93DD8DAAF7011577BBFF921E45A3DD721EF6B0B4AF888264A42B5798A6` | 24 | dopey-zero-dte-risk-thresholds-v1 | proof | live_blocked |
| `artifacts/dopey/zero_dte_risk/zero_dte_blocked_candidates.jsonl` | zero_dte_blocked_candidates | `A39436D550801C7057CA397A8039575A3153D3F15C10723A9AD3E72C58ED02BD` | 16 | dopey-zero-dte-risk-thresholds-v1 | blocked candidates | live_blocked |
| `artifacts/dopey/zero_dte_risk/zero_dte_approved_candidates.jsonl` | zero_dte_approved_candidates | `5468E3D53F37FDC840D6B5AF8031F7F17F4488639A9D3AF41774FEA5BB1BBE79` | 6 | dopey-zero-dte-risk-thresholds-v1 | approved and throttled candidates | live_blocked |

## Current Summary

- decisions: `24`
- approved for paper open: `5`
- approved with throttle: `1`
- blocked: `16`
- expiry managed only: `1`
- non-0DTE alternative recommendations: `1`
- all fixture expectations matched: `true`
- no real market data: `true`
- no broker: `true`
- paper_only: `true`
- live_blocked: `true`
