# Adversarial Audit

Environment: `dopey-options-paper-v1`  
Review posture: independent read-only attack before any favorite strategy  
Current result: local engineering controls are present; evidence level remains L0,
with no candidate, readiness, sealed result, or qualifying signed forward settlement

## Findings repaired in Ascendancy v1

- Generic buy-count-versus-sell-count logic was replaced with exact one-to-one
  bounded topology for the v1 structure allowlist.
- Dummy opportunities and candidate embeddings are content-addressed and recomputed;
  candidates cannot silently bind to another upstream opportunity.
- The protected initial universe is an exact 200-symbol watch set with 199
  options-mechanics symbols and context-only `VIX`. It cannot be backdated into
  prospective evidence. Non-synthetic decisions require independently sourced
  point-in-time membership captured before and effective at the decision, under the
  exact schema and a 200-symbol maximum.
- Public/date-only snapshots cannot construct a paper-executable price. Quote tier,
  time, receipt, venue, condition, size, completeness, spread, liquidity, adjustment,
  and contract terms are conjunctive.
- A paper price is bound to its quote-gate identity and decision time. A fill requires
  a later firm quote cross for every leg within a package-skew threshold. Every options
  qualifying forward decision receives exactly one immutable `filled` or `missed` execution observation;
  abstentions receive none, and settlement must bind the observation so missed
  opportunities cannot be removed.
- Canonical tickets carry their control snapshot, and acceptance reruns v1 risk,
  behavioral-firewall, and negative-control gates plus authority and exposure caps.
- Local tickets and fill observations cannot self-certify and always remain unverified
  and profitability-ineligible. Only the signed forward recorder can attest their exact
  point-in-time input and artifact hashes for prospective evaluation.
- Candidate gates require the exact 11 negative-control identities and all 70 required
  stress scenarios; missing, unexpected, incomplete, or failed entries block promotion.
- Non-finite risk, prices, sealed metrics, and negative-control effects fail closed.
- Trial ledgers use sequence/content hashes plus local head anchors, detecting entry
  edits and valid-prefix truncation while those anchors remain intact. Joint
  ledger-and-anchor replacement remains detectable only against the operator-custodied
  deployment trust root outside the repository, which is not configured.
- Sealed requests reserve an atomic one-shot budget and accept only predeclared
  aggregate metrics. Candidate code has no raw holdout interface. The mutable budget
  is semantically audited and included in the dynamic-state hash.
- Promotion accepts only the canonical repository root and derives experiment, proof,
  budget, and forward paths internally. Each L1-L5 stage proof requires an exact
  Ed25519 promotion-authority receipt binding the candidate, frozen specification,
  experiment, evaluator, verdict, source artifact, issue time, and paper/live state.
- Sealed proofs bind and verify the evaluator's signed aggregate verdict and signed
  issue time, then enforce request, evaluator-issue, proof-event, and evaluation
  chronology.
- Prospective decisions and settlements require signed receipts from an independent
  forward recorder, as does every options execution observation. Settlement outcomes
  additionally require a distinct outcome-source signer and key. The records embed
  content-addressed prediction, decision, filled-or-missed observation, settlement,
  and source artifacts with strict chronology.
- A repository Ed25519 anchor v2 binds the current dynamic-state and protected-manifest
  hashes plus a monotonic sequence and parent-anchor identity. That in-repository receipt
  proves local signature consistency but cannot grant certification by itself.
- Every L1-L5 transition under the current policy requires the canonical dynamic
  audit to verify an operator-custodied deployment trust root outside the repository.
  That root must pin the exact protected manifest, all four repository trust-config
  hashes and five pairwise-independent signer identities and public keys, the accepted
  anchor and parent, and a minimum sequence. The current environment reports no such
  root, so metadata, an old repository, or an old receipt cannot manufacture promotion.
- L5 defines the outcome as complete-cost net utility as a fraction of paper bankroll,
  requires candidate-mode-specific matched baselines, and computes lower and Brier
  bounds over market-session clusters rather than pooled trade counts. Missed fills
  remain in the matched sample at zero candidate utility.
- The release package is limited to `dopey`, `dopey.ascendancy*`,
  `dopey.constitution*`, `dopey.settlement*`, `dopey.truth*`,
  `sealed_evaluator_client*`, and `verifier*`. Legacy execution/governor/broker
  namespaces are excluded. Source-tree live-order gates and adapters permanently deny
  live operation and cannot be unlocked by configuration.

## Findings intentionally unresolved

- Current source chains are date-only Yahoo snapshots, not executable market data.
- Existing volatility surfaces are descriptive and not certified static-arbitrage
  free, event-aware, or stable under extrapolation.
- Existing Greeks and assignment logic are not lifecycle-grade for American options,
  discrete dividends, borrow, early exercise, pin risk, or higher-order exposure.
- No partial-fill, queue, routing, market-impact, outage, or realized-fill corpus is
  available.
- Promotion-authority, sealed-evaluator, forward-evidence, and dynamic-anchor trust
  configurations all default to and currently remain `not_configured`. No external
  services or independently held private keys have been supplied, and the mandatory
  operator-custodied deployment trust root outside the repository is not supplied.
- No sealed evaluator, clean-room candidate replication, prospective candidate, or
  qualifying signed forward settlement exists.
- The static protected-source manifest, dynamic-state audit, and repository anchor detect
  local mutation and structural inconsistency. They are not an ACL, OS/process boundary,
  rollback-resistant custody system, or proof that a configured signer is operationally
  independent. Anti-rollback certification exists only when the deployment-owned root is
  supplied from outside the repository and matches every pinned identity. Signature
  verification proves possession of a pinned private key, not process isolation.

Each unresolved item is a hard abstention or promotion block. No repair in this lab
inherits approval for a legacy strategy implementation.
