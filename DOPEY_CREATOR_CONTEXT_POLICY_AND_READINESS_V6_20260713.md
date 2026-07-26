# DOPEY Creator Context Policy and Readiness v6 - 2026-07-13

## Outcome

The creator-authorized 60-day context-duration requirement is removed from code, readiness ranking, generated artifacts, the operator dashboard, and current README language. Complete joint snapshots continue to be captured as provenance and research telemetry, but elapsed calendar or market days no longer gate context evidence.

DOPEY remains `paper_only=true`, `live_blocked=true`, and `not_action_ready` because independent evidence blockers remain. This policy change does not claim edge, profitability, or live readiness.

## Enforced Context Policy

- policy version: `dopey-context-evidence-v2`
- calendar-duration gate enabled: `false`
- policy authority: `creator_directive_2026-07-13`
- minimum snapshot days: `null`
- observed joint snapshot days: `2` telemetry only
- current context status: `blocked_insufficient_resolved_context_decisions`
- resolved decisions: `0 / 200`
- next context gate: three-era purged walk-forward ablation after the resolved-decision sample exists
- positive context promotion: disabled
- context sizing: disabled
- defensive veto: enabled

One-snapshot-day regression coverage proves that 200 resolved decisions advance to `blocked_pending_purged_walk_forward_validation`; elapsed days are not consulted.

## Hardening Delivered

- Removed `point_in_time_context_days` from the acceleration bottleneck list.
- Re-ranked resolved context decisions as the first context bottleneck.
- Added explicit duration-policy authority and snapshot-telemetry semantics to the gate and acceleration artifacts.
- Changed the ambiguous status from `blocked_insufficient_point_in_time_history` to `blocked_insufficient_resolved_context_decisions`.
- Made the standalone context gate authoritative for the operator dashboard so a failed news refresh cannot leave old `2/60` language visible.
- Made the equity-first engine refresh the independent context gate before external news validation, preserving current policy state even when news intake fails closed.
- Updated the dashboard and README to distinguish observed snapshot history from gating evidence.
- Bumped the local MCP server identity to `0.3.0` and updated its policy language.
- Preserved the 200 resolved-decision requirement, 100 closed-paper-trade sample, cohort edge, regime robustness, statistical truth, stress, freshness, and discipline checks.

## Validation

- Targeted context/control-plane suite excluding the known real-manifest check: `20 passed, 1 deselected`.
- Full targeted suite: `20 passed, 1 failed`.
- The preserved failure is `test_real_staged_cross_asset_and_news_inputs_validate_end_to_end`; the real news manifest reports `partial_explicit_source_failures`.
- Python compilation: passed for all changed Python modules and tests.
- Scoped `git diff --check`: passed; only line-ending notices were emitted.
- Repo-local MCP state: server `0.3.0`, no duration bottleneck, resolved decisions first, `paper_only=true`, `live_blocked=true`.
- Operator dashboard state: new context status visible, duration gate disabled, snapshot history role populated.
- In-app MCP transport: still closed; repo-local STDIO and direct state construction are validated instead.

## Protected Public Lake

- status: `public_lake_locked_clean`
- active public symbols: `160`
- active public rows: `1,292,545`
- active fixture symbols: `0`
- test-symbol residue: `0`
- restore required: `false`
- broker connection used: `false`
- live trading enabled: `false`

## Remaining Real Blockers

- resolved context decisions: `0 / 200`
- forward closed paper trades: `4 / 100`
- forward-paper wins: `0 / 4`
- closed path P&L: `-24.862` premium units
- discipline halt: active, five cooldown sessions remaining as of the current ledger
- cohort beats baseline at 95% CI: false
- cohort regime robustness: false
- statistical truth promotion: false
- compounding: blocked, allowed multiplier `0.0`, sample `4 / 100`
- news manifest: `partial_explicit_source_failures`

The acceleration scheduler currently sees news intake, cross-asset intake, and intraday watch as due. They were not force-run because paper-research execution remains separately confirmation-gated. Scheduled task state is `DOPEY_AccelerationCycle=Ready`, `DOPEY_DailyRitual=Ready`, and redundant `DOPEY_Intraday=Disabled`.

No broker was connected, no credentials were requested, no order path was added, no real order was placed, and no git commit was created.
