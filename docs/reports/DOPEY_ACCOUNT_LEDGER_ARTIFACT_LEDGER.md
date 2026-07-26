# DOPEY Account Ledger Artifact Ledger

Session date: 2026-07-03

All artifacts are offline, fixture-only, paper-only, and live-blocked.

| Artifact path | Artifact type | SHA256 | Record count | Proof layer | Safety state |
|---|---|---|---:|---|---|
| `artifacts/dopey/account_ledger/paper_account_ledger.json` | paper_account_ledger | `7A555CC69E6BF963A44AD6BC93DE7A084E3642265EC6E6523BA4BBFCF7F61EA6` | 1 | account lifecycle | live_blocked |
| `artifacts/dopey/account_ledger/day_trade_policy.json` | day_trade_policy | `3DA7EC3A6FE4C619DD205C3587FF6C74F830F535AC913466AE4000BDE9273628` | 1 | configurable policy | live_blocked |
| `artifacts/dopey/account_ledger/pdt_safe_policy.json` | pdt_safe_policy | `C7F66B473DA062397EC1518D6266AFE949DA88F2A648B599F612A2B1A2776A0D` | 1 | configurable PDT-safe facade | live_blocked |
| `artifacts/dopey/account_ledger/rotation_plan.json` | rotation_plan | `3A7FFA67197DC8268190032A8C420493F595744745D994613197C2952F54E67A` | 1 | rotation planner | live_blocked |
| `artifacts/dopey/account_ledger/rotation_planner_proof.jsonl` | rotation_planner_proof | `6F7D1E15717AB0B649F1E95BE21F35DCD439432514301657E526984ED78999AE` | 105 | rotation proof | live_blocked |
| `artifacts/dopey/account_ledger/day_trade_event_log.jsonl` | day_trade_event_log | `C02DD07A9D7543718B60C1C6C26CCF922F341A1C55581EF229BA58932DDE53B1` | 2 | no-day-trade evidence | live_blocked |
| `artifacts/dopey/account_ledger/zero_dte_account_lifecycle_proof.jsonl` | zero_dte_account_lifecycle_proof | `A4A5369F19C85C0EA2BDD93D79B7B63B7BA58EF4EA0754D148B7C66772E9A1D4` | 105 | 0DTE account lifecycle | live_blocked |
| `artifacts/dopey/account_ledger/paperbroker_account_ledger_proof.jsonl` | paperbroker_account_ledger_proof | `DB8708A0FCF0DBC120519CD8C2151E14F53D10A6EBFC21755BE3F0775483CE4A` | 105 | PaperBroker account ledger | live_blocked |
| `artifacts/dopey/validation/test_shard_plan.json` | test_shard_plan | `9A4F666F740704C1B234C65E3A53A237F61656E4A62E690A93F7DA53B85AF0F5` | 1 | validation stabilizer | no_pass_on_timeout |

## Export Visibility

These artifacts are selected by the export verifier for the shared-folder
handoff profile and reviewed by the export review assistant.

- bundle id: `dopey-export-handoff-shared-folder-53dcaade8c8a`
- shared export path: `Z:\dopey-export-handoff-shared-folder-53dcaade8c8a`
- active forbidden live decisions: `0`
- credential findings: `0`
- copy status: `verified`

## 0DTE Risk Feed Into Account Ledger

The account ledger now requires a dedicated 0DTE risk decision before recording
a 0DTE paper open. Accepted 0DTE ledger positions retain the risk decision,
max paper premium at risk, max paper contracts, and expiry handling plan in
position policy flags. Rejected 0DTE candidates remain outside the open-position
ledger and are recorded in the 0DTE risk blocked-candidate proof artifacts.
