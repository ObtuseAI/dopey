# DOPEY Broker-Readiness Preflight Checklist And Read-Only Boundary Simulator

## Objective

This bundle adds an offline broker-readiness preflight checklist and a fixture-only read-only boundary simulator. It proves the current boundary between DOPEY paper governance and any future broker-capability work.

## Not Broker Integration

This is not broker integration. It creates no Robinhood MCP connection, no broker connection, no credentials, no scheduler, no network market-data path, no live order review, no live order placement, no cancellation path, no real sizing, no buying-power read, and no account-balance read.

## Preflight Checklist

The checklist writes `artifacts/dopey/broker_readiness/broker_preflight_checks.jsonl` with 81 checks. It consumes existing active policy, lifecycle, account ledger, PaperBroker, no-day-trade, allocation, portfolio, stress ladder, incident, audit, export review, and validation proof layers.

Key confirmations:

- Long call and long put policy checks pass.
- Sell-to-open, naked option, uncovered writing, unsupported spread, and undefined-risk checks remain blocked.
- Normal same-day open/close remains blocked.
- 0DTE remains a special lifecycle, not a same-day churn loophole.
- Lifecycle, PaperBroker, account ledger, incident, audit, export, and validation artifacts remain paper-only/live-blocked.
- Full-suite timeout remains `inconclusive_timeout`, not pass.

## Read-Only Boundary Simulator

The simulator writes `artifacts/dopey/broker_readiness/read_only_boundary_simulations.jsonl` with 24 simulated request classes. Fixture-only read operations are marked read-only allowed, but write/execute, credential, scheduler, network, live execution, order placement, order cancellation, real account balance, buying power, and real sizing requests are blocked.

## Broker Capability Fixtures

The fixture library writes `artifacts/dopey/broker_readiness/broker_capability_fixtures.json` with simulated broker names only:

- `SIMULATED_ROBINHOOD_AGENTIC_OPTIONS`
- `SIMULATED_BROKER_GENERIC_OPTIONS`

No fixture contacts either broker.

## Manual Approval Gates

Future read-only capability detection requires explicit human approval. Live execution, credential setup, broker integration, scheduler creation, and deployment remain unapproved and blocked.

## Blocked Paths

The boundary block ledger contains 22 records for write/execute and safety-failure classes, including order placement, cancellation, credential access, `.env` access, scheduler creation, network market data, live execution, Robinhood path before approval, broker integration before approval, account balance, buying power, real sizing, missing audit proof, safety findings, credential findings, scheduler findings, and full-suite timeout misclassification.

## Incident Integration

Broker-readiness boundary violations map to terminal-block incidents with no auto-recovery. The mapped incident classes cover broker capability detector attempts before approval, Robinhood integration attempts, credential requests, `.env` access, scheduler creation, network market-data dependency, live order review, live placement, real account balance reads, buying-power reads, and real sizing logic.

## Audit, Report, Export, Review

The audit artifact loader recognizes broker-readiness preflight checks, read-only boundary simulations, broker capability fixtures, run result, boundary blocks, and proof ledgers. Reporting surfaces broker-readiness status, manual gates, write/execute blocks, credential/scheduler/network blocks, next gate, and safety state. Export selection and export review include the broker-readiness report, ledger, summary, proof, and boundary artifacts.

## Validation

Targeted broker-readiness runner status: `ok`.

- preflight checks: `81`
- read-only simulations: `24`
- capability fixtures: `12`
- boundary blocks: `22`
- manual gates: `13`
- proof records: `105`
- readiness_status: `read_only_boundary_simulated`
- not_broker_ready: `true`
- not_live_ready: `true`
- next_required_gate: `explicit_human_approval_for_future_read_only_capability_detector_bundle`
- full_suite_status: `inconclusive_timeout`
- collect_only_count: `1950`
- bounded_full_pytest_timeout_ms: `133856`
- bounded_full_pytest_windows_flush_oserror_seen: `true`
- full_suite_timeout_recorded_as_pass: `false`

Targeted shard results:

- broker readiness: `115 passed`
- lifecycle: `132 passed`
- incident response: `185 passed`
- portfolio stress ladder: `113 passed`
- portfolio replay: `110 passed`
- proof-weighted allocator: `100 passed`
- hybrid swing/0DTE V3: `107 passed`
- cross-underlying V2: `91 passed`
- adversarial corpus: `86 passed`
- threshold optimizer: `67 passed`
- outcome replay and risk model: `133 passed`
- account ledger / rotation / PaperBroker: `57 passed`
- active policy integration: `32 passed`

Smokes passed for offline audit, reporting, export verifier, export review, and validation stabilizer.

## Limitations

This is deterministic fixture evidence only. It does not prove broker capability, live readiness, profitability, predictive power, market accuracy, account state, buying power, or live execution safety.

## Safety State

DOPEY remains paper-only, broker-disconnected, credentialless, schedulerless, network-market-data-free, live-blocked, and not live-ready.

## Next Required Gate

Explicit human approval for a future read-only capability detector bundle.

## Manual Approval Packet Update - 2026-07-04

- Manual approval packet created: `DOPEY_READ_ONLY_BROKER_CAPABILITY_DETECTOR_MANUAL_APPROVAL_PACKET_V1`.
- Future read-only broker capability detector remains not approved and was not run.
- Exact acknowledgement required in a future bundle: `I APPROVE DOPEY READ-ONLY BROKER CAPABILITY DETECTOR ONLY. NO CREDENTIAL STORAGE. NO LIVE ORDERS. NO ORDER PLACEMENT. NO ORDER CANCELLATION. NO SCHEDULER. NO AUTONOMOUS LIVE TRADING. NO REAL SIZING. READ-ONLY DETECTION ONLY.`
- Next gate: `explicit_human_approval_for_read_only_broker_capability_detector_only`.

## Read-Only Detector Dry-Run Fixture Validator

- validator_exists: `true`
- validator_function: `validates future detector input/output shape without running a detector`
- detector_approved: `false`
- detector_run_attempted: `false`
- broker_connection_attempted: `false`
- credentials_accessed: `false`
- live_blocked: `true`

## Read-Only Detector Dry-Run Fixture Validator

- validator_exists: `true`
- validator_function: `validates future detector shape without running detector`
- detector_approved: `false`
- detector_run_attempted: `false`
- broker_connection_attempted: `false`
- credentials_accessed: `false`
- live_blocked: `true`
