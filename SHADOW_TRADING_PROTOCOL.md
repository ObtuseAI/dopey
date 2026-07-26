# Prospective Shadow Protocol

Status: protocol only; evidence level L0. No candidate and no qualifying signed
forward decision or settlement exists. L5 is paper shadow only and never authorizes
live capital.

Before collection, freeze the candidate, environment, data identity, cost model,
policy, and evaluator version. Earlier promotion stages must be satisfied through
canonical evidence and signed promotion-authority receipts. The sealed result must
carry a valid pinned-evaluator signature over the exact verdict and evaluator issue
time. The current certification policy requires a repository dynamic-state anchor v2
that binds the dynamic state, protected manifest, monotonic sequence, and parent, plus
an explicitly supplied `DOPEY_DEPLOYMENT_TRUST_ROOT.json` held outside the repository.
That operator-custodied root must pin the exact manifest, all four repository trust
files, and five pairwise-independent signer identities and keys: dynamic anchor,
promotion authority, sealed evaluator, forward recorder, and outcome source.

The protected initial membership contract contains 200 watch symbols, 199
options-mechanics symbols, and context-only `VIX`. It is a mechanics snapshot, not a
prospective membership witness. Every qualifying forward decision must bind an
independently sourced point-in-time membership artifact that was captured before and
is effective at the decision, conforms to the exact dynamic schema, and contains at
most 200 sorted, unique symbols.

Append only through the root-scoped canonical
`shadow_trading/FORWARD_EVIDENCE.jsonl` writer. A local ticket or fill observation is
always unverified and profitability-ineligible; it cannot self-certify. The forward
recorder must independently attest the exact point-in-time input and subject-artifact
hashes. Every decision, every options execution observation, and every settlement must
include an Ed25519 recorder receipt that binds the environment, receipt purpose,
candidate, frozen specification, record identity, subject-artifact hash, issue time,
and signer identity/version. Every qualifying forward options decision must have exactly one immutable
execution observation with status `filled` or `missed`; an abstention decision must
have none. Each settlement must bind that observation and must additionally bind its
independently sourced outcome with an Ed25519 outcome-source receipt using the same
exact field contract. The recorder and outcome source must use distinct signer
identities and distinct pinned keys.

Record at least 100 immutable decisions and 100 mature settlements across at least 20
market sessions. Every decision embeds content-addressed prediction and ticket-or-
abstention artifacts. Filled and missed observations both remain in the ledger; a
missed fill contributes zero candidate net utility rather than disappearing. Every
settlement embeds outcome, grade, matched-baseline utilities, complete-cost identity,
and source-evidence artifacts and must occur after a strictly later maturity. Future timestamps,
duplicate opportunities, opaque artifact IDs, rewrites, synthetic records, replay,
backtests, and model-only records do not satisfy the threshold.

Before promotion evaluation, require all 11 exact negative controls and all 70 required
stress scenarios. L5 defines the outcome as complete-cost net utility as a fraction of
paper bankroll. An options-expression candidate is compared with no trade, a
risk-matched underlying, and a simple option or vertical; an abstention candidate is
compared with no trade, always express, and random abstention. Utility lower bounds and
the Brier-score upper bound use market-session clusters, not pooled trade counts.

Any drift, negative-control anomaly, limit breach, missing settlement, invalid
dynamic-state hash, missing required receipt, signer/key identity conflict, or absent
required external anchor quarantines the candidate. The canonical writer constrains
paths but is not an OS/process permission boundary. Signatures authenticate data
against pinned keys; they do not by themselves prove organizational independence or
external key custody.

`PROMOTION_AUTHORITY_TRUST.json`, `SEALED_EVALUATOR_TRUST.json`,
`FORWARD_EVIDENCE_TRUST.json`, and `DYNAMIC_ANCHOR_TRUST.json` all currently report
`not_configured`, and no operator-custodied deployment trust root has been supplied.
Therefore no record can qualify for L5 in the current environment. L5 is permanently
paper-only and cannot authorize a live order.
