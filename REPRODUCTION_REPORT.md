# Reproduction Report

Current scope: Ascendancy v1 engineering reproduction. No strategy candidate,
sealed result, independent replication result, qualifying signed forward settlement,
or performance result exists to reproduce.

Base code reference: `ccf460eb514fa19ed1769f3c8cfa70bc6c8754ed` plus the current uncommitted working tree  
Environment: `dopey-options-paper-v1`  
Source-data manifest hash: `6ddc39e58e69c0b8a411ffee2c36d8a4cbd5d05f98340bee997ddbdf5572bad3`  
Evaluator version: `sealed-v1`, `not_configured`

External trust state:

- `PROMOTION_AUTHORITY_TRUST.json`: `not_configured`
- `SEALED_EVALUATOR_TRUST.json`: `not_configured`
- `FORWARD_EVIDENCE_TRUST.json`: `not_configured`
- `DYNAMIC_ANCHOR_TRUST.json`: `not_configured`
- External deployment trust root: not supplied; it must be operator-custodied outside
  the repository

## Clean-install packaging check

Run from `C:\Users\CH\dopey-options-lab` with Python 3.11 or newer:

```powershell
py -3.11 -m venv .repro-venv
.\.repro-venv\Scripts\python.exe -m pip install --upgrade pip
.\.repro-venv\Scripts\python.exe -m pip install ".[dev]"
$repo = (Get-Location).Path
Push-Location $env:TEMP
& "$repo\.repro-venv\Scripts\python.exe" -c "import dopey, sealed_evaluator_client, verifier"
Pop-Location
```

Package discovery explicitly includes only `dopey`, `dopey.ascendancy*`,
`dopey.constitution*`, `dopey.settlement*`, `dopey.truth*`,
`sealed_evaluator_client*`, and `verifier*`. It does not include broad `dopey*`, legacy
execution, governor, or broker-readiness namespaces. Source-tree live-order gates and
broker adapters permanently deny live operation; no configuration can turn an Ascendancy
artifact into a live order. Successful clean-environment installation and out-of-tree
import confirm distribution coverage only. They do not establish external trust, market
evidence, independent replication, sealed evaluation, calibration, profitability, or
readiness.

## Local engineering checks

```powershell
.\.repro-venv\Scripts\python.exe -m ruff check dopey\ascendancy verifier sealed_evaluator_client tests\test_dopey_ascendancy_v1.py tests\test_dopey_quote_ticket_trust.py tests\test_dopey_promotion_trust.py tests\test_dopey_protection_boundaries.py tests\test_dopey_sealed_signatures.py tests\test_dopey_forward_signatures.py
.\.repro-venv\Scripts\python.exe -m pytest -q tests\test_dopey_ascendancy_v1.py tests\test_dopey_quote_ticket_trust.py tests\test_dopey_promotion_trust.py tests\test_dopey_protection_boundaries.py tests\test_dopey_sealed_signatures.py tests\test_dopey_forward_signatures.py
.\.repro-venv\Scripts\python.exe -m verifier.audit --repository-root C:\Users\CH\dopey-options-lab --source-manifest C:\Users\CH\dopey\dopey_data\real\manifests\options_data_manifest.json
```

The local audit is designed to verify the environment freeze, the protected initial
200-symbol watch universe (199 options-mechanics symbols plus context-only `VIX`),
protected-source
enumeration, source-data identity, registry and ledger consistency, one-shot budget
semantics, canonical dynamic-state identity, and any configured signed dynamic anchor.
Prospective decisions require separately sourced point-in-time membership, captured before
and effective at the decision under the exact schema and capped at 200 symbols. With the
current default trust files, the audit must report the repository anchor as not configured
and certification as ineligible. Local hashes and writers are same-environment consistency
controls, not OS/process isolation or external key custody.

After independent operators configure all four repository trust files and issue a signed
dynamic-anchor v2 receipt, they must create `DOPEY_DEPLOYMENT_TRUST_ROOT.json` outside the
repository with `verifier.external_root.build_external_trust_root_contract`. The contract
pins the exact `PROTECTED_MANIFEST.json` SHA-256, the four repository trust-file hashes,
all five pairwise-independent Ed25519 signer identities and keys, the accepted anchor
and parent, and the minimum accepted sequence. The external audit is then explicit:

```powershell
.\.repro-venv\Scripts\python.exe -m verifier.audit --repository-root C:\Users\CH\dopey-options-lab --source-manifest C:\Users\CH\dopey\dopey_data\real\manifests\options_data_manifest.json --external-trust-root C:\operator-custody\DOPEY_DEPLOYMENT_TRUST_ROOT.json
```

The equivalent Python APIs are
`verifier.audit.audit_dynamic_state_with_external_root` and
`verifier.audit.run_ascendancy_audit_with_external_root`. Omitting the external-root
argument intentionally leaves certification false even when the in-repository receipt is
valid. A trust-root path inside the repository is rejected.

The reproduced forward protocol must also preserve the implemented scientific controls:
local tickets and fill observations remain unverified and profitability-ineligible; a
separate signed forward record must attest their exact input and artifact hashes without
rewriting them. Every qualifying forward options decision has exactly one filled-or-missed
execution observation, abstentions have none, and
settlements bind the observation. Candidate gates require 11 exact negative controls and
all 70 required stress scenarios. L5 compares complete-cost paper-bankroll utility with the
required candidate-mode-specific matched baselines and uses market-session-clustered utility
and Brier bounds. These mechanics remain L0 until qualifying external evidence exists.

Completion still requires external operators and services to provision distinct
promotion, evaluator, recorder, outcome-source, and policy-required anchor keys;
qualifying point-in-time market and outcome evidence; and an independently controlled
clean-room rebuild of a frozen finalist. None exists today, so the evidence level
remains L0 and `not_action_ready`.
