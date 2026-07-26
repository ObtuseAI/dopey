# DOPEY Autonomy, Capability, and Trading-Readiness Review

Date: 2026-07-24
Repository: `C:\Users\CH\dopey`
Branch at review: `agent/dopey-vnext-operational-readiness`
Change state: uncommitted for operator review

## Executive verdict

DOPEY is materially more autonomous, auditable, and fail-closed after this
review, but it is not action-ready and cannot honestly be certified as the
best trading agent in the world. Its legitimate autonomy remains bounded to
paper research, shadow evaluation, evidence settlement, and operational
recovery. Live trading, broker authority, credentials, and evidence-threshold
relaxation remain blocked.

The current machine-checked verdict is `not_action_ready`. The main blockers
are insufficient and negative forward evidence, absent cohort/regime proof,
an inconclusive nightly suite, a breached reliability budget, and stress
evidence that must be regenerated against the exact current book and current
valuation inputs.

## Hardening delivered

### Autonomous improvement and recursive learning

- Upgraded the autonomous-improvement policy to v2.
- Added a content-hashed, fresh, fail-closed reliability guard at both policy creation
  and policy consumption.
- Neutralized interval acceleration from the currently active legacy v1 policy;
  the effective schedule is now `active_recovery_only_cadence_baseline`.
- Preserved bounded timeout/retry recovery while reliability is red.
- Excluded externally owned daily and nightly lanes from self-improvement
  claims and overrides.
- Sealed the mutation surface to interval, timeout, and retry fields.
- Added previous-policy hash verification, field-level transition evidence,
  automatic rollback evidence, immutable cycle history, an append-only
  transition ledger, and an activation commit marker.
- Made the active policy consumable only when its history, transition, prepared
  result, active pointer, and commit marker agree.
- Preserved `paper_only=true`, `live_blocked=true`, unchanged evidence
  thresholds, and explicit human authority for any expansion beyond research.

### Reliability and operational truth

- Upgraded the reliability SLO to v2 with a generation timestamp and
  reproducibility hash.
- Corrected the 95% SLO math: one miss in a 14-session window now breaches the
  SLO instead of being incorrectly permitted.
- Made missing, malformed, future-dated, or stale forward marking, supervisor,
  nightly, and disk evidence fail closed.
- Corrected the supervisor journal path and accepted the journal's real
  `run_utc` timestamp.
- Added read-only active-run liveness classification. The current supervisor
  artifact is truthfully classified as `stale_running_artifact`.
- Corrected the kaizen ledger to consume the real supervisor journal.

### Stress, entry, and action-readiness integrity

- Bound stress evidence to the exact order-independent forward book snapshot.
- Bound valuation evidence to the current options-chain snapshot, complete
  contract coverage, stress scenarios, limits, pricing-model version, and the
  currently resolved risk-free rate.
- Added full stress-artifact integrity verification and current-input
  comparison at the action-readiness gate.
- Upgraded the forward entry risk guard to v2. Missing current quotes,
  entry-state quote fallbacks, stale policies, stale books, and tampered stress
  artifacts now fail closed.
- Removed the import-time cached risk-free rate so long-running processes
  resolve the governed rate for each stress evaluation.
- The existing production stress artifact remains blocked until a supervised
  paper cycle regenerates it from the exact current book and inputs.

### Skills, tools, and capability truth

- Capability discovery was subsequently upgraded to v7; see the meta-capability
  foundry review for the current integrity and provenance semantics.
- Separated `missing`, `detected_unverified`, and `observed_usable` semantics.
- Stopped treating a PATH entry, skill directory, or plugin cache entry as
  proven runtime capability.
- Added safe cross-client Codex, Claude Code, and Cursor configuration
  inspection without reporting credential names or values.
- Verified that research execution is configured off across clients and that
  the Codex-only frontier setting is intentional.
- Current configuration is
  `configured_client_specific_frontier_policy_runtime_unverified`.
- Missing additions are Context7 MCP and an optional local Ollama/LM Studio
  provider. OpenAI Docs, GitHub, and browser capabilities are detected but
  remain runtime-verification items in the durable artifact.
- The connected DOPEY MCP process observed during this review still had
  pre-change modules in memory. It must be restarted before connector
  responses reflect v7 and the
  recovery-only effective schedule.

## Current evidence snapshot

- Readiness: `not_action_ready`
- Validated forward trades: 4 of 100 required
- Validated net forward P&L: -18.452 premium units
- Raw/censored/quarantined outcomes: 24 / 17 / 3
- Open forward positions: 17
- Validated entry cohorts: 3
- Cohorts beating matched baseline: 0
- Regime-robust cohorts: 0
- Statistical promotion: blocked, `insufficient_real_sample`
- Compounding: disabled; observed geometric mean -0.41017533 and observed
  sequence growth factor 0.12102964
- Nightly: 3,751 passed, 0 failed, but `inconclusive_timeout` and
  `suite_green=false`
- Reliability: `error_budget_breached`
  - Three missed chain-fetch sessions in the trailing 14-session window
  - Stale supervisor active-run heartbeat
- Stress artifact: integrity-valid but stale relative to the current book and
  valuation inputs; scenario readiness remains blocked

## Validation

- Focused integration and regression suite: 73 passed
- Ruff lint: passed
- Ruff format check: passed
- Git whitespace/error check: passed
- A later adversarial review identified additional P1 integrity defects in
  cognitive evaluation, memory envelopes, trade-memory publication, and
  recursive-evolution evidence binding. The current disposition and validation
  are recorded in `DOPEY_META_CAPABILITY_FOUNDRY_REVIEW_20260724.md`.
- No live orders, broker connections, credential requests, research-cycle
  launches, or autonomy-policy activation were performed
- No commit was created

## Highest-value next work

1. Restart the DOPEY MCP client process so it loads the hardened modules.
2. Reconcile the stale supervisor active-run evidence and complete a supervised
   paper-only supervisor run.
3. Regenerate adversarial stress evidence from the exact current book, current
   chain snapshot, policy, model, and rate.
4. Resolve nightly fitness-determinism timeouts and obtain a complete green
   nightly verdict.
5. Accrue at least 100 real, classified forward closes with positive,
   multi-cohort, multi-regime evidence. Counts alone must never trigger trades.
6. Wire the existing purged rolling-origin and embargo machinery into real
   history candidate selection with point-in-time universe and corporate-action
   inputs, an untouched benchmark, and selection-adjusted inference.
7. Add an observed-use capability ledger and typed adapter registry so stubs,
   cached skills, configured clients, and runtime-proven tools cannot be
   conflated.
8. Add independent evaluation and outcome recording before any stronger trust
   tier is claimed.

## Governance basis

This hardening follows the same core principles expressed by the NIST AI Risk
Management Framework, Federal Reserve SR 11-7 model-risk guidance, and FINRA's
algorithmic-trading guidance: continuous monitoring, independent validation,
pre-production testing, change review, and fail-safe recovery.

Sources:

- https://airc.nist.gov/airmf-resources/airmf/5-sec-core/
- https://www.federalreserve.gov/supervisionreg/srletters/sr1107a1.pdf
- https://www.finra.org/rules-guidance/key-topics/algorithmic-trading
