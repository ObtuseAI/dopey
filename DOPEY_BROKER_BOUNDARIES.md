# DOPEY BROKER BOUNDARIES

## CURRENT STATE (2026-07-22): the owner-authorized Live Branch supersedes "no live execution" — for equities only

Everything below this section describes the original options-execution seal and the
legacy broker adapters. It remains true — those components are still hard-blocked —
but it is no longer the whole story. `DOPEY_CONSTITUTION.md` v2 (owner authorization
`owner-confirmation-2026-07-19-live-branch`) established a scoped live-equity branch:

- **The only live path is the `dopey_live/` package**, talking exclusively to the
  official Robinhood Agentic Trading MCP (`https://agent.robinhood.com/mcp/trading`)
  through an ephemeral, read-only-sandboxed Codex agent. Order fields are computed
  deterministically in Python before the agent runs; the agent is transport, and the
  full MCP tool-call transcript is re-validated field-by-field afterward. Every order
  is recorded in hash-chained ledgers with a mandatory paper twin staged first.
- **Equities only.** Options execution is owner-disabled
  (`options_execution_enabled: false`) and the legacy options-execution seal below is
  untouched.
- **Cash account discipline**: the agentic account is a cash account. Entries are
  sized against SETTLED funds only (`dopey_live/settlement.py`): unsettled T+1 sale
  proceeds are subtracted from buying power, and incomplete broker order history
  fails closed to zero spendable. Buying with settled cash only makes a
  system-caused good-faith violation structurally impossible regardless of when the
  owner or an exit later sells.
- **Owner actions are reconciled, not fought**: a position the owner sold directly in
  the brokerage app settles against broker sell-fill evidence as an append-only
  `live_position_owner_liquidation_observed` event; an UNEXPLAINED disappearance
  still hard-blocks the cycle.
- **Auth lives in the Codex MCP client, never in this repo** (`codex mcp login
  robinhood-trading`). An expired OAuth session is detected and surfaced as
  `blocked_robinhood_auth_required` with that exact remediation; no credential is
  ever stored or read by DOPEY code.
- **No autonomous schedule is installed.** The live branch runs only when the
  operator invokes `operator_tools/operator_live_branch.py` (orders additionally
  require `--execute`). Installing `DOPEY_LiveBranch` in Task Scheduler is a
  deliberate, currently-unexercised future step.
- **The entire `dopey_live/` package is hash-sealed** in `PROTECTED_MANIFEST.json`
  (source-root coverage). Any source change there requires regenerating the manifest
  via `verifier.protected_manifest.build_ascendancy_protected_manifest` and passing
  the environment freeze test — live-order code cannot change incidentally.

Research maturity and live authority remain separate: the truth layer still reports
no demonstrated edge (L0), and research promotion gates are unaffected by the
existence of this branch.

---

## No unofficial Robinhood private API execution

The unofficial Robinhood private API is **forbidden**. `allow_unofficial_robinhood_api` is `false`
by default and `RobinhoodMCPAdapter` raises `ValueError` if it is ever set `true` in the first
pass. No credential harvesting, no token exfiltration, no private endpoint calls.

## Robinhood MCP is discovery-only in the first pass

`RobinhoodMCPAccountAdapter` and `RobinhoodMCPAdapter` expose `discover_tools()` only.
`get_account_snapshot()`, `get_option_chain()`, and `place_order()` return a no-op/raise in the
first pass. `place_order()` raises `LiveTradingDisabledError` unless an explicit future live
mode is enabled AND options-exec capability is discovered at runtime.

## Broker-agnostic abstraction

All brokers implement `BrokerInterface` (`get_capabilities`, `get_account_snapshot`,
`get_option_chain`, `preview_order`, `place_order`, `cancel_order`). Dopey never talks to a
specific broker's private surface directly in the execution path; it talks to the interface and
lets `BrokerCapabilityDetector` decide what is supported.

## Capability detection

`BrokerCapabilityDetector` returns disabled/unknown for Robinhood options exec unless an explicit
future live mode has discovered capability. For paper brokers, options exec is supported (paper
exec is safe). No code path may *assume* options execution — it must be *discovered*.

## Paper broker first

`PaperBroker` is the only broker that actually simulates fills in the first pass. It logs to a
proof ledger, never connects to a funded account, and rejects any intent with `live_allowed=true`.

## Live blocked by default

The `LiveOrderGate` blocks every live order in the default config. A live order may pass only if
ALL of: config mode is `MICRO_LIVE`/`ADAPTIVE_LIVE`, `live_trading_enabled` is `true`, broker
capability supports the structure, the strategy has a sufficient proof bundle, the order is
defined-risk, the account budget policy approves, and the `ExecutionIntent` has
`live_allowed: true`.

## Adapter inventory (first pass)

| Adapter | Live? | Creds? | Notes |
|---|---|---|---|
| `PaperBroker` | no | no | simulated paper fills; logs to ledger |
| `RobinhoodMCPAdapter` | no | no | discovery-only; `place_order` raises |
| `AlpacaOptionsAdapter` | no | no | paper/sandbox stub; `place_order` raises for live |
| `TradierOptionsAdapter` | no | no | paper/sandbox stub; `place_order` raises for live |

## DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_V1
- Approval-intake validator exists as an offline fixture-only validator.
- Invalid or scope-expanding approvals terminal-block or require manual review.
- Exact approval can only make a future detector eligible for a later bundle.
- Approval intake does not run the detector, connect to a broker, create credentials, place orders, create a scheduler, or allow real sizing.

## DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_V1

- status: `handoff_gate_validated`
- future_bundle_eligible_count: `12`
- current_detector_run_allowed_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- separate_future_bundle_required: `true`
- explicit_reapproval_required: `true`
- pre_run_safety_scan_required: `true`
- post_run_evidence_required: `true`

## DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_V1

- status: `pre_run_safety_scanner_validated`
- future_bundle_preparation_allowed_count: `16`
- detector_run_allowed_now_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- command_templates_disabled: `true`
- separate_future_bundle_required: `true`
- explicit_reapproval_required: `true`
- pre_run_safety_scan_required: `true`
- post_run_evidence_required: `true`
- pre_run_scanner_does_not_run_detector: `true`
- future_bundle_preparation_is_not_broker_connection: `true`
- boundary_leak_terminal_blocks: `true`

## DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_V1

- status: `human_approved_read_only_detector_validated`
- detector_status_distribution: `{'not_run_approval_missing': 31, 'not_run_manual_review_required': 1, 'not_run_pre_run_blocked': 1, 'not_run_terminal_block': 19, 'read_only_detector_fixture_completed': 68}`
- post_run_evidence_written: `true`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_manual_review`
- completeness_score: `88`
- promotion_decision: `manual_review_required`
- terminal_block_count: `0`
- manual_review_count: `1`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_incomplete`
- completeness_score: `88`
- promotion_decision: `hold_review_only`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_incomplete`
- completeness_score: `88`
- promotion_decision: `hold_review_only`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`

## DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_V1

- status: `evidence_contract_complete`
- completeness_score: `100`
- promotion_decision: `eligible_for_simulated_quote_order_review_mirror`
- terminal_block_count: `0`
- manual_review_count: `0`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
- next_recommended_target: `broker-readiness v2 simulated quote/order-review mirror`
